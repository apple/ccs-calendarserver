##
# Copyright (c) 2008 Apple Inc. All rights reserved.
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

from twistedcaldav.resource import CalDAVResource, CommonHomeResource, CalendarHomeResource, AddressBookHomeResource

from twistedcaldav.test.util import InMemoryPropertyStore
from twistedcaldav.test.util import TestCase


class StubProperty(object):
    def qname(self):
        return "StubQnamespace", "StubQname"

class StubHome(object):
    def properties(self):
        return []
    
    def addNotifier(self, notifier):
        pass


class CalDAVResourceTests(TestCase):
    def setUp(self):
        TestCase.setUp(self)
        self.resource = CalDAVResource()
        self.resource._dead_properties = InMemoryPropertyStore()

    def test_writeDeadPropertyWritesProperty(self):
        prop = StubProperty()
        self.resource.writeDeadProperty(prop)
        self.assertEquals(self.resource._dead_properties.get(("StubQnamespace", "StubQname")),
                          prop)

class CommonHomeResourceTests(TestCase):

    def test_commonHomeliveProperties(self):
        resource = CommonHomeResource(None, None, None, StubHome())
        self.assertTrue(('http://calendarserver.org/ns/', 'push-transports') in resource.liveProperties())
        self.assertTrue(('http://calendarserver.org/ns/', 'pushkey') in resource.liveProperties())

    def test_calendarHomeliveProperties(self):
        resource = CalendarHomeResource(None, None, None, StubHome())
        self.assertTrue(('http://calendarserver.org/ns/', 'push-transports') in resource.liveProperties())
        self.assertTrue(('http://calendarserver.org/ns/', 'pushkey') in resource.liveProperties())
        self.assertTrue(('http://calendarserver.org/ns/', 'xmpp-uri') in resource.liveProperties())
        self.assertTrue(('http://calendarserver.org/ns/', 'xmpp-heartbeat-uri') in resource.liveProperties())
        self.assertTrue(('http://calendarserver.org/ns/', 'xmpp-server') in resource.liveProperties())

    def test_addressBookHomeliveProperties(self):
        resource = AddressBookHomeResource(None, None, None, StubHome())
        self.assertTrue(('http://calendarserver.org/ns/', 'push-transports') in resource.liveProperties())
        self.assertTrue(('http://calendarserver.org/ns/', 'pushkey') in resource.liveProperties())
        self.assertTrue(('http://calendarserver.org/ns/', 'xmpp-uri') not in resource.liveProperties())
        self.assertTrue(('http://calendarserver.org/ns/', 'xmpp-heartbeat-uri') not in resource.liveProperties())
        self.assertTrue(('http://calendarserver.org/ns/', 'xmpp-server') not in resource.liveProperties())
