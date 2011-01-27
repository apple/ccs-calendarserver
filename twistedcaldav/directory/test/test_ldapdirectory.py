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
    from twistedcaldav.directory.ldapdirectory import buildFilter
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
