##
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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

try:
    from twistedcaldav.directory.appleopendirectory import OpenDirectoryService
except ImportError:
    pass
else:
    from twisted.trial.unittest import SkipTest
    from twisted.internet.defer import inlineCallbacks
    from twisted.python.runtime import platform
    from twext.web2.auth.digest import DigestedCredentials
    import twistedcaldav.directory.test.util
    from twistedcaldav.directory import augment
    from twistedcaldav.directory.directory import DirectoryService
    from twistedcaldav.directory.appleopendirectory import OpenDirectoryRecord
    from calendarserver.platform.darwin.od import dsattributes

    # Wonky hack to prevent unclean reactor shutdowns
    class DummyReactor(object):
        @staticmethod
        def callLater(*args):
            pass
    import twistedcaldav.directory.appleopendirectory
    twistedcaldav.directory.appleopendirectory.reactor = DummyReactor

    class OpenDirectory (
        twistedcaldav.directory.test.util.BasicTestCase,
        twistedcaldav.directory.test.util.DigestTestCase
    ):
        """
        Test Open Directory directory implementation.
        """
        if not platform.isMacOSX():
            skip = "Currently, OpenDirectory backend only works on MacOS X."
        recordTypes = set((
            DirectoryService.recordType_users,
            DirectoryService.recordType_groups,
        ))

        users = groups = {}

        def setUp(self):
            super(OpenDirectory, self).setUp()
            try:
                self._service = OpenDirectoryService(
                    {
                        "node" : "/Search",
                        "augmentService": augment.AugmentXMLDB(xmlFiles=()),
                    }
                )
            except ImportError, e:
                raise SkipTest("OpenDirectory module is not available: %s" % (e,))

        def service(self):
            return self._service

        def test_fullNameNone(self):
            record = OpenDirectoryRecord(
                service               = self.service(),
                recordType            = DirectoryService.recordType_users,
                guid                  = "B1F93EB1-DA93-4772-9141-81C250DA36C2",
                nodeName              = "/LDAPv2/127.0.0.1",
                shortNames            = ("user",),
                authIDs               = set(),
                fullName              = None,
                firstName             = "Some",
                lastName              = "User",
                emailAddresses        = set(("someuser@example.com",)),
                memberGUIDs           = [],
                nestedGUIDs           = [],
                extProxies            = [],
                extReadOnlyProxies    = [],
            )
            self.assertEquals(record.fullName, "")

        def test_invalidODDigest(self):
            record = OpenDirectoryRecord(
                service               = self.service(),
                recordType            = DirectoryService.recordType_users,
                guid                  = "B1F93EB1-DA93-4772-9141-81C250DA35B3",
                nodeName              = "/LDAPv2/127.0.0.1",
                shortNames            = ("user",),
                authIDs               = set(),
                fullName              = "Some user",
                firstName             = "Some",
                lastName              = "User",
                emailAddresses        = set(("someuser@example.com",)),
                memberGUIDs           = [],
                nestedGUIDs           = [],
                extProxies            = [],
                extReadOnlyProxies    = [],
            )

            digestFields = {}
            digested = DigestedCredentials("user", "GET", "example.com", digestFields, None)

            self.assertFalse(record.verifyCredentials(digested))

        def test_validODDigest(self):
            record = OpenDirectoryRecord(
                service               = self.service(),
                recordType            = DirectoryService.recordType_users,
                guid                  = "B1F93EB1-DA93-4772-9141-81C250DA35B3",
                nodeName              = "/LDAPv2/127.0.0.1",
                shortNames            = ("user",),
                authIDs               = set(),
                fullName              = "Some user",
                firstName             = "Some",
                lastName              = "User",
                emailAddresses        = set(("someuser@example.com",)),
                memberGUIDs           = [],
                nestedGUIDs           = [],
                extProxies            = [],
                extReadOnlyProxies    = [],
            )

            digestFields = {
                "username":"user",
                "realm":"/Search",
                "nonce":"ABC",
                "uri":"/",
                "response":"123",
                "algorithm":"md5",
            }

            response = (
                'Digest username="%(username)s", '
                'realm="%(realm)s", '
                'nonce="%(nonce)s", '
                'uri="%(uri)s", '
                'response="%(response)s",'
                'algorithm=%(algorithm)s'
            ) % digestFields

            record.digestcache = {}
            record.digestcache["/"] = response
            digested = DigestedCredentials("user", "GET", "example.com", digestFields, None)

            self.assertTrue(record.verifyCredentials(digested))

            # This should be defaulted
            del digestFields["algorithm"]

            self.assertTrue(record.verifyCredentials(digested))

        def test_queryDirectorySingleGUID(self):
            """ Test for lookup on existing and non-existing GUIDs """

            def lookupMethod(obj, attr, value, matchType, casei, recordTypes, attributes, count=0):

                data = {
                    "dsRecTypeStandard:Users" : [
                        {
                            dsattributes.kDS1AttrGeneratedUID : "1234567890",
                            dsattributes.kDSNAttrRecordName : ["user1", "User 1"],
                            dsattributes.kDSNAttrRecordType : dsattributes.kDSStdRecordTypeUsers,
                        },
                    ],
                    "dsRecTypeStandard:Groups" : [],
                }
                results = []
                for recordType in recordTypes:
                    for entry in data[recordType]:
                        if entry[attr] == value:
                            results.append(("", entry))
                return results

            recordTypes = [DirectoryService.recordType_users, DirectoryService.recordType_groups]
            self.service().queryDirectory(recordTypes, self.service().INDEX_TYPE_GUID, "1234567890", lookupMethod=lookupMethod)
            self.assertTrue(self.service().recordWithGUID("1234567890"))
            self.assertFalse(self.service().recordWithGUID("987654321"))


        def test_queryDirectoryDuplicateGUIDs(self):
            """ Test for lookup on duplicate GUIDs, ensuring they don't get
                faulted in """

            def lookupMethod(obj, attr, value, matchType, casei, recordType, attributes, count=0):

                data = [
                    {
                        dsattributes.kDS1AttrGeneratedUID : "1234567890",
                        dsattributes.kDSNAttrRecordName : ["user1", "User 1"],
                        dsattributes.kDSNAttrRecordType : dsattributes.kDSStdRecordTypeUsers,
                    },
                    {
                        dsattributes.kDS1AttrGeneratedUID : "1234567890",
                        dsattributes.kDSNAttrRecordName : ["user2", "User 2"],
                        dsattributes.kDSNAttrRecordType : dsattributes.kDSStdRecordTypeUsers,
                    },
                ]
                results = []
                for entry in data:
                    if entry[attr] == value:
                        results.append(("", entry))
                return results

            recordTypes = [DirectoryService.recordType_users, DirectoryService.recordType_groups]
            self.service().queryDirectory(recordTypes, self.service().INDEX_TYPE_GUID, "1234567890", lookupMethod=lookupMethod)
            self.assertFalse(self.service().recordWithGUID("1234567890"))

        def test_queryDirectoryLocalUsers(self):
            """ Test for lookup on local users, ensuring they do get
                faulted in """

            def lookupMethod(obj, attr, value, matchType, casei, recordTypes, attributes, count=0):
                data = {
                    "dsRecTypeStandard:Users" : [
                        {
                            dsattributes.kDS1AttrGeneratedUID : "1234567890",
                            dsattributes.kDSNAttrRecordName : ["user1", "User 1"],
                            dsattributes.kDSNAttrRecordType : dsattributes.kDSStdRecordTypeUsers,
                            dsattributes.kDSNAttrMetaNodeLocation : "/Local/Default",
                        },
                        {
                            dsattributes.kDS1AttrGeneratedUID : "987654321",
                            dsattributes.kDSNAttrRecordName : ["user2", "User 2"],
                            dsattributes.kDSNAttrRecordType : dsattributes.kDSStdRecordTypeUsers,
                            dsattributes.kDSNAttrMetaNodeLocation : "/LDAPv3/127.0.0.1",
                        },
                    ],
                    "dsRecTypeStandard:Groups" : [],
                }
                results = []
                for recordType in recordTypes:
                    for entry in data[recordType]:
                        if entry[attr] == value:
                            results.append(("", entry))
                return results

            recordTypes = [DirectoryService.recordType_users, DirectoryService.recordType_groups]
            self.service().queryDirectory(recordTypes, self.service().INDEX_TYPE_GUID, "1234567890", lookupMethod=lookupMethod)
            self.service().queryDirectory(recordTypes, self.service().INDEX_TYPE_GUID, "987654321", lookupMethod=lookupMethod)
            self.assertTrue(self.service().recordWithGUID("1234567890"))
            self.assertTrue(self.service().recordWithGUID("987654321"))

        def test_queryDirectoryEmailAddresses(self):
            """ Test to ensure we only ask for users when email address is
                part of the query """

            def lookupMethod(obj, attr, value, matchType, casei, recordType, attributes, count=0):

                if recordType != ['dsRecTypeStandard:Users']:
                    raise ValueError

                return []

            recordTypes = [DirectoryService.recordType_users, DirectoryService.recordType_groups]
            self.service().queryDirectory(recordTypes, self.service().INDEX_TYPE_CUA, "mailto:user1@example.com", lookupMethod=lookupMethod)


        @inlineCallbacks
        def test_recordsMatchingFields(self):


            def lookupMethod(obj, attribute, value, matchType, caseless,
                recordTypes, attributes):

                data = {
                    dsattributes.kDSStdRecordTypeUsers : (
                        {
                            dsattributes.kDS1AttrDistinguishedName : "Morgen Sagen",
                            dsattributes.kDSNAttrRecordName : "morgen",
                            dsattributes.kDS1AttrFirstName : "Morgen",
                            dsattributes.kDS1AttrLastName : "Sagen",
                            dsattributes.kDSNAttrEMailAddress : "morgen@example.com",
                            dsattributes.kDSNAttrMetaNodeLocation : "/LDAPv3/127.0.0.1",
                            dsattributes.kDS1AttrGeneratedUID : "83479230-821E-11DE-B6B0-DBB02C6D659D",
                            dsattributes.kDSNAttrRecordType : dsattributes.kDSStdRecordTypeUsers,
                        },
                        {
                            dsattributes.kDS1AttrDistinguishedName : "Morgan Sagan",
                            dsattributes.kDSNAttrRecordName : "morgan",
                            dsattributes.kDS1AttrFirstName : "Morgan",
                            dsattributes.kDS1AttrLastName : "Sagan",
                            dsattributes.kDSNAttrEMailAddress : "morgan@example.com",
                            dsattributes.kDSNAttrMetaNodeLocation : "/LDAPv3/127.0.0.1",
                            dsattributes.kDS1AttrGeneratedUID : "93479230-821E-11DE-B6B0-DBB02C6D659D",
                            dsattributes.kDSNAttrRecordType : dsattributes.kDSStdRecordTypeUsers,
                        },
                        {
                            dsattributes.kDS1AttrDistinguishedName : "Shari Sagen",
                            dsattributes.kDSNAttrRecordName : "shari",
                            dsattributes.kDS1AttrFirstName : "Shari",
                            dsattributes.kDS1AttrLastName : "Sagen",
                            dsattributes.kDSNAttrEMailAddress : "shari@example.com",
                            dsattributes.kDSNAttrMetaNodeLocation : "/LDAPv3/127.0.0.1",
                            dsattributes.kDS1AttrGeneratedUID : "A3479230-821E-11DE-B6B0-DBB02C6D659D",
                            dsattributes.kDSNAttrRecordType : dsattributes.kDSStdRecordTypeUsers,
                        },
                        {
                            dsattributes.kDS1AttrDistinguishedName : "Local Morgen",
                            dsattributes.kDSNAttrRecordName : "localmorgen",
                            dsattributes.kDS1AttrFirstName : "Local",
                            dsattributes.kDS1AttrLastName : "Morgen",
                            dsattributes.kDSNAttrEMailAddress : "localmorgen@example.com",
                            dsattributes.kDSNAttrMetaNodeLocation : "/Local/Default",
                            dsattributes.kDS1AttrGeneratedUID : "B3479230-821E-11DE-B6B0-DBB02C6D659D",
                            dsattributes.kDSNAttrRecordType : dsattributes.kDSStdRecordTypeUsers,
                        },
                    ),
                    dsattributes.kDSStdRecordTypeGroups : (
                        {
                            dsattributes.kDS1AttrDistinguishedName : "Test Group",
                            dsattributes.kDSNAttrRecordName : "testgroup",
                            dsattributes.kDS1AttrFirstName : None,
                            dsattributes.kDS1AttrLastName : None,
                            dsattributes.kDSNAttrEMailAddress : None,
                            dsattributes.kDSNAttrMetaNodeLocation : "/LDAPv3/127.0.0.1",
                            dsattributes.kDS1AttrGeneratedUID : "C3479230-821E-11DE-B6B0-DBB02C6D659D",
                            dsattributes.kDSNAttrRecordType : dsattributes.kDSStdRecordTypeGroups,
                        },
                        {
                            dsattributes.kDS1AttrDistinguishedName : "Morgen's Group",
                            dsattributes.kDSNAttrRecordName : "morgensgroup",
                            dsattributes.kDS1AttrFirstName : None,
                            dsattributes.kDS1AttrLastName : None,
                            dsattributes.kDSNAttrEMailAddress : None,
                            dsattributes.kDSNAttrMetaNodeLocation : "/LDAPv3/127.0.0.1",
                            dsattributes.kDS1AttrGeneratedUID : "D3479230-821E-11DE-B6B0-DBB02C6D659D",
                            dsattributes.kDSNAttrRecordType : dsattributes.kDSStdRecordTypeGroups,
                        },
                    ),
                    dsattributes.kDSStdRecordTypePlaces : (),
                    dsattributes.kDSStdRecordTypeResources : (),
                }

                def attributeMatches(fieldValue, value, caseless, matchType):
                    if fieldValue is None:
                        return False
                    if caseless:
                        fieldValue = fieldValue.lower()
                        value = value.lower()
                    if matchType == dsattributes.eDSStartsWith:
                        if fieldValue.startswith(value):
                            return True
                    elif matchType == dsattributes.eDSContains:
                        try:
                            fieldValue.index(value)
                            return True
                        except ValueError:
                            pass
                    else: # exact
                        if fieldValue == value:
                            return True
                    return False

                results = []
                for recordType in recordTypes:
                    for row in data[recordType]:
                        if attributeMatches(row[attribute], value, caseless,
                            matchType):
                            results.append((row[dsattributes.kDSNAttrRecordName], row))

                return results


            #
            # OR
            #
            fields = [
                ("fullName", "mor", True, u"starts-with"),
                ("emailAddresses", "mor", True, u"starts-with"),
                ("firstName", "mor", True, u"starts-with"),
                ("lastName", "mor", True, u"starts-with"),
            ]

            # any record type
            results = (yield self.service().recordsMatchingFields(
                fields,
                lookupMethod=lookupMethod
            ))
            results = list(results)
            self.assertEquals(len(results), 4)
            for record in results:
                self.assertTrue(isinstance(record, OpenDirectoryRecord))

            # just users
            results = (yield self.service().recordsMatchingFields(fields,
                recordType="users",
                lookupMethod=lookupMethod))
            results = list(results)
            self.assertEquals(len(results), 3)

            # just groups
            results = (yield self.service().recordsMatchingFields(fields,
                recordType="groups",
                lookupMethod=lookupMethod))
            results = list(results)
            self.assertEquals(len(results), 1)


            #
            # AND
            #
            fields = [
                ("firstName", "morgen", True, u"equals"),
                ("lastName", "age", True, u"contains")
            ]
            results = (yield self.service().recordsMatchingFields(fields,
                operand="and", lookupMethod=lookupMethod))
            results = list(results)
            self.assertEquals(len(results), 1)

            #
            # case sensitivity
            #
            fields = [
                ("firstName", "morgen", False, u"equals"),
            ]
            results = (yield self.service().recordsMatchingFields(fields,
                lookupMethod=lookupMethod))
            results = list(results)
            self.assertEquals(len(results), 0)

            fields = [
                ("firstName", "morgen", True, u"equals"),
            ]
            results = (yield self.service().recordsMatchingFields(
                fields,
                lookupMethod=lookupMethod
            ))
            results = list(results)
            self.assertEquals(len(results), 1)

            #
            # no matches
            #
            fields = [
                ("firstName", "xyzzy", True, u"starts-with"),
                ("lastName", "plugh", True, u"contains")
            ]
            results = (yield self.service().recordsMatchingFields(
                fields,
                operand="and",
                lookupMethod=lookupMethod
            ))
            results = list(results)
            self.assertEquals(len(results), 0)


    class OpenDirectorySubset (OpenDirectory):
        """
        Test the recordTypes subset feature of Apple OpenDirectoryService.
        """
        recordTypes = set((
            DirectoryService.recordType_users,
            DirectoryService.recordType_groups,
        ))

        def setUp(self):
            super(OpenDirectorySubset, self).setUp()
            self._service = OpenDirectoryService(
                {
                    "node" : "/Search",
                    "recordTypes" : (DirectoryService.recordType_users, DirectoryService.recordType_groups),
                    "augmentService" : augment.AugmentXMLDB(xmlFiles=()),
                }
            )
