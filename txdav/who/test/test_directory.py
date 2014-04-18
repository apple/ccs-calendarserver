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
Directory tests
"""

from twisted.internet.defer import inlineCallbacks
from twistedcaldav.test.util import StoreTestCase
from twext.who.directory import DirectoryRecord
from twext.who.idirectory import FieldName, RecordType
from txdav.who.directory import CalendarDirectoryRecordMixin
from uuid import UUID
from twext.who.expression import (
    MatchType, MatchFlags, MatchExpression
)



class TestDirectoryRecord(DirectoryRecord, CalendarDirectoryRecordMixin):
    pass



class DirectoryTestCase(StoreTestCase):

    @inlineCallbacks
    def test_expandedMembers(self):

        record = yield self.directory.recordWithUID(u"both_coasts")

        direct = yield record.members()
        self.assertEquals(
            set([u"left_coast", u"right_coast"]),
            set([r.uid for r in direct])
        )

        expanded = yield record.expandedMembers()
        self.assertEquals(
            set([u"Chris Lecroy", u"Cyrus Daboo", u"David Reid", u"Wilfredo Sanchez"]),
            set([r.displayName for r in expanded])
        )


    def test_canonicalCalendarUserAddress(self):

        record = TestDirectoryRecord(
            self.directory,
            {
                FieldName.uid: u"test",
                FieldName.shortNames: [u"name"],
                FieldName.recordType: RecordType.user,
            }
        )
        self.assertEquals(
            record.canonicalCalendarUserAddress(),
            u"urn:x-uid:test"
        )

        # Even with email address, canonical still remains urn:x-uid:

        record = TestDirectoryRecord(
            self.directory,
            {
                FieldName.uid: u"test",
                FieldName.shortNames: [u"name"],
                FieldName.emailAddresses: [u"test@example.com"],
                FieldName.recordType: RecordType.user,
            }
        )
        self.assertEquals(
            record.canonicalCalendarUserAddress(),
            u"urn:x-uid:test"
        )


    def test_calendarUserAddresses(self):
        """
        Verify the right CUAs are advertised, which no longer includes the
        /principals/ flavors (although those are still recognized by
        recordWithCalendarUserAddress( ) for backwards compatibility).
        """

        record = TestDirectoryRecord(
            self.directory,
            {
                FieldName.uid: u"test",
                FieldName.guid: UUID("E2F6C57F-BB15-4EF9-B0AC-47A7578386F1"),
                FieldName.shortNames: [u"name1", u"name2"],
                FieldName.emailAddresses: [u"test@example.com", u"another@example.com"],
                FieldName.recordType: RecordType.user,
            }
        )
        self.assertEquals(
            record.calendarUserAddresses,
            frozenset(
                [
                    u"urn:x-uid:test",
                    u"urn:uuid:E2F6C57F-BB15-4EF9-B0AC-47A7578386F1",
                    u"mailto:test@example.com",
                    u"mailto:another@example.com",
                ]
            )
        )

        record = TestDirectoryRecord(
            self.directory,
            {
                FieldName.uid: u"test",
                FieldName.shortNames: [u"name1", u"name2"],
                FieldName.recordType: RecordType.user,
            }
        )
        self.assertEquals(
            record.calendarUserAddresses,
            frozenset(
                [
                    u"urn:x-uid:test",
                ]
            )
        )


    @inlineCallbacks
    def test_recordsFromMatchExpression(self):
        expression = MatchExpression(
            FieldName.uid,
            u"6423F94A-6B76-4A3A-815B-D52CFD77935D",
            MatchType.equals,
            MatchFlags.none
        )
        records = yield self.directory.recordsFromExpression(expression)
        self.assertEquals(len(records), 1)


    @inlineCallbacks
    def test_recordsFromMatchExpressionNonUnicode(self):
        expression = MatchExpression(
            FieldName.guid,
            UUID("6423F94A-6B76-4A3A-815B-D52CFD77935D"),
            MatchType.equals,
            MatchFlags.caseInsensitive
        )
        records = yield self.directory.recordsFromExpression(expression)
        self.assertEquals(len(records), 1)


    @inlineCallbacks
    def test_recordWithCalendarUserAddress(self):
        """
        Make sure various CUA forms are recognized and hasCalendars is honored.
        Note: /principals/ CUAs are recognized but not advertised anymore; see
        record.calendarUserAddresses.
        """

        # hasCalendars
        record = yield self.directory.recordWithCalendarUserAddress(
            u"mailto:wsanchez@example.com"
        )
        self.assertNotEquals(record, None)
        self.assertEquals(record.uid, u"6423F94A-6B76-4A3A-815B-D52CFD77935D")

        record = yield self.directory.recordWithCalendarUserAddress(
            u"urn:x-uid:6423F94A-6B76-4A3A-815B-D52CFD77935D"
        )
        self.assertNotEquals(record, None)
        self.assertEquals(record.uid, u"6423F94A-6B76-4A3A-815B-D52CFD77935D")

        record = yield self.directory.recordWithCalendarUserAddress(
            u"urn:uuid:6423F94A-6B76-4A3A-815B-D52CFD77935D"
        )
        self.assertNotEquals(record, None)
        self.assertEquals(record.uid, u"6423F94A-6B76-4A3A-815B-D52CFD77935D")

        record = yield self.directory.recordWithCalendarUserAddress(
            u"/principals/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D"
        )
        self.assertNotEquals(record, None)
        self.assertEquals(record.uid, u"6423F94A-6B76-4A3A-815B-D52CFD77935D")

        record = yield self.directory.recordWithCalendarUserAddress(
            u"/principals/users/wsanchez"
        )
        self.assertNotEquals(record, None)
        self.assertEquals(record.uid, u"6423F94A-6B76-4A3A-815B-D52CFD77935D")

        # no hasCalendars
        record = yield self.directory.recordWithCalendarUserAddress(
            u"mailto:nocalendar@example.com"
        )
        self.assertEquals(record, None)
