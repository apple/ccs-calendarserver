##
# Copyright (c) 2005-2008 Apple Inc. All rights reserved.
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

"""
Notification framework for Calendar Server

This module implements client code which is executed within the context of
icalserver itself, and also server code (the "notification server") which is
run as a separate process, launched as part of "./run".

The notification server process is implemented as a twistd plugin
(with a tapname of "caldav_notifier"), and is comprised of two
services -- one handling the internal channel between icalserver
and notification server, the other handling the external channel
between notification server and a remote consumer.

The icalserver tap creates a NotificationClient object at startup;
it deals with passing along notifications to the notification server.
These notifications originate from cache.py:MemcacheChangeNotifier.changed().
"""

# TODO: bindAddress to local
# TODO: add CalDAVTester test for examining new xmpp-uri property

from twisted.internet.protocol import ReconnectingClientFactory, ServerFactory
from twisted.internet.address import IPv4Address
from twisted.internet.ssl import ClientContextFactory
from twisted.internet.defer import inlineCallbacks, Deferred
from twisted.protocols.basic import LineReceiver
from twisted.plugin import IPlugin
from twisted.application import internet, service
from twisted.python.usage import Options, UsageError
from twisted.python.reflect import namedClass
from twisted.words.protocols.jabber import xmlstream
from twisted.words.protocols.jabber.jid import JID
from twisted.words.protocols.jabber.client import XMPPAuthenticator, IQAuthInitializer
from twisted.words.protocols.jabber.xmlstream import IQ
from twisted.words.xish import domish
from twistedcaldav.log import LoggingMixIn
from twistedcaldav.config import config, defaultConfig, defaultConfigFile
from twistedcaldav.memcacher import Memcacher
from twistedcaldav import memcachepool
from zope.interface import Interface, implements
from fnmatch import fnmatch

__all__ = [
    "ClientNotifier",
    "Coalescer",
    "getNodeCacher",
    "getNotificationClient",
    "getPubSubConfiguration",
    "getPubSubHeartbeatURI",
    "getPubSubPath",
    "getPubSubXMPPURI",
    "INotifier",
    "installNotificationClient",
    "InternalNotificationFactory",
    "InternalNotificationProtocol",
    "NotificationClient",
    "NotificationClientFactory",
    "NotificationClientLineProtocol",
    "NotificationServiceMaker",
    "SimpleLineNotificationFactory",
    "SimpleLineNotificationProtocol",
    "SimpleLineNotifier",
    "SimpleLineNotifierService",
    "XMPPNotificationFactory",
    "XMPPNotifier",
]

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# Classes used within calendarserver itself
#

class ClientNotifier(LoggingMixIn):
    """
    Provides a method to send change notifications to the L{NotificationClient}.
    """

    def __init__(self, resource, configOverride=None):
        self._resource = resource
        self._notify = True
        self.config = configOverride or config

    def enableNotify(self, arg):
        url = self._resource.url()
        self.log_debug("enableNotify: %s" % (url,))
        self._notify = True

    def disableNotify(self):
        url = self._resource.url()
        self.log_debug("disableNotify: %s" % (url,))
        self._notify = False

    def notify(self, op="update"):
        url = self._resource.url()

        if self.config.Notifications.Enabled:
            if self._notify:
                self.log_debug("Notifications are enabled: %s %s" % (op, url))
                return getNotificationClient().send(op, url)
            else:
                self.log_debug("Skipping notification for: %s" % (url,))


class NotificationClientLineProtocol(LineReceiver, LoggingMixIn):
    """
    Notification Client Line Protocol

    Sends updates to the notification server.
    """

    def connectionMade(self):
        self.client.addObserver(self)
        self.factory.connectionMade()

    def connectionLost(self, reason):
        self.client.removeObserver(self)


class NotificationClientFactory(ReconnectingClientFactory,
    LoggingMixIn):
    """
    Notification Client Factory

    Sends updates to the notification server.
    """

    protocol = NotificationClientLineProtocol

    def __init__(self, client):
        self.connected = False
        self.client = client

    def clientConnectionLost(self, connector, reason):
        self.log_error("Connect to notification server lost: %s" % (reason,))
        self.connected = False
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        self.log_error("Unable to connect to notification server: %s" % (reason,))
        self.connected = False
        ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)

    def connectionMade(self):
        self.connected = True
        self.resetDelay()
        self.client.connectionMade()

    def isReady(self):
        return self.connected

    def buildProtocol(self, addr):
        p = self.protocol()
        p.factory = self
        p.client = self.client
        return p


