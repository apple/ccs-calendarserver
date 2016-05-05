##
# Copyright (c) 2016 Apple Inc. All rights reserved.
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
from __future__ import print_function

from calendarserver.push.amppush import AMPPushClientFactory, SubscribeToID
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.internet.defer import inlineCallbacks
from twisted.internet import reactor
from uuid import uuid4


class AMPHub(object):

    _hub = None

    def __init__(self):
        # self.hostsAndPorts = hostsAndPorts
        self.protocols = []
        self.callbacks = {}


    @classmethod
    @inlineCallbacks
    def start(cls, hostsAndPorts):
        """
        Instantiates the AMPHub singleton and connects to the hosts.

        @param hostsAndPorts: The hosts and ports to connect to
        @type hostsAndPorts: A list of (hostname, port) tuples
        """

        cls._hub = cls()

        for host, port in hostsAndPorts:
            endpoint = TCP4ClientEndpoint(reactor, host, port)
            factory = AMPPushClientFactory(cls._hub._pushReceived)
            protocol = yield endpoint.connect(factory)
            cls._hub.protocols.append(protocol)


    @classmethod
    @inlineCallbacks
    def subscribeToIDs(cls, ids, callback):
        """
        Clients can call this method to register a callback which
        will get called whenever a push notification is fired for any
        id in the ids list.

        @param ids: The push IDs to subscribe to
        @type ids: list of strings
        @param callback: The method to call whenever a notification is
            received.
        @type callback: callable which is passed an id (string), a timestamp
            of the change in data triggering this push (integer), and the
            priority level (integer)

        """
        hub = cls._hub

        for id in ids:
            hub.callbacks.setdefault(id, []).append(callback)
            for protocol in hub.protocols:
                yield protocol.callRemote(SubscribeToID, token=str(uuid4()), id=id)


    def _pushReceived(self, id, dataChangedTimestamp, priority=5):
        """
        Called for every incoming push notification, this method then calls
        each callback registered for the given ID.
        """

        for callback in self.callbacks.setdefault(id, []):
            callback(id, dataChangedTimestamp, priority=priority)
