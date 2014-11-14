##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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
from twistedcaldav.util import userAgentProductTokens, matchClientFixes
from twistedcaldav.stdconfig import _updateClientFixes
from twistedcaldav.config import ConfigDict

class TestUtil(twistedcaldav.test.util.TestCase):
    """
    Tests for L{twistedcaldav.util}
    """
    def test_userAgentProductTokens(self):
        """
        Test that L{userAgentProductTokens} correctly parses a User-Agent header.
        """
        for hdr, result in (
            # Valid syntax
            ("Client/1.0", ["Client/1.0", ]),
            ("Client/1.0 FooBar/2", ["Client/1.0", "FooBar/2", ]),
            ("Client/1.0 (commentary here)", ["Client/1.0", ]),
            ("Client/1.0 (FooBar/2)", ["Client/1.0", ]),
            ("Client/1.0 (commentary here) FooBar/2", ["Client/1.0", "FooBar/2", ]),
            ("Client/1.0 (commentary here) FooBar/2 (more commentary here) ", ["Client/1.0", "FooBar/2", ]),

            # Invalid syntax
            ("Client/1.0 (commentary here FooBar/2", ["Client/1.0", ]),
            ("Client/1.0 commentary here) FooBar/2", ["Client/1.0", "commentary", "here)", "FooBar/2", ]),
        ):
            self.assertEqual(userAgentProductTokens(hdr), result, msg="Mismatch: {}".format(hdr))


    def test_matchClientFixes(self):
        """
        Test that L{matchClientFixes} correctly identifies clients with matching fix tokens.
        """
        c = ConfigDict()
        c.ClientFixes = {
            "fix1": [
                "Client/1\\.0.*",
                "Client/1\\.1(\\..*)?",
                "Client/2",
            ],
            "fix2": [
                "Other/1\\.0.*",
            ],
        }
        _updateClientFixes(c)
        _updateClientFixes(c)

        # Valid matches
        for ua in (
            "Client/1.0 FooBar/2",
            "Client/1.0.1 FooBar/2",
            "Client/1.0.1.1 FooBar/2",
            "Client/1.1 FooBar/2",
            "Client/1.1.1 FooBar/2",
            "Client/2 FooBar/2",
        ):
            self.assertEqual(
                matchClientFixes(c, ua),
                set(("fix1",)),
                msg="Did not match {}".format(ua),
            )

        # Valid non-matches
        for ua in (
            "Client/1 FooBar/2",
            "Client/1.10 FooBar/2",
            "Client/2.0 FooBar/2",
            "Client/2.0.1 FooBar/2",
            "Client FooBar/2",
            "Client/3 FooBar/2",
            "Client/3.0 FooBar/2",
            "Client/10 FooBar/2",
            "Client/10.0 FooBar/2",
            "Client/10.0.1 FooBar/2",
            "Client/10.0.1 (Client/1.0) FooBar/2",
            "Client/10.0.1 (foo Client/1.0 bar) FooBar/2",
        ):
            self.assertEqual(
                matchClientFixes(c, ua),
                set(),
                msg="Incorrectly matched {}".format(ua),
            )
