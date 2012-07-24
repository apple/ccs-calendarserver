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

from tempfile import mkstemp
import os
import twistedcaldav.test.util
from plistlib import readPlist
from contrib.certupdate.calendarcertupdate import (
    getMyCert, isThisMyCert, replaceCert, removeCert
)

samplePlist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>SSLAuthorityChain</key>
    <string>/etc/certificates/original.chain.pem</string>
    <key>SSLCertificate</key>
    <string>/etc/certificates/original.cert.pem</string>
    <key>SSLPrivateKey</key>
    <string>/etc/certificates/original.key.pem</string>
    <key>EnableSSL</key>
    <true/>
</dict>
</plist>
"""

class CertUpdateTests(twistedcaldav.test.util.TestCase):
    """
    Calendar Server Certificate Update Tests
    """

    def setUp(self):
        self.fd, self.path = mkstemp(suffix=".plist")
        out = os.fdopen(self.fd, "w")
        out.write(samplePlist)
        out.close()

    def tearDown(self):
        os.remove(self.path)

    def test_getMyCert(self):
        self.assertEquals("/etc/certificates/original.cert.pem", getMyCert(self.path))

    def test_isThisMyCert(self):
        self.assertTrue(isThisMyCert(self.path, "/etc/certificates/original.cert.pem"))
        self.assertFalse(isThisMyCert(self.path, "/etc/certificates/not.cert.pem"))

    def test_replaceCert(self):
        replaceCert(self.path, "/etc/certificates/new.cert.pem")
        plist = readPlist(self.path)
        self.assertEquals(plist["SSLAuthorityChain"], "/etc/certificates/new.chain.pem")
        self.assertEquals(plist["SSLCertificate"], "/etc/certificates/new.cert.pem")
        self.assertEquals(plist["SSLPrivateKey"], "/etc/certificates/new.key.pem")

    def test_removeCert(self):
        removeCert(self.path)
        plist = readPlist(self.path)
        self.assertEquals(plist["SSLAuthorityChain"], "")
        self.assertEquals(plist["SSLCertificate"], "")
        self.assertEquals(plist["SSLPrivateKey"], "")
