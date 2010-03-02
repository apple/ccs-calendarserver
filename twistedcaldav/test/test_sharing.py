##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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


from twistedcaldav.test.util import InMemoryPropertyStore
from twistedcaldav.test.util import TestCase
from twext.web2.dav import davxml
from twistedcaldav.static import CalDAVFile
from twistedcaldav import customxml
from twisted.internet.defer import inlineCallbacks
import os


class SharingTests(TestCase):
    def setUp(self):
        TestCase.setUp(self)
        collection = self.mktemp()
        os.mkdir(collection)
        self.resource = CalDAVFile(collection)
        self.resource._dead_properties = InMemoryPropertyStore()

    @inlineCallbacks
    def test_upgradeToShare(self):
        self.resource.writeDeadProperty(davxml.ResourceType.calendar)
        self.assertEquals(self.resource.resourceType(), davxml.ResourceType.calendar)
        self.assertFalse(self.resource.hasDeadProperty(customxml.Invite()))

        yield self.resource.upgradeToShare(None)

        self.assertEquals(self.resource.resourceType(), davxml.ResourceType.sharedcalendar)
        self.assertEquals(self.resource.readDeadProperty(customxml.Invite), customxml.Invite())
        
        isShared = (yield self.resource.isShared(None))
        self.assertTrue(isShared)
        isVShared = (yield self.resource.isVirtualShare(None))
        self.assertFalse(isVShared)

    @inlineCallbacks
    def test_downgradeFromShare(self):
        self.resource.writeDeadProperty(davxml.ResourceType.sharedcalendar)
        self.resource.writeDeadProperty(customxml.Invite())
        self.assertEquals(self.resource.resourceType(), davxml.ResourceType.sharedcalendar)
        self.assertEquals(self.resource.readDeadProperty(customxml.Invite), customxml.Invite())

        yield self.resource.downgradeFromShare(None)

        self.assertEquals(self.resource.resourceType(), davxml.ResourceType.calendar)
        self.assertFalse(self.resource.hasDeadProperty(customxml.Invite()))
        
        isShared = (yield self.resource.isShared(None))
        self.assertFalse(isShared)
        isVShared = (yield self.resource.isVirtualShare(None))
        self.assertFalse(isVShared)