class NotificationClient(LoggingMixIn):
    """
    Notification Client

    Forwards on notifications from ClientNotifiers to the
    notification server.  A NotificationClient is installed by the tap at
    startup.
    """

    def __init__(self, host, port, reactor=None):
        self.factory = None
        self.host = host
        self.port = port
        self.observers = set()
        self.queued = set()

        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor

    def send(self, op, uri):
        if self.factory is None:
            self.factory = NotificationClientFactory(self)
            self.reactor.connectTCP(self.host, self.port, self.factory)
            self.log_debug("Creating factory")

        msg = "%s %s" % (op, str(uri))
        if self.factory.isReady() and self.observers:
            for observer in self.observers:
                self.log_debug("Sending to notification server: %s" % (msg,))
                observer.sendLine(msg)
        else:
            self.log_debug("Queuing: %s" % (msg,))
            self.queued.add(msg)

    def connectionMade(self):
        if self.factory.isReady() and self.observers:
            for observer in self.observers:
                for msg in self.queued:
                    self.log_debug("Sending from queue: %s" % (msg,))
                    observer.sendLine(msg)
            self.queued.clear()

    def addObserver(self, observer):
        self.observers.add(observer)

    def removeObserver(self, observer):
        self.observers.remove(observer)


_notificationClient = None

def installNotificationClient(host, port, klass=NotificationClient, reactor=None):
    global _notificationClient
    _notificationClient = klass(host, port, reactor=reactor)

def getNotificationClient():
    return _notificationClient



class NodeCreationException(Exception):
    pass

class NodeCacher(Memcacher, LoggingMixIn):

    def __init__(self, reactor=None):
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor
        super(NodeCacher, self).__init__("pubsubnodes")

    def nodeExists(self, nodeName):
        return self.get(nodeName)

    def storeNode(self, nodeName):
        return self.set(nodeName, "1")

    @inlineCallbacks
    def waitForNode(self, notifier, nodeName):
        retryCount = 0
        verified = False
        requestedCreation = False
        while(retryCount < 5):
            if (yield self.nodeExists(nodeName)):
                verified = True
                break

            if not requestedCreation:
                notifier.notify(op="create")
                requestedCreation = True

            retryCount += 1

            pause = Deferred()
            def _timedDeferred():
                pause.callback(True)
            self.reactor.callLater(1, _timedDeferred)
            yield pause

        if not verified:
            self.log_debug("Giving up!")
            raise NodeCreationException("Could not create node %s" % (nodeName,))


_nodeCacher = None

def getNodeCacher():
    global _nodeCacher
    if _nodeCacher is None:
        _nodeCacher = NodeCacher()
    return _nodeCacher





# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# Classes used within Notification Server
#

#
# Internal Channel (from icalserver to notification server)
#

class InternalNotificationProtocol(LineReceiver):
    """
    InternalNotificationProtocol

    Receives notifications from the calendar server.
    """

    def lineReceived(self, line):
        op, uri = line.strip().split()
        self.factory.coalescer.add(op, uri)


class InternalNotificationFactory(ServerFactory):
    """
    Internal Notification Factory

    Receives notifications from the calendar server.
    """

    protocol = InternalNotificationProtocol

    def __init__(self, notifiers, delaySeconds=None):
        self.coalescer = Coalescer(notifiers, delaySeconds=delaySeconds)



class Coalescer(LoggingMixIn):
    """
    Coalescer

    A queue which hangs on to incoming uris for some period of time before
    passing them along to the external notifier listening for these updates.
    A chatty CalDAV client can make several changes in a short period of time,
    and the Coalescer buffers the external clients somewhat.
    """

    delaySeconds = 5
    sendAnywayAfterCount = 5

    def __init__(self, notifiers, reactor=None, delaySeconds=None,
        sendAnywayAfterCount=None):

        if sendAnywayAfterCount:
            self.sendAnywayAfterCount = sendAnywayAfterCount

        if delaySeconds:
            self.delaySeconds = delaySeconds

        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor

        self.uris = {}
        self.notifiers = notifiers

    def add(self, op, uri):

        if op == "create":
            # we don't want to delay a "create" notification; this opcode
            # is meant for XMPP pubsub -- it means create and configure the
            # node but don't publish to it
            for notifier in self.notifiers:
                notifier.enqueue(op, uri)

        else: # normal update notification
            delayed, count = self.uris.get(uri, [None, 0])

            if delayed and delayed.active():
                count += 1
                if count < self.sendAnywayAfterCount:
                    # reschedule for delaySeconds in the future
                    delayed.reset(self.delaySeconds)
                    self.uris[uri][1] = count
                    self.log_info("Delaying: %s" % (uri,))
                else:
                    self.log_info("Not delaying to avoid starvation: %s" % (uri,))
            else:
                self.log_info("Scheduling: %s" % (uri,))
                self.uris[uri] = [self.reactor.callLater(self.delaySeconds,
                    self.delayedEnqueue, op, uri), 0]

    def delayedEnqueue(self, op, uri):
        self.log_info("Time to send: %s" % (uri,))
        self.uris[uri][1] = 0
        for notifier in self.notifiers:
            notifier.enqueue(op, uri)



#
# External Channel (from notification server to other consumers)
#

class INotifier(Interface):
    """
    Notifier Interface

    Defines an enqueue method that Notifier classes need to implement.
    """

    def enqueue(self, op, uri):
        """
        Let's the notifier object know that a change has been made for this
        uri, and enough time has passed to allow for coalescence.

        @type op: C{str}
        @type uri: C{str}
        """


