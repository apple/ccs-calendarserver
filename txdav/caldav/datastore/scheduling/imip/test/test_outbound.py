##
# Copyright (c) 2008-2014 Apple Inc. All rights reserved.
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
from __future__ import print_function

from cStringIO import StringIO

from pycalendar.datetime import PyCalendarDateTime

from twisted.internet.defer import inlineCallbacks, succeed
from twisted.trial import unittest
from twisted.web.template import Element, renderer, flattenString

from twistedcaldav.config import config
from twistedcaldav.ical import Component

from txdav.caldav.datastore.scheduling.imip.outbound import IMIPInvitationWork
from txdav.caldav.datastore.scheduling.imip.outbound import MailSender
from txdav.caldav.datastore.scheduling.imip.outbound import StringFormatTemplateLoader
from txdav.common.datastore.test.util import buildStore

import email
import os


initialInviteText = u"""BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
BEGIN:VEVENT
UID:CFDD5E46-4F74-478A-9311-B3FF905449C3
DTSTART:20200325T154500Z
DTEND:20200325T164500Z
ATTENDEE;CN=Th\xe9 Attendee;CUTYPE=INDIVIDUAL;PARTSTAT=NEEDS-ACTION;RSVP=TRU
 E:mailto:attendee@example.com
ATTENDEE;CN=Th\xe9 Organizer;CUTYPE=INDIVIDUAL;EMAIL=organizer@example.com;P
 ARTSTAT=ACCEPTED:urn:uuid:C3B38B00-4166-11DD-B22C-A07C87E02F6A
ATTENDEE;CN=An Attendee without CUTYPE;EMAIL=nocutype@example.com;PARTSTAT=A
 CCEPTED:urn:uuid:4DB528DC-3E60-44FA-9546-2A00FCDCFFAB
ATTENDEE;EMAIL=nocn@example.com;PARTSTAT=ACCEPTED:urn:uuid:A592CF8B-4FC8-4E4
 F-B543-B2F29A7EEB0B
ORGANIZER;CN=Th\xe9 Organizer;EMAIL=organizer@example.com:urn:uuid:C3B38B00-
 4166-11DD-B22C-A07C87E02F6A
SUMMARY:t\xe9sting outbound( )
DESCRIPTION:awesome description with "<" and "&"
END:VEVENT
END:VCALENDAR
"""

ORGANIZER = "urn:uuid:C3B38B00-4166-11DD-B22C-A07C87E02F6A"
ATTENDEE = "mailto:attendee@example.com"
ICALUID = "CFDD5E46-4F74-478A-9311-B3FF905449C3"

class DummySMTPSender(object):

    def __init__(self):
        self.reset()
        self.shouldSucceed = True


    def reset(self):
        self.sendMessageCalled = False
        self.fromAddr = None
        self.toAddr = None
        self.msgId = None
        self.message = None


    def sendMessage(self, fromAddr, toAddr, msgId, message):
        self.sendMessageCalled = True
        self.fromAddr = fromAddr
        self.toAddr = toAddr
        self.msgId = msgId
        self.message = message
        return succeed(self.shouldSucceed)



