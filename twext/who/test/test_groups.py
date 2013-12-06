##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
Group membership caching implementation tests
"""

from twext.who.groups import GroupCacher, _expandedMembers
from twext.who.idirectory import RecordType
from twext.who.test.test_xml import xmlService
from twisted.internet.defer import inlineCallbacks
from twistedcaldav.test.util import StoreTestCase
from txdav.common.icommondatastore import NotFoundError
from uuid import UUID

class GroupCacherTest(StoreTestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(GroupCacherTest, self).setUp()
        self.xmlService = xmlService(self.mktemp(), xmlData=testXMLConfig)
        self.groupCacher = GroupCacher(
            None,
            self.xmlService,
            None,
            0
        )


    @inlineCallbacks
    def test_expandedMembers(self):
        """
        Verify _expandedMembers() returns a "flattened" set of records
        belonging to a group (and does not return sub-groups themselves,
        only their members)
        """
        record = yield self.xmlService.recordWithUID("__top_group_1__")
        memberUIDs = set()
        for member in (yield _expandedMembers(record)):
            memberUIDs.add(member.uid)
        self.assertEquals(memberUIDs, set(["__cdaboo__",
            "__glyph__", "__sagen__", "__wsanchez__"]))

        # Non group records return an empty set() of members
        record = yield self.xmlService.recordWithUID("__sagen__")
        members = yield _expandedMembers(record)
        self.assertEquals(0, len(list(members)))


    @inlineCallbacks
    def test_refreshGroup(self):
        """
        Verify refreshGroup() adds a group to the Groups table with the
        expected membership hash value and members
        """

        store = self.storeUnderTest()
        txn = store.newTransaction()

        record = yield self.xmlService.recordWithUID("__top_group_1__")
        yield self.groupCacher.refreshGroup(txn, record.guid)

        groupID, name, membershipHash = (yield txn.groupByGUID(record.guid)) #@UnusedVariable
        self.assertEquals(membershipHash, "4b0e162f2937f0f3daa6d10e5a6a6c33")

        groupGUID, name, membershipHash = (yield txn.groupByID(groupID))
        self.assertEquals(groupGUID, record.guid)
        self.assertEquals(name, "Top Group 1")
        self.assertEquals(membershipHash, "4b0e162f2937f0f3daa6d10e5a6a6c33")

        members = (yield txn.membersOfGroup(groupID))
        self.assertEquals(
            set([UUID("9064df911dbc4e079c2b6839b0953876"),
                 UUID("4ad155cbae9b475f986ce08a7537893e"),
                 UUID("3bdcb95484d54f6d8035eac19a6d6e1f"),
                 UUID("7d45cb10479e456bb54d528958c5734b")]),
            members
        )

        records = (yield self.groupCacher.cachedMembers(txn, groupID))
        self.assertEquals(
            set([r.shortNames[0] for r in records]),
            set(["wsanchez", "cdaboo", "glyph", "sagen"])
        )


    @inlineCallbacks
    def test_synchronizeMembers(self):
        """
        After loading in a group via refreshGroup(), pass new member sets to
        synchronizeMembers() and verify members are added and removed as
        expected
        """

        store = self.storeUnderTest()
        txn = store.newTransaction()

        # Refresh the group so it's assigned a group_id
        guid = UUID("49b350c69611477b94d95516b13856ab")
        yield self.groupCacher.refreshGroup(txn, guid)
        groupID, name, membershipHash = (yield txn.groupByGUID(guid)) #@UnusedVariable

        # Remove two members, and add one member
        newSet = set()
        for name in ("wsanchez", "cdaboo", "dre"):
            record = (yield self.xmlService.recordWithShortName(RecordType.user,
                name))
            newSet.add(record.guid)
        numAdded, numRemoved = (yield self.groupCacher.synchronizeMembers(txn,
            groupID, newSet))
        self.assertEquals(numAdded, 1)
        self.assertEquals(numRemoved, 2)
        records = (yield self.groupCacher.cachedMembers(txn, groupID))
        self.assertEquals(
            set([r.shortNames[0] for r in records]),
            set(["wsanchez", "cdaboo", "dre"])
        )

        # Remove all members
        numAdded, numRemoved = (yield self.groupCacher.synchronizeMembers(txn,
            groupID, set()))
        self.assertEquals(numAdded, 0)
        self.assertEquals(numRemoved, 3)
        records = (yield self.groupCacher.cachedMembers(txn, groupID))
        self.assertEquals(len(records), 0)


    @inlineCallbacks
    def test_groupByID(self):

        store = self.storeUnderTest()
        txn = store.newTransaction()

        # Non-existent groupID
        self.failUnlessFailure(txn.groupByID(42), NotFoundError)

        guid = UUID("49b350c69611477b94d95516b13856ab")
        hash = "4b0e162f2937f0f3daa6d10e5a6a6c33"
        yield self.groupCacher.refreshGroup(txn, guid)
        groupID, name, membershipHash = (yield txn.groupByGUID(guid)) #@UnusedVariable
        results = (yield txn.groupByID(groupID))
        self.assertEquals([guid, "Top Group 1", hash], results)


testXMLConfig = """<?xml version="1.0" encoding="utf-8"?>