class SimpleLineNotifier(LoggingMixIn):
    """
    Simple Line Notifier

    Listens for uris from the coalescer and writes them out to any
    connected clients.  Each line is simply a sequence number, a
    space, and a uri string.  If the external client sends a sequence
    number, this notifier will send notification lines for each uri
    that was changed since that sequence number was originally sent.
    A history of such sequence numbers is stored in a python dict.
    If the external client sends a zero, then the history is cleared
    and the next sequence number to use is reset to 1.

    The sequence number is stored as a python long which means it has
    essentially infinite precision.  We discussed rolling over at the
    64-bit boundary, but even if we limit the sequence number to a 64-bit
    signed integer (or 2^63), and we had 100,000 users generating the
    maximum number of notifications (which by default is 6/minute since
    we're coalescing over 10 seconds), it would take 29 million years to
    rollover.
    """

    implements(INotifier)

    def __init__(self, settings):
        self.reset()
        self.observers = set()
        self.sentReset = False

    def enqueue(self, op, uri):

        if op == "update":

            self.latestSeq += 1L

            # Update history
            self.history[uri] = self.latestSeq

            for observer in self.observers:
                msg = "%d %s" % (self.latestSeq, uri)
                self.log_debug("Sending %s" % (msg,))
                observer.sendLine(msg)

    def reset(self):
        self.latestSeq = 0L
        self.history = { } # keys=uri, values=sequenceNumber

    def playback(self, observer, oldSeq):

        hist = self.history
        toSend = [(hist[uri], uri) for uri in hist if hist[uri] > oldSeq]
        toSend.sort() # sorts the tuples based on numeric sequence number

        for seq, uri in toSend:
            msg = "%d %s" % (seq, uri)
            self.log_debug("Sending %s" % (msg,))
            observer.sendLine(msg)


    def addObserver(self, observer):
        self.observers.add(observer)

    def removeObserver(self, observer):
        self.observers.remove(observer)

    def connectionMade(self, observer):
        if not self.sentReset:
            self.log_debug("Sending 0")
            observer.sendLine("0")
            self.sentReset = True


class SimpleLineNotificationProtocol(LineReceiver, LoggingMixIn):
    """
    Simple Line Notification Protocol

    Sends notifications to external consumers.  Also responds to history-
    playback requests.  If an integer is received from an external consumer,
    it is interpreted as a sequence number; all notifications sent since that
    sequence number was sent are resent.
    """

    def connectionMade(self):
        # we just received a connection from the outside; if it's the first
        # since we started running, it means we need to let them know that
        # a reset has happened.  This assumes that only one connection will
        # be made to this channel; if we end up having multiple consumers
        # of this protocol, we would need to uniquely identify them.
        self.notifier.connectionMade(self)

    def lineReceived(self, line):
        val = line.strip()

        # Should be a number requesting all updates since that sequence
        try:
            oldSeq = int(val)
        except ValueError, e:
            self.log_warn("Error parsing %s: %s (from %s)" % (val, e,
                self.transport.getPeer()))
            return

        if oldSeq == 0:
            self.notifier.reset()
        else:
            self.notifier.playback(self, oldSeq)

    def connectionLost(self, reason):
        self.notifier.removeObserver(self)


class SimpleLineNotificationFactory(ServerFactory):
    """
    Simple Line Notification Factory

    Sends notifications to external consumers.
    """

    protocol = SimpleLineNotificationProtocol

    def __init__(self, notifier):
        self.notifier = notifier

    def buildProtocol(self, addr):
        p = self.protocol()
        self.notifier.addObserver(p)
        p.notifier = self.notifier
        return p






