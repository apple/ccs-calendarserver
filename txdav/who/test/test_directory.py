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
                FieldName.uid: u"uid",
                FieldName.shortNames: [u"name"],
                FieldName.recordType: RecordType.user,
            }
        )
        self.assertEquals(
            record.canonicalCalendarUserAddress(),
            u"/principals/__uids__/uid/"
        )


        record = TestDirectoryRecord(
            self.directory,
            {
                FieldName.uid: u"uid",
                FieldName.shortNames: [u"name"],
                FieldName.emailAddresses: [u"test@example.com"],
                FieldName.recordType: RecordType.user,
            }
        )
        self.assertEquals(
            record.canonicalCalendarUserAddress(),
            u"mailto:test@example.com"
        )


        record = TestDirectoryRecord(
            self.directory,
            {
                FieldName.uid: u"uid",
                FieldName.guid: UUID("E2F6C57F-BB15-4EF9-B0AC-47A7578386F1"),
                FieldName.shortNames: [u"name"],
                FieldName.emailAddresses: [u"test@example.com"],
                FieldName.recordType: RecordType.user,
            }
        )
        self.assertEquals(
            record.canonicalCalendarUserAddress(),
            u"urn:uuid:E2F6C57F-BB15-4EF9-B0AC-47A7578386F1"
        )
