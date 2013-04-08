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

from twisted.internet.defer import inlineCallbacks
from twistedcaldav.config import config
from twistedcaldav.scheduling.ischedule import utils
from twistedcaldav.test.util import TestCase
from twisted.python.modules import getModule
from twisted.names.authority import BindAuthority
from twisted.names import client
from twisted.names.test.test_client import FakeResolver

class LookupService (TestCase):


    def setUp(self):
        """
        Replace the resolver with a FakeResolver
        """
        client.theResolver = FakeResolver()


    def tearDown(self):
        """
        By setting the resolver to None, it will be recreated next time a name
        lookup is done.
        """
        client.theResolver = None
        utils.DebugResolver = None


    def test_initResolver(self):
        """
        Test L{lookupServerViaSRV} with a local Bind find
        """

        # Default resolver
        utils.DebugResolver = None
        utils._initResolver()
        self.assertNotEqual(utils.DebugResolver, None)
        self.assertFalse(isinstance(utils.DebugResolver, BindAuthority))

        # Patch config for Bind resolver
        for zonefile in ("db.example.com", "db.two.zones",):
            module = getModule(__name__)
            dataPath = module.filePath.sibling("data")
            bindPath = dataPath.child(zonefile)
            self.patch(config.Scheduling.iSchedule, "DNSDebug", bindPath.path)
            utils.DebugResolver = None
            utils._initResolver()
            self.assertNotEqual(utils.DebugResolver, None)
            self.assertTrue(isinstance(utils.DebugResolver, BindAuthority))


    @inlineCallbacks
    def test_lookupServerViaSRV(self):
        """
        Test L{lookupServerViaSRV} with a local Bind find
        """

        # Patch config
        for zonefile, checks in (
            ("db.example.com", (("example.com", "example.com", 8443,),),),
            ("db.two.zones", (
                ("example.com", "example.com", 8443,),
                ("example.org", "example.org", 8543,),
            ),),
        ):
            module = getModule(__name__)
            dataPath = module.filePath.sibling("data")
            bindPath = dataPath.child(zonefile)
            self.patch(config.Scheduling.iSchedule, "DNSDebug", bindPath.path)
            utils.DebugResolver = None

            for domain, result_host, result_port in checks:
                host, port = (yield utils.lookupServerViaSRV(domain))
                self.assertEqual(host, result_host)
                self.assertEqual(port, result_port)


    @inlineCallbacks
    def test_lookupDataViaTXT(self):
        """
        Test L{lookupDataViaTXT} with a local Bind find
        """

        # Patch config
        for zonefile, checks in (
            ("db.example.com", (("example.com", "_ischedule._domainkey", "v=DKIM1; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDjUfDqd8ICAL0dyq2KdjKN6LS8O/Y4yMxOxgATqtSIMi7baKXEs1w5Wj9efOC2nU+aqyhP2/J6AzfFJfSB+GV5gcIT+LAC4btJKPGjPUyXcQFJV4a73y0jIgCTBzWxdaP6qD9P9rzYlvMPcdrrKiKoAOtI3JZqAAdZudOmGlc4QQIDAQAB"),),),
            ("db.two.zones", (
                ("example.com", "_ischedule._domainkey", "v=DKIM1; p="),
                ("example.org", "_ischedule2._domainkey", "v=DKIM1; s=ischedule; p="),
            )),
        ):
            module = getModule(__name__)
            dataPath = module.filePath.sibling("data")
            bindPath = dataPath.child(zonefile)
            self.patch(config.Scheduling.iSchedule, "DNSDebug", bindPath.path)
            utils.DebugResolver = None

            for domain, prefix, result in checks:
                texts = (yield utils.lookupDataViaTXT(domain, prefix))
                self.assertEqual(texts, [result])
