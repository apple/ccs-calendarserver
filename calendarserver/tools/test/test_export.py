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

"""
Unit tests for L{calendarsever.tools.export}.
"""


import sys
from cStringIO import StringIO

from twisted.trial.unittest import TestCase

from calendarserver.tools.export import usage

class CommandLine(TestCase):
    """
    Simple tests for command-line parsing.
    """

    def test_usageMessage(self):
        """
        The 'usage' message should print something to standard output (and
        nothing to standard error) and exit.
        """
        orig = sys.stdout
        orige = sys.stderr
        try:
            out = sys.stdout = StringIO()
            err = sys.stderr = StringIO()
            self.assertRaises(SystemExit, usage)
        finally:
            sys.stdout = orig
            sys.stderr = orige
        self.assertEquals(len(out.getvalue()) > 0, True, "No output.")
        self.assertEquals(len(err.getvalue()), 0)



