##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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

from twistedcaldav.test.util import TestCase

runTests = False

try:
    import OpenDirectory
    from calendarserver.od import opendirectory, dsattributes, dsquery
    import setup_directory

    directory = opendirectory.odInit("/Search")

    results = list(opendirectory.queryRecordsWithAttribute_list(
        directory,
        dsattributes.kDS1AttrGeneratedUID,
        "9dc04a74-e6dd-11df-9492-0800200c9a66",
        dsattributes.eDSExact,
        False,
        dsattributes.kDSStdRecordTypeUsers,
        None,
        count=0
    ))
    recordNames = [x[0] for x in results]
    # Local user:
    if "odtestalbert" in recordNames:
        runTests = True
    else:
        print "Please run setup_directory.py to populate OD"

except ImportError:
    print "Unable to import OpenDirectory framework"

if runTests:

    USER_ATTRIBUTES = [
        dsattributes.kDS1AttrGeneratedUID,
        dsattributes.kDSNAttrRecordName,
        dsattributes.kDSNAttrAltSecurityIdentities,
        dsattributes.kDSNAttrRecordType,
        dsattributes.kDS1AttrDistinguishedName,
        dsattributes.kDS1AttrFirstName,
        dsattributes.kDS1AttrLastName,
        dsattributes.kDSNAttrEMailAddress,
        dsattributes.kDSNAttrMetaNodeLocation,
    ]

    class OpenDirectoryTests(TestCase):

        def test_odInit(self):

            # Bogus node name
            self.assertRaises(opendirectory.ODError, opendirectory.odInit, "/Foo")

            # Valid node name
            directory = opendirectory.odInit("/Search")
            self.assertTrue(isinstance(directory, opendirectory.Directory))

        def test_adjustMatchType(self):
            self.assertEquals(
                opendirectory.adjustMatchType(OpenDirectory.kODMatchEqualTo, False),
                OpenDirectory.kODMatchEqualTo
            )
            self.assertEquals(
                opendirectory.adjustMatchType(OpenDirectory.kODMatchEqualTo, True),
                OpenDirectory.kODMatchInsensitiveEqualTo
            )
            self.assertEquals(
                opendirectory.adjustMatchType(OpenDirectory.kODMatchContains, False),
                OpenDirectory.kODMatchContains
            )
            self.assertEquals(
                opendirectory.adjustMatchType(OpenDirectory.kODMatchContains, True),
                OpenDirectory.kODMatchInsensitiveContains
            )

        def test_getNodeAttributes(self):

            directory = opendirectory.odInit("/Search")
            results = opendirectory.getNodeAttributes(directory, "/Search", [OpenDirectory.kODAttributeTypeSearchPath])
            self.assertTrue("/Local/Default" in results[OpenDirectory.kODAttributeTypeSearchPath])
            self.assertTrue("/LDAPv3/127.0.0.1" in results[OpenDirectory.kODAttributeTypeSearchPath])

        def test_listAllRecordsWithAttributes_list_master(self):

            directory = opendirectory.odInit("/LDAPv3/127.0.0.1")
            results = list(opendirectory.listAllRecordsWithAttributes_list(
                directory,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.masterUsers:
                self.assertTrue(recordName in recordNames)

        def test_listAllRecordsWithAttributes_list_local(self):

            directory = opendirectory.odInit("/Local/Default")
            results = list(opendirectory.listAllRecordsWithAttributes_list(
                directory,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.localUsers:
                self.assertTrue(recordName in recordNames)


        def test_queryRecordsWithAttribute_list_firstname_exact_insensitive_match(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrFirstName,
                "betty",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestbetty" in recordNames)

        def test_queryRecordsWithAttribute_list_firstname_exact_insensitive_match_multitype(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrFirstName,
                "betty",
                dsattributes.eDSExact,
                False,
                [
                    dsattributes.kDSStdRecordTypeUsers,
                    dsattributes.kDSStdRecordTypeGroups,
                    dsattributes.kDSStdRecordTypeResources,
                    dsattributes.kDSStdRecordTypePlaces,
                ],
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestbetty" in recordNames)

        def test_queryRecordsWithAttribute_list_firstname_begins_insensitive_match(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrFirstName,
                "Amand",
                dsattributes.eDSStartsWith,
                True,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestamanda" in recordNames)

        def test_queryRecordsWithAttribute_list_firstname_begins_insensitive_match_multitype(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrFirstName,
                "Amand",
                dsattributes.eDSStartsWith,
                True,
                [
                    dsattributes.kDSStdRecordTypeUsers,
                    dsattributes.kDSStdRecordTypeGroups,
                    dsattributes.kDSStdRecordTypeResources,
                    dsattributes.kDSStdRecordTypePlaces,
                ],
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestamanda" in recordNames)

        def test_queryRecordsWithAttribute_list_firstname_contains_insensitive_match(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrFirstName,
                "mand",
                dsattributes.eDSContains,
                True,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestamanda" in recordNames)

        def test_queryRecordsWithAttribute_list_firstname_contains_insensitive_match_multitype(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrFirstName,
                "mand",
                dsattributes.eDSContains,
                True,
                [
                    dsattributes.kDSStdRecordTypeUsers,
                    dsattributes.kDSStdRecordTypeGroups,
                    dsattributes.kDSStdRecordTypeResources,
                    dsattributes.kDSStdRecordTypePlaces,
                ],
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestamanda" in recordNames)

        def test_queryRecordsWithAttribute_list_lastname_exact_insensitive_match(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrLastName,
                "test",
                dsattributes.eDSExact,
                True,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.masterUsers:
                self.assertTrue(recordName in recordNames)
            for recordName, info in setup_directory.localUsers:
                self.assertTrue(recordName in recordNames)

        def test_queryRecordsWithAttribute_list_lastname_exact_insensitive_match_multitype(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrLastName,
                "test",
                dsattributes.eDSExact,
                True,
                [
                    dsattributes.kDSStdRecordTypeUsers,
                    dsattributes.kDSStdRecordTypeGroups,
                    dsattributes.kDSStdRecordTypeResources,
                    dsattributes.kDSStdRecordTypePlaces,
                ],
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.masterUsers:
                self.assertTrue(recordName in recordNames)
            for recordName, info in setup_directory.localUsers:
                self.assertTrue(recordName in recordNames)

        def test_queryRecordsWithAttribute_list_lastname_begins_insensitive_match(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrLastName,
                "tes",
                dsattributes.eDSStartsWith,
                True,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.masterUsers:
                self.assertTrue(recordName in recordNames)
            for recordName, info in setup_directory.localUsers:
                self.assertTrue(recordName in recordNames)

        def test_queryRecordsWithAttribute_list_lastname_begins_insensitive_match_multitype(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrLastName,
                "tes",
                dsattributes.eDSStartsWith,
                True,
                [
                    dsattributes.kDSStdRecordTypeUsers,
                    dsattributes.kDSStdRecordTypeGroups,
                    dsattributes.kDSStdRecordTypeResources,
                    dsattributes.kDSStdRecordTypePlaces,
                ],
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.masterUsers:
                self.assertTrue(recordName in recordNames)
            for recordName, info in setup_directory.localUsers:
                self.assertTrue(recordName in recordNames)

        def test_queryRecordsWithAttribute_list_lastname_contains_insensitive_match(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrLastName,
                "es",
                dsattributes.eDSContains,
                True,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.masterUsers:
                self.assertTrue(recordName in recordNames)
            for recordName, info in setup_directory.localUsers:
                self.assertTrue(recordName in recordNames)

        def test_queryRecordsWithAttribute_list_lastname_contains_insensitive_match_multitype(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrLastName,
                "es",
                dsattributes.eDSContains,
                True,
                [
                    dsattributes.kDSStdRecordTypeUsers,
                    dsattributes.kDSStdRecordTypeGroups,
                    dsattributes.kDSStdRecordTypeResources,
                    dsattributes.kDSStdRecordTypePlaces,
                ],
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.masterUsers:
                self.assertTrue(recordName in recordNames)
            for recordName, info in setup_directory.localUsers:
                self.assertTrue(recordName in recordNames)

        def test_queryRecordsWithAttribute_list_email_begins_insensitive_match(self):
            # This test won't pass until this is fixed: <rdar://problem/8608148>

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDSNAttrEMailAddress,
                "aman",
                dsattributes.eDSStartsWith,
                True,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestamanda" in recordNames)

        test_queryRecordsWithAttribute_list_email_begins_insensitive_match.todo = "This test won't pass until this is fixed: <rdar://problem/8608148>"

        def test_queryRecordsWithAttribute_list_email_begins_insensitive_match_multitype(self):
            # This test won't pass until this is fixed: <rdar://problem/8608148>

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDSNAttrEMailAddress,
                "aman",
                dsattributes.eDSStartsWith,
                True,
                [
                    dsattributes.kDSStdRecordTypeUsers,
                    dsattributes.kDSStdRecordTypeGroups,
                    dsattributes.kDSStdRecordTypeResources,
                    dsattributes.kDSStdRecordTypePlaces,
                ],
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestamanda" in recordNames)

        test_queryRecordsWithAttribute_list_email_begins_insensitive_match_multitype.todo = "This test won't pass until this is fixed: <rdar://problem/8608148>"


        def test_queryRecordsWithAttribute_list_guid_exact_sensitive_match_master(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrGeneratedUID,
                "9dc04a70-e6dd-11df-9492-0800200c9a66",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            # OD Master user:
            self.assertTrue("odtestamanda" in recordNames)

        def test_queryRecordsWithAttribute_list_guid_exact_sensitive_match_multitype_master(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrGeneratedUID,
                "9dc04a70-e6dd-11df-9492-0800200c9a66",
                dsattributes.eDSExact,
                False,
                [
                    dsattributes.kDSStdRecordTypeUsers,
                    dsattributes.kDSStdRecordTypeGroups,
                    dsattributes.kDSStdRecordTypeResources,
                    dsattributes.kDSStdRecordTypePlaces,
                ],
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            # OD Master user:
            self.assertTrue("odtestamanda" in recordNames)


        def test_queryRecordsWithAttribute_list_guid_exact_sensitive_match_local(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrGeneratedUID,
                "9dc04a74-e6dd-11df-9492-0800200c9a66",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            # Local user:
            self.assertTrue("odtestalbert" in recordNames)


        def test_queryRecordsWithAttribute_list_guid_exact_sensitive_match_multitype_local(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrGeneratedUID,
                "9dc04a74-e6dd-11df-9492-0800200c9a66",
                dsattributes.eDSExact,
                False,
                [
                    dsattributes.kDSStdRecordTypeUsers,
                    dsattributes.kDSStdRecordTypeGroups,
                    dsattributes.kDSStdRecordTypeResources,
                    dsattributes.kDSStdRecordTypePlaces,
                ],
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            # Local user:
            self.assertTrue("odtestalbert" in recordNames)



        def test_queryRecordsWithAttribute_list_groupMembers_recordName_master(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDSNAttrRecordName,
                "odtestgrouptop",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeGroups,
                [
                    dsattributes.kDSNAttrGroupMembers,
                    dsattributes.kDSNAttrNestedGroups,
                ],
                count=0
            ))
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestgrouptop" in recordNames)
            groupMembers = results[0][1][dsattributes.kDSNAttrGroupMembers]
            self.assertEquals(
                groupMembers,
                setup_directory.masterGroups[0][1][OpenDirectory.kODAttributeTypeGroupMembers]
            )

        def test_queryRecordsWithAttribute_list_groupMembers_recordName_local(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDSNAttrRecordName,
                "odtestsubgroupa",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeGroups,
                [
                    dsattributes.kDSNAttrGroupMembers,
                    dsattributes.kDSNAttrNestedGroups,
                ],
                count=0
            ))
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestsubgroupa" in recordNames)
            groupMembers = results[0][1][dsattributes.kDSNAttrGroupMembers]
            self.assertEquals(
                groupMembers,
                setup_directory.localGroups[0][1][OpenDirectory.kODAttributeTypeGroupMembers]
            )


        def test_queryRecordsWithAttribute_list_groupMembers_guid_master(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrGeneratedUID,
                "6c6cd280-e6e3-11df-9492-0800200c9a66",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeGroups,
                [
                    dsattributes.kDSNAttrGroupMembers,
                    dsattributes.kDSNAttrNestedGroups,
                ],
                count=0
            ))
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestgrouptop" in recordNames)
            groupMembers = results[0][1][dsattributes.kDSNAttrGroupMembers]
            self.assertEquals(
                groupMembers,
                setup_directory.masterGroups[0][1][OpenDirectory.kODAttributeTypeGroupMembers]
            )

        def test_queryRecordsWithAttribute_list_groupMembers_guid_local(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrGeneratedUID,
                "6c6cd281-e6e3-11df-9492-0800200c9a66",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeGroups,
                [
                    dsattributes.kDSNAttrGroupMembers,
                    dsattributes.kDSNAttrNestedGroups,
                ],
                count=0
            ))
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestsubgroupa" in recordNames)
            groupMembers = results[0][1][dsattributes.kDSNAttrGroupMembers]
            self.assertEquals(
                groupMembers,
                setup_directory.localGroups[0][1][OpenDirectory.kODAttributeTypeGroupMembers]
            )


        def test_queryRecordsWithAttribute_list_groupsForGUID(self):

            directory = opendirectory.odInit("/Search")

            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDSNAttrGroupMembers,
                "9dc04a70-e6dd-11df-9492-0800200c9a66",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeGroups,
                [
                    dsattributes.kDS1AttrGeneratedUID,
                ],
                count=0
            ))
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestgrouptop" in recordNames)


            results = list(opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDSNAttrNestedGroups,
                "9dc04a70-e6dd-11df-9492-0800200c9a66",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeGroups,
                [
                    dsattributes.kDS1AttrGeneratedUID,
                ],
                count=0
            ))
            recordNames = [x[0] for x in results]
            self.assertEquals([], recordNames)

        def test_queryRecordsWithAttributes_list_master(self):

            directory = opendirectory.odInit("/Search")

            expressions = [
                dsquery.match(dsattributes.kDS1AttrDistinguishedName, "aman", "starts-with"),
                dsquery.match(dsattributes.kDS1AttrFirstName, "amanda", "equals"),
                dsquery.match(dsattributes.kDS1AttrLastName, "es", "contains"),
                dsquery.match(dsattributes.kDSNAttrEMailAddress, "amanda@", "starts-with"),
            ]

            compound = dsquery.expression(dsquery.expression.OR, expressions).generate()

            results = list(opendirectory.queryRecordsWithAttributes_list(
                directory,
                compound,
                True,
                [
                    dsattributes.kDSStdRecordTypeUsers,
                    dsattributes.kDSStdRecordTypeGroups,
                    dsattributes.kDSStdRecordTypeResources,
                    dsattributes.kDSStdRecordTypePlaces,
                ],
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            # Master user:
            self.assertTrue("odtestamanda" in recordNames)

        def test_queryRecordsWithAttributes_list_local(self):

            directory = opendirectory.odInit("/Search")

            expressions = [
                dsquery.match(dsattributes.kDS1AttrDistinguishedName, "bil", "starts-with"),
                dsquery.match(dsattributes.kDS1AttrFirstName, "Bill", "equals"),
                dsquery.match(dsattributes.kDS1AttrLastName, "es", "contains"),
                dsquery.match(dsattributes.kDSNAttrEMailAddress, "bill@", "starts-with"),
            ]

            compound = dsquery.expression(dsquery.expression.OR, expressions).generate()

            results = list(opendirectory.queryRecordsWithAttributes_list(
                directory,
                compound,
                True,
                [
                    dsattributes.kDSStdRecordTypeUsers,
                    dsattributes.kDSStdRecordTypeGroups,
                    dsattributes.kDSStdRecordTypeResources,
                    dsattributes.kDSStdRecordTypePlaces,
                ],
                USER_ATTRIBUTES,
                count=0
            ))
            recordNames = [x[0] for x in results]
            # Local user:
            self.assertTrue("odtestbill" in recordNames)


        def test_getUserRecord_existing(self):
            directory = opendirectory.odInit("/Search")
            record = opendirectory.getUserRecord(directory, "odtestbill")
            self.assertNotEquals(record, None)

        def test_getUserRecord_missing(self):
            directory = opendirectory.odInit("/Search")
            record = opendirectory.getUserRecord(directory, "i_do_not_exist")
            self.assertEquals(record, None)

        def test_basicAuth_master(self):
            directory = opendirectory.odInit("/Search")
            result = opendirectory.authenticateUserBasic(directory,
                "/LDAPv3/127.0.0.1", "odtestamanda", "password")
            self.assertTrue(result)

        def test_basicAuth_local(self):
            directory = opendirectory.odInit("/Search")
            result = opendirectory.authenticateUserBasic(directory,
                "/Local/Default", "odtestalbert", "password")
            self.assertTrue(result)

        def test_unicode_results(self):
            directory = opendirectory.odInit("/Search")
            record = opendirectory.getUserRecord(directory, "odtestbill")
            name, data = opendirectory.recordToResult(record)
            for value in data.values():
                if isinstance(value, list):
                    for item in value:
                        self.assertTrue(type(item) is unicode)
                else:
                    self.assertTrue(type(value) is unicode)