class XMPPNotifier(LoggingMixIn):
    """
    XMPP Notifier

    Uses pubsub XMPP requests to let subscribers know when there
    has been a change made to a DAV resource (currently just
    CalendarHomeFiles).  Uses XMPP login info from the config file
    to determine which pubsub service to connect to.  When it's
    time to send a notification, XMPPNotifier computes a node path
    corresponding to the DAV resource and emits a publish request
    for that node.  If the request comes back 404 XMPPNotifier will
    create the node and then go through the configuration process,
    followed by a publish retry.

    For monitoring purposes, you can subscribe to the server's JID
    as long as your own JID matches the "AllowedJIDs" pattern(s) in
    the config file; XMPPNotifier will send error messages to your
    JID.  If you also want to receive non-error, debug messages,
    send the calendar server JID the message, "debug on".  Send
    "help" for other commands.

    To let clients know that the notifications from the calendar server
    are still flowing, a "heartbeat" node is published to every 30
    minutes (configurable).

    """

    implements(INotifier)

    pubsubNS = 'http://jabber.org/protocol/pubsub'

    def __init__(self, settings, reactor=None, configOverride=None,
        heartbeat=True, roster=True):
        self.xmlStream = None
        self.settings = settings
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor
        self.config = configOverride or config
        self.doHeartbeat = heartbeat and self.settings['HeartbeatMinutes'] != 0
        self.doRoster = roster

        self.roster = {}
        self.outstanding = {}

    def lockNode(self, nodeName):
        if self.outstanding.has_key(nodeName):
            return False
        else:
            self.outstanding[nodeName] = 1
            return True

    def unlockNode(self, failure, nodeName):
        try:
            del self.outstanding[nodeName]
        except KeyError:
            pass

    def sendHeartbeat(self):
        if self.doHeartbeat and self.xmlStream is not None:
            self.enqueue("update", "", lock=False)
            self.reactor.callLater(self.settings['HeartbeatMinutes'] * 60,
                self.sendHeartbeat)

    def enqueue(self, op, uri, lock=True):
        if self.xmlStream is not None:
            # Convert uri to node
            nodeName = self.uriToNodeName(uri)
            if op == "create":
                if not self.lockNode(nodeName):
                    # this node is busy, so it must already be created, or at
                    # least in the proccess
                    return
                self.createNode(nodeName, publish=False)
            else:
                self.publishNode(nodeName, lock=lock)

    def uriToNodeName(self, uri):
        return getPubSubPath(uri, getPubSubConfiguration(self.config))

    def publishNode(self, nodeName, lock=True):
        if self.xmlStream is None:
            # We lost our connection
            self.unlockNode(None, nodeName)
            return

        try:
            if lock and not self.lockNode(nodeName):
                return

            iq = IQ(self.xmlStream)
            pubsubElement = iq.addElement('pubsub', defaultUri=self.pubsubNS)
            publishElement = pubsubElement.addElement('publish')
            publishElement['node'] = nodeName
            if self.settings["NodeConfiguration"]["pubsub#deliver_payloads"] == '1':
                itemElement = publishElement.addElement('item')
                payloadElement = itemElement.addElement('plistfrag',
                    defaultUri='plist-apple')

            self.sendDebug("Publishing (%s)" % (nodeName,), iq)
            d = iq.send(to=self.settings['ServiceAddress'])
            d.addCallback(self.publishNodeSuccess, nodeName)
            d.addErrback(self.publishNodeFailure, nodeName)
        except:
            self.unlockNode(None, nodeName)
            raise

    def publishNodeSuccess(self, iq, nodeName):
        self.unlockNode(None, nodeName)
        self.sendDebug("Node publish successful (%s)" % (nodeName,), iq)

    def publishNodeFailure(self, result, nodeName):
        try:
            iq = result.value.getElement()

            if iq.name == "error":
                if iq['code'] == '400':
                    self.requestConfigurationForm(nodeName, True)

                elif iq['code'] == '404':
                    self.createNode(nodeName)
            else:
                self.log_error("PubSub node publish error: %s" %
                    (iq.toXml().encode('ascii', 'replace')),)
                self.sendDebug("Node publish failed (%s)" % (nodeName,), iq)
                # Don't know how to proceed
                self.unlockNode(None, nodeName)
        except:
            self.unlockNode(None, nodeName)
            raise

    def createNode(self, nodeName, publish=True):
        if self.xmlStream is None:
            # We lost our connection
            self.unlockNode(None, nodeName)
            return

        try:
            iq = IQ(self.xmlStream)
            pubsubElement = iq.addElement('pubsub', defaultUri=self.pubsubNS)
            child = pubsubElement.addElement('create')
            child['node'] = nodeName
            d = iq.send(to=self.settings['ServiceAddress'])
            d.addCallback(self.createNodeSuccess, nodeName, publish)
            d.addErrback(self.createNodeFailure, nodeName, publish)
        except:
            self.unlockNode(None, nodeName)
            raise

    def createNodeSuccess(self, iq, nodeName, publish):
        try:
            self.sendDebug("Node creation successful (%s)" % (nodeName,), iq)
            # now time to configure; fetch the form
            self.requestConfigurationForm(nodeName, publish)
        except:
            self.unlockNode(None, nodeName)
            raise

    def createNodeFailure(self, result, nodeName, publish):
        try:
            iq = result.value.getElement()
            if iq['code'] == '409':
                # node already exists, proceed to configure
                self.sendDebug("Node already exists (%s)" % (nodeName,), iq)
                self.requestConfigurationForm(nodeName, publish)
            else:
                # couldn't create node, give up
                self.unlockNode(None, nodeName)
                self.log_error("PubSub node creation error: %s" %
                    (iq.toXml().encode('ascii', 'replace')),)
                self.sendError("Node creation failed (%s)" % (nodeName,), iq)
        except:
            self.unlockNode(None, nodeName)
            raise

    def requestConfigurationForm(self, nodeName, publish):
        if self.xmlStream is None:
            # We lost our connection
            self.unlockNode(None, nodeName)
            return

        try:
            iq = IQ(self.xmlStream, type='get')
            child = iq.addElement('pubsub',
                defaultUri=self.pubsubNS+"#owner")
            child = child.addElement('configure')
            child['node'] = nodeName
            d = iq.send(to=self.settings['ServiceAddress'])
            d.addCallback(self.requestConfigurationFormSuccess, nodeName,
                publish)
            d.addErrback(self.requestConfigurationFormFailure, nodeName)
        except:
            self.unlockNode(None, nodeName)
            raise

    def _getChild(self, element, name):
        for child in element.elements():
            if child.name == name:
                return child
        return None

    def requestConfigurationFormSuccess(self, iq, nodeName, publish):
        if self.xmlStream is None:
            # We lost our connection
            self.unlockNode(None, nodeName)
            return

        try:
            nodeConf = self.settings["NodeConfiguration"]
            self.sendDebug("Received configuration form (%s)" % (nodeName,), iq)
            pubsubElement = self._getChild(iq, 'pubsub')
            if pubsubElement:
                configureElement = self._getChild(pubsubElement, 'configure')
                if configureElement:
                    formElement = configureElement.firstChildElement()
                    if formElement['type'] == 'form':
                        # We've found the form; start building a response
                        filledIq = IQ(self.xmlStream, type='set')
                        filledPubSub = filledIq.addElement('pubsub',
                            defaultUri=self.pubsubNS+"#owner")
                        filledConfigure = filledPubSub.addElement('configure')
                        filledConfigure['node'] = nodeName
                        filledForm = filledConfigure.addElement('x',
                            defaultUri='jabber:x:data')
                        filledForm['type'] = 'submit'

                        configMatches = True
                        for field in formElement.elements():
                            if field.name == 'field':
                                var = field['var']
                                if var == "FORM_TYPE":
                                    filledForm.addChild(field)
                                else:
                                    value = nodeConf.get(var, None)
                                    if (value is not None and
                                        (str(self._getChild(field,
                                        "value")) != value)):
                                        # this field needs configuring
                                        configMatches = False
                                        filledField = filledForm.addElement('field')
                                        filledField['var'] = var
                                        filledField['type'] = field['type']
                                        valueElement = filledField.addElement('value')
                                        valueElement.addContent(value)
                                        # filledForm.addChild(field)
                        if configMatches:
                            cancelIq = IQ(self.xmlStream, type='set')
                            cancelPubSub = cancelIq.addElement('pubsub',
                                defaultUri=self.pubsubNS+"#owner")
                            cancelConfig = cancelPubSub.addElement('configure')
                            cancelConfig['node'] = nodeName
                            cancelX = cancelConfig.addElement('x',
                                defaultUri='jabber:x:data')
                            cancelX['type'] = 'cancel'
                            self.sendDebug("Cancelling configuration (%s)"
                                           % (nodeName,), cancelIq)
                            d = cancelIq.send(to=self.settings['ServiceAddress'])
                        else:
                            self.sendDebug("Sending configuration form (%s)"
                                           % (nodeName,), filledIq)
                            d = filledIq.send(to=self.settings['ServiceAddress'])
                        d.addCallback(self.configurationSuccess, nodeName,
                            publish)
                        d.addErrback(self.configurationFailure, nodeName)
                        return

            # Couldn't process configuration form, give up
            self.unlockNode(None, nodeName)

        except:
            # Couldn't process configuration form, give up
            self.unlockNode(None, nodeName)
            raise

    def requestConfigurationFormFailure(self, result, nodeName):
        # If we get here we're giving up
        try:
            iq = result.value.getElement()
            self.log_error("PubSub configuration form request error: %s" %
                (iq.toXml().encode('ascii', 'replace')),)
            self.sendError("Failed to receive configuration form (%s)" %
                (nodeName,), iq)
        finally:
            self.unlockNode(None, nodeName)

    def configurationSuccess(self, iq, nodeName, publish):
        if self.xmlStream is None:
            # We lost our connection
            self.unlockNode(None, nodeName)
            return

        try:
            self.log_debug("PubSub node %s is configured" % (nodeName,))
            self.sendDebug("Configured node (%s)" % (nodeName,), iq)
            nodeCacher = getNodeCacher()
            nodeCacher.storeNode(nodeName)
            if publish:
                self.publishNode(nodeName, lock=False)
            else:
                self.unlockNode(None, nodeName)
        except:
            self.unlockNode(None, nodeName)
            raise

    def configurationFailure(self, result, nodeName):
        # If we get here we're giving up
        try:
            iq = result.value.getElement()
            self.log_error("PubSub node configuration error: %s" %
                (iq.toXml().encode('ascii', 'replace')),)
            self.sendError("Failed to configure node (%s)" % (nodeName,), iq)
        finally:
            self.unlockNode(None, nodeName)

    def deleteNode(self, nodeName):
        if self.xmlStream is None:
            # We lost our connection
            self.unlockNode(None, nodeName)
            return

        try:
            if not self.lockNode(nodeName):
                return

            iq = IQ(self.xmlStream)
            pubsubElement = iq.addElement('pubsub',
                defaultUri=self.pubsubNS+"#owner")
            publishElement = pubsubElement.addElement('delete')
            publishElement['node'] = nodeName
            self.sendDebug("Deleting (%s)" % (nodeName,), iq)
            d = iq.send(to=self.settings['ServiceAddress'])
            d.addCallback(self.deleteNodeSuccess, nodeName)
            d.addErrback(self.deleteNodeFailure, nodeName)
        except:
            self.unlockNode(None, nodeName)
            raise

    def deleteNodeSuccess(self, iq, nodeName):
        self.unlockNode(None, nodeName)
        self.sendDebug("Node delete successful (%s)" % (nodeName,), iq)

    def deleteNodeFailure(self, result, nodeName):
        try:
            iq = result.value.getElement()
            self.log_error("PubSub node delete error: %s" %
                (iq.toXml().encode('ascii', 'replace')),)
            self.sendDebug("Node delete failed (%s)" % (nodeName,), iq)
        finally:
            self.unlockNode(None, nodeName)


    def requestRoster(self):
        if self.doRoster:
            self.roster = {}
            rosterIq = IQ(self.xmlStream, type='get')
            rosterIq.addElement("query", "jabber:iq:roster")
            d = rosterIq.send()
            d.addCallback(self.handleRoster)

    def allowedInRoster(self, jid):
        for pattern in self.settings.get("AllowedJIDs", []):
            if fnmatch(jid, pattern):
                return True
        return False

    def handleRoster(self, iq):
        for child in iq.children[0].children:
            jid = child['jid']
            if self.allowedInRoster(jid):
                self.log_info("In roster: %s" % (jid,))
                if not self.roster.has_key(jid):
                    self.roster[jid] = { 'debug' : False, 'available' : False }
            else:
                self.log_info("JID not allowed in roster: %s" % (jid,))

    def handlePresence(self, iq):
        self.log_info("Presence IQ: %s" %
            (iq.toXml().encode('ascii', 'replace')),)
        presenceType = iq.getAttribute('type')

        if presenceType == 'subscribe':
            frm = JID(iq['from']).userhost()
            if self.allowedInRoster(frm):
                self.roster[frm] = { 'debug' : False, 'available' : True }
                response = domish.Element(('jabber:client', 'presence'))
                response['to'] = iq['from']
                response['type'] = 'subscribed'
                self.xmlStream.send(response)

                # request subscription as well
                subscribe = domish.Element(('jabber:client', 'presence'))
                subscribe['to'] = iq['from']
                subscribe['type'] = 'subscribe'
                self.xmlStream.send(subscribe)
            else:
                self.log_info("JID not allowed in roster: %s" % (frm,))
                # Reject
                response = domish.Element(('jabber:client', 'presence'))
                response['to'] = iq['from']
                response['type'] = 'unsubscribed'
                self.xmlStream.send(response)

        elif presenceType == 'unsubscribe':
            frm = JID(iq['from']).userhost()
            if self.roster.has_key(frm):
                del self.roster[frm]
            response = domish.Element(('jabber:client', 'presence'))
            response['to'] = iq['from']
            response['type'] = 'unsubscribed'
            self.xmlStream.send(response)

            # remove from roster as well
            removal = IQ(self.xmlStream, type='set')
            query = removal.addElement("query", "jabber:iq:roster")
            query.addElement("item")
            query.item["jid"] = iq["from"]
            query.item["subscription"] = "remove"
            removal.send()

        elif presenceType == 'unavailable':
            frm = JID(iq['from']).userhost()
            if self.roster.has_key(frm):
                self.roster[frm]['available'] = False

        else:
            frm = JID(iq['from']).userhost()
            if self.allowedInRoster(frm):
                if self.roster.has_key(frm):
                    self.roster[frm]['available'] = True
                else:
                    self.roster[frm] = { 'debug' : False, 'available' : True }
            else:
                self.log_info("JID not allowed in roster: %s" % (frm,))

    def streamOpened(self, xmlStream):
        self.xmlStream = xmlStream
        xmlStream.addObserver('/message', self.handleMessage)
        xmlStream.addObserver('/presence', self.handlePresence)
        self.requestRoster()
        self.sendHeartbeat()


    def streamClosed(self):
        self.xmlStream = None

    def sendDebug(self, txt, element):
        txt = "DEBUG: %s %s" % (txt, element.toXml().encode('ascii', 'replace'))
        for jid, info in self.roster.iteritems():
            if info['available'] and info['debug']:
                self.sendAlert(jid, txt)

    def sendError(self, txt, element):
        txt = "ERROR: %s %s" % (txt, element.toXml().encode('ascii', 'replace'))
        for jid, info in self.roster.iteritems():
            if info['available']:
                self.sendAlert(jid, txt)

    def sendAlert(self, jid, txt):
        if self.xmlStream is not None:
            message = domish.Element(('jabber:client', 'message'))
            message['to'] = JID(jid).full()
            message.addElement('body', content=txt)
            self.xmlStream.send(message)

    def handleMessage(self, iq):
        body = getattr(iq, 'body', None)
        if body:
            response = None
            frm = JID(iq['from']).userhost()
            if frm in self.roster:
                txt = str(body).lower()
                if txt == "help":
                    response = "debug on, debug off, roster, create <nodename>, publish <nodename>, hammer <count>"
                elif txt == "roster":
                    response = "Roster: %s" % (str(self.roster),)
                elif txt == "debug on":
                    self.roster[frm]['debug'] = True
                    response = "Debugging on"
                elif txt == "debug off":
                    self.roster[frm]['debug'] = False
                    response = "Debugging off"
                elif txt == "outstanding":
                    response = "Outstanding: %s" % (str(self.outstanding),)
                elif txt.startswith("publish"):
                    try:
                        publish, nodeName = str(body).split()
                    except ValueError:
                        response = "Please phrase it like 'publish nodename'"
                    else:
                        response = "Publishing node %s" % (nodeName,)
                        self.reactor.callLater(1, self.enqueue, "update",
                            nodeName)
                elif txt.startswith("delete"):
                    try:
                        delete, nodeName = str(body).split()
                    except ValueError:
                        response = "Please phrase it like 'delete nodename'"
                    else:
                        response = "Deleting node %s" % (nodeName,)
                        self.reactor.callLater(1, self.deleteNode, nodeName)
                elif txt.startswith("create"):
                    try:
                        publish, nodeName = str(body).split()
                    except ValueError:
                        response = "Please phrase it like 'create nodename'"
                    else:
                        response = "Creating and configuring node %s" % (nodeName,)
                        self.reactor.callLater(1, self.enqueue, "create",
                            nodeName)
                elif txt.startswith("hammer"):
                    try:
                        hammer, count = txt.split()
                        count = int(count)
                    except ValueError:
                        response = "Please phrase it like 'hammer 100'"
                    else:
                        response = "Hammer will commence now, %d times" % (count,)
                        self.reactor.callLater(1, self.hammer, count)
                else:
                    response = "I don't understand.  Try 'help'."
            else:
                response = "Sorry, you are not authorized to converse with this server"

            if response:
                message = domish.Element(('jabber:client', 'message'))
                message['to'] = JID(iq['from']).full()
                message.addElement('body', content=response)
                self.xmlStream.send(message)


    def hammer(self, count):
        for i in xrange(count):
            self.enqueue("update", "hammertesting%d" % (i,))


