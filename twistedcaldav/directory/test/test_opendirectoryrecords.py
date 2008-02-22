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

import twisted.trial.unittest

try:
    from twistedcaldav.directory.appleopendirectory import OpenDirectoryService as RealOpenDirectoryService
    import dsattributes
except ImportError:
    pass
else:
    from twistedcaldav.directory.directory import DirectoryService
    from twistedcaldav.directory.util import uuidFromName

    class OpenDirectoryService (RealOpenDirectoryService):
        def _queryDirectory(directory, recordType, shortName=None, guid=None):
            if shortName is None and guid is None:
                return directory.fakerecords[recordType]

            assert shortName is None or guid is None
            if guid is not None:
                guid = guid.lower()

            records = []

            for name, record in directory.fakerecords[recordType]:
                if name == shortName or record[dsattributes.kDS1AttrGeneratedUID] == guid:
                    records.append((name, record))

            return tuple(records)
    
    class ReloadCache(twisted.trial.unittest.TestCase):
        def setUp(self):
            super(ReloadCache, self).setUp()
            self._service = OpenDirectoryService(node="/Search", dosetup=False)
            self._service.servicetags.add("FE588D50-0514-4DF9-BCB5-8ECA5F3DA274:030572AE-ABEC-4E0F-83C9-FCA304769E5F:calendar")
            
        def tearDown(self):
            for call in self._service._delayedCalls:
                call.cancel()

        def _verifyRecords(self, recordType, expected):
            expected = set(expected)
            found = set(self._service._records[recordType]["records"].keys())
            
            missing = expected.difference(found)
            extras = found.difference(expected)

            self.assertTrue(len(missing) == 0, msg="Directory records not found: %s" % (missing,))
            self.assertTrue(len(extras) == 0, msg="Directory records not expected: %s" % (extras,))
                
        def _verifyRecordsCheckEnabled(self, recordType, expected, enabled):
            expected = set(expected)
            found = set([item for item in self._service._records[recordType]["records"].iterkeys()
                         if self._service._records[recordType]["records"][item].enabledForCalendaring == enabled])
            
            missing = expected.difference(found)
            extras = found.difference(expected)

            self.assertTrue(len(missing) == 0, msg="Directory records not found: %s" % (missing,))
            self.assertTrue(len(extras) == 0, msg="Directory records not expected: %s" % (extras,))
                
        def _verifyDisabledRecords(self, recordType, expectedNames, expectedGUIDs):
            def check(disabledType, expected):
                expected = set(expected)
                found = self._service._records[recordType][disabledType]
            
                missing = expected.difference(found)
                extras = found.difference(expected)

                self.assertTrue(len(missing) == 0, msg="Disabled directory records not found: %s" % (missing,))
                self.assertTrue(len(extras) == 0, msg="Disabled directory records not expected: %s" % (extras,))

            check("disabled names", expectedNames)
            check("disabled guids", (guid.lower() for guid in expectedGUIDs))

        def test_normal(self):
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    fakeODRecordWithServicesLocator("User 01"),
                    fakeODRecordWithServicesLocator("User 02"),
                ],
                DirectoryService.recordType_groups: [
                    fakeODRecordWithServicesLocator("Group 01"),
                    fakeODRecordWithServicesLocator("Group 02"),
                ],
                DirectoryService.recordType_resources: [
                    fakeODRecordWithServicesLocator("Resource 01"),
                    fakeODRecordWithServicesLocator("Resource 02"),
                ],
                DirectoryService.recordType_locations: [
                    fakeODRecordWithServicesLocator("Location 01"),
                    fakeODRecordWithServicesLocator("Location 02"),
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users)
            self._service.reloadCache(DirectoryService.recordType_groups)
            self._service.reloadCache(DirectoryService.recordType_resources)
            self._service.reloadCache(DirectoryService.recordType_locations)

            self._verifyRecords(DirectoryService.recordType_users, ("user01", "user02"))
            self._verifyDisabledRecords(DirectoryService.recordType_users, (), ())

            self._verifyRecords(DirectoryService.recordType_groups, ("group01", "group02"))
            self._verifyDisabledRecords(DirectoryService.recordType_groups, (), ())

            self._verifyRecords(DirectoryService.recordType_resources, ("resource01", "resource02"))
            self._verifyDisabledRecords(DirectoryService.recordType_resources, (), ())

            self._verifyRecords(DirectoryService.recordType_locations, ("location01", "location02"))
            self._verifyDisabledRecords(DirectoryService.recordType_locations, (), ())

        def test_normal_disabledusers(self):
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    fakeODRecordWithServicesLocator("User 01"),
                    fakeODRecordWithServicesLocator("User 02"),
                    fakeODRecordWithoutServicesLocator("User 03"),
                    fakeODRecordWithoutServicesLocator("User 04"),
                ],
                DirectoryService.recordType_groups: [
                    fakeODRecordWithServicesLocator("Group 01"),
                    fakeODRecordWithServicesLocator("Group 02"),
                    fakeODRecordWithoutServicesLocator("Group 03"),
                    fakeODRecordWithoutServicesLocator("Group 04"),
                ],
                DirectoryService.recordType_resources: [
                    fakeODRecordWithServicesLocator("Resource 01"),
                    fakeODRecordWithServicesLocator("Resource 02"),
                    fakeODRecordWithoutServicesLocator("Resource 03"),
                    fakeODRecordWithoutServicesLocator("Resource 04"),
                ],
                DirectoryService.recordType_locations: [
                    fakeODRecordWithServicesLocator("Location 01"),
                    fakeODRecordWithServicesLocator("Location 02"),
                    fakeODRecordWithoutServicesLocator("Location 03"),
                    fakeODRecordWithoutServicesLocator("Location 04"),
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users)
            self._service.reloadCache(DirectoryService.recordType_groups)
            self._service.reloadCache(DirectoryService.recordType_resources)
            self._service.reloadCache(DirectoryService.recordType_locations)

            self._verifyRecordsCheckEnabled(DirectoryService.recordType_users, ("user01", "user02"), True)
            self._verifyRecordsCheckEnabled(DirectoryService.recordType_users, ("user03", "user04"), False)

            self._verifyRecordsCheckEnabled(DirectoryService.recordType_groups, ("group01", "group02"), True)
            self._verifyRecordsCheckEnabled(DirectoryService.recordType_groups, ("group03", "group04"), False)

            self._verifyRecordsCheckEnabled(DirectoryService.recordType_resources, ("resource01", "resource02"), True)
            self._verifyRecordsCheckEnabled(DirectoryService.recordType_resources, (), False)

            self._verifyRecordsCheckEnabled(DirectoryService.recordType_locations, ("location01", "location02"), True)
            self._verifyRecordsCheckEnabled(DirectoryService.recordType_locations, (), False)

        def test_normalCacheMiss(self):
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    fakeODRecordWithServicesLocator("User 01"),
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users)

            self._verifyRecords(DirectoryService.recordType_users, ("user01",))
            self._verifyDisabledRecords(DirectoryService.recordType_users, (), ())

            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    fakeODRecordWithServicesLocator("User 01"),
                    fakeODRecordWithServicesLocator("User 02"),
                    fakeODRecordWithServicesLocator("User 03", guid="D10F3EE0-5014-41D3-8488-3819D3EF3B2A"),
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users, shortName="user02")
            self._service.reloadCache(DirectoryService.recordType_users, guid="D10F3EE0-5014-41D3-8488-3819D3EF3B2A")

            self._verifyRecords(DirectoryService.recordType_users, ("user01", "user02", "user03"))
            self._verifyDisabledRecords(DirectoryService.recordType_users, (), ())

        def test_duplicateRecords(self):
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    fakeODRecordWithServicesLocator("User 01"),
                    fakeODRecordWithServicesLocator("User 02"),
                    fakeODRecordWithServicesLocator("User 02"),
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users)

            self._verifyRecords(DirectoryService.recordType_users, ("user01", "user02"))
            self._verifyDisabledRecords(DirectoryService.recordType_users, (), ())
            self._verifyDisabledRecords(DirectoryService.recordType_users, (), ())


        def test_duplicateName(self):
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    fakeODRecordWithServicesLocator("User 01"),
                    fakeODRecordWithServicesLocator("User 02", guid="A25775BB-1281-4606-98C6-2893B2D5CCD7"),
                    fakeODRecordWithServicesLocator("User 02", guid="30CA2BB9-C935-4A5D-80E2-79266BCB0255"),
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users)

            self._verifyRecords(DirectoryService.recordType_users, ("user01",))
            self._verifyDisabledRecords(
                DirectoryService.recordType_users,
                ("user02",),
                ("A25775BB-1281-4606-98C6-2893B2D5CCD7", "30CA2BB9-C935-4A5D-80E2-79266BCB0255"),
            )

        def test_duplicateGUID(self):
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    fakeODRecordWithServicesLocator("User 01"),
                    fakeODRecordWithServicesLocator("User 02", guid="113D7F74-F84A-4F17-8C96-CE8F10D68EF8"),
                    fakeODRecordWithServicesLocator("User 03", guid="113D7F74-F84A-4F17-8C96-CE8F10D68EF8"),
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users)

            self._verifyRecords(DirectoryService.recordType_users, ("user01",))
            self._verifyDisabledRecords(
                DirectoryService.recordType_users,
                ("user02", "user03"),
                ("113D7F74-F84A-4F17-8C96-CE8F10D68EF8",),
            )

        def test_duplicateCombo(self):
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    fakeODRecordWithServicesLocator("User 01"),
                    fakeODRecordWithServicesLocator("User 02", guid="113D7F74-F84A-4F17-8C96-CE8F10D68EF8"),
                    fakeODRecordWithServicesLocator("User 02", guid="113D7F74-F84A-4F17-8C96-CE8F10D68EF8", shortName="user03"),
                    fakeODRecordWithServicesLocator("User 02", guid="136E369F-DB40-4135-878D-B75D38242D39"),
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users)

            self._verifyRecords(DirectoryService.recordType_users, ("user01",))
            self._verifyDisabledRecords(
                DirectoryService.recordType_users,
                ("user02", "user03"),
                ("113D7F74-F84A-4F17-8C96-CE8F10D68EF8", "136E369F-DB40-4135-878D-B75D38242D39"),
            )

        def test_duplicateGUIDCacheMiss(self):
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    fakeODRecordWithServicesLocator("User 01"),
                    fakeODRecordWithServicesLocator("User 02", guid="EDB9EE55-31F2-4EA9-B5FB-D8AE2A8BA35E"),
                    fakeODRecordWithServicesLocator("User 03", guid="D10F3EE0-5014-41D3-8488-3819D3EF3B2A"),
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users)

            self._verifyRecords(DirectoryService.recordType_users, ("user01", "user02", "user03"))
            self._verifyDisabledRecords(DirectoryService.recordType_users, (), ())
            
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    fakeODRecordWithServicesLocator("User 01"),
                    fakeODRecordWithServicesLocator("User 02", guid="EDB9EE55-31F2-4EA9-B5FB-D8AE2A8BA35E"),
                    fakeODRecordWithServicesLocator("User 02", guid="EDB9EE55-31F2-4EA9-B5FB-D8AE2A8BA35E", shortName="user04"),
                    fakeODRecordWithServicesLocator("User 03", guid="62368DDF-0C62-4C97-9A58-DE9FD46131A0"),
                    fakeODRecordWithServicesLocator("User 03", guid="62368DDF-0C62-4C97-9A58-DE9FD46131A0", shortName="user05"),
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users, shortName="user04")
            self._service.reloadCache(DirectoryService.recordType_users, guid="62368DDF-0C62-4C97-9A58-DE9FD46131A0")

            self._verifyRecords(DirectoryService.recordType_users, ("user01",))
            self._verifyDisabledRecords(
                DirectoryService.recordType_users,
                ("user02", "user03", "user04", "user05"),
                ("EDB9EE55-31F2-4EA9-B5FB-D8AE2A8BA35E", "62368DDF-0C62-4C97-9A58-DE9FD46131A0", "D10F3EE0-5014-41D3-8488-3819D3EF3B2A"),
            )