<directory realm="xyzzy">

  <record type="user">
    <uid>__wsanchez__</uid>
    <guid>3BDCB954-84D5-4F6D-8035-EAC19A6D6E1F</guid>
    <short-name>wsanchez</short-name>
    <short-name>wilfredo_sanchez</short-name>
    <full-name>Wilfredo Sanchez</full-name>
    <password>zehcnasw</password>
    <email>wsanchez@bitbucket.calendarserver.org</email>
    <email>wsanchez@devnull.twistedmatrix.com</email>
  </record>

  <record type="user">
    <uid>__glyph__</uid>
    <guid>9064DF91-1DBC-4E07-9C2B-6839B0953876</guid>
    <short-name>glyph</short-name>
    <full-name>Glyph Lefkowitz</full-name>
    <password>hpylg</password>
    <email>glyph@bitbucket.calendarserver.org</email>
    <email>glyph@devnull.twistedmatrix.com</email>
  </record>

  <record type="user">
    <uid>__sagen__</uid>
    <guid>4AD155CB-AE9B-475F-986C-E08A7537893E</guid>
    <short-name>sagen</short-name>
    <full-name>Morgen Sagen</full-name>
    <password>negas</password>
    <email>sagen@bitbucket.calendarserver.org</email>
    <email>shared@example.com</email>
  </record>

  <record type="user">
    <uid>__cdaboo__</uid>
    <guid>7D45CB10-479E-456B-B54D-528958C5734B</guid>
    <short-name>cdaboo</short-name>
    <full-name>Cyrus Daboo</full-name>
    <password>suryc</password>
    <email>cdaboo@bitbucket.calendarserver.org</email>
  </record>

  <record type="user">
    <uid>__dre__</uid>
    <guid>CFC88493-DBFF-42B9-ADC7-9B3DA0B0769B</guid>
    <short-name>dre</short-name>
    <full-name>Andre LaBranche</full-name>
    <password>erd</password>
    <email>dre@bitbucket.calendarserver.org</email>
    <email>shared@example.com</email>
  </record>

  <record type="group">
    <uid>__top_group_1__</uid>
    <guid>49B350C6-9611-477B-94D9-5516B13856AB</guid>
    <short-name>top-group-1</short-name>
    <full-name>Top Group 1</full-name>
    <email>topgroup1@example.com</email>
    <member-uid>__wsanchez__</member-uid>
    <member-uid>__glyph__</member-uid>
    <member-uid>__sub_group_1__</member-uid>
  </record>

  <record type="group">
    <uid>__sub_group_1__</uid>
    <guid>86144F73-345A-4097-82F1-B782672087C7</guid>
    <short-name>sub-group-1</short-name>
    <full-name>Sub Group 1</full-name>
    <email>subgroup1@example.com</email>
    <member-uid>__sagen__</member-uid>
    <member-uid>__cdaboo__</member-uid>
  </record>

</directory>
"""



from twisted.trial import unittest
from twistedcaldav.config import config
from twistedcaldav.ical import Component, normalize_iCalStr

from txdav.caldav.datastore.test.util import buildCalendarStore
from txdav.common.datastore.test.util import populateCalendarsFrom, \
    CommonCommonTests

import os
from calendarserver.tap.util import directoryFromConfig

class GroupAttendeeReconciliation(CommonCommonTests, unittest.TestCase):
    """
    CalendarObject splitting tests
    """

    @inlineCallbacks
    def setUp(self):
        config.Scheduling.Options.AllowGroupAsAttendee = True

        yield super(GroupAttendeeReconciliation, self).setUp()
        self.patch(config.DirectoryService.params, "xmlFile",
            os.path.join(
                os.path.dirname(__file__), "accounts", "accounts.xml"
            )
        )
        self.patch(config.ResourceService.params, "xmlFile",
            os.path.join(
                os.path.dirname(__file__), "accounts", "resources.xml"
            )
        )
        self._sqlCalendarStore = yield buildCalendarStore(self, self.notifierFactory, directoryFromConfig(config))
        yield self.populate()

        self.paths = {}


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlCalendarStore


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()

    requirements = {
        "user01" : {
            "calendar" : {}
        },
    }

    @inlineCallbacks
    def test_groupAttendeeReconciliation(self):
        """
        Test that (manual) splitting of calendar objects works.
        """
        calendar = yield self.calendarUnderTest(name="calendar", home="user01")

        data_put = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VTIMEZONE
LAST-MODIFIED:20040110T032845Z
TZID:US/Eastern
BEGIN:DAYLIGHT
DTSTART:20000404T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20001026T020000
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ORGANIZER:MAILTO:user01@example.com
ATTENDEE:mailto:user01@example.com
ATTENDEE:mailto:user02@example.com
ATTENDEE:MAILTO:group01@example.com
END:VEVENT
END:VCALENDAR"""

        data_get = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
BEGIN:VEVENT
UID:event1@ninevah.local
DTSTART;TZID=US/Eastern:20140101T100000
DURATION:PT1H
ATTENDEE;CN=User 01;EMAIL=user01@example.com;RSVP=TRUE:urn:uuid:user01
ATTENDEE;CN=User 02;EMAIL=user02@example.com;RSVP=TRUE;SCHEDULE-STATUS=1.2:urn:uuid:user02
ATTENDEE;CN=Group 01;EMAIL=group01@example.com;RSVP=TRUE;SCHEDULE-STATUS=3.7:urn:uuid:group01
CREATED:20060101T150000Z
ORGANIZER;CN=User 01;EMAIL=user01@example.com:urn:uuid:user01
SUMMARY:event 1
END:VEVENT
END:VCALENDAR
"""

        vcalendar = Component.fromString(data_put)
        cobj = yield calendar.createCalendarObjectWithName("data1.ics", vcalendar)
        self.assertFalse(hasattr(cobj, "_workItems"))
        yield self.commit()

        cobj = yield self.calendarObjectUnderTest(name="data1.ics", calendar_name="calendar", home="user01")
        vcalendar = yield cobj.component()
        print("normalize_iCalStr(vcalendar)=%s" % (normalize_iCalStr(vcalendar),))
        print("normalize_iCalStr(data_get)=%s" % (normalize_iCalStr(data_get),))
        self.assertEqual(normalize_iCalStr(vcalendar), normalize_iCalStr(data_get))