class XMPPNotificationFactory(xmlstream.XmlStreamFactory, LoggingMixIn):

    def __init__(self, notifier, settings, reactor=None, keepAlive=True):
        self.log_info("Setting up XMPPNotificationFactory")

        self.notifier = notifier
        self.settings = settings
        self.jid = settings['JID']
        self.keepAliveSeconds = settings.get('KeepAliveSeconds', 120)
        self.xmlStream = None
        self.presenceCall = None
        self.doKeepAlive = keepAlive
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor

        xmlstream.XmlStreamFactory.__init__(self,
            XMPPAuthenticator(JID(self.jid), settings['Password']))

        self.addBootstrap(xmlstream.STREAM_CONNECTED_EVENT, self.connected)
        self.addBootstrap(xmlstream.STREAM_END_EVENT, self.disconnected)
        self.addBootstrap(xmlstream.INIT_FAILED_EVENT, self.initFailed)

        self.addBootstrap(xmlstream.STREAM_AUTHD_EVENT, self.authenticated)
        self.addBootstrap(IQAuthInitializer.INVALID_USER_EVENT,
            self.authFailed)
        self.addBootstrap(IQAuthInitializer.AUTH_FAILED_EVENT,
            self.authFailed)

    def connected(self, xmlStream):
        self.xmlStream = xmlStream
        self.log_info("XMPP connection successful")
        # Log all traffic
        xmlStream.rawDataInFn = self.rawDataIn
        xmlStream.rawDataOutFn = self.rawDataOut

    def disconnected(self, xmlStream):
        self.notifier.streamClosed()
        self.xmlStream = None
        if self.presenceCall is not None:
            self.presenceCall.cancel()
            self.presenceCall = None
        self.log_info("XMPP disconnected")

    def initFailed(self, failure):
        self.xmlStream = None
        self.log_info("XMPP Initialization failed: %s" % (failure,))

    def authenticated(self, xmlStream):
        self.log_info("XMPP authentication successful: %s" % (self.jid,))
        # xmlStream.addObserver('/message', self.handleMessage)
        self.sendPresence()
        self.notifier.streamOpened(xmlStream)

    def authFailed(self, e):
        self.log_error("Failed to log in XMPP (%s); check JID and password" %
            (self.jid,))

    def sendPresence(self):
        if self.doKeepAlive and self.xmlStream is not None:
            presence = domish.Element(('jabber:client', 'presence'))
            self.xmlStream.send(presence)
            self.presenceCall = self.reactor.callLater(self.keepAliveSeconds,
                self.sendPresence)

    def rawDataIn(self, buf):
        self.log_debug("RECV: %s" % unicode(buf, 'utf-8').encode('ascii',
            'replace'))

    def rawDataOut(self, buf):
        self.log_debug("SEND: %s" % unicode(buf, 'utf-8').encode('ascii',
            'replace'))


