#
# Copyright (c) 2009-2010 Apple Inc. All rights reserved.
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

from uuid import uuid4

from twistedcaldav.directory.cachingdirectory import CachingDirectoryService
from twistedcaldav.directory.cachingdirectory import CachingDirectoryRecord
from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.directory.util import uuidFromName
from twistedcaldav.directory.augment import AugmentRecord
from twistedcaldav.test.util import TestCase


class TestDirectoryService (CachingDirectoryService):

    realmName = "Dummy Realm"

    def recordTypes(self):
        return (
            DirectoryService.recordType_users,
            DirectoryService.recordType_groups,
            DirectoryService.recordType_locations,
            DirectoryService.recordType_resources,
        )

    def queryDirectory(self, recordTypes, indexType, indexKey):
        
        self.queried = True

        for recordType in recordTypes:
            for record in self.fakerecords[recordType]:
                cacheIt = False
                if indexType in (
                    CachingDirectoryService.INDEX_TYPE_SHORTNAME,
                    CachingDirectoryService.INDEX_TYPE_CUA,
                    CachingDirectoryService.INDEX_TYPE_AUTHID,
                ):
                    if indexKey in record[indexType]:
                        cacheIt = True
                else:
                    if indexKey == record[indexType]:
                        cacheIt = True

                if cacheIt:
                    cacheRecord = CachingDirectoryRecord(
                        service               = self,
                        recordType            = recordType,
                        guid                  = record.get("guid"),
                        shortNames            = record.get("shortname"),
                        authIDs               = record.get("authid"),
                        fullName              = record.get("fullName"),
                        firstName             = "",
                        lastName              = "",
                        emailAddresses        = record.get("email"),
                    ) 
                    
                    augmentRecord = AugmentRecord(
                        uid = cacheRecord.guid,
                        enabled=True,
                        enabledForCalendaring = True,
                    )
                    
                    cacheRecord.addAugmentInformation(augmentRecord)

                    self.recordCacheForType(recordType).addRecord(cacheRecord,
                        indexType, indexKey)

class CachingDirectoryTest(TestCase):
    
    baseGUID = str(uuid4())

    def setUp(self):
        super(CachingDirectoryTest, self).setUp()
        self.service = TestDirectoryService()
        self.service.queried = False

    def loadRecords(self, records):
        self.service._initCaches()
        self.service.fakerecords = records
        self.service.queried = False

    def fakeRecord(
        self,
        fullName,
        shortNames=None,
        guid=None,
        emails=None,
        members=None,
        resourceInfo=None,
        multinames=False
    ):
        if shortNames is None:
            shortNames = (self.shortNameForFullName(fullName),)
            if multinames:
                shortNames += (fullName,)
    
        if guid is None:
            guid = self.guidForShortName(shortNames[0])
        else:
            guid = guid.lower()
    
        if emails is None:
            emails = ("%s@example.com" % (shortNames[0],),)
    
        attrs = {
            "fullName": fullName,
            "guid": guid,
            "shortname": shortNames,
            "email": emails,
            "cua": tuple(["mailto:%s" % email for email in emails]),
            "authid": tuple(["Kerberos:%s" % email for email in emails])
        }
        
        if members:
            attrs["members"] = members
    
        if resourceInfo:
            attrs["resourceInfo"] = resourceInfo
    
        return attrs
    
    def shortNameForFullName(self, fullName):
        return fullName.lower().replace(" ", "")
    
    def guidForShortName(self, shortName):
        return uuidFromName(self.baseGUID, shortName)

    def dummyRecords(self):
        SIZE = 10
        self.loadRecords({
            DirectoryService.recordType_users: [
                self.fakeRecord("User %02d" % x, multinames=(x>5)) for x in range(1,SIZE+1)
            ],
            DirectoryService.recordType_groups: [
                self.fakeRecord("Group %02d" % x) for x in range(1,SIZE+1)
            ],
            DirectoryService.recordType_resources: [
                self.fakeRecord("Resource %02d" % x) for x in range(1,SIZE+1)
            ],
            DirectoryService.recordType_locations: [
                self.fakeRecord("Location %02d" % x) for x in range(1,SIZE+1)
            ],
        })

    def verifyRecords(self, recordType, expectedGUIDs):
        
        records = self.service.listRecords(recordType)
        recordGUIDs = set([record.guid for record in records])
        self.assertEqual(recordGUIDs, expectedGUIDs)