class OutboundTests(unittest.TestCase):

    @inlineCallbacks
    def setUp(self):
        self.store = yield buildStore(self, None)
        self.directory = self.store.directoryService()
        self.sender = MailSender("server@example.com", 7, DummySMTPSender(),
            language="en")

        def _getSender(ignored):
            return self.sender
        self.patch(IMIPInvitationWork, "getMailSender", _getSender)

        self.wp = None
        self.store.queuer.callWithNewProposals(self._proposalCallback)


    def _proposalCallback(self, wp):
        self.wp = wp


    @inlineCallbacks
    def test_work(self):
        txn = self.store.newTransaction()
        wp = (yield txn.enqueue(IMIPInvitationWork,
            fromAddr=ORGANIZER,
            toAddr=ATTENDEE,
            icalendarText=initialInviteText.replace("\n", "\r\n"),
        ))
        self.assertEquals(wp, self.wp)
        yield txn.commit()
        yield wp.whenExecuted()

        txn = self.store.newTransaction()
        token = (yield txn.imipGetToken(
            ORGANIZER,
            ATTENDEE,
            ICALUID
        ))
        self.assertTrue(token)
        organizer, attendee, icaluid = (yield txn.imipLookupByToken(token))[0]
        yield txn.commit()
        self.assertEquals(organizer, ORGANIZER)
        self.assertEquals(attendee, ATTENDEE)
        self.assertEquals(icaluid, ICALUID)


    @inlineCallbacks
    def test_workFailure(self):
        self.sender.smtpSender.shouldSucceed = False

        txn = self.store.newTransaction()
        wp = (yield txn.enqueue(IMIPInvitationWork,
            fromAddr=ORGANIZER,
            toAddr=ATTENDEE,
            icalendarText=initialInviteText.replace("\n", "\r\n"),
        ))
        yield txn.commit()
        yield wp.whenExecuted()
        # Verify a new work proposal was not created
        self.assertEquals(wp, self.wp)


    def _interceptEmail(self, inviteState, calendar, orgEmail, orgCn,
        attendees, fromAddress, replyToAddress, toAddress, language="en"):
        self.inviteState = inviteState
        self.calendar = calendar
        self.orgEmail = orgEmail
        self.orgCn = orgCn
        self.attendees = attendees
        self.fromAddress = fromAddress
        self.replyToAddress = replyToAddress
        self.toAddress = toAddress
        self.language = language
        self.results = self._actualGenerateEmail(inviteState, calendar,
            orgEmail, orgCn, attendees, fromAddress, replyToAddress, toAddress,
            language=language)
        return self.results


    @inlineCallbacks
    def test_outbound(self):
        """
        Make sure outbound( ) stores tokens properly so they can be looked up
        """

        config.Scheduling.iMIP.Sending.Address = "server@example.com"
        self.patch(config.Localization, "LocalesDirectory", os.path.join(os.path.dirname(__file__), "locales"))
        self._actualGenerateEmail = self.sender.generateEmail
        self.patch(self.sender, "generateEmail", self._interceptEmail)

        data = (
            # Initial invite
            (
                initialInviteText,
                "CFDD5E46-4F74-478A-9311-B3FF905449C3",
                "urn:uuid:C3B38B00-4166-11DD-B22C-A07C87E02F6A",
                "mailto:attendee@example.com",
                "new",
                "organizer@example.com",
                u"Th\xe9 Organizer",
                [
                    (u'Th\xe9 Attendee', u'attendee@example.com'),
                    (u'Th\xe9 Organizer', u'organizer@example.com'),
                    (u'An Attendee without CUTYPE', u'nocutype@example.com'),
                    (None, u'nocn@example.com'),
                ],
                u"Th\xe9 Organizer <organizer@example.com>",
                "=?utf-8?q?Th=C3=A9_Organizer_=3Corganizer=40example=2Ecom=3E?=",
                "attendee@example.com",
            ),

            # Update
            (
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
BEGIN:VEVENT
UID:CFDD5E46-4F74-478A-9311-B3FF905449C3
DTSTART:20100325T154500Z
DTEND:20100325T164500Z
ATTENDEE;CN=The Attendee;CUTYPE=INDIVIDUAL;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:
 mailto:attendee@example.com
ATTENDEE;CN=The Organizer;CUTYPE=INDIVIDUAL;EMAIL=organizer@example.com;PAR
 TSTAT=ACCEPTED:urn:uuid:C3B38B00-4166-11DD-B22C-A07C87E02F6A
ORGANIZER;CN=The Organizer;EMAIL=organizer@example.com:urn:uuid:C3B38B00-41
 66-11DD-B22C-A07C87E02F6A
SUMMARY:testing outbound( ) *update*
END:VEVENT
END:VCALENDAR
""",
                "CFDD5E46-4F74-478A-9311-B3FF905449C3",
                "urn:uuid:C3B38B00-4166-11DD-B22C-A07C87E02F6A",
                "mailto:attendee@example.com",
                "update",
                "organizer@example.com",
                "The Organizer",
                [
                    (u'The Attendee', u'attendee@example.com'),
                    (u'The Organizer', u'organizer@example.com')
                ],
                "The Organizer <organizer@example.com>",
                "The Organizer <organizer@example.com>",
                "attendee@example.com",
            ),

            # Reply
            (
                """BEGIN:VCALENDAR
VERSION:2.0
METHOD:REPLY
BEGIN:VEVENT
UID:DFDD5E46-4F74-478A-9311-B3FF905449C4
DTSTART:20100325T154500Z
DTEND:20100325T164500Z
ATTENDEE;CN=The Attendee;CUTYPE=INDIVIDUAL;EMAIL=attendee@example.com;PARTST
 AT=ACCEPTED:urn:uuid:C3B38B00-4166-11DD-B22C-A07C87E02F6A
ORGANIZER;CN=The Organizer;EMAIL=organizer@example.com:mailto:organizer@exam
 ple.com
SUMMARY:testing outbound( ) *reply*
END:VEVENT
END:VCALENDAR
""",
                None,
                "urn:uuid:C3B38B00-4166-11DD-B22C-A07C87E02F6A",
                "mailto:organizer@example.com",
                "reply",
                "organizer@example.com",
                "The Organizer",
                [
                    (u'The Attendee', u'attendee@example.com'),
                ],
                "attendee@example.com",
                "attendee@example.com",
                "organizer@example.com",
            ),

        )
        for (inputCalendar, UID, inputOriginator, inputRecipient, inviteState,
            outputOrganizerEmail, outputOrganizerName, outputAttendeeList,
            outputFrom, encodedFrom, outputRecipient) in data:

            txn = self.store.newTransaction()
            yield self.sender.outbound(
                txn,
                inputOriginator,
                inputRecipient,
                Component.fromString(inputCalendar.replace("\n", "\r\n")),
                onlyAfter=PyCalendarDateTime(2010, 1, 1, 0, 0, 0)
            )
            yield txn.commit()

            msg = email.message_from_string(self.sender.smtpSender.message)
            self.assertEquals(msg["From"], encodedFrom)
            self.assertEquals(self.inviteState, inviteState)
            self.assertEquals(self.orgEmail, outputOrganizerEmail)
            self.assertEquals(self.orgCn, outputOrganizerName)
            self.assertEquals(self.attendees, outputAttendeeList)
            self.assertEquals(self.fromAddress, outputFrom)
            self.assertEquals(self.toAddress, outputRecipient)

            if UID: # The organizer is local, and server is sending to remote
                    # attendee
                txn = self.store.newTransaction()
                token = (yield txn.imipGetToken(inputOriginator, inputRecipient,
                    UID))
                yield txn.commit()
                self.assertNotEquals(token, None)
                self.assertEquals(msg["Reply-To"],
                    "server+%s@example.com" % (token,))

                # Make sure attendee property for organizer exists and matches
                # the CUA of the organizer property
                orgValue = self.calendar.getOrganizerProperty().value()
                self.assertEquals(
                    orgValue,
                    self.calendar.getAttendeeProperty([orgValue]).value()
                )

            else: # Reply only -- the attendee is local, and server is sending reply to remote organizer

                self.assertEquals(msg["Reply-To"], self.fromAddress)

            # Check that we don't send any messages for events completely in
            # the past.
            self.sender.smtpSender.reset()
            txn = self.store.newTransaction()
            yield self.sender.outbound(
                txn,
                inputOriginator,
                inputRecipient,
                Component.fromString(inputCalendar.replace("\n", "\r\n")),
                onlyAfter=PyCalendarDateTime(2021, 1, 1, 0, 0, 0)
            )
            yield txn.commit()
            self.assertFalse(self.sender.smtpSender.sendMessageCalled)


    @inlineCallbacks
    def test_tokens(self):
        txn = self.store.newTransaction()
        token = (yield txn.imipLookupByToken("xyzzy"))
        yield txn.commit()
        self.assertEquals(token, [])

        txn = self.store.newTransaction()
        token1 = (yield txn.imipCreateToken("organizer", "attendee", "icaluid"))
        yield txn.commit()

        txn = self.store.newTransaction()
        token2 = (yield txn.imipGetToken("organizer", "attendee", "icaluid"))
        yield txn.commit()
        self.assertEquals(token1, token2)

        txn = self.store.newTransaction()
        self.assertEquals((yield txn.imipLookupByToken(token1)),
            [["organizer", "attendee", "icaluid"]])
        yield txn.commit()

        txn = self.store.newTransaction()
        yield txn.imipRemoveToken(token1)
        yield txn.commit()

        txn = self.store.newTransaction()
        self.assertEquals((yield txn.imipLookupByToken(token1)), [])
        yield txn.commit()


    @inlineCallbacks
    def test_mailtoTokens(self):
        """
        Make sure old mailto tokens are still honored
        """

        organizerEmail = "mailto:organizer@example.com"

        # Explictly store a token with mailto: CUA for organizer
        # (something that doesn't happen any more, but did in the past)
        txn = self.store.newTransaction()
        origToken = (yield txn.imipCreateToken(organizerEmail,
            "mailto:attendee@example.com",
            "CFDD5E46-4F74-478A-9311-B3FF905449C3"
            )
        )
        yield txn.commit()

        inputCalendar = initialInviteText
        UID = "CFDD5E46-4F74-478A-9311-B3FF905449C3"
        inputOriginator = "urn:uuid:C3B38B00-4166-11DD-B22C-A07C87E02F6A"
        inputRecipient = "mailto:attendee@example.com"

        txn = self.store.newTransaction()
        yield self.sender.outbound(txn, inputOriginator, inputRecipient,
            Component.fromString(inputCalendar.replace("\n", "\r\n")),
            onlyAfter=PyCalendarDateTime(2010, 1, 1, 0, 0, 0))

        # Verify we didn't create a new token...
        txn = self.store.newTransaction()
        token = (yield txn.imipGetToken(inputOriginator, inputRecipient, UID))
        yield txn.commit()
        self.assertEquals(token, None)

        # But instead kept the old one...
        txn = self.store.newTransaction()
        token = (yield txn.imipGetToken(organizerEmail, inputRecipient, UID))
        yield txn.commit()
        self.assertEquals(token, origToken)


    def generateSampleEmail(self):
        """
        Invoke L{MailHandler.generateEmail} and parse the result.
        """
        calendar = Component.fromString(initialInviteText)
        msgID, msgTxt = self.sender.generateEmail(
            inviteState='new',
            calendar=calendar,
            orgEmail=u"user01@localhost",
            orgCN=u"User Z\xe9ro One",
            attendees=[(u"Us\xe9r One", "user01@localhost"),
                       (u"User 2", "user02@localhost")],
            fromAddress="user01@localhost",
            replyToAddress="imip-system@localhost",
            toAddress="user03@localhost",
        )
        message = email.message_from_string(msgTxt)
        return msgID, message


    def test_generateEmail(self):
        """
        L{MailHandler.generateEmail} generates a MIME-formatted email with a
        text/plain part, a text/html part, and a text/calendar part.
        """
        msgID, message = self.generateSampleEmail()
        self.assertEquals(message['Message-ID'], msgID)
        expectedTypes = set(["text/plain", "text/html", "text/calendar"])
        actualTypes = set([
            part.get_content_type() for part in message.walk()
            if part.get_content_type().startswith("text/")
        ])
        self.assertEquals(actualTypes, expectedTypes)


    def test_emailEncoding(self):
        """
        L{MailHandler.generateEmail} will preserve any non-ASCII characters
        present in the fields that it formats in the message body.
        """
        _ignore_msgID, message = self.generateSampleEmail()
        textPart = partByType(message, "text/plain")
        htmlPart = partByType(message, "text/html")

        plainText = textPart.get_payload(decode=True).decode(
            textPart.get_content_charset()
        )
        htmlText = htmlPart.get_payload(decode=True).decode(
            htmlPart.get_content_charset()
        )

        self.assertIn(u"Us\u00e9r One", plainText)
        self.assertIn(u'<a href="mailto:user01@localhost">Us\u00e9r One</a>',
                      htmlText)

        # The same assertion, but with the organizer's form.
        self.assertIn(
            u'<a href="mailto:user01@localhost">User Z\u00e9ro One</a>',
            htmlText)


    def test_emailQuoting(self):
        """
        L{MailHandler.generateEmail} will HTML-quote all relevant fields in the
        HTML part, but not the text/plain part.
        """
        _ignore_msgID, message = self.generateSampleEmail()
        htmlPart = partByType(message, "text/html").get_payload(decode=True)
        plainPart = partByType(message, "text/plain").get_payload(decode=True)
        expectedPlain = 'awesome description with "<" and "&"'
        expectedHTML = expectedPlain.replace("&", "&amp;").replace("<", "&lt;")

        self.assertIn(expectedPlain, plainPart)
        self.assertIn(expectedHTML, htmlPart)


    def test_stringFormatTemplateLoader(self):
        """
        L{StringFormatTemplateLoader.load} will convert a template with
        C{%(x)s}-format slots by converting it to a template with C{<t:slot
        name="x" />} slots, and a renderer on the document element named
        according to the constructor argument.
        """
        class StubElement(Element):
            loader = StringFormatTemplateLoader(
                lambda : StringIO(
                    "<test><alpha>%(slot1)s</alpha>%(other)s</test>"
                ),
                "testRenderHere"
            )

            @renderer
            def testRenderHere(self, request, tag):
                return tag.fillSlots(slot1="hello",
                                     other="world")
        result = []
        flattenString(None, StubElement()).addCallback(result.append)
        self.assertEquals(result,
                          ["<test><alpha>hello</alpha>world</test>"])


    def test_templateLoaderWithAttributes(self):
        """
        L{StringFormatTemplateLoader.load} will convert a template with
        C{%(x)s}-format slots inside attributes into t:attr elements containing
        t:slot slots.
        """
        class StubElement(Element):
            loader = StringFormatTemplateLoader(
                lambda : StringIO(
                    '<test><alpha beta="before %(slot1)s after">inner</alpha>'
                    '%(other)s</test>'
                ),
                "testRenderHere"
            )

            @renderer
            def testRenderHere(self, request, tag):
                return tag.fillSlots(slot1="hello",
                                     other="world")
        result = []
        flattenString(None, StubElement()).addCallback(result.append)
        self.assertEquals(result,
                          ['<test><alpha beta="before hello after">'
                           'inner</alpha>world</test>'])


    def test_templateLoaderTagSoup(self):
        """
        L{StringFormatTemplateLoader.load} will convert a template with
        C{%(x)s}-format slots into t:slot slots, and render a well-formed output
        document, even if the input is malformed (i.e. missing necessary closing
        tags).
        """
        class StubElement(Element):
            loader = StringFormatTemplateLoader(
                lambda : StringIO(
                    '<test><alpha beta="before %(slot1)s after">inner</alpha>'
                    '%(other)s'
                ),
                "testRenderHere"
            )

            @renderer
            def testRenderHere(self, request, tag):
                return tag.fillSlots(slot1="hello",
                                     other="world")
        result = []
        flattenString(None, StubElement()).addCallback(result.append)
        self.assertEquals(result,
                          ['<test><alpha beta="before hello after">'
                           'inner</alpha>world</test>'])



def partByType(message, contentType):
    """
    Retrieve a MIME part from an L{email.message.Message} based on a content
    type.
    """
    for part in message.walk():
        if part.get_content_type() == contentType:
            return part
    raise KeyError(contentType)
