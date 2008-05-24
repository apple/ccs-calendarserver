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

from twisted.trial.unittest import TestCase

from twistedcaldav.resource import CalDAVResource

from twistedcaldav.test.util import InMemoryPropertyStore


class StubProperty(object):
    def qname(self):
        return "StubQname"


class CalDAVResourceTests(TestCase):
    def setUp(self):
        self.resource = CalDAVResource()
        self.resource._dead_properties = InMemoryPropertyStore()

    def test_writeDeadPropertyWritesProperty(self):
        prop = StubProperty()
        self.resource.writeDeadProperty(prop)
        self.assertEquals(self.resource._dead_properties.get("StubQname"),
                          prop)
