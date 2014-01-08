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

try:
    from twistedcaldav.directory.ldapdirectory import (
        buildFilter, buildFilterFromTokens, LdapDirectoryService,
        MissingGuidException, MissingRecordNameException,
        normalizeDNstr, dnContainedIn
    )
    from twistedcaldav.directory.util import splitIntoBatches
    from twistedcaldav.test.util import proxiesFile
    from twistedcaldav.directory.calendaruserproxyloader import XMLCalendarUserProxyLoader
    from twistedcaldav.directory import calendaruserproxy
    from twistedcaldav.directory.directory import GroupMembershipCache, GroupMembershipCacheUpdater
    from twisted.internet.defer import inlineCallbacks
    from string import maketrans
    import ldap
except ImportError:
    print("Skipping because ldap module not installed")
else:
    from twistedcaldav.test.util import TestCase

    class BuildFilterTestCase(TestCase):

        def test_buildFilter(self):
            mapping = {
                "recordName" : "uid",
                "fullName" : "cn",
                "emailAddresses" : "mail",
                "firstName" : "givenName",
                "lastName" : "sn",
                "guid" : "generateduid",
                "memberIDAttr" : "generateduid",
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
                    "recordType" : "users",
                    "expected" : "(&(uid=*)(generateduid=*)(|(cn=mor*)(mail=mor*)(givenName=mor*)(sn=mor*)))",
                    "optimize" : False,
                },
                {
                    "fields" : [
                        ("fullName", "mor(", True, u"starts-with"),
                        ("emailAddresses", "mor)", True, u"contains"),
                        ("firstName", "mor*", True, u"exact"),
                        ("lastName", "mor\\", True, u"starts-with")
                    ],
                    "operand" : "or",
                    "recordType" : "users",
                    "expected" : "(&(uid=*)(generateduid=*)(|(cn=mor\\28*)(mail=*mor\\29*)(givenName=mor\\2a)(sn=mor\\5c*)))",
                    "optimize" : False,
                },
                {
                    "fields" : [
                        ("fullName", "mor", True, u"starts-with"),
                    ],
                    "operand" : "or",
                    "recordType" : "users",
                    "expected" : "(&(uid=*)(generateduid=*)(cn=mor*))",
                    "optimize" : False,
                },
                {
                    "fields" : [
                        ("fullName", "mor", True, u"contains"),
                        ("emailAddresses", "mor", True, u"equals"),
                        ("invalid", "mor", True, u"starts-with"),
                    ],
                    "operand" : "and",
                    "recordType" : "users",
                    "expected" : "(&(uid=*)(generateduid=*)(&(cn=*mor*)(mail=mor)))",
                    "optimize" : False,
                },
                {
                    "fields" : [
                        ("invalid", "mor", True, u"contains"),
                        ("invalid", "mor", True, u"starts-with"),
                    ],
                    "operand" : "and",
                    "recordType" : "users",
                    "expected" : None,
                    "optimize" : False,
                },
                {
                    "fields" : [ ],
                    "operand" : "and",
                    "recordType" : "users",
                    "expected" : None,
                    "optimize" : False,
                },
                {
                    "fields" : [
                        ("fullName", "mor", True, u"starts-with"),
                        ("fullName", "sag", True, u"starts-with"),
                        ("emailAddresses", "mor", True, u"starts-with"),
                        ("emailAddresses", "sag", True, u"starts-with"),
                        ("firstName", "mor", True, u"starts-with"),
                        ("firstName", "sag", True, u"starts-with"),
                        ("lastName", "mor", True, u"starts-with"),
                        ("lastName", "sag", True, u"starts-with"),
                    ],
                    "operand" : "or",
                    "recordType" : "users",
                    "expected" : "(&(uid=*)(generateduid=*)(|(&(givenName=mor*)(sn=sag*))(&(givenName=sag*)(sn=mor*))))",
                    "optimize" : True,
                },
                {
                    "fields" : [
                        ("fullName", "mor", True, u"starts-with"),
                        ("fullName", "sag", True, u"starts-with"),
                        ("emailAddresses", "mor", True, u"starts-with"),
                        ("emailAddresses", "sag", True, u"starts-with"),
                        ("firstName", "mor", True, u"starts-with"),
                        ("firstName", "sag", True, u"starts-with"),
                        ("lastName", "mor", True, u"starts-with"),
                        ("lastName", "sag", True, u"starts-with"),
                    ],
                    "operand" : "or",
                    "recordType" : "groups",
                    "expected" : None,
                    "optimize" : True,
                },
                {
                    "fields" : [
                        ("fullName", "mor", True, u"starts-with"),
                        ("fullName", "sag", True, u"starts-with"),
                        ("emailAddresses", "mor", True, u"starts-with"),
                        ("emailAddresses", "sag", True, u"starts-with"),
                        ("firstName", "mor", True, u"starts-with"),
                        ("firstName", "sag", True, u"starts-with"),
                        ("lastName", "mor", True, u"starts-with"),
                        ("lastName", "sag", True, u"starts-with"),
                    ],
                    "operand" : "or",
                    "recordType" : "groups",
                    "expected" : None,
                    "optimize" : True,
                },
                {
                    "fields" : [
                        ("guid", "xyzzy", True, u"equals"),
                        ("guid", "plugh", True, u"equals"),
                    ],
                    "operand" : "or",
                    "recordType" : "groups",
                    "expected" : "(&(uid=*)(generateduid=*)(|(generateduid=xyzzy)(generateduid=plugh)))",
                    "optimize" : True,
                },
                {
                    "fields" : [
                        ("fullName", "mor", True, u"contains"),
                        ("fullName", "sag", True, u"contains"),
                    ],
                    "operand" : "or",
                    "recordType" : "locations",
                    "expected" : "(&(uid=*)(generateduid=*)(|(cn=*mor*)(cn=*sag*)))",
                    "optimize" : True,
                },
                {
                    "fields" : [
                        ("fullName", "mor", True, u"contains"),
                        ("fullName", "sag", True, u"contains"),
                    ],
                    "operand" : "or",
                    "recordType" : "resources",
                    "expected" : "(&(uid=*)(generateduid=*)(|(cn=*mor*)(cn=*sag*)))",
                    "optimize" : True,
                },
            ]
            for entry in entries:
                self.assertEquals(
                    buildFilter(entry["recordType"], mapping, entry["fields"],
                        operand=entry["operand"], optimizeMultiName=entry["optimize"]),
                    entry["expected"]
                )


    class BuildFilterFromTokensTestCase(TestCase):

        def test_buildFilterFromTokens(self):

            entries = [
                {
                    "tokens" : ["foo"],
                    "mapping" : {
                        "fullName" : "cn",
                        "emailAddresses" : "mail",
                    },
                    "expected" : "(&(a=b)(|(cn=*foo*)(mail=foo*)))",
                    "extra" : "(a=b)",
                },
                {
                    "tokens" : ["foo"],
                    "mapping" : {
                        "fullName" : "cn",
                        "emailAddresses" : ["mail", "mailAliases"],
                    },
                    "expected" : "(&(a=b)(|(cn=*foo*)(mail=foo*)(mailAliases=foo*)))",
                    "extra" : "(a=b)",
                },
                {
                    "tokens" : [],
                    "mapping" : {
                        "fullName" : "cn",
                        "emailAddresses" : "mail",
                    },
                    "expected" : None,
                    "extra" : None,
                },
                {
                    "tokens" : ["foo", "bar"],
                    "mapping" : { },
                    "expected" : None,
                    "extra" : None,
                },
                {
                    "tokens" : ["foo", "bar"],
                    "mapping" : {
                        "emailAddresses" : "mail",
                    },
                    "expected" : "(&(mail=foo*)(mail=bar*))",
                    "extra" : None,
                },
                {
                    "tokens" : ["foo", "bar"],
                    "mapping" : {
                        "fullName" : "cn",
                        "emailAddresses" : "mail",
                    },
                    "expected" : "(&(|(cn=*foo*)(mail=foo*))(|(cn=*bar*)(mail=bar*)))",
                    "extra" : None,
                },
                {
                    "tokens" : ["foo", "bar"],
                    "mapping" : {
                        "fullName" : "cn",
                        "emailAddresses" : ["mail", "mailAliases"],
                    },
                    "expected" : "(&(|(cn=*foo*)(mail=foo*)(mailAliases=foo*))(|(cn=*bar*)(mail=bar*)(mailAliases=bar*)))",
                    "extra" : None,
                },
                {
                    "tokens" : ["foo", "bar", "baz("],
                    "mapping" : {
                        "fullName" : "cn",
                        "emailAddresses" : "mail",
                    },
                    "expected" : "(&(|(cn=*foo*)(mail=foo*))(|(cn=*bar*)(mail=bar*))(|(cn=*baz\\28*)(mail=baz\\28*)))",
                    "extra" : None,
                },
            ]
            for entry in entries:
                self.assertEquals(
                    buildFilterFromTokens(None, entry["mapping"], entry["tokens"], extra=entry["extra"]),
                    entry["expected"]
                )

    class StubList(object):
        def __init__(self, wrapper):
            self.ldap = wrapper

        def startSearch(self, base, scope, filterstr, attrList=None,
            timeout=-1, sizelimit=0):
            self.base = base
            self.scope = scope
            self.filterstr = filterstr
            self.attrList = attrList
            self.timeout = timeout
            self.sizelimit = sizelimit

        def processResults(self):
            self.allResults = self.ldap.search_s(self.base, self.scope,
                self.filterstr, attrlist=self.attrList)

    class StubAsync(object):
        def List(self, wrapper):
            return StubList(wrapper)


    class LdapDirectoryTestWrapper(object):
        """
        A test stub which replaces search_s( ) with a version that will return
        whatever you have previously called addTestResults( ) with.
        """


        def __init__(self, actual, records):
            self.actual = actual
            self.async = StubAsync()

            # Test data returned from search_s.
            # Note that some DNs have various extra whitespace added and mixed
            # up case since LDAP is pretty loose about these.
            self.records = records


        def search_s(self, base, scope, filterstr="(objectClass=*)",
            attrlist=None):
            """ A simple implementation of LDAP search filter processing """

            base = normalizeDNstr(base)
            results = []
            for dn, attrs in self.records:
                dn = normalizeDNstr(dn)
                if dn == base:
                    results.append(("ignored", (dn, attrs)))
                elif dnContainedIn(ldap.dn.str2dn(dn), ldap.dn.str2dn(base)):
                    if filterstr in ("(objectClass=*)", "(!(objectClass=organizationalUnit))"):
                        results.append(("ignored", (dn, attrs)))
                    else:
                        trans = maketrans("&(|)", "   |")
                        fragments = filterstr.encode("utf-8").translate(trans).split("|")
                        for fragment in fragments:
                            if not fragment:
                                continue
                            fragment = fragment.strip()
                            key, value = fragment.split("=")
                            if value in attrs.get(key, []):
                                results.append(("ignored", (dn, attrs)))
                                break
                            elif value == "*" and key in attrs:
                                results.append(("ignored", (dn, attrs)))
                                break

            return results


    class LdapDirectoryServiceTestCase(TestCase):

        nestedUsingDifferentAttributeUsingDN = (
            (
                (
                    "cn=Recursive1_coasts, cn=gROUps,dc=example, dc=com",
                    {
                        'cn': ['recursive1_coasts'],
                        'apple-generateduid': ['recursive1_coasts'],
                        'uniqueMember': [
                            'uid=wsanchez ,cn=users, dc=eXAMple,dc=com',
                        ],
                        'nestedGroups': [
                            'cn=recursive2_coasts,cn=groups,dc=example,dc=com',
                        ],
                    }
                ),
                (
                    "cn=recursive2_coasts,cn=groups,dc=example,dc=com",
                    {
                        'cn': ['recursive2_coasts'],
                        'apple-generateduid': ['recursive2_coasts'],
                        'uniqueMember': [
                            'uid=cdaboo,cn=users,dc=example,dc=com',
                        ],
                        'nestedGroups': [
                            'cn=recursive1_coasts,cn=groups,dc=example,dc=com',
                        ],
                    }
                ),
                (
                    'cn=both_coasts,cn=groups,dc=example,dc=com',
                    {
                        'cn': ['both_coasts'],
                        'apple-generateduid': ['both_coasts'],
                        'nestedGroups': [
                            'cn=right_coast,cn=groups,dc=example,dc=com',
                            'cn=left_coast,cn=groups,dc=example,dc=com',
                        ],
                    }
                ),
                (
                    'cn=right_coast,cn=groups,dc=example,dc=com',
                    {
                        'cn': ['right_coast'],
                        'apple-generateduid': ['right_coast'],
                        'uniqueMember': [
                            'uid=cdaboo,cn=users,dc=example,dc=com',
                        ],
                    }
                ),
                (
                    'cn=left_coast,cn=groups,dc=example,dc=com',
                    {
                        'cn': ['left_coast'],
                        'apple-generateduid': ['left_coast'],
                        'uniqueMember': [
                            'uid=wsanchez, cn=users,dc=example,dc=com',
                            'uid=lecroy,cn=users,dc=example,dc=com',
                            'uid=dreid,cn=users,dc=example,dc=com',
                        ],
                    }
                ),
                (
                    "uid=odtestamanda,cn=users,dc=example,dc=com",
                    {
                        'uid': ['odtestamanda'],
                        # purposely throw in an un-normalized GUID
                        'apple-generateduid': ['9dc04a70-e6dd-11df-9492-0800200c9a66'],
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
                (
                    "uid=odtestcarlene,cn=users,dc=example,dc=com",
                    {
                        'uid': ['odtestcarlene'],
                        # Note: no guid here, to test this record is skipped
                        'sn': ['Test'],
                        'mail': ['odtestcarlene@example.com'],
                        'givenName': ['Carlene'],
                        'cn': ['Carlene Test']
                    }
                ),
                (
                    "uid=cdaboo,cn=users,dc=example,dc=com",
                    {
                        'uid': ['cdaboo'],
                        'apple-generateduid': ['5A985493-EE2C-4665-94CF-4DFEA3A89500'],
                        'sn': ['Daboo'],
                        'mail': ['daboo@example.com'],
                        'givenName': ['Cyrus'],
                        'cn': ['Cyrus Daboo']
                    }
                ),
                (
                    "uid=wsanchez  ,  cn=users  , dc=example,dc=com",
                    {
                        'uid': ['wsanchez'],
                        'apple-generateduid': ['6423F94A-6B76-4A3A-815B-D52CFD77935D'],
                        'sn': ['Sanchez'],
                        'mail': ['wsanchez@example.com'],
                        'givenName': ['Wilfredo'],
                        'cn': ['Wilfredo Sanchez']
                    }
                ),
                (
                    "uid=testresource  ,  cn=resources  , dc=example,dc=com",
                    {
                        'uid': ['testresource'],
                        'apple-generateduid': ['D91B21B9-B856-495A-8E36-0E5AD54EFB3A'],
                        'sn': ['Resource'],
                        'givenName': ['Test'],
                        'cn': ['Test Resource'],
                        # purposely throw in an un-normalized GUID
                        'read-write-proxy' : ['6423f94a-6b76-4a3a-815b-d52cfd77935d'],
                        'read-only-proxy' : ['5A985493-EE2C-4665-94CF-4DFEA3A89500'],
                    }
                ),
                (
                    "uid=testresource2  ,  cn=resources  , dc=example,dc=com",
                    {
                        'uid': ['testresource2'],
                        'apple-generateduid': ['753E5A60-AFFD-45E4-BF2C-31DAB459353F'],
                        'sn': ['Resource2'],
                        'givenName': ['Test'],
                        'cn': ['Test Resource2'],
                        'read-write-proxy' : ['6423F94A-6B76-4A3A-815B-D52CFD77935D'],
                    }
                ),
            ),
            {
                "augmentService" : None,
                "groupMembershipCache" : None,
                "cacheTimeout": 1, # Minutes
                "negativeCaching": False,
                "warningThresholdSeconds": 3,
                "batchSize": 500,
                "queryLocationsImplicitly": True,
                "restrictEnabledRecords": True,
                "restrictToGroup": "both_coasts",
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
                        "rdn": "cn=Users",
                        "attr": "uid", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "", # additional filter for this type
                        "loginEnabledAttr" : "", # attribute controlling login
                        "loginEnabledValue" : "yes", # "True" value of above attribute
                        "calendarEnabledAttr" : "enable-calendar", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "uid",
                            "fullName" : "cn",
                            "emailAddresses" : ["mail", "emailAliases"],
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                    "groups": {
                        "rdn": "cn=Groups",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "", # additional filter for this type
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : ["mail", "emailAliases"],
                        },
                    },
                    "locations": {
                        "rdn": "cn=Places",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "(objectClass=apple-resource)", # additional filter for this type
                        "calendarEnabledAttr" : "", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "associatedAddressAttr" : "assocAddr",
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : "", # old style, single string
                        },
                    },
                    "resources": {
                        "rdn": "cn=Resources",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "(objectClass=apple-resource)", # additional filter for this type
                        "calendarEnabledAttr" : "", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : [], # new style, array
                        },
                    },
                    "addresses": {
                        "rdn": "cn=Buildings",
                        "geoAttr" : "coordinates",
                        "streetAddressAttr" : "postal",
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                        },
                    },
                },
                "groupSchema": {
                    "membersAttr": "uniqueMember", # how members are specified
                    "nestedGroupsAttr": "nestedGroups", # how nested groups are specified
                    "memberIdAttr": "", # which attribute the above refer to
                },
                "resourceSchema": {
                    "resourceInfoAttr": "apple-resource-info", # contains location/resource info
                    "autoScheduleAttr": None,
                    "proxyAttr": "read-write-proxy",
                    "readOnlyProxyAttr": "read-only-proxy",
                    "autoAcceptGroupAttr": None,
                },
                "partitionSchema": {
                    "serverIdAttr": "server-id", # maps to augments server-id
                    "partitionIdAttr": "partition-id", # maps to augments partition-id
                },
            }
        )
        nestedUsingSameAttributeUsingDN = (
            (
                (
                    "cn=Recursive1_coasts, cn=gROUps,dc=example, dc=com",
                    {
                        'cn': ['recursive1_coasts'],
                        'apple-generateduid': ['recursive1_coasts'],
                        'uniqueMember': [
                            'uid=wsanchez ,cn=users, dc=eXAMple,dc=com',
                            'cn=recursive2_coasts,cn=groups,dc=example,dc=com',
                        ],
                    }
                ),
                (
                    "cn=recursive2_coasts,cn=groups,dc=example,dc=com",
                    {
                        'cn': ['recursive2_coasts'],
                        'apple-generateduid': ['recursive2_coasts'],
                        'uniqueMember': [
                            'uid=cdaboo,cn=users,dc=example,dc=com',
                            'cn=recursive1_coasts,cn=groups,dc=example,dc=com',
                        ],
                    }
                ),
                (
                    'cn=both_coasts,cn=groups,dc=example,dc=com',
                    {
                        'cn': ['both_coasts'],
                        'apple-generateduid': ['both_coasts'],
                        'uniqueMember': [
                            'cn=right_coast,cn=groups,dc=example,dc=com',
                            'cn=left_coast,cn=groups,dc=example,dc=com',
                        ],
                    }
                ),
                (
                    'cn=right_coast,cn=groups,dc=example,dc=com',
                    {
                        'cn': ['right_coast'],
                        'apple-generateduid': ['right_coast'],
                        'uniqueMember': [
                            'uid=cdaboo,cn=users,dc=example,dc=com',
                        ],
                    }
                ),
                (
                    'cn=left_coast,cn=groups,dc=example,dc=com',
                    {
                        'cn': ['left_coast'],
                        'apple-generateduid': ['left_coast'],
                        'uniqueMember': [
                            'uid=wsanchez, cn=users,dc=example,dc=com',
                            'uid=lecroy,cn=users,dc=example,dc=com',
                            'uid=dreid,cn=users,dc=example,dc=com',
                        ],
                    }
                ),
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
                (
                    "uid=odtestcarlene,cn=users,dc=example,dc=com",
                    {
                        'uid': ['odtestcarlene'],
                        # Note: no guid here, to test this record is skipped
                        'sn': ['Test'],
                        'mail': ['odtestcarlene@example.com'],
                        'givenName': ['Carlene'],
                        'cn': ['Carlene Test']
                    }
                ),
                (
                    "uid=cdaboo,cn=users,dc=example,dc=com",
                    {
                        'uid': ['cdaboo'],
                        'apple-generateduid': ['5A985493-EE2C-4665-94CF-4DFEA3A89500'],
                        'sn': ['Daboo'],
                        'mail': ['daboo@example.com'],
                        'givenName': ['Cyrus'],
                        'cn': ['Cyrus Daboo']
                    }
                ),
                (
                    "uid=wsanchez  ,  cn=users  , dc=example,dc=com",
                    {
                        'uid': ['wsanchez'],
                        'apple-generateduid': ['6423F94A-6B76-4A3A-815B-D52CFD77935D'],
                        'sn': ['Sanchez'],
                        'mail': ['wsanchez@example.com'],
                        'givenName': ['Wilfredo'],
                        'cn': ['Wilfredo Sanchez']
                    }
                ),
            ),
            {
                "augmentService" : None,
                "groupMembershipCache" : None,
                "cacheTimeout": 1, # Minutes
                "negativeCaching": False,
                "warningThresholdSeconds": 3,
                "batchSize": 500,
                "queryLocationsImplicitly": True,
                "restrictEnabledRecords": True,
                "restrictToGroup": "both_coasts",
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
                        "rdn": "cn=Users",
                        "attr": "uid", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "", # additional filter for this type
                        "loginEnabledAttr" : "", # attribute controlling login
                        "loginEnabledValue" : "yes", # "True" value of above attribute
                        "calendarEnabledAttr" : "enable-calendar", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "uid",
                            "fullName" : "cn",
                            "emailAddresses" : ["mail", "emailAliases"],
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                    "groups": {
                        "rdn": "cn=Groups",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "", # additional filter for this type
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : ["mail", "emailAliases"],
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                    "locations": {
                        "rdn": "cn=Places",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "(objectClass=apple-resource)", # additional filter for this type
                        "calendarEnabledAttr" : "", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : "", # old style, single string
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                    "resources": {
                        "rdn": "cn=Resources",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "(objectClass=apple-resource)", # additional filter for this type
                        "calendarEnabledAttr" : "", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : [], # new style, array
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                },
                "groupSchema": {
                    "membersAttr": "uniqueMember", # how members are specified
                    "nestedGroupsAttr": "", # how nested groups are specified
                    "memberIdAttr": "", # which attribute the above refer to
                },
                "resourceSchema": {
                    "resourceInfoAttr": "apple-resource-info", # contains location/resource info
                    "autoScheduleAttr": None,
                    "proxyAttr": None,
                    "readOnlyProxyAttr": None,
                    "autoAcceptGroupAttr": None,
                },
                "partitionSchema": {
                    "serverIdAttr": "server-id", # maps to augments server-id
                    "partitionIdAttr": "partition-id", # maps to augments partition-id
                },
            }
        )
        nestedUsingDifferentAttributeUsingGUID = (
            (
                (
                    "cn=Recursive1_coasts, cn=gROUps,dc=example, dc=com",
                    {
                        'cn': ['recursive1_coasts'],
                        'apple-generateduid': ['recursive1_coasts'],
                        'uniqueMember': [
                            '6423F94A-6B76-4A3A-815B-D52CFD77935D',
                        ],
                        'nestedGroups': [
                            'recursive2_coasts',
                        ],
                    }
                ),
                (
                    "cn=recursive2_coasts,cn=groups,dc=example,dc=com",
                    {
                        'cn': ['recursive2_coasts'],
                        'apple-generateduid': ['recursive2_coasts'],
                        'uniqueMember': [
                            '5A985493-EE2C-4665-94CF-4DFEA3A89500',
                        ],
                        'nestedGroups': [
                            'recursive1_coasts',
                        ],
                    }
                ),
                (
                    'cn=both_coasts,cn=groups,dc=example,dc=com',
                    {
                        'cn': ['both_coasts'],
                        'apple-generateduid': ['both_coasts'],
                        'nestedGroups': [
                            'right_coast',
                            'left_coast',
                        ],
                    }
                ),
                (
                    'cn=right_coast,cn=groups,dc=example,dc=com',
                    {
                        'cn': ['right_coast'],
                        'apple-generateduid': ['right_coast'],
                        'uniqueMember': [
                            '5A985493-EE2C-4665-94CF-4DFEA3A89500',
                        ],
                    }
                ),
                (
                    'cn=left_coast,cn=groups,dc=example,dc=com',
                    {
                        'cn': ['left_coast'],
                        'apple-generateduid': ['left_coast'],
                        'uniqueMember': [
                            '6423F94A-6B76-4A3A-815B-D52CFD77935D',
                        ],
                    }
                ),
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
                (
                    "uid=odtestcarlene,cn=users,dc=example,dc=com",
                    {
                        'uid': ['odtestcarlene'],
                        # Note: no guid here, to test this record is skipped
                        'sn': ['Test'],
                        'mail': ['odtestcarlene@example.com'],
                        'givenName': ['Carlene'],
                        'cn': ['Carlene Test']
                    }
                ),
                (
                    "uid=cdaboo,cn=users,dc=example,dc=com",
                    {
                        'uid': ['cdaboo'],
                        'apple-generateduid': ['5A985493-EE2C-4665-94CF-4DFEA3A89500'],
                        'sn': ['Daboo'],
                        'mail': ['daboo@example.com'],
                        'givenName': ['Cyrus'],
                        'cn': ['Cyrus Daboo']
                    }
                ),
                (
                    "uid=wsanchez  ,  cn=users  , dc=example,dc=com",
                    {
                        'uid': ['wsanchez'],
                        'apple-generateduid': ['6423F94A-6B76-4A3A-815B-D52CFD77935D'],
                        'sn': ['Sanchez'],
                        'mail': ['wsanchez@example.com'],
                        'givenName': ['Wilfredo'],
                        'cn': ['Wilfredo Sanchez']
                    }
                ),
            ),
            {
                "augmentService" : None,
                "groupMembershipCache" : None,
                "cacheTimeout": 1, # Minutes
                "negativeCaching": False,
                "warningThresholdSeconds": 3,
                "batchSize": 500,
                "queryLocationsImplicitly": True,
                "restrictEnabledRecords": True,
                "restrictToGroup": "both_coasts",
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
                        "rdn": "cn=Users",
                        "attr": "uid", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "", # additional filter for this type
                        "loginEnabledAttr" : "", # attribute controlling login
                        "loginEnabledValue" : "yes", # "True" value of above attribute
                        "calendarEnabledAttr" : "enable-calendar", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "uid",
                            "fullName" : "cn",
                            "emailAddresses" : ["mail", "emailAliases"],
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                    "groups": {
                        "rdn": "cn=Groups",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "", # additional filter for this type
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : ["mail", "emailAliases"],
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                    "locations": {
                        "rdn": "cn=Places",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "(objectClass=apple-resource)", # additional filter for this type
                        "calendarEnabledAttr" : "", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : "", # old style, single string
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                    "resources": {
                        "rdn": "cn=Resources",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "(objectClass=apple-resource)", # additional filter for this type
                        "calendarEnabledAttr" : "", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : [], # new style, array
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                },
                "groupSchema": {
                    "membersAttr": "uniqueMember", # how members are specified
                    "nestedGroupsAttr": "nestedGroups", # how nested groups are specified
                    "memberIdAttr": "apple-generateduid", # which attribute the above refer to
                },
                "resourceSchema": {
                    "resourceInfoAttr": "apple-resource-info", # contains location/resource info
                    "autoScheduleAttr": None,
                    "proxyAttr": None,
                    "readOnlyProxyAttr": None,
                    "autoAcceptGroupAttr": None,
                },
                "partitionSchema": {
                    "serverIdAttr": "server-id", # maps to augments server-id
                    "partitionIdAttr": "partition-id", # maps to augments partition-id
                },
            }
        )
        nestedUsingSameAttributeUsingGUID = (
            (
                (
                    "cn=Recursive1_coasts, cn=gROUps,dc=example, dc=com",
                    {
                        'cn': ['recursive1_coasts'],
                        'apple-generateduid': ['recursive1_coasts'],
                        'uniqueMember': [
                            '6423F94A-6B76-4A3A-815B-D52CFD77935D',
                            'recursive2_coasts',
                        ],
                    }
                ),
                (
                    "cn=recursive2_coasts,cn=groups,dc=example,dc=com",
                    {
                        'cn': ['recursive2_coasts'],
                        'apple-generateduid': ['recursive2_coasts'],
                        'uniqueMember': [
                            '5A985493-EE2C-4665-94CF-4DFEA3A89500',
                            'recursive1_coasts',
                        ],
                    }
                ),
                (
                    'cn=both_coasts,cn=groups,dc=example,dc=com',
                    {
                        'cn': ['both_coasts'],
                        'apple-generateduid': ['both_coasts'],
                        'uniqueMember': [
                            'right_coast',
                            'left_coast',
                        ],
                    }
                ),
                (
                    'cn=right_coast,cn=groups,dc=example,dc=com',
                    {
                        'cn': ['right_coast'],
                        'apple-generateduid': ['right_coast'],
                        'uniqueMember': [
                            '5A985493-EE2C-4665-94CF-4DFEA3A89500',
                        ],
                    }
                ),
                (
                    'cn=left_coast,cn=groups,dc=example,dc=com',
                    {
                        'cn': ['left_coast'],
                        'apple-generateduid': ['left_coast'],
                        'uniqueMember': [
                            '6423F94A-6B76-4A3A-815B-D52CFD77935D',
                        ],
                    }
                ),
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
                (
                    "uid=odtestcarlene,cn=users,dc=example,dc=com",
                    {
                        'uid': ['odtestcarlene'],
                        # Note: no guid here, to test this record is skipped
                        'sn': ['Test'],
                        'mail': ['odtestcarlene@example.com'],
                        'givenName': ['Carlene'],
                        'cn': ['Carlene Test']
                    }
                ),
                (
                    "uid=cdaboo,cn=users,dc=example,dc=com",
                    {
                        'uid': ['cdaboo'],
                        'apple-generateduid': ['5A985493-EE2C-4665-94CF-4DFEA3A89500'],
                        'sn': ['Daboo'],
                        'mail': ['daboo@example.com'],
                        'givenName': ['Cyrus'],
                        'cn': ['Cyrus Daboo']
                    }
                ),
                (
                    "uid=wsanchez  ,  cn=users  , dc=example,dc=com",
                    {
                        'uid': ['wsanchez'],
                        'apple-generateduid': ['6423F94A-6B76-4A3A-815B-D52CFD77935D'],
                        'sn': ['Sanchez'],
                        'mail': ['wsanchez@example.com'],
                        'givenName': ['Wilfredo'],
                        'cn': ['Wilfredo Sanchez']
                    }
                ),
            ),
            {
                "augmentService" : None,
                "groupMembershipCache" : None,
                "cacheTimeout": 1, # Minutes
                "negativeCaching": False,
                "warningThresholdSeconds": 3,
                "batchSize": 500,
                "queryLocationsImplicitly": True,
                "restrictEnabledRecords": True,
                "restrictToGroup": "both_coasts",
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
                        "rdn": "cn=Users",
                        "attr": "uid", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "", # additional filter for this type
                        "loginEnabledAttr" : "", # attribute controlling login
                        "loginEnabledValue" : "yes", # "True" value of above attribute
                        "calendarEnabledAttr" : "enable-calendar", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "uid",
                            "fullName" : "cn",
                            "emailAddresses" : ["mail", "emailAliases"],
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                    "groups": {
                        "rdn": "cn=Groups",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "", # additional filter for this type
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : ["mail", "emailAliases"],
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                    "locations": {
                        "rdn": "cn=Places",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "(objectClass=apple-resource)", # additional filter for this type
                        "calendarEnabledAttr" : "", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : "", # old style, single string
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                    "resources": {
                        "rdn": "cn=Resources",
                        "attr": "cn", # used only to synthesize email address
                        "emailSuffix": None, # used only to synthesize email address
                        "filter": "(objectClass=apple-resource)", # additional filter for this type
                        "calendarEnabledAttr" : "", # attribute controlling calendaring
                        "calendarEnabledValue" : "yes", # "True" value of above attribute
                        "mapping": { # maps internal record names to LDAP
                            "recordName": "cn",
                            "fullName" : "cn",
                            "emailAddresses" : [], # new style, array
                            "firstName" : "givenName",
                            "lastName" : "sn",
                        },
                    },
                },
                "groupSchema": {
                    "membersAttr": "uniqueMember", # how members are specified
                    "nestedGroupsAttr": "", # how nested groups are specified
                    "memberIdAttr": "apple-generateduid", # which attribute the above refer to
                },
                "resourceSchema": {
                    "resourceInfoAttr": "apple-resource-info", # contains location/resource info
                    "autoScheduleAttr": None,
                    "proxyAttr": None,
                    "readOnlyProxyAttr": None,
                    "autoAcceptGroupAttr": None,
                },
                "partitionSchema": {
                    "serverIdAttr": "server-id", # maps to augments server-id
                    "partitionIdAttr": "partition-id", # maps to augments partition-id
                },
            }
        )

        def setupService(self, scenario):
            self.service = LdapDirectoryService(scenario[1])
            self.service.ldap = LdapDirectoryTestWrapper(self.service.ldap, scenario[0])
            self.patch(ldap, "async", StubAsync())


        def test_ldapWrapper(self):
            """
            Exercise the fake search_s implementation
            """
            self.setupService(self.nestedUsingDifferentAttributeUsingDN)

            # Get all groups
            self.assertEquals(
                len(self.service.ldap.search_s("cn=groups,dc=example,dc=com", 0, "(objectClass=*)", [])), 5)

            self.assertEquals(
                len(self.service.ldap.search_s("cn=recursive1_coasts,cn=groups,dc=example,dc=com", 2, "(objectClass=*)", [])), 1)

            self.assertEquals(
                len(self.service.ldap.search_s("cn=groups,dc=example,dc=com", 0, "(|(apple-generateduid=right_coast)(apple-generateduid=left_coast))", [])), 2)


        def test_ldapRecordCreation(self):
            """
            Exercise _ldapResultToRecord(), which converts a dictionary
            of LDAP attributes into an LdapDirectoryRecord
            """
            self.setupService(self.nestedUsingDifferentAttributeUsingDN)

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

            # User missing guidAttr

            dn = "uid=odtestamanda,cn=users,dc=example,dc=com"
            attrs = {
                'uid': ['odtestamanda'],
                'cn': ['Amanda Test'],
            }

            self.assertRaises(MissingGuidException,
                self.service._ldapResultToRecord, dn, attrs,
                self.service.recordType_users)

            # User missing record name

            dn = "uid=odtestamanda,cn=users,dc=example,dc=com"
            attrs = {
                'apple-generateduid': ['9ABDD881-B3A4-4065-9DA7-12095F40A898'],
                'cn': ['Amanda Test'],
            }

            self.assertRaises(MissingRecordNameException,
                self.service._ldapResultToRecord, dn, attrs,
                self.service.recordType_users)

            # Group with direct user members and nested group

            dn = "cn=odtestgrouptop,cn=groups,dc=example,dc=com"
            guid = '6C6CD280-E6E3-11DF-9492-0800200C9A66'
            attrs = {
                'apple-generateduid': [guid],
                'uniqueMember':
                    [
                        'uid=odtestamanda,cn=users,dc=example,dc=com',
                        'uid=odtestbetty,cn=users,dc=example,dc=com',
                        'cn=odtestgroupb,cn=groups,dc=example,dc=com',
                    ],
                'cn': ['odtestgrouptop']
            }
            record = self.service._ldapResultToRecord(dn, attrs,
                self.service.recordType_groups)
            self.assertEquals(record.guid, guid)
            self.assertEquals(record.memberGUIDs(),
                set([
                     'cn=odtestgroupb,cn=groups,dc=example,dc=com',
                     'uid=odtestamanda,cn=users,dc=example,dc=com',
                     'uid=odtestbetty,cn=users,dc=example,dc=com',
                     ])
            )

            # Group with illegal DN value in members

            dn = "cn=odtestgrouptop,cn=groups,dc=example,dc=com"
            guid = '6C6CD280-E6E3-11DF-9492-0800200C9A66'
            attrs = {
                'apple-generateduid': [guid],
                'uniqueMember':
                    [
                        'uid=odtestamanda,cn=users,dc=example,dc=com',
                        'uid=odtestbetty ,cn=users,dc=example,dc=com',
                        'cn=odtestgroupb+foo,cn=groups,dc=example,dc=com',
                    ],
                'cn': ['odtestgrouptop']
            }
            record = self.service._ldapResultToRecord(dn, attrs,
                self.service.recordType_groups)
            self.assertEquals(record.guid, guid)
            self.assertEquals(record.memberGUIDs(),
                set([
                     'uid=odtestamanda,cn=users,dc=example,dc=com',
                     'uid=odtestbetty,cn=users,dc=example,dc=com',
                     ])
            )

            # Resource with delegates, autoSchedule = True, and autoAcceptGroup

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
<key>AutoAcceptGroup</key>
<string>77A8EB52-AA2A-42ED-8843-B2BEE863AC70</string>
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
            self.assertEquals(record.autoAcceptGroup,
                '77A8EB52-AA2A-42ED-8843-B2BEE863AC70')

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
            self.assertEquals(record.autoAcceptGroup, "")


            # Now switch off the resourceInfoAttr and switch to individual
            # attributes...
            self.service.resourceSchema = {
                "resourceInfoAttr" : "",
                "autoScheduleAttr" : "auto-schedule",
                "autoScheduleEnabledValue" : "yes",
                "proxyAttr" : "proxy",
                "readOnlyProxyAttr" : "read-only-proxy",
                "autoAcceptGroupAttr" : "auto-accept-group",
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
                'auto-accept-group' : ['77A8EB52-AA2A-42ED-8843-B2BEE863AC70'],
            }
            record = self.service._ldapResultToRecord(dn, attrs,
                self.service.recordType_resources)
            self.assertEquals(record.guid, guid)
            self.assertEquals(record.externalProxies(),
                set(['6C6CD280-E6E3-11DF-9492-0800200C9A66']))
            self.assertEquals(record.externalReadOnlyProxies(),
                set(['6AA1AE12-592F-4190-A069-547CD83C47C0']))
            self.assertTrue(record.autoSchedule)
            self.assertEquals(record.autoAcceptGroup,
                '77A8EB52-AA2A-42ED-8843-B2BEE863AC70')

            # Record with lowercase guid
            dn = "uid=odtestamanda,cn=users,dc=example,dc=com"
            guid = '9dc04a70-e6dd-11df-9492-0800200c9a66'
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
            self.assertEquals(record.guid, guid.upper())

            # Location with associated Address

            dn = "cn=odtestlocation,cn=locations,dc=example,dc=com"
            guid = "D3094652-344B-4633-8DB8-09639FA00FB6"
            attrs = {
                "apple-generateduid": [guid],
                "cn": ["odtestlocation"],
                "assocAddr" : ["6C6CD280-E6E3-11DF-9492-0800200C9A66"],
            }
            record = self.service._ldapResultToRecord(dn, attrs,
                self.service.recordType_locations)
            self.assertEquals(record.extras, {
                "associatedAddress": "6C6CD280-E6E3-11DF-9492-0800200C9A66"
            })
           
            # Address with street and geo

            dn = "cn=odtestaddress,cn=buildings,dc=example,dc=com"
            guid = "6C6CD280-E6E3-11DF-9492-0800200C9A66"
            attrs = {
                "apple-generateduid": [guid],
                "cn": ["odtestaddress"],
                "coordinates" : ["geo:1,2"],
                "postal" : ["1 Infinite Loop, Cupertino, CA"],
            }
            record = self.service._ldapResultToRecord(dn, attrs,
                self.service.recordType_addresses)
            self.assertEquals(record.extras, {
                "geo": "geo:1,2",
                "streetAddress" : "1 Infinite Loop, Cupertino, CA",
            })
           

        def test_listRecords(self):
            """
            listRecords makes an LDAP query (with fake results in this test)
            and turns the results into records
            """
            self.setupService(self.nestedUsingDifferentAttributeUsingDN)

            records = self.service.listRecords(self.service.recordType_users)
            self.assertEquals(len(records), 4)
            self.assertEquals(
                set([r.firstName for r in records]),
                set(["Amanda", "Betty", "Cyrus", "Wilfredo"]) # Carlene is skipped because no guid in LDAP
            )

        def test_restrictedPrincipalsUsingDN(self):
            """
            If restrictToGroup is in place, restrictedPrincipals should return only the principals
            within that group.  In this case we're testing scenarios in which membership
            is specified by DN
            """
            for scenario in (
                self.nestedUsingSameAttributeUsingDN,
                self.nestedUsingDifferentAttributeUsingDN,
                ):
                self.setupService(scenario)

                self.assertEquals(
                    set([
                        "cn=left_coast,cn=groups,dc=example,dc=com",
                        "cn=right_coast,cn=groups,dc=example,dc=com",
                        "uid=cdaboo,cn=users,dc=example,dc=com",
                        "uid=dreid,cn=users,dc=example,dc=com",
                        "uid=lecroy,cn=users,dc=example,dc=com",
                        "uid=wsanchez,cn=users,dc=example,dc=com",
                    ]),
                    self.service.restrictedPrincipals)

                dn = "uid=cdaboo,cn=users,dc=example,dc=com"
                attrs = {
                    'uid': ['cdaboo'],
                    'apple-generateduid': ['5A985493-EE2C-4665-94CF-4DFEA3A89500'],
                    'sn': ['Daboo'],
                    'mail': ['daboo@example.com'],
                    'givenName': ['Cyrus'],
                    'cn': ['Cyrus Daboo']
                }
                self.assertTrue(self.service.isAllowedByRestrictToGroup(dn, attrs))

                dn = "uid=unknown,cn=users,dc=example,dc=com"
                attrs = {
                    'uid': ['unknown'],
                    'apple-generateduid': ['5A985493-EE2C-4665-94CF-4DFEA3A89500'],
                    'sn': ['unknown'],
                    'mail': ['unknown@example.com'],
                    'givenName': ['unknown'],
                    'cn': ['unknown']
                }
                self.assertFalse(self.service.isAllowedByRestrictToGroup(dn, attrs))


        def test_restrictedPrincipalsUsingGUID(self):
            """
            If restrictToGroup is in place, restrictedPrincipals should return only the principals
            within that group.  In this case we're testing scenarios in which membership
            is specified by an attribute, not DN
            """
            for scenario in (
                self.nestedUsingDifferentAttributeUsingGUID,
                self.nestedUsingSameAttributeUsingGUID,
                ):
                self.setupService(scenario)

                self.assertEquals(
                    set([
                        "left_coast",
                        "right_coast",
                        "5A985493-EE2C-4665-94CF-4DFEA3A89500",
                        "6423F94A-6B76-4A3A-815B-D52CFD77935D",
                    ]),
                    self.service.restrictedPrincipals)

                dn = "uid=cdaboo,cn=users,dc=example,dc=com"
                attrs = {
                    'uid': ['cdaboo'],
                    'apple-generateduid': ['5A985493-EE2C-4665-94CF-4DFEA3A89500'],
                    'sn': ['Daboo'],
                    'mail': ['daboo@example.com'],
                    'givenName': ['Cyrus'],
                    'cn': ['Cyrus Daboo']
                }
                self.assertTrue(self.service.isAllowedByRestrictToGroup(dn, attrs))

                dn = "uid=unknown,cn=users,dc=example,dc=com"
                attrs = {
                    'uid': ['unknown'],
                    'apple-generateduid': ['unknown'],
                    'sn': ['unknown'],
                    'mail': ['unknown@example.com'],
                    'givenName': ['unknown'],
                    'cn': ['unknown']
                }
                self.assertFalse(self.service.isAllowedByRestrictToGroup(dn, attrs))



        @inlineCallbacks
        def test_groupMembershipAliases(self):
            """
            Exercise a directory environment where group membership does not refer
            to guids but instead uses LDAP DNs.  This example uses the LDAP attribute
            "uniqueMember" to specify members of a group.  The value of this attribute
            is each members' DN.  Even though the proxy database deals strictly in
            guids, updateCache( ) is smart enough to map between guids and this
            attribute which is referred to in the code as record.cachedGroupsAlias().
            """
            self.setupService(self.nestedUsingDifferentAttributeUsingDN)

            # Set up proxydb and preload it from xml
            calendaruserproxy.ProxyDBService = calendaruserproxy.ProxySqliteDB("proxies.sqlite")
            yield XMLCalendarUserProxyLoader(proxiesFile.path).updateProxyDB()

            # Set up the GroupMembershipCache
            cache = GroupMembershipCache("ProxyDB", expireSeconds=60)
            self.service.groupMembershipCache = cache
            updater = GroupMembershipCacheUpdater(calendaruserproxy.ProxyDBService,
                self.service, 30, 15, 30, cache=cache, useExternalProxies=False)

            self.assertEquals((False, 8, 8), (yield updater.updateCache()))

            users = self.service.recordType_users

            for shortName, groups in [
                ("cdaboo", set(["both_coasts", "recursive1_coasts", "recursive2_coasts"])),
                ("wsanchez", set(["both_coasts", "left_coast", "recursive1_coasts", "recursive2_coasts"])),
            ]:

                record = self.service.recordWithShortName(users, shortName)
                self.assertEquals(groups, (yield record.cachedGroups()))


        def test_getExternalProxyAssignments(self):
            """
            Verify getExternalProxyAssignments can extract assignments from the
            directory, and that guids are normalized.
            """
            self.setupService(self.nestedUsingDifferentAttributeUsingDN)
            self.assertEquals(
                self.service.getExternalProxyAssignments(),
                [
                    ('D91B21B9-B856-495A-8E36-0E5AD54EFB3A#calendar-proxy-read',
                        ['5A985493-EE2C-4665-94CF-4DFEA3A89500']),
                    ('D91B21B9-B856-495A-8E36-0E5AD54EFB3A#calendar-proxy-write',
                        ['6423F94A-6B76-4A3A-815B-D52CFD77935D']),
                    ('753E5A60-AFFD-45E4-BF2C-31DAB459353F#calendar-proxy-write',
                        ['6423F94A-6B76-4A3A-815B-D52CFD77935D'])
                ]
            )



        def test_splitIntoBatches(self):
            self.setupService(self.nestedUsingDifferentAttributeUsingDN)
            # Data is perfect multiple of size
            results = list(splitIntoBatches(set(range(12)), 4))
            self.assertEquals(results,
                [set([0, 1, 2, 3]), set([4, 5, 6, 7]), set([8, 9, 10, 11])])

            # Some left overs
            results = list(splitIntoBatches(set(range(12)), 5))
            self.assertEquals(results,
                [set([0, 1, 2, 3, 4]), set([8, 9, 5, 6, 7]), set([10, 11])])

            # Empty
            results = list(splitIntoBatches(set([]), 5)) # empty data
            self.assertEquals(results, [set([])])

        def test_recordTypeForDN(self):
            # Ensure dn comparison is case insensitive and ignores extra
            # whitespace
            self.setupService(self.nestedUsingDifferentAttributeUsingDN)

            # Base DNs for each recordtype should already be lowercase
            for dn in self.service.typeDNs.itervalues():
                dnStr = ldap.dn.dn2str(dn)
                self.assertEquals(dnStr, dnStr.lower())

            # Match
            dnStr = "uid=foo,cn=USers ,dc=EXAMple,dc=com"
            self.assertEquals(self.service.recordTypeForDN(dnStr), "users")
            dnStr = "uid=foo,cn=PLaces,dc=EXAMple,dc=com"
            self.assertEquals(self.service.recordTypeForDN(dnStr), "locations")
            dnStr = "uid=foo,cn=Groups  ,dc=EXAMple,dc=com"
            self.assertEquals(self.service.recordTypeForDN(dnStr), "groups")
            dnStr = "uid=foo,cn=Resources  ,dc=EXAMple,dc=com"
            self.assertEquals(self.service.recordTypeForDN(dnStr), "resources")

            # No Match
            dnStr = "uid=foo,cn=US ers ,dc=EXAMple,dc=com"
            self.assertEquals(self.service.recordTypeForDN(dnStr), None)

        def test_normalizeDN(self):
            for input, expected in (
                ("uid=foo,cn=users,dc=example,dc=com",
                 "uid=foo,cn=users,dc=example,dc=com"),
                ("uid=FoO,cn=uSeRs,dc=ExAmPlE,dc=CoM",
                 "uid=foo,cn=users,dc=example,dc=com"),
                ("uid=FoO , cn=uS eRs , dc=ExA mPlE ,   dc=CoM",
                 "uid=foo,cn=us ers,dc=exa mple,dc=com"),
                ("uid=FoO , cn=uS  eRs , dc=ExA    mPlE ,   dc=CoM",
                 "uid=foo,cn=us ers,dc=exa mple,dc=com"),
            ):
                self.assertEquals(expected, normalizeDNstr(input))

        def test_queryDirectory(self):
            """
            Verify queryDirectory skips LDAP queries where there has been no
            LDAP attribute mapping provided for the given index type.
            """
            self.setupService(self.nestedUsingDifferentAttributeUsingDN)

            self.history = []

            def stubSearchMethod(base, scope, filterstr="(objectClass=*)",
                attrlist=None, timeoutSeconds=-1, resultLimit=0):
                self.history.append((base, scope, filterstr))

            recordTypes = [
                self.service.recordType_users,
                self.service.recordType_groups,
                self.service.recordType_locations,
                self.service.recordType_resources,
            ]
            self.service.queryDirectory(
                recordTypes,
                self.service.INDEX_TYPE_CUA,
                "mailto:test@example.com",
                queryMethod=stubSearchMethod
            )
            self.assertEquals(
                self.history,
                [('cn=users,dc=example,dc=com', 2, '(&(!(objectClass=organizationalUnit))(|(mail=test@example.com)(emailAliases=test@example.com)))'), ('cn=groups,dc=example,dc=com', 2, '(&(!(objectClass=organizationalUnit))(|(mail=test@example.com)(emailAliases=test@example.com)))')]
            )
