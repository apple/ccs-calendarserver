##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

"""
Inbound IMIP mail handling for Calendar Server
"""

from twext.enterprise.dal.record import fromTable
from twext.enterprise.jobqueue import WorkItem, RegeneratingWorkItem
from twext.internet.gaiendpoint import GAIEndpoint
from twext.python.log import Logger, LegacyLogger

from twisted.application import service
from twisted.internet import protocol, defer, ssl
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.mail import pop3client, imap4
from twisted.mail.smtp import messageid

from twistedcaldav.config import config
from twistedcaldav.ical import Property, Component

from txdav.caldav.datastore.scheduling.imip.scheduler import IMIPScheduler
from txdav.caldav.datastore.scheduling.imip.smtpsender import SMTPSender
from txdav.caldav.datastore.scheduling.itip import iTIPRequestStatus
from txdav.common.datastore.sql_tables import schema

import datetime
import email.utils


log = Logger()

#
# Monkey patch imap4.log so it doesn't emit useless logging,
# specifically, "Unhandled unsolicited response" nonsense.
#
class IMAPLogger(LegacyLogger):
    def msg(self, *message, **kwargs):
        if message and message[0].startswith("Unhandled unsolicited response:"):
            return

        super(IMAPLogger, self).msg(self, *message, **kwargs)

imap4.log = IMAPLogger()


""" SCHEMA:
create table IMIP_REPLY_WORK (
  WORK_ID                       integer primary key default nextval('WORKITEM_SEQ') not null,
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  ORGANIZER                     varchar(255) not null,
  ATTENDEE                      varchar(255) not null,
  ICALENDAR_TEXT                text         not null
);
create table IMIP_POLLING_WORK (
  WORK_ID                       integer primary key default nextval('WORKITEM_SEQ') not null,
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP)
);
"""

class IMIPReplyWork(WorkItem, fromTable(schema.IMIP_REPLY_WORK)):

    @inlineCallbacks
    def doWork(self):
        calendar = Component.fromString(self.icalendarText)
        yield injectMessage(self.transaction, self.organizer, self.attendee, calendar)



class IMIPPollingWork(RegeneratingWorkItem, fromTable(schema.IMIP_POLLING_WORK)):

    # FIXME: purge all old tokens here
    group = "imip_polling"

    def regenerateInterval(self):
        """
        Return the interval in seconds between regenerating instances.
        """
        mailRetriever = self.transaction._mailRetriever
        if mailRetriever is not None:
            return mailRetriever.settings["PollingSeconds"]

        # The lack of mailRetriever means IMIP polling is turned off.
        # Returning None will cause this work item to no longer be scheduled.
        return None


    @inlineCallbacks
    def doWork(self):

        mailRetriever = self.transaction._mailRetriever
        if mailRetriever is not None:
            yield mailRetriever.fetchMail()



class MailRetriever(service.Service):

    def __init__(self, store, directory, settings, reactor=None):
        self.store = store
        self.settings = settings
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor

        # If we're using our dedicated account on our local server, we're free
        # to delete all messages that arrive in the inbox so as to not let
        # cruft build up
        self.deleteAllMail = shouldDeleteAllMail(
            config.ServerHostName,
            settings.Server, settings.Username)
        self.mailReceiver = MailReceiver(store, directory)
        mailType = settings['Type']
        if mailType.lower().startswith('pop'):
            self.factory = POP3DownloadFactory
        else:
            self.factory = IMAP4DownloadFactory

        contextFactory = None
        if settings["UseSSL"]:
            contextFactory = ssl.ClientContextFactory()
        self.point = GAIEndpoint(
            self.reactor, settings.Server,
            settings.Port, contextFactory=contextFactory)


    def fetchMail(self):
        return self.point.connect(self.factory(
            self.settings, self.mailReceiver,
            self.deleteAllMail))


    @inlineCallbacks
    def scheduleNextPoll(self, seconds=None):
        if seconds is None:
            seconds = self.settings["PollingSeconds"]
        yield IMIPPollingWork.reschedule(self.store, seconds)



def shouldDeleteAllMail(serverHostName, inboundServer, username):
    """
    Given the hostname of the calendar server, the hostname of the pop/imap
    server, and the username we're using to access inbound mail, determine
    whether we should delete all messages in the inbox or whether to leave
    all unprocessed messages.

    @param serverHostName: the calendar server hostname (config.ServerHostName)
    @type serverHostName: C{str}
    @param inboundServer: the pop/imap server hostname
    @type inboundServer: C{str}
    @param username: the name of the account we're using to retrieve mail
    @type username: C{str}
    @return: True if we should delete all messages from the inbox, False otherwise
    @rtype: C{boolean}
    """
    return (
        inboundServer in (serverHostName, "localhost") and
        username == "com.apple.calendarserver"
    )



