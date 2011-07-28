##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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
    from twistedcaldav.directory.ldapdirectory import buildFilter, LdapDirectoryService
except ImportError:
    print "Skipping because ldap module not installed"
else:
    from twistedcaldav.test.util import TestCase

    class BuildFilterTestCase(TestCase):

        def test_buildFilter(self):
            mapping = {
                "fullName" : "cn",
                "emailAddresses" : "mail",
                "firstName" : "givenName",
                "lastName" : "sn",
            }

            entries = [
                {
                    "fields" : [
                        ("fullName", "mor", True, u"starts-with"),
                        ("emailAddresses", "mor", True, u"starts-with"),
                        ("firstName", "mor", True, u"starts-with"),
                        ("lastName", "mor", True, u"starts-with")
                    ],
                    "operand" : "or",
                    "recordType" : None,
                    "expected" : "(|(cn=mor*)(mail=mor*)(givenName=mor*)(sn=mor*))"
                },
                {
                    "fields" : [
                        ("fullName", "mor", True, u"starts-with"),
                    ],
                    "operand" : "or",
                    "recordType" : None,
                    "expected" : "(cn=mor*)"
                },
                {
                    "fields" : [
                        ("fullName", "mor", True, u"contains"),
                        ("emailAddresses", "mor", True, u"equals"),
                        ("invalid", "mor", True, u"starts-with"),
                    ],
                    "operand" : "and",
                    "recordType" : None,
                    "expected" : "(&(cn=*mor*)(mail=mor))"
                },
                {
                    "fields" : [
                        ("invalid", "mor", True, u"contains"),
                        ("invalid", "mor", True, u"starts-with"),
                    ],
                    "operand" : "and",
                    "recordType" : None,
                    "expected" : None
                },
                {
                    "fields" : [ ],
                    "operand" : "and",
                    "recordType" : None,
                    "expected" : None
                },
            ]
            for entry in entries:
                self.assertEquals(
                    buildFilter(mapping, entry["fields"],
                        operand=entry["operand"]),
                    entry["expected"]
                )


    class LdapDirectoryTestWrapper(object):
        """
        A test stub which replaces search_s( ) with a version that will return
        whatever you have previously called setTestResults( ) with.
        """

        def __init__(self, actual):
            self.actual = actual
            self.testResults = None

        def setTestResults(self, results):
            self.testResults = results

        def search_s(self, base, scope, filter="(objectClass=*)",
            attrList=None):
            return self.testResults


    class LdapDirectoryServiceTestCase(TestCase):

        def setUp(self):
            params = {
                "augmentService" : None,
                "groupMembershipCache" : None,
                "cacheTimeout": 1, # Minutes
                "negativeCaching": False,
                "restrictEnabledRecords": False,
                "restrictToGroup": "",
                "recordTypes": ("users", "groups", "locations", "resources"),
                "uri": "ldap://localhost/",
                "tls": False,
                "tlsCACertFile": None,
                "tlsCACertDir": None,
                "tlsRequireCert": None, # never, allow, try, demand, hard
                "credentials": {
                    "dn": None,
                    "password": None,
                },
                "authMethod": "LDAP",
                "rdnSchema": {
                    "base": "dc=example,dc=com",
                    "guidAttr": "apple-generateduid",
                    "users": {
                        "rdn": "cn=users",
                        "attr": "uid", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "(objectClass=apple-user)", # additional filter for this type
                        "loginEnabledAttr" : "", # attribute controlling login
                        "loginEnabledValue" : "yes", # "True" value of above attribute
                        "calendarEnabledAttr" : "enable-calendar", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "uid",
                            "fullName" : "cn",
                            "emailAddresses" : "mail",
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                    "groups": {
                        "rdn": "cn=groups",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "(objectClass=apple-group)", # additional filter for this type
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : "mail",
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                    "locations": {
                        "rdn": "cn=places",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "(objectClass=apple-resource)", # additional filter for this type
                        "calendarEnabledAttr" : "", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : "mail",
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                    "resources": {
                        "rdn": "cn=resources",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "(objectClass=apple-resource)", # additional filter for this type
                        "calendarEnabledAttr" : "", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : "mail",
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                },
                "groupSchema": {
                    "membersAttr": "apple-group-memberguid", # how members are specified
                    "nestedGroupsAttr": "apple-group-nestedgroup", # how nested groups are specified
                    "memberIdAttr": "apple-generateduid", # which attribute the above refer to
                },
                "resourceSchema": {
                    "resourceInfoAttr": "apple-resource-info", # contains location/resource info
                    "autoScheduleAttr": None,
                    "proxyAttr": None,
                    "readOnlyProxyAttr": None,
                },
                "partitionSchema": {
                    "serverIdAttr": "server-id", # maps to augments server-id
                    "partitionIdAttr": "partition-id", # maps to augments partition-id
                },
            }

            self.service = LdapDirectoryService(params)
            self.service.ldap = LdapDirectoryTestWrapper(self.service.ldap)


        def test_ldapRecordCreation(self):
            """
            Exercise _ldapResultToRecord(), which converts a dictionary
            of LDAP attributes into an LdapDirectoryRecord
            """

            # User without enabled-for-calendaring specified

            dn = "uid=odtestamanda,cn=users,dc=example,dc=com"
            guid = '9DC04A70-E6DD-11DF-9492-0800200C9A66'
            attrs = {
                'uid': ['odtestamanda'],
                'apple-generateduid': [guid],
                'sn': ['Test'],
                'mail': ['odtestamanda@example.com', 'alternate@example.com'],
                'givenName': ['Amanda'],
                'cn': ['Amanda Test']
            }

            record = self.service._ldapResultToRecord(dn, attrs,
                self.service.recordType_users)
            self.assertEquals(record.guid, guid)
            self.assertEquals(record.emailAddresses,
                set(['alternate@example.com', 'odtestamanda@example.com']))
            self.assertEquals(record.shortNames, ('odtestamanda',))
            self.assertEquals(record.fullName, 'Amanda Test')
            self.assertEquals(record.firstName, 'Amanda')
            self.assertEquals(record.lastName, 'Test')
            self.assertEquals(record.serverID, None)
            self.assertEquals(record.partitionID, None)
            self.assertFalse(record.enabledForCalendaring)

            # User with enabled-for-calendaring specified

            dn = "uid=odtestamanda,cn=users,dc=example,dc=com"
            guid = '9DC04A70-E6DD-11DF-9492-0800200C9A66'
            attrs = {
                'uid': ['odtestamanda'],
                'apple-generateduid': [guid],
                'enable-calendar': ["yes"],
                'sn': ['Test'],
                'mail': ['odtestamanda@example.com', 'alternate@example.com'],
                'givenName': ['Amanda'],
                'cn': ['Amanda Test']
            }

            record = self.service._ldapResultToRecord(dn, attrs,
                self.service.recordType_users)
            self.assertTrue(record.enabledForCalendaring)

            # User with "podding" info

            dn = "uid=odtestamanda,cn=users,dc=example,dc=com"
            guid = '9DC04A70-E6DD-11DF-9492-0800200C9A66'
            attrs = {
                'uid': ['odtestamanda'],
                'apple-generateduid': [guid],
                'cn': ['Amanda Test'],
                'server-id' : ["test-server-id"],
                'partition-id' : ["test-partition-id"],
            }

            record = self.service._ldapResultToRecord(dn, attrs,
                self.service.recordType_users)
            self.assertEquals(record.serverID, "test-server-id")
            self.assertEquals(record.partitionID, "test-partition-id")

            # Group with direct user members and nested group

            dn = "cn=odtestgrouptop,cn=groups,dc=example,dc=com"
            guid = '6C6CD280-E6E3-11DF-9492-0800200C9A66'
            attrs = {
                'apple-generateduid': [guid],
                'apple-group-memberguid':
                    [
                        '9DC04A70-E6DD-11DF-9492-0800200C9A66',
                        '9DC04A71-E6DD-11DF-9492-0800200C9A66'
                    ],
                'apple-group-nestedgroup':
                    [
                        '6C6CD282-E6E3-11DF-9492-0800200C9A66'
                    ],
                'cn': ['odtestgrouptop']
            }
            record = self.service._ldapResultToRecord(dn, attrs,
                self.service.recordType_groups)
            self.assertEquals(record.guid, guid)
            self.assertEquals(record.memberGUIDs(),
                set(['6C6CD282-E6E3-11DF-9492-0800200C9A66',
                     '9DC04A70-E6DD-11DF-9492-0800200C9A66',
                     '9DC04A71-E6DD-11DF-9492-0800200C9A66'])
            )

            # Resource with delegates and autoSchedule = True

            dn = "cn=odtestresource,cn=resources,dc=example,dc=com"
            guid = 'D3094652-344B-4633-8DB8-09639FA00FB6'
            attrs = {
                'apple-generateduid': [guid],
                'cn': ['odtestresource'],
                'apple-resource-info': ["""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
<key>com.apple.WhitePagesFramework</key>
<dict>
 <key>AutoAcceptsInvitation</key>
<true/>
<key>CalendaringDelegate</key>
<string>6C6CD280-E6E3-11DF-9492-0800200C9A66</string>
<key>ReadOnlyCalendaringDelegate</key>
<string>6AA1AE12-592F-4190-A069-547CD83C47C0</string>
</dict>
</dict>
</plist>"""]
            }
            record = self.service._ldapResultToRecord(dn, attrs,
                self.service.recordType_resources)
            self.assertEquals(record.guid, guid)
            self.assertEquals(record.externalProxies(),
                set(['6C6CD280-E6E3-11DF-9492-0800200C9A66']))
            self.assertEquals(record.externalReadOnlyProxies(),
                set(['6AA1AE12-592F-4190-A069-547CD83C47C0']))
            self.assertTrue(record.autoSchedule)

            # Resource with no delegates and autoSchedule = False

            dn = "cn=odtestresource,cn=resources,dc=example,dc=com"
            guid = 'D3094652-344B-4633-8DB8-09639FA00FB6'
            attrs = {
                'apple-generateduid': [guid],
                'cn': ['odtestresource'],
                'apple-resource-info': ["""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
<key>com.apple.WhitePagesFramework</key>
<dict>
 <key>AutoAcceptsInvitation</key>
<false/>
</dict>
</dict>
</plist>"""]
            }
            record = self.service._ldapResultToRecord(dn, attrs,
                self.service.recordType_resources)
            self.assertEquals(record.guid, guid)
            self.assertEquals(record.externalProxies(),
                set())
            self.assertEquals(record.externalReadOnlyProxies(),
                set())
            self.assertFalse(record.autoSchedule)


            # Now switch off the resourceInfoAttr and switch to individual
            # attributes...
            self.service.resourceSchema = {
                "resourceInfoAttr" : "",
                "autoScheduleAttr" : "auto-schedule",
                "autoScheduleEnabledValue" : "yes",
                "proxyAttr" : "proxy",
                "readOnlyProxyAttr" : "read-only-proxy",
            }

            # Resource with delegates and autoSchedule = True

            dn = "cn=odtestresource,cn=resources,dc=example,dc=com"
            guid = 'D3094652-344B-4633-8DB8-09639FA00FB6'
            attrs = {
                'apple-generateduid': [guid],
                'cn': ['odtestresource'],
                'auto-schedule' : ['yes'],
                'proxy' : ['6C6CD280-E6E3-11DF-9492-0800200C9A66'],
                'read-only-proxy' : ['6AA1AE12-592F-4190-A069-547CD83C47C0'],
            }
            record = self.service._ldapResultToRecord(dn, attrs,
                self.service.recordType_resources)
            self.assertEquals(record.guid, guid)
            self.assertEquals(record.externalProxies(),
                set(['6C6CD280-E6E3-11DF-9492-0800200C9A66']))
            self.assertEquals(record.externalReadOnlyProxies(),
                set(['6AA1AE12-592F-4190-A069-547CD83C47C0']))
            self.assertTrue(record.autoSchedule)

        def test_listRecords(self):
            """
            listRecords makes an LDAP query (with fake results in this test)
            and turns the results into records
            """

            self.service.ldap.setTestResults([
                (
                    "uid=odtestamanda,cn=users,dc=example,dc=com",
                    {
                        'uid': ['odtestamanda'],
                        'apple-generateduid': ['9DC04A70-E6DD-11DF-9492-0800200C9A66'],
                        'sn': ['Test'],
                        'mail': ['odtestamanda@example.com', 'alternate@example.com'],
                        'givenName': ['Amanda'],
                        'cn': ['Amanda Test']
                    }
                ),
                (
                    "uid=odtestbetty,cn=users,dc=example,dc=com",
                    {
                        'uid': ['odtestbetty'],
                        'apple-generateduid': ['93A8F5C5-49D8-4641-840F-CD1903B0394C'],
                        'sn': ['Test'],
                        'mail': ['odtestbetty@example.com'],
                        'givenName': ['Betty'],
                        'cn': ['Betty Test']
                    }
                ),
            ])
            records = self.service.listRecords(self.service.recordType_users)
            self.assertEquals(len(records), 2)
            self.assertEquals(
                set([r.firstName for r in records]),
                set(["Amanda", "Betty"])
            )
