##
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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
from __future__ import print_function

runLDAPTests = False
runODTests = False

try:
    import ldap
    import socket

    testServer = "localhost"
    base = ",".join(["dc=%s" % (p,) for p in socket.gethostname().split(".")])
    print("Using base: %s" % (base,))

    try:
        cxn = ldap.open(testServer)
        results = cxn.search_s(base, ldap.SCOPE_SUBTREE, "(uid=odtestamanda)",
            ["cn"])
        if len(results) == 1:
            runLDAPTests = True
    except ldap.LDAPError:
        pass # Don't run live tests

except ImportError:
    print("Could not import ldap module (skipping LDAP tests)")

try:
    from calendarserver.platform.darwin.od import opendirectory, dsattributes

    directory = opendirectory.odInit("/Search")

    results = list(opendirectory.queryRecordsWithAttribute_list(
        directory,
        dsattributes.kDS1AttrGeneratedUID,
        "9DC04A70-E6DD-11DF-9492-0800200C9A66",
        dsattributes.eDSExact,
        False,
        dsattributes.kDSStdRecordTypeUsers,
        None,
        count=0
    ))
    recordNames = [x[0] for x in results]
    if "odtestamanda" in recordNames:
        runODTests = True
    else:
        print("Test OD records not found (skipping OD tests)")

except ImportError:
    print("Could not import OpenDirectory framework (skipping OD tests)")


if runLDAPTests or runODTests:

    from twistedcaldav.test.util import TestCase
    from twistedcaldav.directory import augment
    from twistedcaldav.directory.test.test_xmlfile import augmentsFile
    from twisted.internet.defer import inlineCallbacks

    class LiveDirectoryTests(object):

        def test_ldapRecordWithShortName(self):
            record = self.svc.recordWithShortName("users", "odtestamanda")
            self.assertTrue(record is not None)

        def test_ldapRecordWithGUID(self):
            record = self.svc.recordWithGUID("9DC04A70-E6DD-11DF-9492-0800200C9A66")
            self.assertTrue(record is not None)

        @inlineCallbacks
        def test_ldapRecordsMatchingFields(self):
            fields = (
                ("firstName", "Amanda", True, "exact"),
                ("lastName", "Te", True, "starts-with"),
            )
            records = list(
                (yield self.svc.recordsMatchingFields(fields, operand="and"))
            )
            self.assertEquals(1, len(records))
            record = self.svc.recordWithGUID("9DC04A70-E6DD-11DF-9492-0800200C9A66")
            self.assertEquals(records, [record])

        @inlineCallbacks
        def test_restrictToGroup(self):
            self.svc.restrictEnabledRecords = True
            self.svc.restrictToGroup = "odtestgrouptop"

            # Faulting in specific records will return records outside of
            # the restrictToGroup, but they won't be enabledForCalendaring
            # and AddressBooks:

            # Amanda is a direct member of that group
            record = self.svc.recordWithShortName("users", "odtestamanda")
            self.assertTrue(record.enabledForCalendaring)
            self.assertTrue(record.enabledForAddressBooks)

            # Betty is a direct member of that group
            record = self.svc.recordWithShortName("users", "odtestbetty")
            self.assertTrue(record.enabledForCalendaring)
            self.assertTrue(record.enabledForAddressBooks)

            # Carlene is in a nested group
            record = self.svc.recordWithShortName("users", "odtestcarlene")
            self.assertTrue(record.enabledForCalendaring)
            self.assertTrue(record.enabledForAddressBooks)

            # Denise is not in the group
            record = self.svc.recordWithShortName("users", "odtestdenise")
            self.assertFalse(record.enabledForCalendaring)
            self.assertFalse(record.enabledForAddressBooks)

            # Searching for records using principal-property-search will not
            # yield records outside of the restrictToGroup:

            fields = (
                ("lastName", "Test", True, "exact"),
            )
            records = list(
                (yield self.svc.recordsMatchingFields(fields))
            )
            self.assertEquals(3, len(records))

            # These two are directly in the restrictToGroup:
            record = self.svc.recordWithShortName("users", "odtestamanda")
            self.assertTrue(record in records)
            record = self.svc.recordWithShortName("users", "odtestbetty")
            self.assertTrue(record in records)
            # Carlene is still picked up because she is in a nested group
            record = self.svc.recordWithShortName("users", "odtestcarlene")
            self.assertTrue(record in records)



    if runLDAPTests:

        from twistedcaldav.directory.ldapdirectory import LdapDirectoryService
        print("Running live LDAP tests against %s" % (testServer,))

        class LiveLDAPDirectoryServiceCase(LiveDirectoryTests, TestCase):

            def setUp(self):
                params = {
                    "augmentService":
                        augment.AugmentXMLDB(xmlFiles=(augmentsFile.path,)),
                    "uri": "ldap://%s" % (testServer,),
                    "rdnSchema": {
                        "base": base,
                        "guidAttr": "apple-generateduid",
                        "users": {
                            "rdn": "cn=users",
                            "attr": "uid", # used only to synthesize email address
                            "emailSuffix": None, # used only to synthesize email address
                            "filter": None, # additional filter for this type
                            "loginEnabledAttr" : "", # attribute controlling login
                            "loginEnabledValue" : "yes", # "True" value of above attribute
                            "mapping" : { # maps internal record names to LDAP
                                "recordName": "uid",
                                "fullName" : "cn",
                                "emailAddresses" : ["mail"], # multiple LDAP fields supported
                                "firstName" : "givenName",
                                "lastName" : "sn",
                            },
                        },
                        "groups": {
                            "rdn": "cn=groups",
                            "attr": "cn", # used only to synthesize email address
                            "emailSuffix": None, # used only to synthesize email address
                            "filter": None, # additional filter for this type
                            "mapping" : { # maps internal record names to LDAP
                                "recordName": "cn",
                                "fullName" : "cn",
                                "emailAddresses" : ["mail"], # multiple LDAP fields supported
                                "firstName" : "givenName",
                                "lastName" : "sn",
                            },
                        },
                    },
                    "groupSchema": {
                        "membersAttr": "apple-group-memberguid", # how members are specified
                        "nestedGroupsAttr" : "apple-group-nestedgroup", # how nested groups are specified
                        "memberIdAttr": "apple-generateduid", # which attribute the above refers to
                    },
                }
                self.svc = LdapDirectoryService(params)


    if runODTests:

        from twistedcaldav.directory.appleopendirectory import OpenDirectoryService
        print("Running live OD tests")

        class LiveODDirectoryServiceCase(LiveDirectoryTests, TestCase):

            def setUp(self):
                params = {
                    "augmentService":
                        augment.AugmentXMLDB(xmlFiles=(augmentsFile.path,)),
                }
                self.svc = OpenDirectoryService(params)
