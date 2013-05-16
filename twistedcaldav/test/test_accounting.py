##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

from twext.web2.channel.http import HTTPLoggingChannelRequest
from twext.web2 import http_headers
from twext.web2.channel.http import HTTPChannel
from twistedcaldav.accounting import emitAccounting
from twistedcaldav.config import config
import twistedcaldav.test.util

import os
import stat

class AccountingITIP (twistedcaldav.test.util.TestCase):

    def setUp(self):
        super(AccountingITIP, self).setUp()
        config.AccountingCategories.iTIP = True
        config.AccountingPrincipals = ["*", ]
        os.mkdir(config.AccountingLogRoot)


    class _Principal(object):

        class _Record(object):

            def __init__(self, guid):
                self.guid = guid

        def __init__(self, guid):

            self.record = self._Record(guid)


    def test_permissions_makedirs(self):
        """
        Test permissions when creating accounting
        """

        # Make log root non-writeable
        os.chmod(config.AccountingLogRoot, stat.S_IRUSR)

        emitAccounting("iTIP", self._Principal("1234-5678"), "bogus")


    def test_file_instead_of_directory(self):
        """
        Test permissions when creating accounting
        """

        # Make log root a file
        config.AccountingLogRoot = "other"
        open(config.AccountingLogRoot, "w").close()
        emitAccounting("iTIP", self._Principal("1234-5678"), "bogus")



class AccountingHTTP (twistedcaldav.test.util.TestCase):

    def setUp(self):

        super(AccountingHTTP, self).setUp()
        config.AccountingCategories.HTTP = True
        config.AccountingPrincipals = ["*", ]


    def test_channel_request(self):
        """
        Test permissions when creating accounting
        """

        # Make channel request object
        channelRequest = HTTPLoggingChannelRequest(HTTPChannel())
        self.assertTrue(channelRequest != None)


    def test_logging(self):
        """
        Test permissions when creating accounting
        """

        class FakeRequest(object):

            def handleContentChunk(self, data):
                pass
            def handleContentComplete(self):
                pass

        # Make log root a file
        channelRequest = HTTPLoggingChannelRequest(HTTPChannel(), queued=1)
        channelRequest.request = FakeRequest()

        channelRequest.gotInitialLine("GET / HTTP/1.1")
        channelRequest.lineReceived("Host:localhost")
        channelRequest.lineReceived("Content-Length:5")
        channelRequest.handleContentChunk("Bogus")
        channelRequest.handleContentComplete()
        channelRequest.writeHeaders(200, http_headers.Headers({"Content-Type": http_headers.MimeType('text', 'plain'), "Content-Length": "4"}))
        channelRequest.transport.write("Data")
        channelRequest.finish()
