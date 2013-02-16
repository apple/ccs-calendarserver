##
# Copyright (c) 2011-2013 Apple Inc. All rights reserved.
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
from twistedcaldav.config import ConfigDict
from calendarserver.push.notifier import PushService
from twisted.internet.defer import inlineCallbacks, succeed
from twisted.application import service

class StubService(service.Service):
    def __init__(self, settings, store):
        self.settings = settings
        self.store = store
        self.reset()

    def reset(self):
        self.history = []

    def enqueue(self, id):
        self.history.append(id)
        return(succeed(None))

    @classmethod
    def makeService(cls, settings, store):
        return cls(settings, store)

class PushServiceTests(TestCase):

    @inlineCallbacks
    def test_enqueue(self):
        settings = ConfigDict({
            "Services" : {
                "Stub" : {
                    "Service" : "calendarserver.push.test.test_notifier.StubService",
                    "Enabled" : True,
                    "Foo" : "Bar",
                },
            },
        })
        svc = PushService.makeService(settings, None)
        yield svc.enqueue("testing")
        self.assertEquals(svc.subServices[0].history, ["testing"])


