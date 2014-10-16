##
# Copyright (c) 2009-2014 Apple Inc. All rights reserved.
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

from txweb2.test.test_server import SimpleRequest

from twisted.trial import unittest

from twistedcaldav.stdconfig import config

from txdav.caldav.datastore.scheduling.ischedule.localservers import (
    ServersDB, SERVER_SECRET_HEADER
)

import StringIO as StringIO


class ServerTests(unittest.TestCase):

    data1 = """<?xml version="1.0" encoding="utf-8"?>
<servers>
  <server>
    <id>00001</id>
    <uri>http://caldav1.example.com:8008</uri>
    <allowed-from>127.0.0.1</allowed-from>
    <shared-secret>foobar</shared-secret>
  </server>
  <server>
    <id>00002</id>
    <uri>https://caldav2.example.com:8843</uri>
  </server>
</servers>
"""

    data2 = """<?xml version="1.0" encoding="utf-8"?>
<servers>
  <server>
    <id>00001</id>
    <uri>http://caldav1.example.com:8008</uri>
    <allowed-from>localhost</allowed-from>
    <shared-secret>foobar</shared-secret>
  </server>
  <server>
    <id>00002</id>
    <uri>https://caldav2.example.com:8843</uri>
  </server>
</servers>
"""

    def _setupServers(self, data=data1):
        self.patch(config, "ServerHostName", "caldav1.example.com")
        self.patch(config, "HTTPPort", 8008)

        xmlFile = StringIO.StringIO(data)
        servers = ServersDB()
        servers.load(xmlFile, ignoreIPLookupFailures=True)

        return servers


    def test_read_ok(self):

        servers = self._setupServers()

        self.assertTrue(servers.getServerById("00001") is not None)
        self.assertTrue(servers.getServerById("00002") is not None)

        self.assertEqual(servers.getServerById("00001").uri, "http://caldav1.example.com:8008")
        self.assertEqual(servers.getServerById("00002").uri, "https://caldav2.example.com:8843")

        self.assertEqual(servers.getServerById("00001").allowed_from_ips, set(("127.0.0.1",)))
        self.assertEqual(servers.getServerById("00002").allowed_from_ips, set())

        self.assertEqual(servers.getServerById("00001").shared_secret, "foobar")
        self.assertEqual(servers.getServerById("00002").shared_secret, None)


    def test_this_server(self):

        servers = self._setupServers()

        self.assertTrue(servers.getServerById("00001").thisServer)
        self.assertFalse(servers.getServerById("00002").thisServer)
        self.assertEqual(servers.getThisServer(), servers.getServerById("00001"))

        self.patch(config, "ServerHostName", "caldav2.example.com")
        self.patch(config, "SSLPort", 8443)
        self.patch(config, "BindSSLPorts", [8843])

        xmlFile = StringIO.StringIO(ServerTests.data1)
        servers = ServersDB()
        servers.load(xmlFile, ignoreIPLookupFailures=True)

        self.assertFalse(servers.getServerById("00001").thisServer)
        self.assertTrue(servers.getServerById("00002").thisServer)
        self.assertEqual(servers.getThisServer(), servers.getServerById("00002"))


    def test_all_except_this_server(self):

        servers = self._setupServers()

        self.assertTrue(servers.getServerById("00001").thisServer)
        self.assertFalse(servers.getServerById("00002").thisServer)
        self.assertEqual(servers.allServersExceptThis(), [servers.getServerById("00002"), ])

        self.patch(config, "ServerHostName", "caldav2.example.com")
        self.patch(config, "SSLPort", 8443)
        self.patch(config, "BindSSLPorts", [8843])

        xmlFile = StringIO.StringIO(ServerTests.data1)
        servers = ServersDB()
        servers.load(xmlFile, ignoreIPLookupFailures=True)

        self.assertFalse(servers.getServerById("00001").thisServer)
        self.assertTrue(servers.getServerById("00002").thisServer)
        self.assertEqual(servers.allServersExceptThis(), [servers.getServerById("00001"), ])


    def test_check_this_ip(self):

        servers = self._setupServers()
        servers.getServerById("00001").ips = set(("127.0.0.2",))
        servers.getServerById("00002").ips = set(("127.0.0.3",))

        self.assertTrue(servers.getServerById("00001").checkThisIP("127.0.0.2"))
        self.assertFalse(servers.getServerById("00001").checkThisIP("127.0.0.3"))


    def test_check_allowed_from(self):

        for servers in (self._setupServers(), self._setupServers(data=self.data2),):
            self.assertTrue(servers.getServerById("00001").hasAllowedFromIP())
            self.assertFalse(servers.getServerById("00002").hasAllowedFromIP())

            self.assertTrue(servers.getServerById("00001").checkAllowedFromIP("127.0.0.1"))
            self.assertFalse(servers.getServerById("00001").checkAllowedFromIP("127.0.0.2"))
            self.assertFalse(servers.getServerById("00001").checkAllowedFromIP("127.0.0.3"))
            self.assertFalse(servers.getServerById("00002").checkAllowedFromIP("127.0.0.1"))
            self.assertFalse(servers.getServerById("00002").checkAllowedFromIP("127.0.0.2"))
            self.assertFalse(servers.getServerById("00002").checkAllowedFromIP("127.0.0.3"))


    def test_check_shared_secret(self):

        servers = self._setupServers()

        request = SimpleRequest(None, "POST", "/ischedule")
        request.headers.addRawHeader(SERVER_SECRET_HEADER, "foobar")
        self.assertTrue(servers.getServerById("00001").checkSharedSecret(request.headers))

        request = SimpleRequest(None, "POST", "/ischedule")
        request.headers.addRawHeader(SERVER_SECRET_HEADER, "foobar1")
        self.assertFalse(servers.getServerById("00001").checkSharedSecret(request.headers))

        request = SimpleRequest(None, "POST", "/ischedule")
        self.assertFalse(servers.getServerById("00001").checkSharedSecret(request.headers))

        request = SimpleRequest(None, "POST", "/ischedule")
        request.headers.addRawHeader(SERVER_SECRET_HEADER, "foobar")
        self.assertFalse(servers.getServerById("00002").checkSharedSecret(request.headers))

        request = SimpleRequest(None, "POST", "/ischedule")
        request.headers.addRawHeader(SERVER_SECRET_HEADER, "foobar1")
        self.assertFalse(servers.getServerById("00002").checkSharedSecret(request.headers))

        request = SimpleRequest(None, "POST", "/ischedule")
        self.assertTrue(servers.getServerById("00002").checkSharedSecret(request.headers))
