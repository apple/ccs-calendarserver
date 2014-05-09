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
txdav.who.util tests
"""

import os

from txdav.who.util import directoryFromConfig
from txdav.who.test.support import InMemoryDirectoryService
from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase
from twistedcaldav.config import ConfigDict
from twisted.python.filepath import FilePath
from txdav.who.augment import AugmentedDirectoryService
from twext.who.aggregate import DirectoryService as AggregateDirectoryService
from twext.who.xml import DirectoryService as XMLDirectoryService
from txdav.who.delegates import (
    DirectoryService as DelegateDirectoryService,
    RecordType as DelegateRecordType
)
from twext.who.directory import DirectoryRecord
from twext.who.idirectory import RecordType, NoSuchRecordError
from txdav.who.idirectory import RecordType as CalRecordType
from txdav.who.wiki import (
    DirectoryService as WikiDirectoryService,
    RecordType as WikiRecordType,
)


class StubStore(object):
    pass



class UtilTest(TestCase):

    def setUp(self):
        sourceDir = FilePath(__file__).parent().child("accounts")
        self.serverRoot = os.path.abspath(self.mktemp())
        os.mkdir(self.serverRoot)
        self.dataRoot = os.path.join(self.serverRoot, "data")
        if not os.path.exists(self.dataRoot):
            os.makedirs(self.dataRoot)
        destDir = FilePath(self.dataRoot)

        accounts = destDir.child("accounts.xml")
        sourceAccounts = sourceDir.child("accounts.xml")
        accounts.setContent(sourceAccounts.getContent())

        resources = destDir.child("resources.xml")
        sourceResources = sourceDir.child("resources.xml")
        resources.setContent(sourceResources.getContent())

        augments = destDir.child("augments.xml")
        sourceAugments = sourceDir.child("augments.xml")
        augments.setContent(sourceAugments.getContent())


    @inlineCallbacks
    def test_directoryFromConfig(self):

        config = ConfigDict(
            {
                "DataRoot": self.dataRoot,
                "Authentication": {
                    "Wiki": {
                        "Enabled": True,
                        "CollabHost": "localhost",
                        "CollabPort": 4444,
                    },
                },
                "DirectoryService": {
                    "Enabled": True,
                    "type": "XML",
                    "params": {
                        "xmlFile": "accounts.xml",
                        "recordTypes": ["users", "groups"],
                    },
                },
                "ResourceService": {
                    "Enabled": True,
                    "type": "XML",
                    "params": {
                        "xmlFile": "resources.xml",
                        "recordTypes": ["locations", "resources", "addresses"],
                    },
                },
                "AugmentService": {
                    "Enabled": True,
                    # FIXME: This still uses an actual class name:
                    "type": "twistedcaldav.directory.augment.AugmentXMLDB",
                    "params": {
                        "xmlFiles": ["augments.xml"],
                    },
                },
            }
        )

        store = StubStore()
        service = directoryFromConfig(config, store=store)

        # Inspect the directory service structure
        self.assertTrue(isinstance(service, AugmentedDirectoryService))
        self.assertTrue(isinstance(service._directory, AggregateDirectoryService))
        self.assertEquals(len(service._directory.services), 4)
        self.assertTrue(
            isinstance(service._directory.services[0], XMLDirectoryService)
        )
        self.assertEquals(
            set(service._directory.services[0].recordTypes()),
            set([RecordType.user, RecordType.group])
        )
        self.assertTrue(
            isinstance(service._directory.services[1], XMLDirectoryService)
        )
        self.assertEquals(
            set(service._directory.services[1].recordTypes()),
            set(
                [
                    CalRecordType.location,
                    CalRecordType.resource,
                    CalRecordType.address
                ]
            )
        )
        self.assertTrue(
            isinstance(service._directory.services[2], DelegateDirectoryService)
        )
        self.assertEquals(
            set(service._directory.services[2].recordTypes()),
            set(
                [
                    DelegateRecordType.readDelegateGroup,
                    DelegateRecordType.writeDelegateGroup,
                    DelegateRecordType.readDelegatorGroup,
                    DelegateRecordType.writeDelegatorGroup,
                ]
            )
        )
        self.assertTrue(
            isinstance(service._directory.services[3], WikiDirectoryService)
        )
        self.assertEquals(
            set(service._directory.services[3].recordTypes()),
            set([WikiRecordType.macOSXServerWiki])
        )

        # And make sure it's functional:
        record = yield service.recordWithUID("group07")
        self.assertEquals(record.fullNames, [u'Group 07'])



class IndexDirectoryServiceTest(TestCase):

    @inlineCallbacks
    def test_updateRecords(self):
        service = InMemoryDirectoryService(u"xyzzy")

        # Record does not exist
        record = yield service.recordWithUID(u"foo")
        self.assertEquals(None, record)

        records = (
            DirectoryRecord(
                service,
                {
                    service.fieldName.uid: u"foo",
                    service.fieldName.shortNames: (u"foo1", u"foo2"),
                    service.fieldName.recordType: RecordType.user,
                }
            ),
        )
        try:
            # Trying to update a record when it does not exist should fail
            yield service.updateRecords(records, create=False)
        except NoSuchRecordError:
            pass
        except:
            self.fail("Did not raise NoSuchRecordError when create=False and record does not exist")

        record = yield service.recordWithUID(u"foo")
        self.assertEquals(None, record)

        # Create the record
        yield service.updateRecords(records, create=True)

        record = yield service.recordWithUID(u"foo")
        self.assertEquals(record.uid, u"foo")

        records = yield service.recordsWithRecordType(RecordType.user)
        self.assertEquals(len(records), 1)
        self.assertEquals(list(records)[0].uid, u"foo")

        record = yield service.recordWithShortName(RecordType.user, u"foo1")
        self.assertEquals(record.uid, u"foo")
        record = yield service.recordWithShortName(RecordType.user, u"foo2")
        self.assertEquals(record.uid, u"foo")

        records = (
            DirectoryRecord(
                service,
                {
                    service.fieldName.uid: u"foo",
                    service.fieldName.shortNames: (u"foo3", u"foo4"),
                    service.fieldName.recordType: RecordType.group,
                }
            ),
            DirectoryRecord(
                service,
                {
                    service.fieldName.uid: u"bar",
                    service.fieldName.shortNames: (u"bar1", u"bar2"),
                    service.fieldName.recordType: RecordType.user,
                }
            ),
        )

        # Update the existing record and create a new one
        yield service.updateRecords(records, create=True)

        record = yield service.recordWithUID(u"foo")
        self.assertEquals(record.uid, u"foo")
        self.assertEquals(set(record.shortNames), set((u'foo3', u'foo4')))

        records = yield service.recordsWithRecordType(RecordType.group)
        self.assertEquals(len(records), 1)
        self.assertEquals(list(records)[0].uid, u"foo")

        records = yield service.recordsWithRecordType(RecordType.user)
        self.assertEquals(len(records), 1)
        self.assertEquals(list(records)[0].uid, u"bar")

        record = yield service.recordWithShortName(RecordType.group, u"foo3")
        self.assertEquals(record.uid, u"foo")
        record = yield service.recordWithShortName(RecordType.group, u"foo4")
        self.assertEquals(record.uid, u"foo")

        # Remove a record
        yield service.removeRecords((u"foo",))
        record = yield service.recordWithUID(u"foo")
        self.assertEquals(None, record)
