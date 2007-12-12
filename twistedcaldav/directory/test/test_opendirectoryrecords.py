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
    from twistedcaldav.directory.appleopendirectory import OpenDirectoryService
    import dsattributes
except ImportError:
    pass
else:
    from twistedcaldav.directory.directory import DirectoryService

    def _queryDirectory(dir, recordType, shortName=None):

        if shortName:
            for name, record in dir.fakerecords[recordType]:
                if name == shortName:
                    return ((name, record),)
            else:
                return ()
        else:
            return dir.fakerecords[recordType]
    
    class ReloadCache(twisted.trial.unittest.TestCase):

        def setUp(self):
            super(ReloadCache, self).setUp()
            self._service = OpenDirectoryService(node="/Search", dosetup=False)
            OpenDirectoryService._queryDirectory = _queryDirectory
            
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
                
        def _verifyDisabledRecords(self, recordType, disabled_type, expected):
            expected = set(expected)
            found = self._service._records[recordType]["disabled_%s" % (disabled_type,)]
            
            missing = expected.difference(found)
            extras = found.difference(expected)

            self.assertTrue(len(missing) == 0, msg="Disabled directory records not found: %s" % (missing,))
            self.assertTrue(len(extras) == 0, msg="Disabled directory records not expected: %s" % (extras,))

        def test_Normal(self):
            
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    ["user01", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user01",
                        dsattributes.kDS1AttrDistinguishedName: "User 01",
                        dsattributes.kDSNAttrEMailAddress: "user01@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["user02", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user02",
                        dsattributes.kDS1AttrDistinguishedName: "User 02",
                        dsattributes.kDSNAttrEMailAddress: "user02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                ],
                DirectoryService.recordType_groups: [
                    ["group01", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_group01",
                        dsattributes.kDS1AttrDistinguishedName: "Group 01",
                        dsattributes.kDSNAttrEMailAddress: "group01@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["group02", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_group02",
                        dsattributes.kDS1AttrDistinguishedName: "Group 02",
                        dsattributes.kDSNAttrEMailAddress: "group02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                ],
                DirectoryService.recordType_resources: [
                    ["resource01", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_resource01",
                        dsattributes.kDS1AttrDistinguishedName: "Resource 01",
                        dsattributes.kDSNAttrEMailAddress: "resource01@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["resource02", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_resource02",
                        dsattributes.kDS1AttrDistinguishedName: "Resource 02",
                        dsattributes.kDSNAttrEMailAddress: "resource02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                ],
                DirectoryService.recordType_locations: [
                    ["location01", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_location01",
                        dsattributes.kDS1AttrDistinguishedName: "Location 01",
                        dsattributes.kDSNAttrEMailAddress: "location01@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["location02", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_location02",
                        dsattributes.kDS1AttrDistinguishedName: "Location 02",
                        dsattributes.kDSNAttrEMailAddress: "location02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users)
            self._service.reloadCache(DirectoryService.recordType_groups)
            self._service.reloadCache(DirectoryService.recordType_resources)
            self._service.reloadCache(DirectoryService.recordType_locations)

            self._verifyRecords(DirectoryService.recordType_users, ("user01", "user02",))
            self._verifyDisabledRecords(DirectoryService.recordType_users, "names", ())
            self._verifyDisabledRecords(DirectoryService.recordType_users, "guids", ())

            self._verifyRecords(DirectoryService.recordType_groups, ("group01", "group02",))
            self._verifyDisabledRecords(DirectoryService.recordType_groups, "names", ())
            self._verifyDisabledRecords(DirectoryService.recordType_groups, "guids", ())

            self._verifyRecords(DirectoryService.recordType_resources, ("resource01", "resource02",))
            self._verifyDisabledRecords(DirectoryService.recordType_resources, "names", ())
            self._verifyDisabledRecords(DirectoryService.recordType_resources, "guids", ())

            self._verifyRecords(DirectoryService.recordType_locations, ("location01", "location02",))
            self._verifyDisabledRecords(DirectoryService.recordType_locations, "names", ())
            self._verifyDisabledRecords(DirectoryService.recordType_locations, "guids", ())

        def test_DuplicateRecords(self):
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    ["user01", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user01",
                        dsattributes.kDS1AttrDistinguishedName: "User 01",
                        dsattributes.kDSNAttrEMailAddress: "user01@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["user02", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user02",
                        dsattributes.kDS1AttrDistinguishedName: "User 02",
                        dsattributes.kDSNAttrEMailAddress: "user02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["user02", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user02",
                        dsattributes.kDS1AttrDistinguishedName: "User 02",
                        dsattributes.kDSNAttrEMailAddress: "user02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users)

            self._verifyRecords(DirectoryService.recordType_users, ("user01", "user02",))
            self._verifyDisabledRecords(DirectoryService.recordType_users, "names", ())
            self._verifyDisabledRecords(DirectoryService.recordType_users, "guids", ())


        def test_DuplicateName(self):
            
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    ["user01", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user01",
                        dsattributes.kDS1AttrDistinguishedName: "User 01",
                        dsattributes.kDSNAttrEMailAddress: "user01@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["user02", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user02-1",
                        dsattributes.kDS1AttrDistinguishedName: "User 02",
                        dsattributes.kDSNAttrEMailAddress: "user02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["user02", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user02-2",
                        dsattributes.kDS1AttrDistinguishedName: "User 02",
                        dsattributes.kDSNAttrEMailAddress: "user02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users)

            self._verifyRecords(DirectoryService.recordType_users, ("user01",))
            self._verifyDisabledRecords(DirectoryService.recordType_users, "names", ("user02",))
            self._verifyDisabledRecords(DirectoryService.recordType_users, "guids", ("GUID_user02-1", "GUID_user02-2", ))

        def test_DuplicateGUID(self):
            
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    ["user01", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user01",
                        dsattributes.kDS1AttrDistinguishedName: "User 01",
                        dsattributes.kDSNAttrEMailAddress: "user01@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["user02", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user02",
                        dsattributes.kDS1AttrDistinguishedName: "User 02",
                        dsattributes.kDSNAttrEMailAddress: "user02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["user03", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user02",
                        dsattributes.kDS1AttrDistinguishedName: "User 02",
                        dsattributes.kDSNAttrEMailAddress: "user02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users)

            self._verifyRecords(DirectoryService.recordType_users, ("user01",))
            self._verifyDisabledRecords(DirectoryService.recordType_users, "names", ("user02", "user03",))
            self._verifyDisabledRecords(DirectoryService.recordType_users, "guids", ("GUID_user02", ))

        def test_DuplicateCombo(self):
            
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    ["user01", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user01",
                        dsattributes.kDS1AttrDistinguishedName: "User 01",
                        dsattributes.kDSNAttrEMailAddress: "user01@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["user02", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user02",
                        dsattributes.kDS1AttrDistinguishedName: "User 02",
                        dsattributes.kDSNAttrEMailAddress: "user02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["user03", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user02",
                        dsattributes.kDS1AttrDistinguishedName: "User 02",
                        dsattributes.kDSNAttrEMailAddress: "user02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["user02", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user02-2",
                        dsattributes.kDS1AttrDistinguishedName: "User 02",
                        dsattributes.kDSNAttrEMailAddress: "user02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users)

            self._verifyRecords(DirectoryService.recordType_users, ("user01",))
            self._verifyDisabledRecords(DirectoryService.recordType_users, "names", ("user02", "user03",))
            self._verifyDisabledRecords(DirectoryService.recordType_users, "guids", ("GUID_user02", "GUID_user02-2"))

        def test_DuplicateGUIDCacheMiss(self):
            
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    ["user01", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user01",
                        dsattributes.kDS1AttrDistinguishedName: "User 01",
                        dsattributes.kDSNAttrEMailAddress: "user01@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["user02", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user02",
                        dsattributes.kDS1AttrDistinguishedName: "User 02",
                        dsattributes.kDSNAttrEMailAddress: "user02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users)

            self._verifyRecords(DirectoryService.recordType_users, ("user01", "user02",))
            self._verifyDisabledRecords(DirectoryService.recordType_users, "names", ())
            self._verifyDisabledRecords(DirectoryService.recordType_users, "guids", ())
            
            self._service.fakerecords = {
                DirectoryService.recordType_users: [
                    ["user01", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user01",
                        dsattributes.kDS1AttrDistinguishedName: "User 01",
                        dsattributes.kDSNAttrEMailAddress: "user01@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["user02", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user02",
                        dsattributes.kDS1AttrDistinguishedName: "User 02",
                        dsattributes.kDSNAttrEMailAddress: "user02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                    ["user03", {
                        dsattributes.kDS1AttrGeneratedUID: "GUID_user02",
                        dsattributes.kDS1AttrDistinguishedName: "User 02",
                        dsattributes.kDSNAttrEMailAddress: "user02@example.com",
                        dsattributes.kDSNAttrServicesLocator: "12345:67890:calendar",
                        dsattributes.kDSNAttrMetaNodeLocation: "/LDAPv3/127.0.0.1",
                    }],
                ],
            }

            self._service.reloadCache(DirectoryService.recordType_users, "user03")

            self._verifyRecords(DirectoryService.recordType_users, ("user01", "user02",))
            self._verifyDisabledRecords(DirectoryService.recordType_users, "names", ("user03",))
            self._verifyDisabledRecords(DirectoryService.recordType_users, "guids", ("GUID_user02", ))

