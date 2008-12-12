##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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
from twistedcaldav.test.util import TestCase

try:
    from twistedcaldav.directory.appleopendirectory import OpenDirectoryService as RealOpenDirectoryService
    import dsattributes
except ImportError:
    pass
else:
    from twistedcaldav.directory.directory import DirectoryService
    from twistedcaldav.directory.util import uuidFromName

    class OpenDirectoryService (RealOpenDirectoryService):
        def _queryDirectory(self, recordType, shortName=None, guid=None):
            if shortName is None and guid is None:
                return self.fakerecords[recordType]

            assert shortName is None or guid is None
            if guid is not None:
                guid = guid.lower()

            records = []

            for name, record in self.fakerecords[recordType]:
                if name == shortName or record[dsattributes.kDS1AttrGeneratedUID] == guid:
                    records.append((name, record))

            return tuple(records)
    
    class ReloadCache(TestCase):
        def setUp(self):
            super(ReloadCache, self).setUp()
            self.service = OpenDirectoryService(node="/Search", dosetup=False)
            
        def tearDown(self):
            for call in self.service._delayedCalls:
                call.cancel()

        def loadRecords(self, records):
            self.service.fakerecords = records

            for recordType in self.service.recordTypes():
                if recordType not in records:
                    self.service.fakerecords[recordType] = []
                self.service.reloadCache(recordType)

        def verifyRecords(self, recordType, expected):
            expected = set(expected)
            found = set(self.service._records[recordType]["records"].keys())
            
            missing = expected.difference(found)
            extras = found.difference(expected)

            self.assertTrue(len(missing) == 0, msg="Directory records not found: %s" % (missing,))
            self.assertTrue(len(extras) == 0, msg="Directory records not expected: %s" % (extras,))
                
        def verifyRecordsCheckEnabled(self, recordType, expected, enabled):
            expected = set(expected)
            found = set([item for item in self.service._records[recordType]["records"].iterkeys()
                         if self.service._records[recordType]["records"][item].enabledForCalendaring == enabled])
            
            missing = expected.difference(found)
            extras = found.difference(expected)

            self.assertTrue(len(missing) == 0, msg="Directory records not found: %s" % (missing,))
            self.assertTrue(len(extras) == 0, msg="Directory records not expected: %s" % (extras,))
                
        def verifyDisabledRecords(self, recordType, expectedNames, expectedGUIDs):
            def check(disabledType, expected):
                expected = set(expected)
                found = self.service._records[recordType][disabledType]
            
                missing = expected.difference(found)
                extras = found.difference(expected)

                self.assertTrue(len(missing) == 0, msg="Disabled directory records not found: %s" % (missing,))
                self.assertTrue(len(extras) == 0, msg="Disabled directory records not expected: %s" % (extras,))

            check("disabled names", expectedNames)
            check("disabled guids", (guid.lower() for guid in expectedGUIDs))

        def test_restrictionGroupName(self):
            service = OpenDirectoryService(
                node="/Search",
                restrictEnabledRecords=True,
                restrictToGroup="group_name",
                dosetup=False)
            self.assertTrue(service.restrictEnabledRecords)
            self.assertEqual(service.restrictToGroup, "group_name")
            self.assertFalse(service.restrictToGUID)

        def test_restrictionGroupGUID(self):
            guid = str(uuid4())
            service = OpenDirectoryService(
                node="/Search",
                restrictEnabledRecords=True,
                restrictToGroup=guid,
                dosetup=False)
            self.assertTrue(service.restrictEnabledRecords)
            self.assertEqual(service.restrictToGroup, guid)
            self.assertTrue(service.restrictToGUID)

        def test_normal(self):
            self.loadRecords({
                DirectoryService.recordType_users: [
                    fakeODRecord("User 01"),
                    fakeODRecord("User 02"),
                ],
                DirectoryService.recordType_groups: [
                    fakeODRecord("Group 01"),
                    fakeODRecord("Group 02"),
                ],
                DirectoryService.recordType_resources: [
                    fakeODRecord("Resource 01"),
                    fakeODRecord("Resource 02"),
                ],
                DirectoryService.recordType_locations: [
                    fakeODRecord("Location 01"),
                    fakeODRecord("Location 02"),
                ],
            })

            self.verifyRecords(DirectoryService.recordType_users, ("user01", "user02"))
            self.verifyDisabledRecords(DirectoryService.recordType_users, (), ())

            self.verifyRecords(DirectoryService.recordType_groups, ("group01", "group02"))
            self.verifyDisabledRecords(DirectoryService.recordType_groups, (), ())

            self.verifyRecords(DirectoryService.recordType_resources, ("resource01", "resource02"))
            self.verifyDisabledRecords(DirectoryService.recordType_resources, (), ())

            self.verifyRecords(DirectoryService.recordType_locations, ("location01", "location02"))
            self.verifyDisabledRecords(DirectoryService.recordType_locations, (), ())

        def test_normal_disabledusers(self):
            self.service.restrictEnabledRecords = True
            self.service.restrictToGroup = "restrictedaccess"

            self.service.fakerecords = {
                DirectoryService.recordType_users: [
                    fakeODRecord("User 01"),
                    fakeODRecord("User 02"),
                    fakeODRecord("User 03"),
                    fakeODRecord("User 04"),
                ],
                DirectoryService.recordType_groups: [
                    fakeODRecord("Group 01"),
                    fakeODRecord("Group 02"),
                    fakeODRecord("Group 03"),
                    fakeODRecord("Group 04"),
                ],
                DirectoryService.recordType_resources: [
                    fakeODRecord("Resource 01"),
                    fakeODRecord("Resource 02"),
                    fakeODRecord("Resource 03"),
                    fakeODRecord("Resource 04"),
                ],
                DirectoryService.recordType_locations: [
                    fakeODRecord("Location 01"),
                    fakeODRecord("Location 02"),
                    fakeODRecord("Location 03"),
                    fakeODRecord("Location 04"),
                ],
            }

            # Disable certain records
            self.service.restrictedGUIDs = set((
                self.service.fakerecords[DirectoryService.recordType_users][0][1][dsattributes.kDS1AttrGeneratedUID],
                self.service.fakerecords[DirectoryService.recordType_users][1][1][dsattributes.kDS1AttrGeneratedUID],
                self.service.fakerecords[DirectoryService.recordType_resources][0][1][dsattributes.kDS1AttrGeneratedUID],
                self.service.fakerecords[DirectoryService.recordType_resources][1][1][dsattributes.kDS1AttrGeneratedUID],
                self.service.fakerecords[DirectoryService.recordType_locations][0][1][dsattributes.kDS1AttrGeneratedUID],
                self.service.fakerecords[DirectoryService.recordType_locations][1][1][dsattributes.kDS1AttrGeneratedUID],
                self.service.fakerecords[DirectoryService.recordType_groups][0][1][dsattributes.kDS1AttrGeneratedUID],
                self.service.fakerecords[DirectoryService.recordType_groups][1][1][dsattributes.kDS1AttrGeneratedUID],
            ))

            self.service.reloadCache(DirectoryService.recordType_users)
            self.service.reloadCache(DirectoryService.recordType_groups)
            self.service.reloadCache(DirectoryService.recordType_resources)
            self.service.reloadCache(DirectoryService.recordType_locations)

            self.verifyRecordsCheckEnabled(DirectoryService.recordType_users, ("user01", "user02"), True)
            self.verifyRecordsCheckEnabled(DirectoryService.recordType_users, ("user03", "user04"), False)

            self.verifyRecordsCheckEnabled(DirectoryService.recordType_groups, ("group01", "group02"), True)
            self.verifyRecordsCheckEnabled(DirectoryService.recordType_groups, ("group03", "group04"), False)

            self.verifyRecordsCheckEnabled(DirectoryService.recordType_resources, ("resource01", "resource02"), True)
            self.verifyRecordsCheckEnabled(DirectoryService.recordType_resources, (), False)

            self.verifyRecordsCheckEnabled(DirectoryService.recordType_locations, ("location01", "location02"), True)
            self.verifyRecordsCheckEnabled(DirectoryService.recordType_locations, (), False)

        def test_normalCacheMiss(self):
            self.loadRecords({
                DirectoryService.recordType_users: [
                    fakeODRecord("User 01"),
                ],
            })

            self.verifyRecords(DirectoryService.recordType_users, ("user01",))
            self.verifyDisabledRecords(DirectoryService.recordType_users, (), ())

            self.service.fakerecords = {
                DirectoryService.recordType_users: [
                    fakeODRecord("User 01"),
                    fakeODRecord("User 02"),
                    fakeODRecord("User 03", guid="D10F3EE0-5014-41D3-8488-3819D3EF3B2A"),
                ],
            }

            self.service.reloadCache(DirectoryService.recordType_users, shortName="user02")
            self.service.reloadCache(DirectoryService.recordType_users, guid="D10F3EE0-5014-41D3-8488-3819D3EF3B2A")

            self.verifyRecords(DirectoryService.recordType_users, ("user01", "user02", "user03"))
            self.verifyDisabledRecords(DirectoryService.recordType_users, (), ())

        def test_noGUID(self):
            self.loadRecords({
                DirectoryService.recordType_users: [
                    fakeODRecord("User 01", guid=""),
                ],
            })

            self.verifyRecords(DirectoryService.recordType_users, ())

        def test_systemRecord(self):
            self.loadRecords({
                DirectoryService.recordType_users: [
                    fakeODRecord("root",   guid="FFFFEEEE-DDDD-CCCC-BBBB-AAAA00000000"),
                    fakeODRecord("daemon", guid="FFFFEEEE-DDDD-CCCC-BBBB-AAAA00000001"),
                    fakeODRecord("uucp",   guid="ffffeeee-dddd-cccc-bbbb-aaaa00000004"), # Try lowercase also
                    fakeODRecord("nobody", guid="ffffeeee-dddd-cccc-bbbb-aaaafffffffe"),
                ],
            })

            self.verifyRecords(DirectoryService.recordType_users, ())

        def test_duplicateEmail(self):
            self.loadRecords({
                DirectoryService.recordType_users: [
                    fakeODRecord("User 01"),
                    fakeODRecord("User 02", email="shared@example.com"),
                    fakeODRecord("User 03", email="shared@example.com"),
                ],
            })

            self.verifyRecords(DirectoryService.recordType_users, ("user01", "user02", "user03"))
            self.verifyDisabledRecords(DirectoryService.recordType_users, (), ())

            self.assertTrue (self.service.recordWithShortName(DirectoryService.recordType_users, "user01").emailAddresses)
            self.assertFalse(self.service.recordWithShortName(DirectoryService.recordType_users, "user02").emailAddresses)
            self.assertFalse(self.service.recordWithShortName(DirectoryService.recordType_users, "user03").emailAddresses)

        def test_duplicateRecords(self):
            self.loadRecords({
                DirectoryService.recordType_users: [
                    fakeODRecord("User 01"),
                    fakeODRecord("User 02"),
                    fakeODRecord("User 02"),
                ],
            })

            self.verifyRecords(DirectoryService.recordType_users, ("user01", "user02"))
            self.verifyDisabledRecords(DirectoryService.recordType_users, (), ())
            self.verifyDisabledRecords(DirectoryService.recordType_users, (), ())

        def test_duplicateName(self):
            self.loadRecords({
                DirectoryService.recordType_users: [
                    fakeODRecord("User 01"),
                    fakeODRecord("User 02", guid="A25775BB-1281-4606-98C6-2893B2D5CCD7"),
                    fakeODRecord("User 02", guid="30CA2BB9-C935-4A5D-80E2-79266BCB0255"),
                ],
            })

            self.verifyRecords(DirectoryService.recordType_users, ("user01",))
            self.verifyDisabledRecords(
                DirectoryService.recordType_users,
                ("user02",),
                ("A25775BB-1281-4606-98C6-2893B2D5CCD7", "30CA2BB9-C935-4A5D-80E2-79266BCB0255"),
            )

        def test_duplicateGUID(self):
            self.loadRecords({
                DirectoryService.recordType_users: [
                    fakeODRecord("User 01"),
                    fakeODRecord("User 02", guid="113D7F74-F84A-4F17-8C96-CE8F10D68EF8"),
                    fakeODRecord("User 03", guid="113D7F74-F84A-4F17-8C96-CE8F10D68EF8"),
                ],
            })

            self.verifyRecords(DirectoryService.recordType_users, ("user01",))
            self.verifyDisabledRecords(
                DirectoryService.recordType_users,
                ("user02", "user03"),
                ("113D7F74-F84A-4F17-8C96-CE8F10D68EF8",),
            )

        def test_duplicateCombo(self):
            self.loadRecords({
                DirectoryService.recordType_users: [
                    fakeODRecord("User 01"),
                    fakeODRecord("User 02", guid="113D7F74-F84A-4F17-8C96-CE8F10D68EF8"),
                    fakeODRecord("User 02", guid="113D7F74-F84A-4F17-8C96-CE8F10D68EF8", shortName="user03"),
                    fakeODRecord("User 02", guid="136E369F-DB40-4135-878D-B75D38242D39"),
                ],
            })

            self.verifyRecords(DirectoryService.recordType_users, ("user01",))
            self.verifyDisabledRecords(
                DirectoryService.recordType_users,
                ("user02", "user03"),
                ("113D7F74-F84A-4F17-8C96-CE8F10D68EF8", "136E369F-DB40-4135-878D-B75D38242D39"),
            )

        def test_duplicateGUIDCacheMiss(self):
            self.loadRecords({
                DirectoryService.recordType_users: [
                    fakeODRecord("User 01"),
                    fakeODRecord("User 02", guid="EDB9EE55-31F2-4EA9-B5FB-D8AE2A8BA35E"),
                    fakeODRecord("User 03", guid="D10F3EE0-5014-41D3-8488-3819D3EF3B2A"),
                ],
            })

            self.verifyRecords(DirectoryService.recordType_users, ("user01", "user02", "user03"))
            self.verifyDisabledRecords(DirectoryService.recordType_users, (), ())
            
            self.service.fakerecords = {
                DirectoryService.recordType_users: [
                    fakeODRecord("User 01"),
                    fakeODRecord("User 02", guid="EDB9EE55-31F2-4EA9-B5FB-D8AE2A8BA35E"),
                    fakeODRecord("User 02", guid="EDB9EE55-31F2-4EA9-B5FB-D8AE2A8BA35E", shortName="user04"),
                    fakeODRecord("User 03", guid="62368DDF-0C62-4C97-9A58-DE9FD46131A0"),
                    fakeODRecord("User 03", guid="62368DDF-0C62-4C97-9A58-DE9FD46131A0", shortName="user05"),
                ],
            }

            self.service.reloadCache(DirectoryService.recordType_users, shortName="user04")
            self.service.reloadCache(DirectoryService.recordType_users, guid="62368DDF-0C62-4C97-9A58-DE9FD46131A0")

            self.verifyRecords(DirectoryService.recordType_users, ("user01",))
            self.verifyDisabledRecords(
                DirectoryService.recordType_users,
                ("user02", "user03", "user04", "user05"),
                ("EDB9EE55-31F2-4EA9-B5FB-D8AE2A8BA35E", "62368DDF-0C62-4C97-9A58-DE9FD46131A0", "D10F3EE0-5014-41D3-8488-3819D3EF3B2A"),
            )

        def test_groupmembers(self):
            self.loadRecords({
                DirectoryService.recordType_users: [
                    fakeODRecord("User 01"),
                    fakeODRecord("User 02"),
                ],
                DirectoryService.recordType_groups: [
                    fakeODRecord("Group 01", members=[
                        guidForShortName("user01"),
                        guidForShortName("user02"),
                    ]),
                    fakeODRecord("Group 02", members=[
                        guidForShortName("resource01"),
                        guidForShortName("user02"),
                    ]),
                ],
                DirectoryService.recordType_resources: [
                    fakeODRecord("Resource 01"),
                    fakeODRecord("Resource 02"),
                ],
                DirectoryService.recordType_locations: [
                    fakeODRecord("Location 01"),
                    fakeODRecord("Location 02"),
                ],
            })

            group1 = self.service.recordWithShortName(DirectoryService.recordType_groups, "group01")
            self.assertTrue(group1 is not None)

            group2 = self.service.recordWithShortName(DirectoryService.recordType_groups, "group02")
            self.assertTrue(group2 is not None)

            user1 = self.service.recordWithShortName(DirectoryService.recordType_users, "user01")
            self.assertTrue(user1 is not None)
            self.assertEqual(set((group1,)), user1.groups()) 
            
            user2 = self.service.recordWithShortName(DirectoryService.recordType_users, "user02")
            self.assertTrue(user2 is not None)
            self.assertEqual(set((group1, group2)), user2.groups()) 
            
            self.service.fakerecords[DirectoryService.recordType_groups] = [
                fakeODRecord("Group 01", members=[
                    guidForShortName("user01"),
                ]),
                fakeODRecord("Group 02", members=[
                    guidForShortName("resource01"),
                    guidForShortName("user02"),
                ]),
            ]
            self.service.reloadCache(DirectoryService.recordType_groups)

            group1 = self.service.recordWithShortName(DirectoryService.recordType_groups, "group01")
            self.assertTrue(group1 is not None)

            group2 = self.service.recordWithShortName(DirectoryService.recordType_groups, "group02")
            self.assertTrue(group2 is not None)

            user1 = self.service.recordWithShortName(DirectoryService.recordType_users, "user01")
            self.assertTrue(user1 is not None)
            self.assertEqual(set((group1,)), user1.groups()) 
            
            user2 = self.service.recordWithShortName(DirectoryService.recordType_users, "user02")
            self.assertTrue(user2 is not None)
            self.assertEqual(set((group2,)), user2.groups()) 
            
            self.service.fakerecords[DirectoryService.recordType_groups] = [
                fakeODRecord("Group 03", members=[
                    guidForShortName("user01"),
                    guidForShortName("user02"),
                ]),
            ]
            self.service.reloadCache(DirectoryService.recordType_groups, guid=guidForShortName("group03"))

            group1 = self.service.recordWithShortName(DirectoryService.recordType_groups, "group01")
            self.assertTrue(group1 is not None)

            group2 = self.service.recordWithShortName(DirectoryService.recordType_groups, "group02")
            self.assertTrue(group2 is not None)

            group3 = self.service.recordWithShortName(DirectoryService.recordType_groups, "group03")
            self.assertTrue(group2 is not None)

            user1 = self.service.recordWithShortName(DirectoryService.recordType_users, "user01")
            self.assertTrue(user1 is not None)
            self.assertEqual(set((group1, group3)), user1.groups()) 
            
            user2 = self.service.recordWithShortName(DirectoryService.recordType_users, "user02")
            self.assertTrue(user2 is not None)
            self.assertEqual(set((group2, group3)), user2.groups()) 

def fakeODRecord(fullName, shortName=None, guid=None, email=None, members=None):
    if shortName is None:
        shortName = shortNameForFullName(fullName)

    if guid is None:
        guid = guidForShortName(shortName)
    else:
        guid = guid.lower()

    if email is None:
        email = "%s@example.com" % (shortName,)

    attrs = {
        dsattributes.kDS1AttrDistinguishedName: fullName,
        dsattributes.kDS1AttrGeneratedUID: guid,
        dsattributes.kDSNAttrEMailAddress: email,
        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
    }
    
    if members:
        attrs[dsattributes.kDSNAttrGroupMembers] = members

    return [ shortName, attrs ]

def shortNameForFullName(fullName):
    return fullName.lower().replace(" ", "")

def guidForShortName(shortName):
    return uuidFromName(OpenDirectoryService.baseGUID, shortName)