class GUIDLookups(CachingDirectoryTest):
    
    def test_emptylist(self):
        self.dummyRecords()

        self.verifyRecords(DirectoryService.recordType_users, set())
        self.verifyRecords(DirectoryService.recordType_groups, set())
        self.verifyRecords(DirectoryService.recordType_resources, set())
        self.verifyRecords(DirectoryService.recordType_locations, set())
    
    def test_cacheoneguid(self):
        self.dummyRecords()

        self.assertTrue(self.service.recordWithGUID(self.guidForShortName("user01")) is not None)
        self.assertTrue(self.service.queried)
        self.verifyRecords(DirectoryService.recordType_users, set((
            self.guidForShortName("user01"),
        )))
        self.verifyRecords(DirectoryService.recordType_groups, set())
        self.verifyRecords(DirectoryService.recordType_resources, set())
        self.verifyRecords(DirectoryService.recordType_locations, set())

        # Make sure it really is cached and won't cause another query
        self.service.queried = False
        self.assertTrue(self.service.recordWithGUID(self.guidForShortName("user01")) is not None)
        self.assertFalse(self.service.queried)

        # Make sure guid is case-insensitive
        self.assertTrue(self.service.recordWithGUID(self.guidForShortName("user01").lower()) is not None)
        
    def test_cacheoneshortname(self):
        self.dummyRecords()

        self.assertTrue(self.service.recordWithShortName(
            DirectoryService.recordType_users,
            "user02"
        ) is not None)
        self.assertTrue(self.service.queried)
        self.verifyRecords(DirectoryService.recordType_users, set((
            self.guidForShortName("user02"),
        )))
        self.verifyRecords(DirectoryService.recordType_groups, set())
        self.verifyRecords(DirectoryService.recordType_resources, set())
        self.verifyRecords(DirectoryService.recordType_locations, set())

        # Make sure it really is cached and won't cause another query
        self.service.queried = False
        self.assertTrue(self.service.recordWithShortName(
            DirectoryService.recordType_users,
            "user02"
        ) is not None)
        self.assertFalse(self.service.queried)

    def test_cacheoneemail(self):
        self.dummyRecords()

        self.assertTrue(self.service.recordWithCalendarUserAddress(
            "mailto:user03@example.com"
        ) is not None)
        self.assertTrue(self.service.queried)
        self.verifyRecords(DirectoryService.recordType_users, set((
            self.guidForShortName("user03"),
        )))
        self.verifyRecords(DirectoryService.recordType_groups, set())
        self.verifyRecords(DirectoryService.recordType_resources, set())
        self.verifyRecords(DirectoryService.recordType_locations, set())

        # Make sure it really is cached and won't cause another query
        self.service.queried = False
        self.assertTrue(self.service.recordWithCalendarUserAddress(
            "mailto:user03@example.com"
        ) is not None)
        self.assertFalse(self.service.queried)

    def test_cacheoneauthid(self):
        self.dummyRecords()

        self.assertTrue(self.service.recordWithAuthID(
            "Kerberos:user03@example.com"
        ) is not None)
        self.assertTrue(self.service.queried)
        self.verifyRecords(DirectoryService.recordType_users, set((
            self.guidForShortName("user03"),
        )))
        self.verifyRecords(DirectoryService.recordType_groups, set())
        self.verifyRecords(DirectoryService.recordType_resources, set())
        self.verifyRecords(DirectoryService.recordType_locations, set())

        # Make sure it really is cached and won't cause another query
        self.service.queried = False
        self.assertTrue(self.service.recordWithAuthID(
            "Kerberos:user03@example.com"
        ) is not None)
        self.assertFalse(self.service.queried)

    def test_negativeCaching(self):
        self.dummyRecords()

        # If negativeCaching is off, each miss will result in a call to
        # queryDirectory( )
        self.service.negativeCaching = False

        self.service.queried = False
        self.assertEquals(self.service.recordWithGUID(self.guidForShortName("missing")), None)
        self.assertTrue(self.service.queried)

        self.service.queried = False
        self.assertEquals(self.service.recordWithGUID(self.guidForShortName("missing")), None)
        self.assertTrue(self.service.queried)


        # However, if negativeCaching is on, a miss is recorded as such,
        # preventing a similar queryDirectory( ) until cacheTimeout passes
        self.service.negativeCaching = True

        self.service.queried = False
        self.assertEquals(self.service.recordWithGUID(self.guidForShortName("missing")), None)
        self.assertTrue(self.service.queried)

        self.service.queried = False
        self.assertEquals(self.service.recordWithGUID(self.guidForShortName("missing")), None)
        self.assertFalse(self.service.queried)

        # Simulate time passing by clearing the negative timestamp for this
        # entry, then try again, this time queryDirectory( ) is called
        self.service._disabledKeys[self.service.INDEX_TYPE_GUID][self.guidForShortName("missing")] = 0

        self.service.queried = False
        self.assertEquals(self.service.recordWithGUID(self.guidForShortName("missing")), None)
        self.assertTrue(self.service.queried)