def getPubSubConfiguration(config):
    # TODO: Should probably cache this
    results = { 'enabled' : False }

    # return the first enabled xmpp service settings in the config file
    for key, settings in config.Notifications.Services.iteritems():
        if (settings["Service"] == "twistedcaldav.notify.XMPPNotifierService"
            and settings["Enabled"]):
            results['enabled'] = True
            results['service'] = settings['ServiceAddress']
            results['host'] = config.ServerHostName
            results['port'] = config.SSLPort or config.HTTPPort
            results['xmpp-server'] = settings['Host']
            results['heartrate'] = settings['HeartbeatMinutes']

    return results

def getPubSubPath(uri, pubSubConfiguration):
    path = "/Public/CalDAV/%s/%d/" % (pubSubConfiguration['host'],
        pubSubConfiguration['port'])
    if uri:
        path += "%s/" % (uri.strip("/"),)
    return path

def getPubSubXMPPURI(uri, pubSubConfiguration):
    return "xmpp:%s?pubsub;node=%s" % (pubSubConfiguration['service'],
        getPubSubPath(uri, pubSubConfiguration))

def getPubSubHeartbeatURI(pubSubConfiguration):
    return "xmpp:%s?pubsub;node=%s" % (pubSubConfiguration['service'],
        getPubSubPath("", pubSubConfiguration))

