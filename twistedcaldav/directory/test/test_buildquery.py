##
# Copyright (c) 2009-2014 Apple Inc. All rights reserved.
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
from twistedcaldav.directory.appleopendirectory import (buildQueries,
    buildLocalQueriesFromTokens, OpenDirectoryService, buildNestedQueryFromTokens)
from calendarserver.platform.darwin.od import dsattributes

class BuildQueryTests(TestCase):

    def test_buildQuery(self):
        self.assertEquals(
            buildQueries(
                [dsattributes.kDSStdRecordTypeUsers],
                (
                    ("firstName", "morgen", True, "starts-with"),
                    ("lastName", "sagen", True, "starts-with"),
                ),
                OpenDirectoryService._ODFields
            ),
            {
                ('dsAttrTypeStandard:FirstName', 'morgen', True, 'starts-with') : [dsattributes.kDSStdRecordTypeUsers],
                ('dsAttrTypeStandard:LastName', 'sagen', True, 'starts-with') : [dsattributes.kDSStdRecordTypeUsers],
            }
        )
        self.assertEquals(
            buildQueries(
                [
                    dsattributes.kDSStdRecordTypeUsers,
                ],
                (
                    ("firstName", "morgen", True, "starts-with"),
                    ("emailAddresses", "morgen", True, "contains"),
                ),
                OpenDirectoryService._ODFields
            ),
            {
                ('dsAttrTypeStandard:FirstName', 'morgen', True, 'starts-with') : [dsattributes.kDSStdRecordTypeUsers],
                ('dsAttrTypeStandard:EMailAddress', 'morgen', True, 'contains') : [dsattributes.kDSStdRecordTypeUsers],
            }
        )
        self.assertEquals(
            buildQueries(
                [
                    dsattributes.kDSStdRecordTypeGroups,
                ],
                (
                    ("firstName", "morgen", True, "starts-with"),
                    ("lastName", "morgen", True, "starts-with"),
                    ("fullName", "morgen", True, "starts-with"),
                    ("emailAddresses", "morgen", True, "contains"),
                ),
                OpenDirectoryService._ODFields
            ),
            {
                ('dsAttrTypeStandard:RealName', 'morgen', True, 'starts-with') : [dsattributes.kDSStdRecordTypeGroups],
                ('dsAttrTypeStandard:EMailAddress', 'morgen', True, 'contains') : [dsattributes.kDSStdRecordTypeGroups],
            }
        )
        self.assertEquals(
            buildQueries(
                [
                    dsattributes.kDSStdRecordTypeUsers,
                    dsattributes.kDSStdRecordTypeGroups,
                ],
                (
                    ("firstName", "morgen", True, "starts-with"),
                    ("lastName", "morgen", True, "starts-with"),
                    ("fullName", "morgen", True, "starts-with"),
                    ("emailAddresses", "morgen", True, "contains"),
                ),
                OpenDirectoryService._ODFields
            ),
            {
                ('dsAttrTypeStandard:RealName', 'morgen', True, 'starts-with') : [dsattributes.kDSStdRecordTypeUsers, dsattributes.kDSStdRecordTypeGroups],
                ('dsAttrTypeStandard:EMailAddress', 'morgen', True, 'contains') : [dsattributes.kDSStdRecordTypeUsers, dsattributes.kDSStdRecordTypeGroups],
                ('dsAttrTypeStandard:FirstName', 'morgen', True, 'starts-with') : [dsattributes.kDSStdRecordTypeUsers],
                ('dsAttrTypeStandard:LastName', 'morgen', True, 'starts-with') : [dsattributes.kDSStdRecordTypeUsers],
            }
        )
        self.assertEquals(
            buildQueries(
                [
                    dsattributes.kDSStdRecordTypeGroups,
                ],
                (
                    ("firstName", "morgen", True, "starts-with"),
                ),
                OpenDirectoryService._ODFields
            ),
            {
            }
        )


    def test_buildLocalQueryFromTokens(self):
        """
        Verify the generating of the simpler queries passed to /Local/Default
        """
        results = buildLocalQueriesFromTokens([], OpenDirectoryService._ODFields)
        self.assertEquals(results, None)

        results = buildLocalQueriesFromTokens(["foo"], OpenDirectoryService._ODFields)
        self.assertEquals(
            results[0].generate(),
            "(|(dsAttrTypeStandard:RealName=*foo*)(dsAttrTypeStandard:EMailAddress=foo*))"
        )

        results = buildLocalQueriesFromTokens(["foo", "bar"], OpenDirectoryService._ODFields)
        self.assertEquals(
            results[0].generate(),
            "(|(dsAttrTypeStandard:RealName=*foo*)(dsAttrTypeStandard:EMailAddress=foo*))"
        )
        self.assertEquals(
            results[1].generate(),
            "(|(dsAttrTypeStandard:RealName=*bar*)(dsAttrTypeStandard:EMailAddress=bar*))"
        )


    def test_buildNestedQueryFromTokens(self):
        """
        Verify the generating of the complex nested queries
        """
        query = buildNestedQueryFromTokens([], OpenDirectoryService._ODFields)
        self.assertEquals(query, None)

        query = buildNestedQueryFromTokens(["foo"], OpenDirectoryService._ODFields)
        self.assertEquals(
            query.generate(),
            "(|(dsAttrTypeStandard:RealName=*foo*)(dsAttrTypeStandard:EMailAddress=foo*)(dsAttrTypeStandard:RecordName=foo*))"
        )

        query = buildNestedQueryFromTokens(["foo", "bar"], OpenDirectoryService._ODFields)
        self.assertEquals(
            query.generate(),
            "(&(|(dsAttrTypeStandard:RealName=*foo*)(dsAttrTypeStandard:EMailAddress=foo*)(dsAttrTypeStandard:RecordName=foo*))(|(dsAttrTypeStandard:RealName=*bar*)(dsAttrTypeStandard:EMailAddress=bar*)(dsAttrTypeStandard:RecordName=bar*)))"
        )

        query = buildNestedQueryFromTokens(["foo", "bar", "baz"], OpenDirectoryService._ODFields)
        self.assertEquals(
            query.generate(),
            "(&(|(dsAttrTypeStandard:RealName=*foo*)(dsAttrTypeStandard:EMailAddress=foo*)(dsAttrTypeStandard:RecordName=foo*))(|(dsAttrTypeStandard:RealName=*bar*)(dsAttrTypeStandard:EMailAddress=bar*)(dsAttrTypeStandard:RecordName=bar*))(|(dsAttrTypeStandard:RealName=*baz*)(dsAttrTypeStandard:EMailAddress=baz*)(dsAttrTypeStandard:RecordName=baz*)))"
        )