def fakeODRecordWithServicesLocator(fullName, shortName=None, guid=None, email=None):
    if shortName is None:
        shortName = shortNameForFullName(fullName)

    if guid is None:
        guid = guidForShortName(shortName)
    else:
        guid = guid.lower()

    if email is None:
        email = "%s@example.com" % (shortName,)

    return [
        shortName, {
            dsattributes.kDS1AttrDistinguishedName: fullName,
            dsattributes.kDS1AttrGeneratedUID: guid,
            dsattributes.kDSNAttrEMailAddress: email,
            dsattributes.kDSNAttrServicesLocator: "FE588D50-0514-4DF9-BCB5-8ECA5F3DA274:030572AE-ABEC-4E0F-83C9-FCA304769E5F:calendar",
            dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
        }
    ]

def fakeODRecordWithoutServicesLocator(fullName, shortName=None, guid=None, email=None):
    if shortName is None:
        shortName = shortNameForFullName(fullName)

    if guid is None:
        guid = guidForShortName(shortName)
    else:
        guid = guid.lower()

    if email is None:
        email = "%s@example.com" % (shortName,)

    return [
        shortName, {
            dsattributes.kDS1AttrDistinguishedName: fullName,
            dsattributes.kDS1AttrGeneratedUID: guid,
            dsattributes.kDSNAttrEMailAddress: email,
            dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
        }
    ]

def shortNameForFullName(fullName):
    return fullName.lower().replace(" ", "")

def guidForShortName(shortName):
    return uuidFromName(OpenDirectoryService.baseGUID, shortName)
