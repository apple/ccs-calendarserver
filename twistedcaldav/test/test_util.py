##
# Copyright (c) 2005-2015 Apple Inc. All rights reserved.
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

from txweb2.http_headers import Headers

from twistedcaldav.config import ConfigDict
from twistedcaldav.stdconfig import _updateClientFixes
from twistedcaldav.util import bestAcceptType, userAgentProductTokens, matchClientFixes
import twistedcaldav.test.util

class AcceptType(twistedcaldav.test.util.TestCase):
    """
    L{bestAcceptType} tests
    """
    def test_bestAcceptType(self):

        data = (
            (
                "#1.1",
                ("Accept", "text/plain"),
                ["text/plain"],
                "text/plain",
            ),
            (
                "#1.2",
                ("Accept", "text/plain"),
                ["text/calendar"],
                None,
            ),
            (
                "#1.3",
                ("Accept", "text/*"),
                ["text/plain"],
                "text/plain",
            ),
            (
                "#1.4",
                ("Accept", "*/*"),
                ["text/plain"],
                "text/plain",
            ),
            (
                "#2.1",
                ("Accept", "text/plain"),
                ["text/plain", "application/text", ],
                "text/plain",
            ),
            (
                "#2.2",
                ("Accept", "text/plain"),
                ["text/calendar", "application/text", ],
                None,
            ),
            (
                "#2.3",
                ("Accept", "text/*"),
                ["text/plain", "application/text", ],
                "text/plain",
            ),
            (
                "#2.4",
                ("Accept", "*/*"),
                ["text/plain", "application/text", ],
                "text/plain",
            ),
            (
                "#2.5",
                ("Accept", "application/text"),
                ["text/plain", "application/text", ],
                "application/text",
            ),
            (
                "#2.6",
                ("Accept", "application/*"),
                ["text/plain", "application/text", ],
                "application/text",
            ),
            (
                "#3.1",
                ("Accept", "text/plain;q=0.5, application/text;q=0.3"),
                ["text/plain", "application/text", ],
                "text/plain",
            ),
            (
                "#3.2",
                ("Accept", "text/plain;q=0.5, application/text;q=0.3"),
                ["text/calendar", "application/calendar", ],
                None,
            ),
            (
                "#3.3",
                ("Accept", "text/plain;q=0.5, application/text;q=0.3"),
                ["text/plain", "application/text", ],
                "text/plain",
            ),
            (
                "#3.4",
                ("Accept", "text/plain;q=0.5, application/text;q=0.3"),
                ["text/plain", "application/text", ],
                "text/plain",
            ),
            (
                "#3.5",
                ("Accept", "text/plain;q=0.3, application/text;q=0.5"),
                ["text/plain", "application/text", ],
                "application/text",
            ),
            (
                "#3.6",
                ("Accept", "text/plain;q=0.5, application/*;q=0.3"),
                ["text/plain", "application/text", ],
                "text/plain",
            ),
            (
                "#4.1",
                ("Accept", "text/plain;q=0.5, application/text;q=0.2, text/*;q=0.3"),
                ["text/calendar", "application/text", ],
                "text/calendar",
            ),
            (
                "#5.1",
                None,
                ["text/calendar", "application/text", ],
                "text/calendar",
            ),
        )

        for title, hdr, allowedTypes, result in data:
            hdrs = Headers()
            if hdr:
                hdrs.addRawHeader(*hdr)
            check = bestAcceptType(hdrs.getHeader("accept"), allowedTypes)
            self.assertEqual(check, result, msg="Failed %s" % (title,))


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
