##
# Copyright (c) 2005-2015 Apple Inc. All rights reserved.
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



from twisted.internet.defer import inlineCallbacks
from calendarserver.tools.resources import migrateResources
from twistedcaldav.test.util import StoreTestCase
from txdav.who.test.support import InMemoryDirectoryService
from twext.who.directory import DirectoryRecord
from txdav.who.idirectory import RecordType as CalRecordType
from txdav.who.directory import CalendarDirectoryRecordMixin


class TestRecord(DirectoryRecord, CalendarDirectoryRecordMixin):
    pass



class MigrateResourcesTest(StoreTestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(MigrateResourcesTest, self).setUp()
        self.store = self.storeUnderTest()

        self.sourceService = InMemoryDirectoryService(None)
        fieldName = self.sourceService.fieldName
        records = (
            TestRecord(
                self.sourceService,
                {
                    fieldName.uid: u"location1",
                    fieldName.shortNames: (u"loc1",),
                    fieldName.recordType: CalRecordType.location,
                }
            ),
            TestRecord(
                self.sourceService,
                {
                    fieldName.uid: u"location2",
                    fieldName.shortNames: (u"loc2",),
                    fieldName.recordType: CalRecordType.location,
                }
            ),
            TestRecord(
                self.sourceService,
                {
                    fieldName.uid: u"resource1",
                    fieldName.shortNames: (u"res1",),
                    fieldName.recordType: CalRecordType.resource,
                }
            ),
        )
        yield self.sourceService.updateRecords(records, create=True)


    @inlineCallbacks
    def test_migrateResources(self):

        # Record location1 has not been migrated
        record = yield self.directory.recordWithUID(u"location1")
        self.assertEquals(record, None)

        # Migrate location1, location2, and resource1
        yield migrateResources(self.sourceService, self.directory)
        record = yield self.directory.recordWithUID(u"location1")
        self.assertEquals(record.uid, u"location1")
        self.assertEquals(record.shortNames[0], u"loc1")
        record = yield self.directory.recordWithUID(u"location2")
        self.assertEquals(record.uid, u"location2")
        self.assertEquals(record.shortNames[0], u"loc2")
        record = yield self.directory.recordWithUID(u"resource1")
        self.assertEquals(record.uid, u"resource1")
        self.assertEquals(record.shortNames[0], u"res1")

        # Add a new location to the sourceService, and modify an existing
        # location
        fieldName = self.sourceService.fieldName
        newRecords = (
            TestRecord(
                self.sourceService,
                {
                    fieldName.uid: u"location1",
                    fieldName.shortNames: (u"newloc1",),
                    fieldName.recordType: CalRecordType.location,
                }
            ),
            TestRecord(
                self.sourceService,
                {
                    fieldName.uid: u"location3",
                    fieldName.shortNames: (u"loc3",),
                    fieldName.recordType: CalRecordType.location,
                }
            ),
        )
        yield self.sourceService.updateRecords(newRecords, create=True)

        yield migrateResources(self.sourceService, self.directory)

        # Ensure an existing record does not get migrated again; verified by
        # seeing if shortNames changed, which they should not:
        record = yield self.directory.recordWithUID(u"location1")
        self.assertEquals(record.uid, u"location1")
        self.assertEquals(record.shortNames[0], u"loc1")

        # Ensure new record does get migrated
        record = yield self.directory.recordWithUID(u"location3")
        self.assertEquals(record.uid, u"location3")
        self.assertEquals(record.shortNames[0], u"loc3")
