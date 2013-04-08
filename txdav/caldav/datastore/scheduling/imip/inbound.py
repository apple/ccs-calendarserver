##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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
import datetime
from calendarserver.tap.util import FakeRequest
import email.utils
from twext.enterprise.dal.record import fromTable
from twext.enterprise.queue import WorkItem
from twext.python.log import Logger, LoggingMixIn
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
from twext.internet.gaiendpoint import GAIEndpoint


log = Logger()

#
# Monkey patch imap4.log so it doesn't emit useless logging,
# specifically, "Unhandled unsolicited response" nonsense.
#
class IMAPLogger(Logger):
    def emit(self, level, message, *args, **kwargs):
        if message.startswith("Unhandled unsolicited response:"):
            return

        Logger.emit(self, level, message, *args, **kwargs)

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
        rootResource = self.transaction._rootResource
        calendar = Component.fromString(self.icalendarText)
        yield injectMessage(self.transaction, rootResource, self.organizer, self.attendee,
            calendar)



class IMIPPollingWork(WorkItem, fromTable(schema.IMIP_POLLING_WORK)):

    # FIXME: delete all other polling work items
    # FIXME: purge all old tokens here

    @inlineCallbacks
    def doWork(self):
        mailRetriever = self.transaction._mailRetriever
        if mailRetriever is not None:
            try:
                yield mailRetriever.fetchMail()
            except Exception, e:
                log.error("Failed to fetch mail (%s)" % (e,))
            finally:
                yield mailRetriever.scheduleNextPoll()



class MailRetriever(service.Service):

    def __init__(self, store, directory, settings, reactor=None):
        self.store = store
        self.settings = settings
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor

        self.mailReceiver = MailReceiver(store, directory)
        mailType = settings['Type']
        if mailType.lower().startswith('pop'):
            self.factory = POP3DownloadFactory
        else:
            self.factory = IMAP4DownloadFactory

        contextFactory = None
        if settings["UseSSL"]:
            contextFactory = ssl.ClientContextFactory()
        self.point = GAIEndpoint(self.reactor, settings.Server,
            settings.Port, contextFactory=contextFactory)


    def startService(self):
        return self.scheduleNextPoll(seconds=0)


    def fetchMail(self):
        return self.point.connect(self.factory(self.settings, self.mailReceiver))


    @inlineCallbacks
    def scheduleNextPoll(self, seconds=None):
        if seconds is None:
            seconds = self.settings["PollingSeconds"]
        txn = self.store.newTransaction()
        notBefore = datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
        yield txn.enqueue(IMIPPollingWork, notBefore=notBefore)
        yield txn.commit()



