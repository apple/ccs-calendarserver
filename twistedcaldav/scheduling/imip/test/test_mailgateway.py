##
# Copyright (c) 2008-2012 Apple Inc. All rights reserved.
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


from cStringIO import StringIO

from pycalendar.datetime import PyCalendarDateTime

from twisted.internet.defer import inlineCallbacks
from twisted.python.filepath import FilePath
from twisted.python.modules import getModule
from twisted.web.template import Element, renderer, flattenString

from twistedcaldav.config import config, ConfigDict
from twistedcaldav.directory import augment
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.ical import Component
from twistedcaldav.scheduling.imip.mailgateway import MailGatewayTokensDatabase
from twistedcaldav.scheduling.imip.mailgateway import MailHandler
from twistedcaldav.scheduling.imip.mailgateway import StringFormatTemplateLoader
from twistedcaldav.scheduling.imip.mailgateway import injectionSettingsFromURL
from twistedcaldav.scheduling.imip.mailgateway import serverForOrganizer
from twistedcaldav.scheduling.ischedule.localservers import Servers
from twistedcaldav.scheduling.itip import iTIPRequestStatus
from twistedcaldav.test.util import TestCase
from twistedcaldav.test.util import xmlFile, augmentsFile

import datetime
import email
import os


def echo(*args):
    return args

