##
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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

from twistedcaldav.test.util import TestCase
from twistedcaldav.directory.wiki import (
    WikiDirectoryService, WikiDirectoryRecord, getWikiAccess
)
from twisted.internet.defer import inlineCallbacks, succeed
from twisted.web.xmlrpc import Fault
from twext.web2.http import HTTPError
from twext.web2 import responsecode

class WikiTestCase(TestCase):
    """
    Test the Wiki Directory Service
    """

    def test_enabled(self):
        service = WikiDirectoryService()
        service.realmName = "Test"
        record = WikiDirectoryRecord(service,
            WikiDirectoryService.recordType_wikis,
            "test",
            None
        )
        self.assertTrue(record.enabled)
        self.assertTrue(record.enabledForCalendaring)


    @inlineCallbacks
    def test_getWikiAccess(self):
        """
        XMLRPC Faults result in HTTPErrors
        """

        def successful(self, user, wiki):
            return succeed("read")

        def fault2(self, user, wiki):
            raise Fault(2, "Bad session")

        def fault12(self, user, wiki):
            raise Fault(12, "Non-existent wiki")

        def fault13(self, user, wiki):
            raise Fault(13, "Non-existent wiki")

        access = (yield getWikiAccess("user", "wiki", method=successful))
        self.assertEquals(access, "read")

        for (method, code) in (
            (fault2, responsecode.FORBIDDEN),
            (fault12, responsecode.NOT_FOUND),
            (fault13, responsecode.SERVICE_UNAVAILABLE),
        ):
            try:
                access = (yield getWikiAccess("user", "wiki", method=method))
            except HTTPError, e:
                self.assertEquals(e.response.code, code)
            except:
                self.fail("Incorrect exception")
            else:
                self.fail("Didn't raise exception")
