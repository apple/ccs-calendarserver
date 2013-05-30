##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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
from twext.python.log import Logger
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.internet.protocol import Factory, ServerFactory
from twisted.protocols import amp
import time
import uuid


log = Logger()


# Control socket message-routing constants
PUSH_ROUTE = "push"


# AMP Commands sent to server

class SubscribeToID(amp.Command):
    arguments = [('token', amp.String()), ('id', amp.String())]
    response = [('status', amp.String())]



class UnsubscribeFromID(amp.Command):
    arguments = [('token', amp.String()), ('id', amp.String())]
    response = [('status', amp.String())]



# AMP Commands sent to client (and forwarded to Master)

class NotificationForID(amp.Command):
    arguments = [('id', amp.String()), ('dataChangedTimestamp', amp.Integer())]
    response = [('status', amp.String())]



# Server classes

class AMPPushForwardingFactory(Factory):
    log = Logger()

    def __init__(self, forwarder):
        self.forwarder = forwarder


    def buildProtocol(self, addr):
        protocol = amp.AMP()
        self.forwarder.protocols.append(protocol)
        return protocol



class AMPPushForwarder(object):
    """
    Runs in the slaves, forwards notifications to the master via AMP
    """
    log = Logger()

    def __init__(self, controlSocket):
        self.protocols = []
        controlSocket.addFactory(PUSH_ROUTE, AMPPushForwardingFactory(self))


    @inlineCallbacks
    def enqueue(self, transaction, id, dataChangedTimestamp=None):
        if dataChangedTimestamp is None:
            dataChangedTimestamp = int(time.time())
        for protocol in self.protocols:
            yield protocol.callRemote(NotificationForID, id=id,
                dataChangedTimestamp=dataChangedTimestamp)



class AMPPushMasterListeningProtocol(amp.AMP):
    """
    Listens for notifications coming in over AMP from the slaves
    """
    log = Logger()

    def __init__(self, master):
        super(AMPPushMasterListeningProtocol, self).__init__()
        self.master = master


    @NotificationForID.responder
    def enqueueFromWorker(self, id, dataChangedTimestamp=None):
        if dataChangedTimestamp is None:
            dataChangedTimestamp = int(time.time())
        self.master.enqueue(None, id, dataChangedTimestamp=dataChangedTimestamp)
        return {"status" : "OK"}



class AMPPushMasterListenerFactory(Factory):
    log = Logger()

    def __init__(self, master):
        self.master = master


    def buildProtocol(self, addr):
        protocol = AMPPushMasterListeningProtocol(self.master)
        return protocol



class AMPPushMaster(object):
    """
    AMPPushNotifierService allows clients to use AMP to subscribe to,
    and receive, change notifications.
    """
    log = Logger()

    def __init__(self, controlSocket, parentService, port, enableStaggering,
        staggerSeconds, reactor=None):
        if reactor is None:
            from twisted.internet import reactor
        from twisted.application.strports import service as strPortsService

        if port:
            # Service which listens for client subscriptions and sends
            # notifications to them
            strPortsService(str(port), AMPPushNotifierFactory(self),
                reactor=reactor).setServiceParent(parentService)

        if controlSocket is not None:
            # Set up the listener which gets notifications from the slaves
            controlSocket.addFactory(PUSH_ROUTE,
                AMPPushMasterListenerFactory(self))

        self.subscribers = []

        if enableStaggering:
            self.scheduler = PushScheduler(reactor, self.sendNotification,
                staggerSeconds=staggerSeconds)
        else:
            self.scheduler = None


    def addSubscriber(self, p):
        self.log.debug("Added subscriber")
        self.subscribers.append(p)


    def removeSubscriber(self, p):
        self.log.debug("Removed subscriber")
        self.subscribers.remove(p)


    def enqueue(self, transaction, pushKey, dataChangedTimestamp=None):
        """
        Sends an AMP push notification to any clients subscribing to this pushKey.

        @param pushKey: The identifier of the resource that was updated, including
            a prefix indicating whether this is CalDAV or CardDAV related.

            "/CalDAV/abc/def/"

        @type pushKey: C{str}
        @param dataChangedTimestamp: Timestamp (epoch seconds) for the data change
            which triggered this notification (Only used for unit tests)
            @type key: C{int}
        """

        # Unit tests can pass this value in; otherwise it defaults to now
        if dataChangedTimestamp is None:
            dataChangedTimestamp = int(time.time())

        tokens = []
        for subscriber in self.subscribers:
            token = subscriber.subscribedToID(pushKey)
            if token is not None:
                tokens.append(token)
        if tokens:
            return self.scheduleNotifications(tokens, pushKey, dataChangedTimestamp)


    @inlineCallbacks
    def sendNotification(self, token, id, dataChangedTimestamp):
        for subscriber in self.subscribers:
            if subscriber.subscribedToID(id):
                yield subscriber.notify(token, id, dataChangedTimestamp)


    @inlineCallbacks
    def scheduleNotifications(self, tokens, id, dataChangedTimestamp):
        if self.scheduler is not None:
            self.scheduler.schedule(tokens, id, dataChangedTimestamp)
        else:
            for token in tokens:
                yield self.sendNotification(token, id, dataChangedTimestamp)



class AMPPushNotifierProtocol(amp.AMP):
    log = Logger()

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

    def notify(self, token, id, dataChangedTimestamp):
        if self.subscribedToID(id) == token:
            self.log.debug("Sending notification for %s to %s" % (id, token))
            return self.callRemote(NotificationForID, id=id,
                dataChangedTimestamp=dataChangedTimestamp)


    def subscribedToID(self, id):
        if self.any is not None:
            return self.any
        return self.subscriptions.get(id, None)


    def connectionLost(self, reason=None):
        self.service.removeSubscriber(self)



class AMPPushNotifierFactory(ServerFactory):
    log = Logger()

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
    def notificationForID(self, id, dataChangedTimestamp):
        yield self.callback(id, dataChangedTimestamp)
        returnValue({"status" : "OK"})

    NotificationForID.responder(notificationForID)



class AMPPushClientFactory(Factory):
    log = Logger()

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
