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

import twistedcaldav.test.util
from contrib.migration.calendarmigrator import mergePlist

class MigrationTests(twistedcaldav.test.util.TestCase):
    """
    Calendar Server Migration Tests
    """

    def test_mergeSSL(self):

        # SSL on for both services
        oldCalDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        oldCardDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8800,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8843,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        expected = {
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "EnableSSL" : True,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)

        # SSL off for both services
        oldCalDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 0,
            "SSLPrivateKey": "",
        }
        oldCardDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8800,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 0,
            "SSLPrivateKey": "",
        }
        expected = {
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)

        # SSL on for only caldav
        oldCalDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        oldCardDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8800,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 0,
            "SSLPrivateKey": "",
        }
        expected = {
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "EnableSSL" : True,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)

        # SSL on for only carddav
        oldCalDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 0,
            "SSLPrivateKey": "",
        }
        oldCardDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8800,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8843,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        expected = {
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "EnableSSL" : True,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)

        # Non standard ports
        oldCalDAV = {
            "BindHTTPPorts": [1111, 2222],
            "BindSSLPorts": [3333],
            "HTTPPort": 8888,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 9999,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        oldCardDAV = {
            "BindHTTPPorts": [4444, 5555],
            "BindSSLPorts": [6666],
            "HTTPPort": 7777,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 11111,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        expected = {
            "BindHTTPPorts": [1111, 2222, 4444, 5555, 7777, 8888],
            "BindSSLPorts": [3333, 6666, 9999, 11111],
            "EnableSSL" : True,
            "HTTPPort": 8888,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 9999,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)



