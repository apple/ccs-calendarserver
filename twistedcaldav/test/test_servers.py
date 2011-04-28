##
# Copyright (c) 2009-2010 Apple Inc. All rights reserved.
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

from twistedcaldav.servers import Servers
from twistedcaldav.test.util import TestCase
import StringIO as StringIO
from twistedcaldav.config import config

class ServerTests(TestCase):

    data1 = """<?xml version="1.0" encoding="utf-8"?>
<servers>
  <server>
    <id>00001</id>
    <uri>http://caldav1.example.com:8008</uri>
  </server>
  <server>
    <id>00002</id>
    <uri>https://caldav2.example.com:8843</uri>
    <partitions>
        <partition>
            <id>A</id>
            <uri>https://machine1.example.com:8443</uri>
        </partition>
        <partition>
            <id>B</id>
            <uri>https://machine2.example.com:8443</uri>
        </partition>
    </partitions>
  </server>
</servers>
"""
        
    def test_read_ok(self):
        
        self.patch(config, "ServerHostName", "caldav1.example.com")
        self.patch(config, "HTTPPort", 8008)

        xmlFile = StringIO.StringIO(ServerTests.data1)
        servers = Servers
        servers.load(xmlFile)

        self.assertTrue(servers.getServerById("00001") is not None)
        self.assertTrue(servers.getServerById("00002") is not None)

        self.assertEqual(servers.getServerById("00001").uri, "http://caldav1.example.com:8008")
        self.assertEqual(servers.getServerById("00002").uri, "https://caldav2.example.com:8843")

        self.assertEqual(len(servers.getServerById("00001").partitions), 0)
        self.assertEqual(len(servers.getServerById("00002").partitions), 2)

        self.assertEqual(servers.getServerById("00002").getPartitionURIForId("A"), "https://machine1.example.com:8443")
        self.assertEqual(servers.getServerById("00002").getPartitionURIForId("B"), "https://machine2.example.com:8443")

    def test_this_server(self):
        
        self.patch(config, "ServerHostName", "caldav1.example.com")
        self.patch(config, "HTTPPort", 8008)
        
        xmlFile = StringIO.StringIO(ServerTests.data1)
        servers = Servers
        servers.load(xmlFile)

        self.assertTrue(servers.getServerById("00001").thisServer)
        self.assertFalse(servers.getServerById("00002").thisServer)
        
        self.patch(config, "ServerHostName", "caldav2.example.com")
        self.patch(config, "SSLPort", 8443)
        self.patch(config, "BindSSLPorts", [8843])
        
        xmlFile = StringIO.StringIO(ServerTests.data1)
        servers = Servers
        servers.load(xmlFile)

        self.assertFalse(servers.getServerById("00001").thisServer)
        self.assertTrue(servers.getServerById("00002").thisServer)
