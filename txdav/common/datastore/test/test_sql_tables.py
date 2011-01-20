# -*- test-case-name: txdav.caldav.datastore.test.test_sql -*-
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

"""
Tests for the SQL Table definitions in txdav.common.datastore.sql_tables: sample
a couple of tables to make sure the schema is adequately parsed.

These aren't unit tests, they're integration tests to verify the behavior tested
by L{txdav.base.datastore.test.test_parseschema}.
"""

from txdav.common.datastore.sql_tables import schema
from twisted.trial.unittest import TestCase

class SampleSomeColumns(TestCase):
    """
    Sample some columns from the tables defined by L{schema} and verify that
    they look correct.
    """

    def test_addressbookObjectResourceID(self):
        self.assertEquals(schema.ADDRESSBOOK_OBJECT.RESOURCE_ID.model.name,
                          "RESOURCE_ID")