@inlineCallbacks
def scheduleNextMailPoll(store, seconds):
    txn = store.newTransaction(label="scheduleNextMailPoll")
    notBefore = datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
    log.debug("Scheduling next mail poll: %s" % (notBefore,))
    yield txn.enqueue(IMIPPollingWork, notBefore=notBefore)
    yield txn.commit()



class MailReceiver(object):

    NO_TOKEN = 0
    UNKNOWN_TOKEN = 1
    MALFORMED_TO_ADDRESS = 2
    NO_ORGANIZER_ADDRESS = 3
    REPLY_FORWARDED_TO_ORGANIZER = 4
    INJECTION_SUBMITTED = 5
    INCOMPLETE_DSN = 6
    UNKNOWN_FAILURE = 7

    def __init__(self, store, directory):
        self.store = store
        self.directory = directory


    def checkDSN(self, message):
        # returns (isdsn, action, icalendar attachment)

        report = deliveryStatus = calBody = None

        for part in message.walk():
            contentType = part.get_content_type()
            if contentType == "multipart/report":
                report = part
                continue
            elif contentType == "message/delivery-status":
                deliveryStatus = part
                continue
            elif contentType == "message/rfc822":
                # original = part
                continue
            elif contentType == "text/calendar":
                calBody = part.get_payload(decode=True)
                continue

        if report is not None and deliveryStatus is not None:
            # we have what appears to be a dsn

            lines = str(deliveryStatus).split("\n")
            for line in lines:
                lower = line.lower()
                if lower.startswith("action:"):
                    # found action:
                    action = lower.split(' ')[1]
                    break
            else:
                action = None

            return True, action, calBody

        else:
            # not a dsn
            return False, None, None


    def _extractToken(self, text):
        try:
            pre, _ignore_post = text.split('@')
            pre, token = pre.split('+')
            return token
        except ValueError:
            return None


    @inlineCallbacks
    def processDSN(self, calBody, msgId):
        calendar = Component.fromString(calBody)
        # Extract the token (from organizer property)
        organizer = calendar.getOrganizer()
        token = self._extractToken(organizer)
        if not token:
            log.error("Mail gateway can't find token in DSN %s" % (msgId,))
            return

        txn = self.store.newTransaction(label="MailReceiver.processDSN")
        result = (yield txn.imipLookupByToken(token))
        yield txn.commit()
        try:
            # Note the results are returned as utf-8 encoded strings
            organizer, attendee, _ignore_icaluid = result[0]
        except:
            # This isn't a token we recognize
            log.error(
                "Mail gateway found a token (%s) but didn't recognize it in message %s"
                % (token, msgId))
            returnValue(self.UNKNOWN_TOKEN)

        calendar.removeAllButOneAttendee(attendee)
        calendar.getOrganizerProperty().setValue(organizer)
        for comp in calendar.subcomponents():
            if comp.name() == "VEVENT":
                comp.addProperty(Property(
                    "REQUEST-STATUS",
                    ["5.1", "Service unavailable"]))
                break
        else:
            # no VEVENT in the calendar body.
            # TODO: what to do in this case?
            pass

        log.warn("Mail gateway processing DSN %s" % (msgId,))
        txn = self.store.newTransaction(label="MailReceiver.processDSN")
        yield txn.enqueue(
            IMIPReplyWork, organizer=organizer, attendee=attendee,
            icalendarText=str(calendar))
        yield txn.commit()
        returnValue(self.INJECTION_SUBMITTED)


    @inlineCallbacks
    def processReply(self, msg):
        # extract the token from the To header
        _ignore_name, addr = email.utils.parseaddr(msg['To'])
        if addr:
            # addr looks like: server_address+token@example.com
            token = self._extractToken(addr)
            if not token:
                log.error(
                    "Mail gateway didn't find a token in message "
                    "%s (%s)" % (msg['Message-ID'], msg['To']))
                returnValue(self.NO_TOKEN)
        else:
            log.error(
                "Mail gateway couldn't parse To: address (%s) in "
                "message %s" % (msg['To'], msg['Message-ID']))
            returnValue(self.MALFORMED_TO_ADDRESS)

        txn = self.store.newTransaction(label="MailReceiver.processReply")
        result = (yield txn.imipLookupByToken(token))
        yield txn.commit()
        try:
            # Note the results are returned as utf-8 encoded strings
            organizer, attendee, _ignore_icaluid = result[0]
        except:
            # This isn't a token we recognize
            log.error(
                "Mail gateway found a token (%s) but didn't "
                "recognize it in message %s"
                % (token, msg['Message-ID']))
            returnValue(self.UNKNOWN_TOKEN)

        for part in msg.walk():
            if part.get_content_type() == "text/calendar":
                calBody = part.get_payload(decode=True)
                break
        else:
            # No icalendar attachment
            log.warn(
                "Mail gateway didn't find an icalendar attachment "
                "in message %s" % (msg['Message-ID'],))

            toAddr = None
            fromAddr = attendee[7:]
            if organizer.startswith("mailto:"):
                toAddr = organizer[7:]
            elif organizer.startswith("urn:x-uid:"):
                uid = organizer[10:]
                record = yield self.directory.recordWithUID(uid)
                try:
                    if record and record.emailAddresses:
                        toAddr = list(record.emailAddresses)[0]
                except AttributeError:
                    pass

            if toAddr is None:
                log.error(
                    "Don't have an email address for the organizer; "
                    "ignoring reply.")
                returnValue(self.NO_ORGANIZER_ADDRESS)

            settings = config.Scheduling["iMIP"]["Sending"]
            smtpSender = SMTPSender(
                settings.Username, settings.Password,
                settings.UseSSL, settings.Server, settings.Port)

            del msg["From"]
            msg["From"] = fromAddr
            del msg["Reply-To"]
            msg["Reply-To"] = fromAddr
            del msg["To"]
            msg["To"] = toAddr
            log.warn("Mail gateway forwarding reply back to organizer")
            yield smtpSender.sendMessage(fromAddr, toAddr, messageid(), msg)
            returnValue(self.REPLY_FORWARDED_TO_ORGANIZER)

        # Process the imip attachment; inject to calendar server

        log.debug(calBody)
        calendar = Component.fromString(calBody)
        event = calendar.mainComponent()

        calendar.removeAllButOneAttendee(attendee)
        organizerProperty = calendar.getOrganizerProperty()
        if organizerProperty is None:
            # ORGANIZER is required per rfc2446 section 3.2.3
            log.warn(
                "Mail gateway didn't find an ORGANIZER in REPLY %s"
                % (msg['Message-ID'],))
            event.addProperty(Property("ORGANIZER", organizer))
        else:
            organizerProperty.setValue(organizer)

        if not calendar.getAttendees():
            # The attendee we're expecting isn't there, so add it back
            # with a SCHEDULE-STATUS of SERVICE_UNAVAILABLE.
            # The organizer will then see that the reply was not successful.
            attendeeProp = Property(
                "ATTENDEE", attendee,
                params={
                    "SCHEDULE-STATUS": iTIPRequestStatus.SERVICE_UNAVAILABLE,
                }
            )
            event.addProperty(attendeeProp)

            # TODO: We have talked about sending an email to the reply-to
            # at this point, to let them know that their reply was missing
            # the appropriate ATTENDEE.  This will require a new localizable
            # email template for the message.

        txn = self.store.newTransaction(label="MailReceiver.processReply")
        yield txn.enqueue(
            IMIPReplyWork, organizer=organizer, attendee=attendee,
            icalendarText=str(calendar))
        yield txn.commit()
        returnValue(self.INJECTION_SUBMITTED)


    # returns a deferred
    def inbound(self, message):
        """
        Given the text of an incoming message, parse and process it.
        The possible return values are:

        NO_TOKEN - there was no token in the To address
        UNKNOWN_TOKEN - there was an unknown token in the To address
        MALFORMED_TO_ADDRESS - we could not parse the To address at all
        NO_ORGANIZER_ADDRESS - no ics attachment and no email to forward to
        REPLY_FORWARDED_TO_ORGANIZER - no ics attachment, but reply forwarded
        INJECTION_SUBMITTED - looks ok, was submitted as a work item
        INCOMPLETE_DSN - not enough in the DSN to go on
        UNKNOWN_FAILURE - any error we aren't specifically catching

        @param message: The body of the email
        @type message: C{str}
        @return: Deferred firing with one of the above action codes
        """
        try:
            msg = email.message_from_string(message)

            isDSN, action, calBody = self.checkDSN(msg)
            if isDSN:
                if action == 'failed' and calBody:
                    # This is a DSN we can handle
                    return self.processDSN(calBody, msg['Message-ID'])
                else:
                    # It's a DSN without enough to go on
                    log.error(
                        "Mail gateway can't process DSN %s"
                        % (msg['Message-ID'],))
                    return succeed(self.INCOMPLETE_DSN)

            log.info(
                "Mail gateway received message %s from %s to %s" %
                (msg['Message-ID'], msg['From'], msg['To']))

            return self.processReply(msg)

        except Exception, e:
            # Don't let a failure of any kind stop us
            log.error("Failed to process message: %s" % (e,))
        return succeed(self.UNKNOWN_FAILURE)



