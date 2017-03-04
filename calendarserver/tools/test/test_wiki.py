##
# Copyright (c) 2005-2017 Apple Inc. All rights reserved.
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
from calendarserver.tools.wiki import migrateWiki
from twistedcaldav.test.util import StoreTestCase
from txdav.who.wiki import DirectoryService as WikiDirectoryService
from txdav.who.idirectory import RecordType as CalRecordType


class MigrateWikiTest(StoreTestCase):

    def configure(self):
        super(MigrateWikiTest, self).configure()
        self.patch(self.config.Authentication.Wiki, "Enabled", False)

    @inlineCallbacks
    def test_migrateWiki(self):

        # Ensure the two records do not exist yet
        record = yield self.directory.recordWithUID(u"wiki-xyzzy")
        self.assertEquals(record, None)
        record = yield self.directory.recordWithUID(u"wiki-plugh")
        self.assertEquals(record, None)

        # We need to create the calendar homes, but we can't unless there are
        # records for these uids.  Since we've disabled the wiki service above,
        # we're temporarily going to substitute a wiki directory service while
        # we create the calendar homes:
        realDirectory = self.store.directoryService()
        tmpWikiService = WikiDirectoryService("test", None)
        tmpWikiService.serversDB = lambda : None
        self.store._directoryService = tmpWikiService
        txn = self.store.newTransaction()
        yield txn.calendarHomeWithUID(u"wiki-xyzzy", create=True)
        yield txn.calendarHomeWithUID(u"wiki-plugh", create=True)
        yield txn.commit()
        self.store._directoryService = realDirectory

        # Migrate wiki principals to resources
        yield migrateWiki(self.store)

        record = yield self.directory.recordWithUID(u"wiki-xyzzy")
        self.assertEquals(record.shortNames, [u"xyzzy"])
        self.assertEquals(record.recordType, CalRecordType.resource)
        record = yield self.directory.recordWithUID(u"wiki-plugh")
        self.assertEquals(record.shortNames, [u"plugh"])
        self.assertEquals(record.recordType, CalRecordType.resource)