#
# Notification Server service config
#

class NotificationOptions(Options):
    optParameters = [[
        "config", "f", defaultConfigFile, "Path to configuration file."
    ]]

    def __init__(self, *args, **kwargs):
        super(NotificationOptions, self).__init__(*args, **kwargs)

        self.overrides = {}

    def _coerceOption(self, configDict, key, value):
        """
        Coerce the given C{val} to type of C{configDict[key]}
        """
        if key in configDict:
            if isinstance(configDict[key], bool):
                value = value == "True"

            elif isinstance(configDict[key], (int, float, long)):
                value = type(configDict[key])(value)

            elif isinstance(configDict[key], (list, tuple)):
                value = value.split(',')

            elif isinstance(configDict[key], dict):
                raise UsageError(
                    "Dict options not supported on the command line"
                )

            elif value == 'None':
                value = None

        return value

    def _setOverride(self, configDict, path, value, overrideDict):
        """
        Set the value at path in configDict
        """
        key = path[0]

        if len(path) == 1:
            overrideDict[key] = self._coerceOption(configDict, key, value)
            return

        if key in configDict:
            if not isinstance(configDict[key], dict):
                raise UsageError(
                    "Found intermediate path element that is not a dictionary"
                )

            if key not in overrideDict:
                overrideDict[key] = {}

            self._setOverride(
                configDict[key], path[1:],
                value, overrideDict[key]
            )


    def opt_option(self, option):
        """
        Set an option to override a value in the config file. True, False, int,
        and float options are supported, as well as comma seperated lists. Only
        one option may be given for each --option flag, however multiple
        --option flags may be specified.
        """

        if "=" in option:
            path, value = option.split('=')
            self._setOverride(
                defaultConfig,
                path.split('/'),
                value,
                self.overrides
            )
        else:
            self.opt_option('%s=True' % (option,))

    opt_o = opt_option

    def postOptions(self):
        config.loadConfig(self['config'])
        config.updateDefaults(self.overrides)
        self.parent['pidfile'] = None