@inlineCallbacks
def injectMessage(txn, organizer, attendee, calendar):

    try:
        scheduler = IMIPScheduler(txn, None)
        results = (yield scheduler.doSchedulingDirectly("iMIP", attendee, [organizer, ], calendar,))
        log.info("Successfully injected iMIP response from %s to %s" % (attendee, organizer))
    except Exception, e:
        log.error("Failed to inject iMIP response (%s)" % (e,))
        raise

    returnValue(results)



#
# POP3
#

class POP3DownloadProtocol(pop3client.POP3Client):
    log = Logger()

    allowInsecureLogin = False

    def serverGreeting(self, greeting):
        self.log.debug("POP servergreeting")
        pop3client.POP3Client.serverGreeting(self, greeting)
        login = self.login(
            self.factory.settings["Username"],
            self.factory.settings["Password"])
        login.addCallback(self.cbLoggedIn)
        login.addErrback(self.cbLoginFailed)


    def cbLoginFailed(self, reason):
        self.log.error(
            "POP3 login failed for %s" %
            (self.factory.settings["Username"],))
        return self.quit()


    def cbLoggedIn(self, result):
        self.log.debug("POP loggedin")
        return self.listSize().addCallback(self.cbGotMessageSizes)


    def cbGotMessageSizes(self, sizes):
        self.log.debug("POP gotmessagesizes")
        downloads = []
        for i in range(len(sizes)):
            downloads.append(self.retrieve(i).addCallback(self.cbDownloaded, i))
        return defer.DeferredList(downloads).addCallback(self.cbFinished)


    @inlineCallbacks
    def cbDownloaded(self, lines, id):
        self.log.debug("POP downloaded message %d" % (id,))
        actionTaken = (yield self.factory.handleMessage("\r\n".join(lines)))

        if self.factory.deleteAllMail:
            # Delete all mail we see
            self.log.debug("POP deleting message %d" % (id,))
            self.delete(id)
        else:
            # Delete only mail we've processed
            if actionTaken == MailReceiver.INJECTION_SUBMITTED:
                self.log.debug("POP deleting message %d" % (id,))
                self.delete(id)


    def cbFinished(self, results):
        self.log.debug("POP finished")
        return self.quit()



