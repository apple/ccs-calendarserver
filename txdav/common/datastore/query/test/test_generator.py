##
# Copyright (c) 2012-2014 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.syntax import SQLFragment, Parameter
from txdav.common.datastore.query.generator import SQLQueryGenerator
from txdav.common.datastore.query import expression

"""
Tests for L{txdav.common.datastore.sql}.
"""

from twisted.trial.unittest import TestCase

from txdav.common.datastore.sql_tables import schema

class SQLQueryGeneratorTests(TestCase):
    """
    Tests for shared functionality in L{txdav.common.datastore.sql}.
    """

    class FakeHomeChild(object):
        _objectSchema = schema.CALENDAR_OBJECT

        def id(self):
            return 1234


    def test_all_query(self):

        expr = expression.allExpression()
        resource = self.FakeHomeChild()
        select, args = SQLQueryGenerator(expr, resource, resource.id()).generate()
        self.assertEqual(select.toSQL(), SQLFragment("select distinct RESOURCE_NAME, ICALENDAR_UID from CALENDAR_OBJECT where CALENDAR_RESOURCE_ID = ?", [1234]))
        self.assertEqual(args, {})


    def test_uid_query(self):

        resource = self.FakeHomeChild()
        obj = resource._objectSchema
        expr = expression.isExpression(obj.UID, 5678, False)
        select, args = SQLQueryGenerator(expr, resource, resource.id()).generate()
        self.assertEqual(select.toSQL(), SQLFragment("select distinct RESOURCE_NAME, ICALENDAR_UID from CALENDAR_OBJECT where CALENDAR_RESOURCE_ID = ? and ICALENDAR_UID = ?", [1234, 5678]))
        self.assertEqual(args, {})


    def test_or_query(self):

        resource = self.FakeHomeChild()
        obj = resource._objectSchema
        expr = expression.orExpression((
            expression.isExpression(obj.UID, 5678, False),
            expression.isnotExpression(obj.RESOURCE_NAME, "foobar.ics", False),
        ))
        select, args = SQLQueryGenerator(expr, resource, resource.id()).generate()
        self.assertEqual(
            select.toSQL(),
            SQLFragment(
                "select distinct RESOURCE_NAME, ICALENDAR_UID from CALENDAR_OBJECT where CALENDAR_RESOURCE_ID = ? and (ICALENDAR_UID = ? or RESOURCE_NAME != ?)",
                [1234, 5678, "foobar.ics"]
            )
        )
        self.assertEqual(args, {})


    def test_and_query(self):

        resource = self.FakeHomeChild()
        obj = resource._objectSchema
        expr = expression.andExpression((
            expression.isExpression(obj.UID, 5678, False),
            expression.isnotExpression(obj.RESOURCE_NAME, "foobar.ics", False),
        ))
        select, args = SQLQueryGenerator(expr, resource, resource.id()).generate()
        self.assertEqual(
            select.toSQL(),
            SQLFragment(
                "select distinct RESOURCE_NAME, ICALENDAR_UID from CALENDAR_OBJECT where CALENDAR_RESOURCE_ID = ? and ICALENDAR_UID = ? and RESOURCE_NAME != ?",
                [1234, 5678, "foobar.ics"]
            )
        )
        self.assertEqual(args, {})


    def test_not_query(self):

        resource = self.FakeHomeChild()
        obj = resource._objectSchema
        expr = expression.notExpression(expression.isExpression(obj.UID, 5678, False))
        select, args = SQLQueryGenerator(expr, resource, resource.id()).generate()
        self.assertEqual(
            select.toSQL(),
            SQLFragment(
                "select distinct RESOURCE_NAME, ICALENDAR_UID from CALENDAR_OBJECT where CALENDAR_RESOURCE_ID = ? and not ICALENDAR_UID = ?",
                [1234, 5678]
            )
        )
        self.assertEqual(args, {})


    def test_in_query(self):

        resource = self.FakeHomeChild()
        obj = resource._objectSchema
        expr = expression.inExpression(obj.RESOURCE_NAME, ["1.ics", "2.ics", "3.ics"], False)
        select, args = SQLQueryGenerator(expr, resource, resource.id()).generate()
        self.assertEqual(
            select.toSQL(),
            SQLFragment(
                "select distinct RESOURCE_NAME, ICALENDAR_UID from CALENDAR_OBJECT where CALENDAR_RESOURCE_ID = ? and RESOURCE_NAME in (?, ?, ?)",
                [1234, Parameter('arg1', 3)]
            )
        )
        self.assertEqual(args, {"arg1": ["1.ics", "2.ics", "3.ics"]})
