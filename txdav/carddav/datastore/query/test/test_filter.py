##
# Copyright (c) 2011-2015 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.syntax import SQLFragment

from twisted.trial.unittest import TestCase

from twistedcaldav import carddavxml

from txdav.carddav.datastore.query.filter import Filter, FilterBase
from txdav.common.datastore.sql_tables import schema
from txdav.carddav.datastore.query.builder import buildExpression
from txdav.common.datastore.query.generator import SQLQueryGenerator
from txdav.carddav.datastore.index_file import sqladdressbookquery

class TestQueryFilter(TestCase):

    _objectSchema = schema.ADDRESSBOOK_OBJECT
    _queryFields = {
        "UID": _objectSchema.UID
    }

    def test_query(self):
        """
        Basic query test - single term.
        Only UID can be queried via sql.
        """

        filter = carddavxml.Filter(
            *[carddavxml.PropertyFilter(
                carddavxml.TextMatch.fromString("Example"),
                **{"name": "UID"}
            )]
        )
        filter = Filter(filter)

        expression = buildExpression(filter, self._queryFields)
        sql = SQLQueryGenerator(expression, self, 1234)
        select, args = sql.generate()

        self.assertEqual(select.toSQL(), SQLFragment("select distinct RESOURCE_NAME, VCARD_UID from ADDRESSBOOK_OBJECT where ADDRESSBOOK_HOME_RESOURCE_ID = ? and VCARD_UID like (? || (? || ?))", [1234, "%", "Example", "%"]))
        self.assertEqual(args, {})


    def test_sqllite_query(self):
        """
        Basic query test - single term.
        Only UID can be queried via sql.
        """

        filter = carddavxml.Filter(
            *[carddavxml.PropertyFilter(
                carddavxml.TextMatch.fromString("Example"),
                **{"name": "UID"}
            )]
        )
        filter = Filter(filter)
        sql, args = sqladdressbookquery(filter, 1234)

        self.assertEqual(sql, " from RESOURCE where RESOURCE.UID GLOB :1")
        self.assertEqual(args, ["*Example*"])



class TestQueryFilterSerialize(TestCase):

    def test_query(self):
        """
        Basic query test - no time range
        """

        filter = carddavxml.Filter(
            *[carddavxml.PropertyFilter(
                carddavxml.TextMatch.fromString("Example"),
                **{"name": "UID"}
            )]
        )
        filter = Filter(filter)
        j = filter.serialize()
        self.assertEqual(j["type"], "Filter")

        f = FilterBase.deserialize(j)
        self.assertTrue(isinstance(f, Filter))