class POP3DownloadFactory(protocol.ClientFactory):
    log = Logger()

    protocol = POP3DownloadProtocol

    def __init__(self, settings, mailReceiver, deleteAllMail):
        self.settings = settings
        self.mailReceiver = mailReceiver
        self.deleteAllMail = deleteAllMail
        self.noisy = False


    def clientConnectionLost(self, connector, reason):
        self.connector = connector
        self.log.debug("POP factory connection lost")


    def clientConnectionFailed(self, connector, reason):
        self.connector = connector
        self.log.info("POP factory connection failed")


    def handleMessage(self, message):
        self.log.debug("POP factory handle message")
        # self.log.debug(message)
        return self.mailReceiver.inbound(message)



#
# IMAP4
#


class IMAP4DownloadProtocol(imap4.IMAP4Client):
    log = Logger()

    def serverGreeting(self, capabilities):
        self.log.debug("IMAP servergreeting")
        return self.authenticate(
            self.factory.settings["Password"]
        ).addCallback(
            self.cbLoggedIn
        ).addErrback(self.ebAuthenticateFailed)


    def ebLogError(self, error):
        self.log.error("IMAP Error: {err}", err=error)


    def ebAuthenticateFailed(self, reason):
        self.log.debug(
            "IMAP authenticate failed for {name}, trying login",
            name=self.factory.settings["Username"])
        return self.login(
            self.factory.settings["Username"],
            self.factory.settings["Password"]
        ).addCallback(
            self.cbLoggedIn
        ).addErrback(self.ebLoginFailed)


    def ebLoginFailed(self, reason):
        self.log.error("IMAP login failed for {name}", name=self.factory.settings["Username"])
        self.transport.loseConnection()


    def cbLoggedIn(self, result):
        self.log.debug("IMAP logged in")
        self.select("Inbox").addCallback(self.cbInboxSelected)


    def cbInboxSelected(self, result):
        self.log.debug("IMAP Inbox selected")
        self.search(imap4.Query(unseen=True)).addCallback(self.cbGotSearch)


    def cbGotSearch(self, results):
        if results:
            ms = imap4.MessageSet()
            for n in results:
                ms.add(n)
            self.fetchUID(ms).addCallback(self.cbGotUIDs)
        else:
            self.cbClosed(None)


    def cbGotUIDs(self, results):
        self.messageUIDs = [result['UID'] for result in results.values()]
        self.messageCount = len(self.messageUIDs)
        self.log.debug("IMAP Inbox has {count} unseen messages", count=self.messageCount)
        if self.messageCount:
            self.fetchNextMessage()
        else:
            # No messages; close it out
            self.close().addCallback(self.cbClosed)


    def fetchNextMessage(self):
        # self.log.debug("IMAP in fetchnextmessage")
        if self.messageUIDs:
            nextUID = self.messageUIDs.pop(0)
            messageListToFetch = imap4.MessageSet(nextUID)
            self.log.debug(
                "Downloading message %d of %d (%s)" %
                (self.messageCount - len(self.messageUIDs), self.messageCount, nextUID))
            self.fetchMessage(messageListToFetch, True).addCallback(
                self.cbGotMessage, messageListToFetch).addErrback(
                    self.ebLogError)
        else:
            self.log.debug("Seeing if anything new has arrived")
            # Go back and see if any more messages have come in
            self.expunge().addCallback(self.cbInboxSelected)


    @inlineCallbacks
    def cbGotMessage(self, results, messageList):
        self.log.debug("IMAP in cbGotMessage")
        try:
            messageData = results.values()[0]['RFC822']
        except IndexError:
            # results will be empty unless the "twistedmail-imap-flags-anywhere"
            # patch from http://twistedmatrix.com/trac/ticket/1105 is applied
            self.log.error("Skipping empty results -- apply twisted patch!")
            self.fetchNextMessage()
            return

        actionTaken = (yield self.factory.handleMessage(messageData))
        if self.factory.deleteAllMail:
            # Delete all mail we see
            yield self.cbFlagDeleted(messageList)
        else:
            # Delete only mail we've processed; the rest are left flagged Seen
            if actionTaken == MailReceiver.INJECTION_SUBMITTED:
                yield self.cbFlagDeleted(messageList)
            else:
                self.fetchNextMessage()


    def cbFlagDeleted(self, messageList):
        self.addFlags(
            messageList, ("\\Deleted",), uid=True
        ).addCallback(self.cbMessageDeleted, messageList)


    def cbMessageDeleted(self, results, messageList):
        self.log.debug("Deleted message")
        self.fetchNextMessage()


    def cbClosed(self, results):
        self.log.debug("Mailbox closed")
        self.logout().addCallback(
            lambda _: self.transport.loseConnection())


    def rawDataReceived(self, data):
        # self.log.debug("RAW RECEIVED: {data}", data=data)
        imap4.IMAP4Client.rawDataReceived(self, data)


    def lineReceived(self, line):
        # self.log.debug("RECEIVED: {line}", line=line)
        imap4.IMAP4Client.lineReceived(self, line)


    def sendLine(self, line):
        # self.log.debug("SENDING: {line}", line=line)
        imap4.IMAP4Client.sendLine(self, line)



class IMAP4DownloadFactory(protocol.ClientFactory):
    log = Logger()

    protocol = IMAP4DownloadProtocol

    def __init__(self, settings, mailReceiver, deleteAllMail):
        self.log.debug("Setting up IMAPFactory")

        self.settings = settings
        self.mailReceiver = mailReceiver
        self.deleteAllMail = deleteAllMail
        self.noisy = False


    def buildProtocol(self, addr):
        p = protocol.ClientFactory.buildProtocol(self, addr)
        username = self.settings["Username"]
        p.registerAuthenticator(imap4.CramMD5ClientAuthenticator(username))
        p.registerAuthenticator(imap4.LOGINAuthenticator(username))
        p.registerAuthenticator(imap4.PLAINAuthenticator(username))
        return p


    def handleMessage(self, message):
        self.log.debug("IMAP factory handle message")
        # self.log.debug(message)
        return self.mailReceiver.inbound(message)


    def clientConnectionLost(self, connector, reason):
        self.connector = connector
        self.log.debug("IMAP factory connection lost")


    def clientConnectionFailed(self, connector, reason):
        self.connector = connector
        self.log.warn("IMAP factory connection failed")
