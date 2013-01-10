##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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
import hashlib
import random
import sys

runTests = False

try:
    from calendarserver.platform.darwin.od import opendirectory, dsattributes, dsquery, setup_directory

    directory = opendirectory.odInit("/Search")

    results = opendirectory.queryRecordsWithAttribute_list(
        directory,
        dsattributes.kDS1AttrGeneratedUID,
        "9DC04A74-E6DD-11DF-9492-0800200C9A66",
        dsattributes.eDSExact,
        False,
        dsattributes.kDSStdRecordTypeUsers,
        None,
        count=0
    )
    recordNames = [x[0] for x in results]
    # Local user:
    if "odtestalbert" in recordNames:
        runTests = True
    else:
        print "Please run setup_directory.py to populate OD"

except ImportError:
    print "Unable to import OpenDirectory framework"


def generateNonce():
    c = tuple([random.randrange(sys.maxint) for _ in range(3)])
    c = '%d%d%d' % c
    return c

def getChallengeResponse(user, password, node, uri, method):
    nonce = generateNonce()

    ha1 = hashlib.md5("%s:%s:%s" % (user, node, password)).hexdigest()
    ha2 = hashlib.md5("%s:%s" % (method, uri)).hexdigest()
    response = hashlib.md5("%s:%s:%s"% (ha1, nonce, ha2)).hexdigest()

    fields = {
        'username': user,
        'nonce': nonce,
        'realm': node,
        'algorithm': 'md5',
        'uri': uri,
        'response': response,
    }

    challenge = 'Digest realm="%(realm)s", nonce="%(nonce)s", algorithm=%(algorithm)s' % fields

    response = (
        'Digest username="%(username)s", '
        'realm="%(realm)s", '
        'nonce="%(nonce)s", '
        'uri="%(uri)s", '
        'response="%(response)s",'
        'algorithm=%(algorithm)s'
    ) % fields

    return challenge, response

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
        (dsattributes.kDSNAttrJPEGPhoto, "base64"),
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
                opendirectory.adjustMatchType(dsattributes.eDSExact, False),
                dsattributes.eDSExact
            )
            self.assertEquals(
                opendirectory.adjustMatchType(dsattributes.eDSExact, True),
                dsattributes.eDSExact | 0x100
            )

        def test_getNodeAttributes(self):

            directory = opendirectory.odInit("/Search")
            results = opendirectory.getNodeAttributes(directory, "/Search", [dsattributes.kDS1AttrSearchPath])
            self.assertTrue("/Local/Default" in results[dsattributes.kDS1AttrSearchPath])
            self.assertTrue("/LDAPv3/127.0.0.1" in results[dsattributes.kDS1AttrSearchPath])

        def test_listAllRecordsWithAttributes_list_master(self):

            directory = opendirectory.odInit("/LDAPv3/127.0.0.1")
            results = opendirectory.listAllRecordsWithAttributes_list(
                directory,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            )
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.masterUsers:
                self.assertTrue(recordName in recordNames)

        def test_listAllRecordsWithAttributes_list_local(self):

            directory = opendirectory.odInit("/Local/Default")
            results = opendirectory.listAllRecordsWithAttributes_list(
                directory,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            )
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.localUsers:
                self.assertTrue(recordName in recordNames)


        def test_queryRecordsWithAttribute_list_firstname_exact_insensitive_match(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrFirstName,
                "betty",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            )
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestbetty" in recordNames)

        def test_queryRecordsWithAttribute_list_firstname_exact_insensitive_match_multitype(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
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
            )
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestbetty" in recordNames)

        def test_queryRecordsWithAttribute_list_firstname_begins_insensitive_match(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrFirstName,
                "Amand",
                dsattributes.eDSStartsWith,
                True,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            )
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestamanda" in recordNames)

        def test_queryRecordsWithAttribute_list_firstname_begins_insensitive_match_multitype(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
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
            )
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestamanda" in recordNames)

        def test_queryRecordsWithAttribute_list_firstname_contains_insensitive_match(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrFirstName,
                "mand",
                dsattributes.eDSContains,
                True,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            )
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestamanda" in recordNames)

        def test_queryRecordsWithAttribute_list_firstname_contains_insensitive_match_multitype(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
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
            )
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestamanda" in recordNames)

        def test_queryRecordsWithAttribute_list_lastname_exact_insensitive_match(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrLastName,
                "test",
                dsattributes.eDSExact,
                True,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            )
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.masterUsers:
                if info[dsattributes.kDS1AttrLastName] == "Test":
                    self.assertTrue(recordName in recordNames)
            for recordName, info in setup_directory.localUsers:
                if info[dsattributes.kDS1AttrLastName] == "Test":
                    self.assertTrue(recordName in recordNames)

        def test_queryRecordsWithAttribute_list_lastname_exact_insensitive_match_multitype(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
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
            )
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.masterUsers:
                if info[dsattributes.kDS1AttrLastName] == "Test":
                    self.assertTrue(recordName in recordNames)
            for recordName, info in setup_directory.localUsers:
                if info[dsattributes.kDS1AttrLastName] == "Test":
                    self.assertTrue(recordName in recordNames)

        def test_queryRecordsWithAttribute_list_lastname_begins_insensitive_match(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrLastName,
                "tes",
                dsattributes.eDSStartsWith,
                True,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            )
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.masterUsers:
                self.assertTrue(recordName in recordNames)
            for recordName, info in setup_directory.localUsers:
                self.assertTrue(recordName in recordNames)

        def test_queryRecordsWithAttribute_list_lastname_begins_insensitive_match_multitype(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
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
            )
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.masterUsers:
                self.assertTrue(recordName in recordNames)
            for recordName, info in setup_directory.localUsers:
                self.assertTrue(recordName in recordNames)

        def test_queryRecordsWithAttribute_list_lastname_contains_insensitive_match(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrLastName,
                "es",
                dsattributes.eDSContains,
                True,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            )
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.masterUsers:
                self.assertTrue(recordName in recordNames)
            for recordName, info in setup_directory.localUsers:
                self.assertTrue(recordName in recordNames)

        def test_queryRecordsWithAttribute_list_lastname_contains_insensitive_match_multitype(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
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
            )
            recordNames = [x[0] for x in results]
            for recordName, info in setup_directory.masterUsers:
                self.assertTrue(recordName in recordNames)
            for recordName, info in setup_directory.localUsers:
                self.assertTrue(recordName in recordNames)

        def test_queryRecordsWithAttribute_list_email_begins_insensitive_match(self):
            # This test won't pass until this is fixed: <rdar://problem/8608148>

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDSNAttrEMailAddress,
                "aman",
                dsattributes.eDSStartsWith,
                True,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            )
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestamanda" in recordNames)


        def test_queryRecordsWithAttribute_list_email_begins_insensitive_match_multitype(self):
            # This test won't pass until this is fixed: <rdar://problem/8608148>

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
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
            )
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestamanda" in recordNames)



        def test_queryRecordsWithAttribute_list_guid_exact_sensitive_match_master(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrGeneratedUID,
                "9DC04A70-E6DD-11DF-9492-0800200C9A66",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            )
            recordNames = [x[0] for x in results]
            # OD Master user:
            self.assertTrue("odtestamanda" in recordNames)

        def test_queryRecordsWithAttribute_list_guid_exact_sensitive_match_multitype_master(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrGeneratedUID,
                "9DC04A70-E6DD-11DF-9492-0800200C9A66",
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
            )
            recordNames = [x[0] for x in results]
            # OD Master user:
            self.assertTrue("odtestamanda" in recordNames)


        def test_queryRecordsWithAttribute_list_guid_exact_sensitive_match_local(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrGeneratedUID,
                "9DC04A74-E6DD-11DF-9492-0800200C9A66",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            )
            recordNames = [x[0] for x in results]
            # Local user:
            self.assertTrue("odtestalbert" in recordNames)


        def test_queryRecordsWithAttribute_list_guid_exact_sensitive_match_multitype_local(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrGeneratedUID,
                "9DC04A74-E6DD-11DF-9492-0800200C9A66",
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
            )
            recordNames = [x[0] for x in results]
            # Local user:
            self.assertTrue("odtestalbert" in recordNames)



        def test_queryRecordsWithAttribute_list_groupMembers_recordName_master(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
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
            )
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestgrouptop" in recordNames)
            groupMembers = results[0][1][dsattributes.kDSNAttrGroupMembers]
            self.assertEquals(
                set(groupMembers),
                set(setup_directory.masterGroups[1][1][dsattributes.kDSNAttrGroupMembers])
            )

        def test_queryRecordsWithAttribute_list_groupMembers_recordName_local(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
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
            )
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestsubgroupa" in recordNames)
            groupMembers = results[0][1][dsattributes.kDSNAttrGroupMembers]
            self.assertEquals(
                set(groupMembers),
                set(setup_directory.localGroups[0][1][dsattributes.kDSNAttrGroupMembers])
            )


        def test_queryRecordsWithAttribute_list_groupMembers_guid_master(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrGeneratedUID,
                "6C6CD280-E6E3-11DF-9492-0800200C9A66",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeGroups,
                [
                    dsattributes.kDSNAttrGroupMembers,
                    dsattributes.kDSNAttrNestedGroups,
                ],
                count=0
            )
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestgrouptop" in recordNames)
            groupMembers = results[0][1][dsattributes.kDSNAttrGroupMembers]
            self.assertEquals(
                set(groupMembers),
                set(setup_directory.masterGroups[1][1][dsattributes.kDSNAttrGroupMembers])
            )

        def test_queryRecordsWithAttribute_list_groupMembers_guid_local(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrGeneratedUID,
                "6C6CD281-E6E3-11DF-9492-0800200C9A66",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeGroups,
                [
                    dsattributes.kDSNAttrGroupMembers,
                    dsattributes.kDSNAttrNestedGroups,
                ],
                count=0
            )
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestsubgroupa" in recordNames)
            groupMembers = results[0][1][dsattributes.kDSNAttrGroupMembers]
            self.assertEquals(
                groupMembers,
                setup_directory.localGroups[0][1][dsattributes.kDSNAttrGroupMembers]
            )


        def test_queryRecordsWithAttribute_list_groupsForGUID(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDSNAttrGroupMembers,
                "9DC04A70-E6DD-11DF-9492-0800200C9A66",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeGroups,
                [
                    dsattributes.kDS1AttrGeneratedUID,
                ],
                count=0
            )
            recordNames = [x[0] for x in results]
            self.assertTrue("odtestgrouptop" in recordNames)


            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDSNAttrNestedGroups,
                "9DC04A70-E6DD-11DF-9492-0800200C9A66",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeGroups,
                [
                    dsattributes.kDS1AttrGeneratedUID,
                ],
                count=0
            )
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

            results = opendirectory.queryRecordsWithAttributes_list(
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
            )
            recordNames = [x[0] for x in results]
            # Master user:
            self.assertTrue("odtestamanda" in recordNames)

        def test_queryRecordsWithAttributes_list_nonascii(self):

            directory = opendirectory.odInit("/Search")

            expressions = [
                dsquery.match(dsattributes.kDS1AttrFirstName, "\xe4\xbd\x90", "contains"),
                dsquery.match(dsattributes.kDS1AttrLastName, "Test", "contains"),
            ]

            compound = dsquery.expression(dsquery.expression.AND, expressions).generate()

            results = opendirectory.queryRecordsWithAttributes_list(
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
            )
            recordNames = [x[0] for x in results]
            # Master user:
            self.assertTrue("odtestsatou" in recordNames)


        def test_queryRecordsWithAttributes_list_local(self):

            directory = opendirectory.odInit("/Search")

            expressions = [
                dsquery.match(dsattributes.kDS1AttrDistinguishedName, "bil", "starts-with"),
                dsquery.match(dsattributes.kDS1AttrFirstName, "Bill", "equals"),
                dsquery.match(dsattributes.kDS1AttrLastName, "es", "contains"),
                dsquery.match(dsattributes.kDSNAttrEMailAddress, "bill@", "starts-with"),
            ]

            compound = dsquery.expression(dsquery.expression.OR, expressions).generate()

            results = opendirectory.queryRecordsWithAttributes_list(
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
            )
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

        def test_digestAuth_master(self):
            directory = opendirectory.odInit("/Search")

            user = "odtestamanda"
            password = "password"
            node = "/LDAPv3/127.0.0.1"
            uri = "principals/users/odtestamanda"
            method = "PROPFIND"

            challenge, response = getChallengeResponse(user, password, node,
                uri, method)

            result = opendirectory.authenticateUserDigest(directory, node,
                user, challenge, response, method)
            self.assertTrue(result)

        def test_digestAuth_master_wrong_password(self):
            directory = opendirectory.odInit("/Search")

            user = "odtestamanda"
            password = "wrong"
            node = "/LDAPv3/127.0.0.1"
            uri = "principals/users/odtestamanda"
            method = "PROPFIND"

            challenge, response = getChallengeResponse(user, password, node,
                uri, method)

            self.assertEquals(
                False,
                opendirectory.authenticateUserDigest(directory, node, user,
                    challenge, response, method)
            )

        def test_digestAuth_master_missing_record(self):
            directory = opendirectory.odInit("/Search")

            user = "missingperson"
            password = "wrong"
            node = "/LDAPv3/127.0.0.1"
            uri = "principals/users/odtestamanda"
            method = "PROPFIND"

            challenge, response = getChallengeResponse(user, password, node,
                uri, method)

            self.assertRaises(opendirectory.ODError,
                opendirectory.authenticateUserDigest,
                directory, node, user, challenge, response, method)

        def test_digestAuth_local(self):
            directory = opendirectory.odInit("/Search")

            user = "odtestalbert"
            password = "password"
            node = "/Local/Default"
            uri = "principals/users/odtestalbert"
            method = "PROPFIND"

            challenge, response = getChallengeResponse(user, password, node,
                uri, method)

            result = opendirectory.authenticateUserDigest(directory, node,
                user, challenge, response, method)
            self.assertTrue(result)

        def test_result_types(self):
            directory = opendirectory.odInit("/Search")
            record = opendirectory.getUserRecord(directory, "odtestbill")
            name, data = opendirectory.recordToResult(record, {})
            for value in data.values():
                if isinstance(value, list):
                    for item in value:
                        self.assertTrue(type(item) is str)
                else:
                    self.assertTrue(type(value) is str)

        def test_nonascii_record_by_guid(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrGeneratedUID,
                "CA795296-D77A-4E09-A72F-869920A3D284",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            )
            result = results[0][1]
            self.assertEquals(
                result[dsattributes.kDS1AttrDistinguishedName],
                "Unicode Test \xc3\x90"
            )

        def test_nonascii_record_by_name(self):

            directory = opendirectory.odInit("/Search")

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrDistinguishedName,
                "Unicode Test \xc3\x90",
                dsattributes.eDSExact,
                False,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            )
            result = results[0][1]
            self.assertEquals(
                result[dsattributes.kDS1AttrGeneratedUID],
                "CA795296-D77A-4E09-A72F-869920A3D284"
            )

            results = opendirectory.queryRecordsWithAttribute_list(
                directory,
                dsattributes.kDS1AttrFirstName,
                "\xe4\xbd\x90\xe8\x97\xa4",
                dsattributes.eDSStartsWith,
                False,
                dsattributes.kDSStdRecordTypeUsers,
                USER_ATTRIBUTES,
                count=0
            )
            result = results[0][1]
            self.assertEquals(
                result[dsattributes.kDS1AttrGeneratedUID],
                "C662F833-75AD-4589-9879-5FF102943CEF"
            )

        def test_attributeNamesFromList(self):
            self.assertEquals(
                ([], {}), opendirectory.attributeNamesFromList(None)
            )
            self.assertEquals(
                (["a", "b"], {"b":"base64"}),
                opendirectory.attributeNamesFromList(["a", ("b", "base64")])
            )

        def test_autoPooled(self):
            """
            Make sure no exception is raised by an autoPooled method
            """
            @opendirectory.autoPooled
            def method(x):
                return x + 1

            self.assertEquals(2, method(1))
