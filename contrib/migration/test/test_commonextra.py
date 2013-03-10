##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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

import twistedcaldav.test.util
from contrib.migration.calendarcommonextra import updateSettings

class CommonExtraTests(twistedcaldav.test.util.TestCase):
    """
    Calendar Server CommonExtra Tests
    """

    def test_updateSettings(self):
        """
        Verify SSL values are updated
        """

        # suppress prints
        from contrib.migration import calendarcommonextra
        self.patch(calendarcommonextra, "log", lambda x : x)

        orig = {
        }
        expected = {
            'Authentication': {'Basic': {'Enabled': True}},
            'EnableSSL': True,
            'RedirectHTTPToHTTPS': True,
            'SSLAuthorityChain': '/test/pchain.pem',
            'SSLCertificate': '/test/path.cert',
            'SSLPrivateKey': '/test/pkey.pem',
        }
        updateSettings(orig, "/test/path.cert")
        self.assertEquals(orig, expected)
