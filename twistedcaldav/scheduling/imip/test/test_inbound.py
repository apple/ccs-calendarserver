##
# Copyright (c) 2008-2013 Apple Inc. All rights reserved.
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


import email
from twisted.internet.defer import inlineCallbacks
from twisted.python.modules import getModule
from twistedcaldav.ical import Component
from twistedcaldav.scheduling.imip.inbound import MailReceiver
from twistedcaldav.scheduling.imip.inbound import MailRetriever
from twistedcaldav.scheduling.imip.inbound import injectMessage
from twistedcaldav.scheduling.imip.inbound import IMIPReplyWork
from twistedcaldav.scheduling.itip import iTIPRequestStatus
from twistedcaldav.test.util import TestCase
from twistedcaldav.test.util import xmlFile
from txdav.common.datastore.test.util import buildStore
from calendarserver.tap.util import getRootResource
from twistedcaldav.config import config, ConfigDict


class InboundTests(TestCase):

    @inlineCallbacks
    def setUp(self):
        super(InboundTests, self).setUp()

        self.store = yield buildStore(self, None)
        self.patch(config.DirectoryService.params, "xmlFile", xmlFile)
        self.root = getRootResource(config, self.store)
        self.directory = self.root.getDirectory()
        self.receiver = MailReceiver(self.store, self.directory)
        self.retriever = MailRetriever(self.store, self.directory,
            ConfigDict({
                "Type" : "pop",
                "UseSSL" : False,
                "Server" : "example.com",
                "Port" : 123,
            })
        )

        def decorateTransaction(txn):
            txn._rootResource = self.root
            txn._mailRetriever = self.retriever

        self.store.callWithNewTransactions(decorateTransaction)
        module = getModule(__name__)
        self.dataPath = module.filePath.sibling("data")

    def dataFile(self, name):
        """
        Get the contents of a given data file from the 'data/mail' test
        fixtures directory.
        """
        return self.dataPath.child(name).getContent()


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
            self.assertEquals(self.receiver.checkDSN(msg), expected)


    @inlineCallbacks
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
        self.assertEquals(
            (yield self.receiver.processDSN(calBody, "xyzzy")),
            MailReceiver.UNKNOWN_TOKEN
        )

        # Make sure a known token *is* processed
        txn = self.store.newTransaction()
        token = (yield txn.imipCreateToken(
            "urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500",
            "mailto:user02@example.com",
            "1E71F9C8-AEDA-48EB-98D0-76E898F6BB5C"
        ))
        yield txn.commit()
        calBody = template % token
        result = (yield self.receiver.processDSN(calBody, "xyzzy"))
        self.assertEquals(result, MailReceiver.INJECTION_SUBMITTED)


    @inlineCallbacks
    def test_processReply(self):
        msg = email.message_from_string(self.dataFile('good_reply'))

        # Make sure an unknown token is not processed
        result = (yield self.receiver.processReply(msg))
        self.assertEquals(result, MailReceiver.UNKNOWN_TOKEN)

        # Make sure a known token *is* processed
        txn = self.store.newTransaction()
        yield txn.imipCreateToken(
            "urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500",
            "mailto:xyzzy@example.com",
            "1E71F9C8-AEDA-48EB-98D0-76E898F6BB5C",
            token="d7cdf68d-8b73-4df1-ad3b-f08002fb285f"
        )
        yield txn.commit()

        result = (yield self.receiver.processReply(msg))
        self.assertEquals(result, MailReceiver.INJECTION_SUBMITTED)


    def test_processReplyMissingOrganizer(self):
        msg = email.message_from_string(self.dataFile('reply_missing_organizer'))

        # stick the token in the database first
        txn = self.store.newTransaction()
        yield txn.imipCreateToken(
            "urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500",
            "mailto:xyzzy@example.com",
            "1E71F9C8-AEDA-48EB-98D0-76E898F6BB5C",
            token="d7cdf68d-8b73-4df1-ad3b-f08002fb285f"
        )
        yield txn.commit()

        result = (yield self.receiver.processReply(msg))
        organizer, _ignore_attendee, calendar = result
        organizerProp = calendar.mainComponent().getOrganizerProperty()
        self.assertTrue(organizerProp is not None)
        self.assertEquals(organizer,
                          "urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500")


    def test_processReplyMissingAttendee(self):
        msg = email.message_from_string(self.dataFile('reply_missing_attendee'))

        txn = self.store.newTransaction()
        yield txn.imipCreateToken(
            "urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500",
            "mailto:xyzzy@example.com",
            "1E71F9C8-AEDA-48EB-98D0-76E898F6BB5C",
            token="d7cdf68d-8b73-4df1-ad3b-f08002fb285f"
        )
        yield txn.commit()

        result = (yield self.receiver.processReply(msg))
        _ignore_organizer, attendee, calendar = result

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
        txn = self.store.newTransaction()
        yield txn.imipCreateToken(
            "urn:uuid:5A985493-EE2C-4665-94CF-4DFEA3A89500",
            "mailto:xyzzy@example.com",
            "1E71F9C8-AEDA-48EB-98D0-76E898F6BB5C",
            token="d7cdf68d-8b73-4df1-ad3b-f08002fb285f"
        )
        yield txn.commit()

        result = (yield self.receiver.processReply(msg))
        self.assertEquals(result, MailReceiver.REPLY_FORWARDED_TO_ORGANIZER)        

    @inlineCallbacks
    def test_injectMessage(self):

        calendar = Component.fromString("""BEGIN:VCALENDAR
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
VERSION:2.0
METHOD:REPLY
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20130208T120000Z
DTSTART:20180601T120000Z
DTEND:20180601T130000Z
ORGANIZER:urn:uuid:user01
ATTENDEE:mailto:xyzzy@example.com;PARTSTAT=ACCEPTED
END:VEVENT
END:VCALENDAR
""")

        txn = self.store.newTransaction()
        result = (yield injectMessage(
                txn,
                self.root,
                "urn:uuid:user01",
                "mailto:xyzzy@example.com",
                calendar
            )
        )
        yield txn.commit()
        self.assertEquals(
            "1.2;Scheduling message has been delivered",
            result.responses[0].children[1].toString()
        )

    @inlineCallbacks
    def test_injectMessageWithError(self):

        calendar = Component.fromString("""BEGIN:VCALENDAR
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
VERSION:2.0
METHOD:REPLY
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20130208T120000Z
DTSTART:20180601T120000Z
DTEND:20180601T130000Z
ORGANIZER:urn:uuid:unknown_user
ATTENDEE:mailto:xyzzy@example.com;PARTSTAT=ACCEPTED
END:VEVENT
END:VCALENDAR
""")

        txn = self.store.newTransaction()
        result = (yield injectMessage(
                txn,
                self.root,
                "urn:uuid:unknown_user",
                "mailto:xyzzy@example.com",
                calendar
            )
        )
        yield txn.commit()
        self.assertEquals(
            "3.7;Invalid Calendar User",
            result.responses[0].children[1].toString()
        )


    @inlineCallbacks
    def test_work(self):

        calendar = """BEGIN:VCALENDAR
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
VERSION:2.0
METHOD:REPLY
BEGIN:VEVENT
UID:12345-67890
DTSTAMP:20130208T120000Z
DTSTART:20180601T120000Z
DTEND:20180601T130000Z
ORGANIZER:urn:uuid:user01
ATTENDEE:mailto:xyzzy@example.com;PARTSTAT=ACCEPTED
END:VEVENT
END:VCALENDAR
"""
        txn = self.store.newTransaction()
        wp = (yield txn.enqueue(IMIPReplyWork,
            organizer="urn:uuid:user01",
            attendee="mailto:xyzzy@example.com",
            icalendarText=calendar
        ))
        yield txn.commit()
        yield wp.whenExecuted()