class MailReceiver(object):

    NO_TOKEN = 0
    UNKNOWN_TOKEN = 1
    MALFORMED_TO_ADDRESS = 2
    NO_ORGANIZER_ADDRESS = 3
    REPLY_FORWARDED_TO_ORGANIZER = 4
    INJECTION_SUBMITTED = 5

    # What about purge( ) and lowercase( )
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
                #original = part
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

        txn = self.store.newTransaction()
        result = (yield txn.imipLookupByToken(token))
        yield txn.commit()
        try:
            # Note the results are returned as utf-8 encoded strings
            organizer, attendee, _ignore_icaluid = result[0]
        except:
            # This isn't a token we recognize
            log.error("Mail gateway found a token (%s) but didn't "
                           "recognize it in message %s"
                           % (token, msgId))
            returnValue(self.UNKNOWN_TOKEN)

        calendar.removeAllButOneAttendee(attendee)
        calendar.getOrganizerProperty().setValue(organizer)
        for comp in calendar.subcomponents():
            if comp.name() == "VEVENT":
                comp.addProperty(Property("REQUEST-STATUS",
                    ["5.1", "Service unavailable"]))
                break
        else:
            # no VEVENT in the calendar body.
            # TODO: what to do in this case?
            pass

        log.warn("Mail gateway processing DSN %s" % (msgId,))
        txn = self.store.newTransaction()
        yield txn.enqueue(IMIPReplyWork, organizer=organizer, attendee=attendee,
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
                log.error("Mail gateway didn't find a token in message "
                               "%s (%s)" % (msg['Message-ID'], msg['To']))
                returnValue(self.NO_TOKEN)
        else:
            log.error("Mail gateway couldn't parse To: address (%s) in "
                           "message %s" % (msg['To'], msg['Message-ID']))
            returnValue(self.MALFORMED_TO_ADDRESS)

        txn = self.store.newTransaction()
        result = (yield txn.imipLookupByToken(token))
        yield txn.commit()
        try:
            # Note the results are returned as utf-8 encoded strings
            organizer, attendee, _ignore_icaluid = result[0]
        except:
            # This isn't a token we recognize
            log.error("Mail gateway found a token (%s) but didn't "
                           "recognize it in message %s"
                           % (token, msg['Message-ID']))
            returnValue(self.UNKNOWN_TOKEN)

        for part in msg.walk():
            if part.get_content_type() == "text/calendar":
                calBody = part.get_payload(decode=True)
                break
        else:
            # No icalendar attachment
            log.warn("Mail gateway didn't find an icalendar attachment "
                          "in message %s" % (msg['Message-ID'],))

            toAddr = None
            fromAddr = attendee[7:]
            if organizer.startswith("mailto:"):
                toAddr = organizer[7:]
            elif organizer.startswith("urn:uuid:"):
                guid = organizer[9:]
                record = self.directory.recordWithGUID(guid)
                if record and record.emailAddresses:
                    toAddr = list(record.emailAddresses)[0]

            if toAddr is None:
                log.error("Don't have an email address for the organizer; "
                               "ignoring reply.")
                returnValue(self.NO_ORGANIZER_ADDRESS)

            settings = config.Scheduling["iMIP"]["Sending"]
            smtpSender = SMTPSender(settings.Username, settings.Password,
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
            log.warn("Mail gateway didn't find an ORGANIZER in REPLY %s"
                          % (msg['Message-ID'],))
            event.addProperty(Property("ORGANIZER", organizer))
        else:
            organizerProperty.setValue(organizer)

        if not calendar.getAttendees():
            # The attendee we're expecting isn't there, so add it back
            # with a SCHEDULE-STATUS of SERVICE_UNAVAILABLE.
            # The organizer will then see that the reply was not successful.
            attendeeProp = Property("ATTENDEE", attendee,
                params={
                    "SCHEDULE-STATUS": iTIPRequestStatus.SERVICE_UNAVAILABLE,
                }
            )
            event.addProperty(attendeeProp)

            # TODO: We have talked about sending an email to the reply-to
            # at this point, to let them know that their reply was missing
            # the appropriate ATTENDEE.  This will require a new localizable
            # email template for the message.

        txn = self.store.newTransaction()
        yield txn.enqueue(IMIPReplyWork, organizer=organizer, attendee=attendee,
            icalendarText=str(calendar))
        yield txn.commit()
        returnValue(self.INJECTION_SUBMITTED)


    # returns a deferred
    def inbound(self, message):

        try:
            msg = email.message_from_string(message)

            isDSN, action, calBody = self.checkDSN(msg)
            if isDSN:
                if action == 'failed' and calBody:
                    # This is a DSN we can handle
                    return self.processDSN(calBody, msg['Message-ID'])
                else:
                    # It's a DSN without enough to go on
                    log.error("Mail gateway can't process DSN %s"
                                   % (msg['Message-ID'],))
                    return succeed(None)

            log.info("Mail gateway received message %s from %s to %s" %
                (msg['Message-ID'], msg['From'], msg['To']))

            return self.processReply(msg)

        except Exception, e:
            # Don't let a failure of any kind stop us
            log.error("Failed to process message: %s" % (e,))
        return succeed(None)



@inlineCallbacks
def injectMessage(txn, root, organizer, attendee, calendar):

    request = FakeRequest(root, None, "/", transaction=txn)
    resource = root.getChild("principals")
    scheduler = IMIPScheduler(request, resource)
    scheduler.originator = attendee
    scheduler.recipients = [organizer, ]
    scheduler.calendar = calendar

    try:
        results = (yield scheduler.doScheduling())
        log.info("Successfully injected iMIP response from %s to %s" %
            (attendee, organizer))
    except Exception, e:
        log.error("Failed to inject iMIP response (%s)" % (e,))
        raise

    returnValue(results)



#
# POP3
#

class POP3DownloadProtocol(pop3client.POP3Client, LoggingMixIn):
    allowInsecureLogin = False

    def serverGreeting(self, greeting):
        self.log_debug("POP servergreeting")
        pop3client.POP3Client.serverGreeting(self, greeting)
        login = self.login(self.factory.settings["Username"],
            self.factory.settings["Password"])
        login.addCallback(self.cbLoggedIn)
        login.addErrback(self.cbLoginFailed)


    def cbLoginFailed(self, reason):
        self.log_error("POP3 login failed for %s" %
            (self.factory.settings["Username"],))
        return self.quit()


    def cbLoggedIn(self, result):
        self.log_debug("POP loggedin")
        return self.listSize().addCallback(self.cbGotMessageSizes)


    def cbGotMessageSizes(self, sizes):
        self.log_debug("POP gotmessagesizes")
        downloads = []
        for i in range(len(sizes)):
            downloads.append(self.retrieve(i).addCallback(self.cbDownloaded, i))
        return defer.DeferredList(downloads).addCallback(self.cbFinished)


    def cbDownloaded(self, lines, id):
        self.log_debug("POP downloaded message %d" % (id,))
        self.factory.handleMessage("\r\n".join(lines))
        self.log_debug("POP deleting message %d" % (id,))
        self.delete(id)


    def cbFinished(self, results):
        self.log_debug("POP finished")
        return self.quit()



class POP3DownloadFactory(protocol.ClientFactory, LoggingMixIn):
    protocol = POP3DownloadProtocol

    def __init__(self, settings, mailReceiver):
        self.mailReceiver = mailReceiver
        self.noisy = False


    def clientConnectionLost(self, connector, reason):
        self.connector = connector
        self.log_debug("POP factory connection lost")


    def clientConnectionFailed(self, connector, reason):
        self.connector = connector
        self.log_info("POP factory connection failed")


    def handleMessage(self, message):
        self.log_debug("POP factory handle message")
        self.log_debug(message)
        return self.mailReceiver.inbound(message)



#
# IMAP4
#


class IMAP4DownloadProtocol(imap4.IMAP4Client, LoggingMixIn):

    def serverGreeting(self, capabilities):
        self.log_debug("IMAP servergreeting")
        return self.authenticate(self.factory.settings["Password"]
            ).addCallback(self.cbLoggedIn
            ).addErrback(self.ebAuthenticateFailed)


    def ebLogError(self, error):
        self.log_error("IMAP Error: %s" % (error,))


    def ebAuthenticateFailed(self, reason):
        self.log_debug("IMAP authenticate failed for %s, trying login" %
            (self.factory.settings["Username"],))
        return self.login(self.factory.settings["Username"],
            self.factory.settings["Password"]
            ).addCallback(self.cbLoggedIn
            ).addErrback(self.ebLoginFailed)


    def ebLoginFailed(self, reason):
        self.log_error("IMAP login failed for %s" %
            (self.factory.settings["Username"],))
        self.transport.loseConnection()


    def cbLoggedIn(self, result):
        self.log_debug("IMAP logged in [%s]" % (self.state,))
        self.select("Inbox").addCallback(self.cbInboxSelected)


    def cbInboxSelected(self, result):
        self.log_debug("IMAP Inbox selected [%s]" % (self.state,))
        allMessages = imap4.MessageSet(1, None)
        self.fetchUID(allMessages, True).addCallback(self.cbGotUIDs)


    def cbGotUIDs(self, results):
        self.log_debug("IMAP got uids [%s]" % (self.state,))
        self.messageUIDs = [result['UID'] for result in results.values()]
        self.messageCount = len(self.messageUIDs)
        self.log_debug("IMAP Inbox has %d messages" % (self.messageCount,))
        if self.messageCount:
            self.fetchNextMessage()
        else:
            # No messages; close it out
            self.close().addCallback(self.cbClosed)


    def fetchNextMessage(self):
        self.log_debug("IMAP in fetchnextmessage [%s]" % (self.state,))
        if self.messageUIDs:
            nextUID = self.messageUIDs.pop(0)
            messageListToFetch = imap4.MessageSet(nextUID)
            self.log_debug("Downloading message %d of %d (%s)" %
                (self.messageCount - len(self.messageUIDs), self.messageCount,
                nextUID))
            self.fetchMessage(messageListToFetch, True).addCallback(
                self.cbGotMessage, messageListToFetch).addErrback(
                    self.ebLogError)
        else:
            self.log_debug("Seeing if anything new has arrived")
            # Go back and see if any more messages have come in
            self.expunge().addCallback(self.cbInboxSelected)


    def cbGotMessage(self, results, messageList):
        self.log_debug("IMAP in cbGotMessage [%s]" % (self.state,))
        try:
            messageData = results.values()[0]['RFC822']
        except IndexError:
            # results will be empty unless the "twistedmail-imap-flags-anywhere"
            # patch from http://twistedmatrix.com/trac/ticket/1105 is applied
            self.log_error("Skipping empty results -- apply twisted patch!")
            self.fetchNextMessage()
            return

        d = self.factory.handleMessage(messageData)
        if isinstance(d, defer.Deferred):
            d.addCallback(self.cbFlagDeleted, messageList)
        else:
            # No deferred returned, so no need for addCallback( )
            self.cbFlagDeleted(None, messageList)


    def cbFlagDeleted(self, results, messageList):
        self.addFlags(messageList, ("\\Deleted",),
            uid=True).addCallback(self.cbMessageDeleted, messageList)


    def cbMessageDeleted(self, results, messageList):
        self.log_debug("IMAP in cbMessageDeleted [%s]" % (self.state,))
        self.log_debug("Deleted message")
        self.fetchNextMessage()


    def cbClosed(self, results):
        self.log_debug("IMAP in cbClosed [%s]" % (self.state,))
        self.log_debug("Mailbox closed")
        self.logout().addCallback(
            lambda _: self.transport.loseConnection())


    def rawDataReceived(self, data):
        self.log_debug("RAW RECEIVED: %s" % (data,))
        imap4.IMAP4Client.rawDataReceived(self, data)


    def lineReceived(self, line):
        self.log_debug("RECEIVED: %s" % (line,))
        imap4.IMAP4Client.lineReceived(self, line)


    def sendLine(self, line):
        self.log_debug("SENDING: %s" % (line,))
        imap4.IMAP4Client.sendLine(self, line)



class IMAP4DownloadFactory(protocol.ClientFactory, LoggingMixIn):
    protocol = IMAP4DownloadProtocol

    def __init__(self, settings, mailReceiver):
        self.log_debug("Setting up IMAPFactory")

        self.settings = settings
        self.mailReceiver = mailReceiver
        self.noisy = False


    def buildProtocol(self, addr):
        p = protocol.ClientFactory.buildProtocol(self, addr)
        username = self.settings["Username"]
        p.registerAuthenticator(imap4.CramMD5ClientAuthenticator(username))
        p.registerAuthenticator(imap4.LOGINAuthenticator(username))
        p.registerAuthenticator(imap4.PLAINAuthenticator(username))
        return p


    def handleMessage(self, message):
        self.log_debug("IMAP factory handle message")
        self.log_debug(message)
        return self.mailReceiver.inbound(message)


    def clientConnectionLost(self, connector, reason):
        self.connector = connector
        self.log_debug("IMAP factory connection lost")


    def clientConnectionFailed(self, connector, reason):
        self.connector = connector
        self.log_warn("IMAP factory connection failed")