initialInviteText = u"""BEGIN:VCALENDAR
VERSION:2.0
METHOD:REQUEST
BEGIN:VEVENT
UID:CFDD5E46-4F74-478A-9311-B3FF905449C3
DTSTART:20100325T154500Z
DTEND:20100325T164500Z
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

class MailHandlerTests(TestCase):

    def setUp(self):
        super(MailHandlerTests, self).setUp()

        self._setupServers(serverData)
        self.directory = XMLDirectoryService(
            {
                'xmlFile' : xmlFile,
                'augmentService' :
                    augment.AugmentXMLDB(xmlFiles=(augmentsFile.path,)),
            }
        )
        self.handler = MailHandler(dataRoot=":memory:", directory=self.directory)
        module = getModule(__name__)
        self.dataPath = module.filePath.sibling("data")


    def _setupServers(self, data):
        self.patch(config, "ServerHostName", "caldav1.example.com")
        self.patch(config, "HTTPPort", 8008)
        self.patch(config.Servers, "Enabled", True)

        xmlFile = StringIO(data)
        servers = Servers
        servers.load(xmlFile, ignoreIPLookupFailures=True)


    def dataFile(self, name):
        """
        Get the contents of a given data file from the 'data/mail' test
        fixtures directory.
        """
        return self.dataPath.child(name).getContent()


    def test_serverDetection(self):
        wsanchez = self.directory.recordWithShortName("users",
            "wsanchez")
        cdaboo = self.directory.recordWithShortName("users",
            "cdaboo")
        server = wsanchez.server()
        self.assertEquals(server.uri, "http://caldav1.example.com:8008")
        server = cdaboo.server()
        self.assertEquals(server.uri, "https://caldav2.example.com:8843")

        url = serverForOrganizer(self.directory,
            "mailto:wsanchez@example.com")
        self.assertEquals(url, "http://caldav1.example.com:8008")
        url = serverForOrganizer(self.directory,
            "mailto:cdaboo@example.com")
        self.assertEquals(url, "https://caldav2.example.com:8843")


    def test_purge_and_lowercase(self):
        """
        Ensure that purge( ) cleans out old tokens, and that lowercase( )
        converts all mailto: to lowercase, since earlier server versions
        didn't do that before inserting into the database.
        """

        # Insert an "old" token
        token = "test_token_1"
        organizer = "urn:uuid:19BFE23D-0269-46CA-877C-D4B521A7A9A5"
        attendee = "mailto:you@example.com"
        icaluid = "123"
        pastDate = datetime.date(2009, 1, 1)
        self.handler.db._db_execute(
            """
            insert into TOKENS (TOKEN, ORGANIZER, ATTENDEE, ICALUID, DATESTAMP)
            values (:1, :2, :3, :4, :5)
            """, token, organizer, attendee, icaluid, pastDate
        )
        self.handler.db._db_commit()

        # purge, and make sure we don't see that token anymore
        self.handler.purge()
        retrieved = self.handler.db.getToken(organizer, attendee, icaluid)
        self.assertEquals(retrieved, None)

        # Insert a token with (old-format) mailto:
        token = "test_token_2"
        organizer = "MailTo:Organizer@Example.com"
        attendee = "MAILTO:YouTwo@Example.com"
        icaluid = "456"
        futureDate = datetime.date(2100, 1, 1)
        self.handler.db._db_execute(
            """
            insert into TOKENS (TOKEN, ORGANIZER, ATTENDEE, ICALUID, DATESTAMP)
            values (:1, :2, :3, :4, :5)
            """, token, organizer, attendee, icaluid, futureDate
        )
        self.handler.db._db_commit()

        self.handler.lowercase()
        retrieved = self.handler.db.getToken(organizer.lower(),
            attendee.lower(), icaluid)
        self.assertIsInstance(retrieved, str)
        self.assertEquals(retrieved, token)

        # Insert a token with (new-format) urn:uuid:
        token = "test_token_3"
        organizer = "urn:uuid:E0CF4031-676B-4668-A9D3-8F33A0212F70"
        attendee = "MAILTO:YouTwo@Example.com"
        icaluid = "789"
        futureDate = datetime.date(2100, 1, 1)
        self.handler.db._db_execute(
            """
            insert into TOKENS (TOKEN, ORGANIZER, ATTENDEE, ICALUID, DATESTAMP)
            values (:1, :2, :3, :4, :5)
            """, token, organizer, attendee, icaluid, futureDate
        )
        self.handler.db._db_commit()

        self.handler.lowercase()
        retrieved = self.handler.db.getToken(organizer,
            attendee.lower(), icaluid)
        self.assertEquals(retrieved, token)


    def test_iconPath(self):
        iconPath = self.handler.getIconPath({'day': '1', 'month': '1'}, False, language='en')
        iconDir = FilePath("/usr/share/caldavd/share/date_icons")

        if iconDir.exists():
            if iconDir.child("JAN").child("01.png"):
                monthName = "JAN"
            else:
                monthName = "01"
            monthPath = iconDir.child(monthName)
            self.assertEquals(iconPath, monthPath.child("01.png").path)


    def test_checkDSNFailure(self):

        data = {
            'good_reply' : (False, None, None),
            'dsn_failure_no_original' : (True, 'failed', None),
            'dsn_failure_no_ics' : (True, 'failed', None),
            'dsn_failure_with_ics' : (True, 'failed', '''BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:REQUEST
PRODID:-//example Inc.//iCal 3.0//EN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:1E71F9C8-AEDA-48EB-98D0-76E898F6BB5C
DTSTART;TZID=US/Pacific:20080812T094500
DTEND;TZID=US/Pacific:20080812T104500
ATTENDEE;CUTYPE=INDIVIDUAL;CN=User 01;PARTSTAT=ACCEPTED:mailto:user01@exam
 ple.com
ATTENDEE;CUTYPE=INDIVIDUAL;RSVP=TRUE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-A
 CTION;CN=nonexistant@example.com:mailto:nonexistant@example.com
CREATED:20080812T191857Z
DTSTAMP:20080812T191932Z
ORGANIZER;CN=User 01:mailto:xyzzy+8e16b897-d544-4217-88e9-a363d08
 46f6c@example.com
SEQUENCE:2
SUMMARY:New Event
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
'''),
        }

        for filename, expected in data.iteritems():
            msg = email.message_from_string(self.dataFile(filename))
            self.assertEquals(self.handler.checkDSN(msg), expected)


    def test_processDSN(self):

        template = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:REQUEST
PRODID:-//example Inc.//iCal 3.0//EN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:1E71F9C8-AEDA-48EB-98D0-76E898F6BB5C
DTSTART;TZID=US/Pacific:20080812T094500
DTEND;TZID=US/Pacific:20080812T104500
ATTENDEE;CUTYPE=INDIVIDUAL;CN=User 01;PARTSTAT=ACCEPTED:mailto:user01@exam
 ple.com
ATTENDEE;CUTYPE=INDIVIDUAL;RSVP=TRUE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-A
 CTION;CN=nonexistant@example.com:mailto:nonexistant@example.com
CREATED:20080812T191857Z
DTSTAMP:20080812T191932Z
ORGANIZER;CN=User 01:mailto:xyzzy+%s@example.com
SEQUENCE:2
SUMMARY:New Event
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
"""

        # Make sure an unknown token is not processed
        calBody = template % "bogus_token"
        self.assertEquals(self.handler.processDSN(calBody, "xyzzy", echo),
           None)

        # Make sure a known token *is* processed
        token = self.handler.db.createToken(
            "urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500",
            "mailto:user02@example.com", "1E71F9C8-AEDA-48EB-98D0-76E898F6BB5C")
        calBody = template % token
        _ignore_url, organizer, attendee, calendar, msgId = self.handler.processDSN(calBody,
            "xyzzy", echo)
        self.assertEquals(organizer, 'urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500')
        self.assertEquals(attendee, 'mailto:user02@example.com')
        self.assertEquals(str(calendar), """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:REQUEST
PRODID:-//example Inc.//iCal 3.0//EN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:1E71F9C8-AEDA-48EB-98D0-76E898F6BB5C
DTSTART;TZID=US/Pacific:20080812T094500
DTEND;TZID=US/Pacific:20080812T104500
CREATED:20080812T191857Z
DTSTAMP:20080812T191932Z
ORGANIZER;CN=User 01:urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500
REQUEST-STATUS:5.1;Service unavailable
SEQUENCE:2
SUMMARY:New Event
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n"))
        self.assertEquals(msgId, 'xyzzy')


    def test_processReply(self):
        msg = email.message_from_string(self.dataFile('good_reply'))

        # Make sure an unknown token is not processed
        result = self.handler.processReply(msg, echo)
        self.assertEquals(result, None)

        # Make sure a known token *is* processed
        self.handler.db.createToken(
            "urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500",
            "mailto:xyzzy@example.com",
            icaluid="1E71F9C8-AEDA-48EB-98D0-76E898F6BB5C",
            token="d7cdf68d-8b73-4df1-ad3b-f08002fb285f"
        )
        url, organizer, attendee, _ignore_calendar, msgId = self.handler.processReply(msg, echo)
        self.assertEquals(url, "https://caldav2.example.com:8843")
        self.assertEquals(organizer,
                          'urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500')
        self.assertEquals(attendee, 'mailto:xyzzy@example.com')
        self.assertEquals(msgId,
                          '<1983F777-BE86-4B98-881E-06D938E60920@example.com>')


    def test_injectionSettingsFromURL(self):
        testData = (
            (
                None,
                {
                    "Scheduling": {
                        "iMIP" : {
                            "MailGatewayServer" : "localhost",
                        },
                    },
                    "EnableSSL" : True,
                    "ServerHostName" : "calendar.example.com",
                    "HTTPPort" : 1111,
                    "SSLPort" : 2222,
                },
                "https://localhost:2222/inbox/",
            ),
            (
                None,
                {
                    "Scheduling": {
                        "iMIP" : {
                            "MailGatewayServer" : "mailgateway.example.com",
                        },
                    },
                    "EnableSSL" : False,
                    "ServerHostName" : "calendar.example.com",
                    "HTTPPort" : 1111,
                    "SSLPort" : 2222,
                },
                "http://calendar.example.com:1111/inbox/",
            ),
            (
                "https://calendar.example.com:1234/",
                { },
                "https://calendar.example.com:1234/inbox/",
            ),
            (
                "https://calendar.example.com:1234",
                { },
                "https://calendar.example.com:1234/inbox/",
            ),
        )

        for url, configData, expected in testData:
            self.assertEquals(
                expected,
                injectionSettingsFromURL(url, ConfigDict(mapping=configData))
            )


    def test_processReplyMissingOrganizer(self):
        msg = email.message_from_string(self.dataFile('reply_missing_organizer'))
        # stick the token in the database first
        self.handler.db.createToken(
            "urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500",
            "mailto:xyzzy@example.com",
            icaluid="1E71F9C8-AEDA-48EB-98D0-76E898F6BB5C",
            token="d7cdf68d-8b73-4df1-ad3b-f08002fb285f"
        )

        _ignore_url, organizer, _ignore_attendee, calendar, _ignore_msgId = self.handler.processReply(
            msg, echo)
        organizerProp = calendar.mainComponent().getOrganizerProperty()
        self.assertTrue(organizerProp is not None)
        self.assertEquals(organizer,
                          "urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500")


    def test_processReplyMissingAttendee(self):
        msg = email.message_from_string(self.dataFile('reply_missing_attendee'))

        # stick the token in the database first
        self.handler.db.createToken(
            "urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500",
            "mailto:xyzzy@example.com",
            icaluid="1E71F9C8-AEDA-48EB-98D0-76E898F6BB5C",
            token="d7cdf68d-8b73-4df1-ad3b-f08002fb285f"
        )

        _ignore_url, _ignore_organizer, attendee, calendar, _ignore_msgId = self.handler.processReply(
            msg, echo)

        # Since the expected attendee was missing, the reply processor should
        # have added an attendee back in with a "5.1;Service unavailable"
        # schedule-status
        attendeeProp = calendar.mainComponent().getAttendeeProperty([attendee])
        self.assertEquals(attendeeProp.parameterValue("SCHEDULE-STATUS"),
                          iTIPRequestStatus.SERVICE_UNAVAILABLE)


    def test_processReplyMissingAttachment(self):

        msg = email.message_from_string(
            self.dataFile('reply_missing_attachment')
        )
        # stick the token in the database first
        self.handler.db.createToken(
            "urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500",
            "mailto:xyzzy@example.com",
            icaluid="1E71F9C8-AEDA-48EB-98D0-76E898F6BB5C",
            token="d7cdf68d-8b73-4df1-ad3b-f08002fb285f"
        )

        self.assertEquals(
            self.handler.processReply(msg, echo, testMode=True),
            ("cdaboo@example.com", "xyzzy@example.com")
        )


    @inlineCallbacks
    def test_outbound(self):
        """
        Make sure outbound( ) stores tokens properly so they can be looked up
        """

        config.Scheduling.iMIP.Sending.Address = "server@example.com"
        self.patch(config.Localization, "LocalesDirectory", os.path.join(os.path.dirname(__file__), "locales"))

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
                "organizer@example.com",
            ),

        )
        for (inputCalendar, UID, inputOriginator, inputRecipient, inviteState,
            outputOrganizerEmail, outputOrganizerName, outputAttendeeList,
            outputFrom, outputRecipient) in data:

            (actualInviteState, actualCalendar, actualOrganizerEmail,
                actualOrganizerName, actualAttendeeList, actualFrom,
                actualRecipient, actualReplyTo) = (yield self.handler.outbound(
                    inputOriginator,
                    inputRecipient,
                    Component.fromString(inputCalendar.replace("\n", "\r\n")),
                    language="ja",
                    send=False,
                    onlyAfter=PyCalendarDateTime(2010, 1, 1, 0, 0, 0))
                )

            self.assertEquals(actualInviteState, inviteState)
            self.assertEquals(actualOrganizerEmail, outputOrganizerEmail)
            self.assertEquals(actualOrganizerName, outputOrganizerName)
            self.assertEquals(actualAttendeeList, outputAttendeeList)
            self.assertEquals(actualFrom, outputFrom)
            self.assertEquals(actualRecipient, outputRecipient)

            if UID: # The organizer is local, and server is sending to remote
                    # attendee

                token = self.handler.db.getToken(inputOriginator,
                    inputRecipient, UID)
                self.assertNotEquals(token, None)
                self.assertEquals(actualReplyTo,
                    "server+%s@example.com" % (token,))

                # Make sure attendee property for organizer exists and matches
                # the CUA of the organizer property
                orgValue = actualCalendar.getOrganizerProperty().value()
                self.assertEquals(
                    orgValue,
                    actualCalendar.getAttendeeProperty([orgValue]).value()
                )

            else: # Reply only -- the attendee is local, and server is sending reply to remote organizer

                self.assertEquals(actualReplyTo, actualFrom)

            # Check that we don't send any messages for events completely in
            # the past.
            result = (yield self.handler.outbound(
                    inputOriginator,
                    inputRecipient,
                    Component.fromString(inputCalendar.replace("\n", "\r\n")),
                    send=False,
                    onlyAfter=PyCalendarDateTime(2012, 1, 1, 0, 0, 0))
                )
            self.assertEquals(result, True)


    @inlineCallbacks
    def test_mailtoTokens(self):
        """
        Make sure old mailto tokens are still honored
        """

        organizerEmail = "mailto:organizer@example.com"

        config.Scheduling.iMIP.Sending.Address = "server@example.com"

        # Explictly store a token with mailto: CUA for organizer
        # (something that doesn't happen any more, but did in the past)
        origToken = self.handler.db.createToken(organizerEmail,
            "mailto:attendee@example.com",
            "CFDD5E46-4F74-478A-9311-B3FF905449C3")

        inputCalendar = initialInviteText
        UID = "CFDD5E46-4F74-478A-9311-B3FF905449C3"
        inputOriginator = "urn:uuid:C3B38B00-4166-11DD-B22C-A07C87E02F6A"
        inputRecipient = "mailto:attendee@example.com"

        (_ignore_actualInviteState, _ignore_actualCalendar, _ignore_actualOrganizerEmail,
            _ignore_actualOrganizerName, _ignore_actualAttendeeList, _ignore_actualFrom,
            _ignore_actualRecipient, _ignore_actualReplyTo) = (yield self.handler.outbound(
                inputOriginator,
                inputRecipient,
                Component.fromString(inputCalendar.replace("\n", "\r\n")),
                send=False,
                onlyAfter=PyCalendarDateTime(2010, 1, 1, 0, 0, 0))
            )

        # Verify we didn't create a new token...
        token = self.handler.db.getToken(inputOriginator,
            inputRecipient, UID)
        self.assertEquals(token, None)

        # But instead kept the old one...
        token = self.handler.db.getToken(organizerEmail,
            inputRecipient, UID)
        self.assertEquals(token, origToken)


    def generateSampleEmail(self):
        """
        Invoke L{MailHandler.generateEmail} and parse the result.
        """
        calendar = Component.fromString(initialInviteText)
        msgID, msgTxt = self.handler.generateEmail(
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



class MailGatewayTokensDatabaseTests(TestCase):

    def setUp(self):
        TestCase.setUp(self)
        self.db = MailGatewayTokensDatabase(":memory:")


    def test_tokens(self):
        self.assertEquals(self.db.lookupByToken("xyzzy"), None)

        token = self.db.createToken("organizer", "attendee", "icaluid")
        self.assertEquals(self.db.getToken("organizer", "attendee", "icaluid"),
                          token)
        self.assertEquals(self.db.lookupByToken(token),
            ("organizer", "attendee", "icaluid"))
        self.db.deleteToken(token)
        self.assertEquals(self.db.lookupByToken(token), None)


serverData = """<?xml version="1.0" encoding="utf-8"?>
<servers>
  <server>
    <id>00001</id>
    <uri>http://caldav1.example.com:8008</uri>
    <allowed-from>127.0.0.1</allowed-from>
    <shared-secret>foobar</shared-secret>
  </server>
  <server>
    <id>00002</id>
    <uri>https://caldav2.example.com:8843</uri>
    <partitions>
        <partition>
            <id>A</id>
            <uri>https://machine1.example.com:8443</uri>
        </partition>
        <partition>
            <id>B</id>
            <uri>https://machine2.example.com:8443</uri>
        </partition>
    </partitions>
  </server>
</servers>
"""
