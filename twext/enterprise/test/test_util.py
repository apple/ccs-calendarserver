##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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

import datetime

from twisted.python.unittest import TestCase

from twext.enterprise.util import parseSQLTimestamp

class TimestampTests(TestCase):
    """
    Tests for date-related functions.
    """

    def test_parseSQLTimestamp(self):
        """
        L{parseSQLTimestamp} parses the traditional SQL timestamp.
        """
        tests = (
            ("2012-04-04 12:34:56", datetime.datetime(2012, 4, 4, 12, 34, 56)),
            ("2012-12-31 01:01:01", datetime.datetime(2012, 12, 31, 1, 1, 1)),
        )

        for sqlStr, result in tests:
            self.assertEqual(parseSQLTimestamp(sqlStr), result)
