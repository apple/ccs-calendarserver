##
# Copyright (c) 2014-2015 Apple Inc. All rights reserved.
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

from __future__ import print_function
from __future__ import absolute_import

"""
Tests for L{txdav.who.wiki}.
"""


from twisted.trial import unittest
from twisted.internet.defer import inlineCallbacks, succeed
from twistedcaldav.test.util import StoreTestCase

from ..wiki import (
    DirectoryService, WikiAccessLevel, getWikiACL, RecordType, DirectoryRecord
)
import txdav.who.wiki


class WikiIndividualServiceTestCase(unittest.TestCase):
    """
    Instantiate a wiki service directly
    """

    @inlineCallbacks
    def test_service(self):
        service = DirectoryService("realm", "localhost", 4444)
        record = yield service.recordWithUID(u"wiki-test")
        self.assertEquals(
            record.shortNames[0],
            u"test"
        )



class WikiAggregateServiceTestCase(StoreTestCase):
    """
    Get a wiki service as part of directoryFromConfig
    """

    def configure(self):
        """
        Override configuration hook to turn on wiki service.
        """
        from twistedcaldav.config import config

        super(WikiAggregateServiceTestCase, self).configure()
        self.patch(config.Authentication.Wiki, "Enabled", True)


    @inlineCallbacks
    def test_service(self):
        record = yield self.directory.recordWithUID(u"wiki-test")
        self.assertEquals(
            record.shortNames[0],
            u"test"
        )



class AccessForRecordTestCase(StoreTestCase):
    """
    Exercise accessForRecord
    """

    def configure(self):
        """
        Override configuration hook to turn on wiki service.
        """
        from twistedcaldav.config import config

        super(AccessForRecordTestCase, self).configure()
        self.patch(config.Authentication.Wiki, "Enabled", True)
        self.patch(
            txdav.who.wiki,
            "accessForUserToWiki",
            self.stubAccessForUserToWiki
        )


    def stubAccessForUserToWiki(self, *args, **kwds):
        return succeed(self.access)


    @inlineCallbacks
    def test_accessForRecord(self):
        record = yield self.directory.recordWithUID(u"wiki-test")

        self.access = "no-access"
        access = yield record.accessForRecord(None)
        self.assertEquals(access, WikiAccessLevel.none)

        self.access = "read"
        access = yield record.accessForRecord(None)
        self.assertEquals(access, WikiAccessLevel.read)

        self.access = "write"
        access = yield record.accessForRecord(None)
        self.assertEquals(access, WikiAccessLevel.write)

        self.access = "admin"
        access = yield record.accessForRecord(None)
        self.assertEquals(access, WikiAccessLevel.write)



# Test getWikiACL()
# Currently stubs out enough functionality to test that an unauthenticated
# request can support read access when generating an ACL element
# TODO: add tests which have auth'd principals in the request

class FakeRequest(object):

    def __init__(self):
        self.authnUser = None



class FakeResource(object):

    def __init__(self, record):
        self.record = record



def stubAccessForRecord(self, record):
    return succeed(self.access)



class GetWikiACLTestCase(StoreTestCase):
    """
    Exercise getWikiACL
    """

    def configure(self):
        """
        Override configuration hook to turn on wiki service.
        """
        from twistedcaldav.config import config

        super(GetWikiACLTestCase, self).configure()
        self.patch(config.Authentication.Wiki, "Enabled", True)
        self.patch(
            txdav.who.wiki.DirectoryRecord,
            "accessForRecord",
            stubAccessForRecord
        )


    @inlineCallbacks
    def test_getWikiACL(self):
        fields = {
            self.directory.fieldName.uid: u"wiki-1",
            self.directory.fieldName.shortNames: [u"wiki-one", ],
            self.directory.fieldName.recordType: RecordType.macOSXServerWiki,
        }
        record = DirectoryRecord(self.directory, fields)
        resource = FakeResource(record)
        request = FakeRequest()

        record.access = WikiAccessLevel.read
        result = yield getWikiACL(resource, request)
        self.assertEqual(
            result.children[0].children[0].children[0].name,
            "unauthenticated"
        )
