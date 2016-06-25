##
# Copyright (c) 2011-2016 Apple Inc. All rights reserved.
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
#
##

from twisted.internet.defer import inlineCallbacks, succeed
from twisted.trial.unittest import TestCase

from contrib.performance.loadtest.amphub import AMPHub

class StubProtocol(object):

    def __init__(self, history):
        self.history = history


    def callRemote(self, *args, **kwds):
        self.history.append((args, kwds))
        return succeed(None)



class AMPHubTestCase(TestCase):

    def callback(self, id, dataChangedTimestamp, priority=5):
        self.callbackHistory.append(id)


    @inlineCallbacks
    def test_amphub(self):
        amphub = AMPHub()
        subscribeHistory = []
        protocol = StubProtocol(subscribeHistory)
        amphub.protocols.append(protocol)
        AMPHub._hub = amphub
        keys = ("a", "b", "c")
        yield AMPHub.subscribeToIDs(keys, self.callback)
        self.assertEquals(len(subscribeHistory), 3)
        for key in keys:
            self.assertEquals(len(amphub.callbacks[key]), 1)

        self.callbackHistory = []
        amphub._pushReceived("a", 0)
        amphub._pushReceived("b", 0)
        amphub._pushReceived("a", 0)
        amphub._pushReceived("c", 0)
        self.assertEquals(self.callbackHistory, ["a", "b", "a", "c"])
