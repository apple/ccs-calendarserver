##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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

from calendarserver.push.util import PushScheduler
from twext.python.log import Logger, LoggingMixIn
from twext.python.log import LoggingMixIn
from twisted.application.internet import StreamServerEndpointService
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.endpoints import TCP4ClientEndpoint, TCP4ServerEndpoint
from twisted.internet.protocol import Factory, ServerFactory
from twisted.protocols import amp
from twistedcaldav.notify import getPubSubPath
import uuid


log = Logger()


# AMP Commands sent to server

class SubscribeToID(amp.Command):
    arguments = [('token', amp.String()), ('id', amp.String())]
    response = [('status', amp.String())]


class UnsubscribeFromID(amp.Command):
    arguments = [('token', amp.String()), ('id', amp.String())]
    response = [('status', amp.String())]


# AMP Commands sent to client

class NotificationForID(amp.Command):
    arguments = [('id', amp.String())]
    response = [('status', amp.String())]


# Server classes

class AMPPushNotifierService(StreamServerEndpointService, LoggingMixIn):
    """
    AMPPushNotifierService allows clients to use AMP to subscribe to,
    and receive, change notifications.
    """

    @classmethod
    def makeService(cls, settings, ignored, serverHostName, reactor=None):
        return cls(settings, serverHostName, reactor=reactor)

    def __init__(self, settings, serverHostName, reactor=None):
        if reactor is None:
            from twisted.internet import reactor
        factory = AMPPushNotifierFactory(self)
        endpoint = TCP4ServerEndpoint(reactor, settings["Port"])
        super(AMPPushNotifierService, self).__init__(endpoint, factory)
        self.subscribers = []

        if settings["EnableStaggering"]:
            self.scheduler = PushScheduler(reactor, self.sendNotification,
                staggerSeconds=settings["StaggerSeconds"])
        else:
            self.scheduler = None

        self.serverHostName = serverHostName

    def addSubscriber(self, p):
        self.log_debug("Added subscriber")
        self.subscribers.append(p)

    def removeSubscriber(self, p):
        self.log_debug("Removed subscriber")
        self.subscribers.remove(p)

    def enqueue(self, op, id):
        """
        Sends an AMP push notification to any clients subscribing to this id.

        @param op: The operation that took place, either "create" or "update"
            (ignored in this implementation)
        @type op: C{str}

        @param id: The identifier of the resource that was updated, including
            a prefix indicating whether this is CalDAV or CardDAV related.
            The prefix is separated from the id with "|", e.g.:

            "CalDAV|abc/def"

            The id is an opaque token as far as this code is concerned, and
            is used in conjunction with the prefix and the server hostname
            to build the actual key value that devices subscribe to.
        @type id: C{str}
        """

        try:
            id.split("|", 1)
        except ValueError:
            # id has no protocol, so we can't do anything with it
            self.log_error("Notification id '%s' is missing protocol" % (id,))
            return

        id = getPubSubPath(id, {"host": self.serverHostName})

        tokens = []
        for subscriber in self.subscribers:
            token = subscriber.subscribedToID(id)
            if token is not None:
                tokens.append(token)
        if tokens:
            return self.scheduleNotifications(tokens, id)


    @inlineCallbacks
    def sendNotification(self, token, id):
        for subscriber in self.subscribers:
            if subscriber.subscribedToID(id):
                yield subscriber.notify(token, id)


    @inlineCallbacks
    def scheduleNotifications(self, tokens, id):
        if self.scheduler is not None:
            self.scheduler.schedule(tokens, id)
        else:
            for token in tokens:
                yield self.sendNotification(token, id)


class AMPPushNotifierProtocol(amp.AMP, LoggingMixIn):

    def __init__(self, service):
        super(AMPPushNotifierProtocol, self).__init__()
        self.service = service
        self.subscriptions = {}
        self.any = None

    def subscribe(self, token, id):
        if id == "any":
            self.any = token
        else:
            self.subscriptions[id] = token
        return {"status" : "OK"}
    SubscribeToID.responder(subscribe)

    def unsubscribe(self, token, id):
        try:
            del self.subscriptions[id]
        except KeyError:
            pass
        return {"status" : "OK"}
    UnsubscribeFromID.responder(unsubscribe)

    def notify(self, token, id):
        if self.subscribedToID(id) == token:
            self.log_debug("Sending notification for %s to %s" % (id, token))
            return self.callRemote(NotificationForID, id=id)

    def subscribedToID(self, id):
        if self.any is not None:
            return self.any
        return self.subscriptions.get(id, None)

    def connectionLost(self, reason=None):
        self.service.removeSubscriber(self)


class AMPPushNotifierFactory(ServerFactory, LoggingMixIn):

    protocol = AMPPushNotifierProtocol

    def __init__(self, service):
        self.service = service

    def buildProtocol(self, addr):
        p = self.protocol(self.service)
        self.service.addSubscriber(p)
        p.service = self.service
        return p


# Client classes

class AMPPushClientProtocol(amp.AMP):
    """
    Implements the client side of the AMP push protocol.  Whenever
    the NotificationForID Command arrives, the registered callback
    will be called with the id.
    """

    def __init__(self, callback):
        super(AMPPushClientProtocol, self).__init__()
        self.callback = callback

    @inlineCallbacks
    def notificationForID(self, id):
        yield self.callback(id)
        returnValue( {"status" : "OK"} )

    NotificationForID.responder(notificationForID)


class AMPPushClientFactory(Factory, LoggingMixIn):

    protocol = AMPPushClientProtocol

    def __init__(self, callback):
        self.callback = callback

    def buildProtocol(self, addr):
        p = self.protocol(self.callback)
        return p


# Client helper methods

@inlineCallbacks
def subscribeToIDs(host, port, ids, callback, reactor=None):
    """
    Clients can call this helper method to register a callback which
    will get called whenever a push notification is fired for any
    id in the ids list.

    @param host: AMP host name to connect to
    @type host: string
    @param port: AMP port to connect to
    @type port: integer
    @param ids: The push IDs to subscribe to
    @type ids: list of strings
    @param callback: The method to call whenever a notification is
        received.
    @type callback: callable which is passed an id (string)
    """

    if reactor is None:
        from twisted.internet import reactor

    token = str(uuid.uuid4())
    endpoint = TCP4ClientEndpoint(reactor, host, port)
    factory = AMPPushClientFactory(callback)
    protocol = yield endpoint.connect(factory)
    for id in ids:
        yield protocol.callRemote(SubscribeToID, token=token, id=id)

    returnValue(factory)