class NotificationServiceMaker(object):
    implements(IPlugin, service.IServiceMaker)

    tapname = "caldav_notifier"
    description = "Notification Server"
    options = NotificationOptions

    def makeService(self, options):

        #
        # Configure Memcached Client Pool
        #
        if config.Memcached.ClientEnabled:
            memcachepool.installPool(
                IPv4Address(
                    'TCP',
                    config.Memcached.BindAddress,
                    config.Memcached.Port),
                config.Memcached.MaxClients)

        multiService = service.MultiService()

        notifiers = []
        for key, settings in config.Notifications.Services.iteritems():
            if settings["Enabled"]:
                notifier = namedClass(settings["Service"])(settings)
                notifier.setServiceParent(multiService)
                notifiers.append(notifier)

        internet.TCPServer(
            config.Notifications.InternalNotificationPort,
            InternalNotificationFactory(notifiers,
                delaySeconds=config.Notifications.CoalesceSeconds)
        ).setServiceParent(multiService)

        return multiService


class SimpleLineNotifierService(service.Service):

    def __init__(self, settings):
        self.notifier = SimpleLineNotifier(settings)
        self.server = internet.TCPServer(settings["Port"],
            SimpleLineNotificationFactory(self.notifier))

    def enqueue(self, op, uri):
        self.notifier.enqueue(op, uri)

    def startService(self):
        self.server.startService()

    def stopService(self):
        self.server.stopService()


class XMPPNotifierService(service.Service):

    def __init__(self, settings):
        self.notifier = XMPPNotifier(settings)

        if settings["Port"] == 5223: # use old SSL method
            self.client = internet.SSLClient(settings["Host"], settings["Port"],
                XMPPNotificationFactory(self.notifier, settings),
                ClientContextFactory())
        else:
            # TLS and SASL
            self.client = internet.TCPClient(settings["Host"], settings["Port"],
                XMPPNotificationFactory(self.notifier, settings))

    def enqueue(self, op, uri):
        self.notifier.enqueue(op, uri)

    def startService(self):
        self.client.startService()

    def stopService(self):
        self.client.stopService()

