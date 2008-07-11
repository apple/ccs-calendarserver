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
# TODO: auto-registration and roster management for XMPP

import os
from twisted.internet import reactor, protocol
from twisted.protocols import basic
from twisted.plugin import IPlugin
from twisted.application import internet, service
from twisted.python.usage import Options, UsageError
from twisted.python.reflect import namedClass
from twisted.words.protocols.jabber import xmlstream
from twisted.words.protocols.jabber.jid import JID
from twisted.words.protocols.jabber.client import BasicAuthenticator, IQ
from twisted.words.xish import domish
from twistedcaldav.log import LoggingMixIn
from twistedcaldav.config import config, parseConfig, defaultConfig
from zope.interface import Interface, implements

__all__ = [
    "Coalescer",
    "getNotificationClient",
    "getPubSubConfiguration",
    "getPubSubPath",
    "getPubSubXMPPURI",
    "INotifier",
    "installNotificationClient",
    "InternalNotificationFactory",
    "InternalNotificationProtocol",
    "NotificationClient",
    "NotificationClientFactory",
    "NotificationClientLineProtocol",
    "NotificationClientUserMixIn",
    "NotificationOptions",
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

class NotificationClientUserMixIn(object):
    """
    Notification Client User (Mixin)

    Provides a method to send change notifications to the L{NotificationClient}.
    """

    def sendNotification(self, uri):
        getNotificationClient().send(uri)



class NotificationClientLineProtocol(basic.LineReceiver, LoggingMixIn):
    """
    Notification Client Line Protocol

    Sends updates to the notification server.
    """

    def connectionMade(self):
        self.client.addObserver(self)
        self.factory.connectionMade()

    def connectionLost(self, reason):
        self.client.removeObserver(self)


class NotificationClientFactory(protocol.ReconnectingClientFactory,
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
        self.log_error("Connect to notification server lost: %s" %
            (reason,))
        self.connected = False
        protocol.ReconnectingClientFactory.clientConnectionLost(self,
            connector, reason)

    def clientConnectionFailed(self, connector, reason):
        self.log_error("Unable to connect to notification server: %s" %
            (reason,))
        self.connected = False
        protocol.ReconnectingClientFactory.clientConnectionFailed(self,
            connector, reason)

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

    Forwards on notifications from NotificationClientUserMixIns to the
    notification server.  A NotificationClient is installed by the tap at
    startup.
    """

    def __init__(self, reactor, host, port):
        self.factory = None
        self.reactor = reactor
        self.host = host
        self.port = port
        self.observers = set()
        self.queued = set()

    def send(self, uri):
        if self.factory is None:
            self.factory = NotificationClientFactory(self)
            self.reactor.connectTCP(self.host, self.port, self.factory)
            self.log_debug("Creating factory")

        if self.factory.isReady() and self.observers:
            for observer in self.observers:
                self.log_debug("Sending to notification server: %s" % (uri,))
                observer.sendLine(str(uri))
        else:
            self.log_debug("Queing: %s" % (uri,))
            self.queued.add(uri)

    def connectionMade(self):
        if self.factory.isReady() and self.observers:
            for observer in self.observers:
                for uri in self.queued:
                    self.log_debug("Sending from queue: %s" % (uri,))
                    observer.sendLine(str(uri))
            self.queued.clear()

    def addObserver(self, observer):
        self.observers.add(observer)

    def removeObserver(self, observer):
        self.observers.remove(observer)


_notificationClient = None

def installNotificationClient(reactor, host, port, klass=NotificationClient):
    global _notificationClient
    _notificationClient = klass(reactor, host, port)

def getNotificationClient():
    return _notificationClient







# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# Classes used within Notification Server
#

#
# Internal Channel (from icalserver to notification server)
#

class InternalNotificationProtocol(basic.LineReceiver):
    """
    InternalNotificationProtocol

    Receives notifications from the calendar server.
    """

    def lineReceived(self, line):
        val = str(line.strip())
        self.factory.coalescer.add(val)


class InternalNotificationFactory(protocol.ServerFactory):
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

    def __init__(self, notifiers, reactor=None, delaySeconds=None):

        if delaySeconds:
            self.delaySeconds = delaySeconds

        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor

        self.uris = dict()
        self.notifiers = notifiers

    def add(self, uri):
        delayed = self.uris.get(uri, None)
        if delayed and delayed.active():
            delayed.reset(self.delaySeconds)
        else:
            self.uris[uri] = self.reactor.callLater(self.delaySeconds,
                self.delayedEnqueue, uri)

    def delayedEnqueue(self, uri):
        for notifier in self.notifiers:
            notifier.enqueue(uri)



#
# External Channel (from notification server to other consumers)
#

class INotifier(Interface):
    """
    Notifier Interface

    Defines an enqueue method that Notifier classes need to implement.
    """

    def enqueue(uri):
        """
        Let's the notifier object know that a change has been made for this
        uri, and enough time has passed to allow for coalescence.

        @type uri: C{str}
        """


class SimpleLineNotifier(object):
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

    def enqueue(self, uri):

        self.latestSeq += 1L

        # Update history
        self.history[uri] = self.latestSeq

        for observer in self.observers:
            observer.sendLine("%d %s" % (self.latestSeq, uri))

    def reset(self):
        self.latestSeq = 0L
        self.history = { } # keys=uri, values=sequenceNumber

    def playback(self, observer, oldSeq):

        hist = self.history
        toSend = [(hist[uri], uri) for uri in hist if hist[uri] > oldSeq]
        toSend.sort() # sorts the tuples based on numeric sequence number

        for seq, uri in toSend:
            observer.sendLine("%d %s" % (seq, str(uri)))


    def addObserver(self, observer):
        self.observers.add(observer)

    def removeObserver(self, observer):
        self.observers.remove(observer)

    def connectionMade(self, observer):
        if not self.sentReset:
            observer.sendLine("0")
            self.sentReset = True


class SimpleLineNotificationProtocol(basic.LineReceiver, LoggingMixIn):
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


class SimpleLineNotificationFactory(protocol.ServerFactory):
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

    For monitoring purposes, you can specify a "TestJID" value in
    the config file; XMPPNotifier will send error messages to that
    JID.  If you also want to receive non-error, debug messages,
    send the calendar server JID the message, "debug on".  Send
    "help" for other commands.  Note, XMPPNotifier doesn't yet
    handle registration or roster management, so you'll need to set
    up the JID accounts out-of-band, using another XMPP client, for
    example.

    """

    implements(INotifier)

    pubsubNS = 'http://jabber.org/protocol/pubsub'

    nodeConf = {
        'pubsub#deliver_payloads' : '0',
        'pubsub#persist_items' : '0',
    }

    def __init__(self, settings, reactor=None, configOverride=None):
        self.xmlStream = None
        self.settings = settings
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor
        self.config = configOverride or config

        self.sendDebugMessages = False

    def enqueue(self, uri):
        if self.xmlStream is not None:
            # Convert uri to node
            nodeName = self.uriToNodeName(uri)
            self.publishNode(nodeName)

    def uriToNodeName(self, uri):
        return getPubSubPath(uri, getPubSubConfiguration(self.config))

    def publishNode(self, nodeName):
        if self.xmlStream is not None:
            iq = IQ(self.xmlStream)
            pubsubElement = iq.addElement('pubsub', defaultUri=self.pubsubNS)
            publishElement = pubsubElement.addElement('publish')
            publishElement['node'] = nodeName
            iq.addCallback(self.responseFromPublish, nodeName)
            iq.send(to=self.settings['ServiceAddress'])

    def responseFromPublish(self, nodeName, iq):
        if iq['type'] == 'result':
            self.sendDebug("Node publish successful (%s)" % (nodeName,), iq)
        else:
            self.log_error("PubSub node publish error: %s" %
                (iq.toXml().encode('ascii', 'replace')),)
            self.sendDebug("Node publish failed (%s)" % (nodeName,), iq)

            errorElement = None
            pubsubElement = None
            for child in iq.elements():
                if child.name == 'error':
                    errorElement = child
                if child.name == 'pubsub':
                    pubsubElement = child

            if errorElement:
                if errorElement['code'] == '400':
                    self.requestConfigurationForm(nodeName)

                elif errorElement['code'] == '404':
                    self.createNode(nodeName)

    def createNode(self, nodeName):
        if self.xmlStream is not None:
            iq = IQ(self.xmlStream)
            pubsubElement = iq.addElement('pubsub', defaultUri=self.pubsubNS)
            child = pubsubElement.addElement('create')
            child['node'] = nodeName
            iq.addCallback(self.responseFromCreate, nodeName)
            iq.send(to=self.settings['ServiceAddress'])

    def responseFromCreate(self, nodeName, iq):
        if iq['type'] == 'result':
            self.sendDebug("Node creation successful (%s)" % (nodeName,), iq)
            # now time to configure; fetch the form
            self.requestConfigurationForm(nodeName)
        else:
            self.log_error("PubSub node creation error: %s" %
                (iq.toXml().encode('ascii', 'replace')),)
            self.sendError("Node creation failed (%s)" % (nodeName,), iq)

    def requestConfigurationForm(self, nodeName):
        if self.xmlStream is not None:
            iq = IQ(self.xmlStream, type='get')
            child = iq.addElement('pubsub', defaultUri=self.pubsubNS+"#owner")
            child = child.addElement('configure')
            child['node'] = nodeName
            iq.addCallback(self.responseFromConfigurationForm, nodeName)
            iq.send(to=self.settings['ServiceAddress'])

    def _getChild(self, element, name):
        for child in element.elements():
            if child.name == name:
                return child
        return None

    def responseFromConfigurationForm(self, nodeName, iq):
        if iq['type'] == 'result':
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

                        for field in formElement.elements():
                            if field.name == 'field':
                                value = self.nodeConf.get(field['var'], None)
                                if value is not None:
                                    valueElement = self._getChild(field,
                                        'value')
                                    valueElement.children = []
                                    valueElement.addContent(value)
                            filledForm.addChild(field)
                        filledIq.addCallback(self.responseFromConfiguration,
                            nodeName)
                        filledIq.send(to=self.settings['ServiceAddress'])
        else:
            self.log_error("PubSub configuration form request error: %s" %
                (iq.toXml().encode('ascii', 'replace')),)
            self.sendError("Failed to receive configuration form (%s)" % (nodeName,), iq)


    def responseFromConfiguration(self, nodeName, iq):
        if iq['type'] == 'result':
            self.log_debug("PubSub node %s is configured" % (nodeName,))
            self.sendDebug("Configured node (%s)" % (nodeName,), iq)
            self.publishNode(nodeName)

        else:
            self.log_error("PubSub node configuration error: %s" %
                (iq.toXml().encode('ascii', 'replace')),)
            self.sendError("Failed to configure node (%s)" % (nodeName,), iq)


    def streamOpened(self, xmlStream):
        self.xmlStream = xmlStream
        xmlStream.addObserver('/message', self.handleMessage)

    def streamClosed(self):
        self.xmlStream = None

    def sendDebug(self, txt, element):
        if self.sendDebugMessages:
            testJid = self.settings.get("TestJID", "")
            if testJid:
                txt = "DEBUG: %s %s" % (txt, element.toXml().encode('ascii',
                    'replace'))
                self.sendAlert(testJid, txt)

    def sendError(self, txt, element):
        testJid = self.settings.get("TestJID", "")
        if testJid:
            txt = "ERROR: %s %s" % (txt, element.toXml().encode('ascii',
                'replace'))
            self.sendAlert(testJid, txt)

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
            txt = str(body).lower()
            if txt == "help":
                response = "debug on, debug off"
            elif txt == "debug on":
                self.sendDebugMessages = True
                response = "Debugging on"
            elif txt == "debug off":
                self.sendDebugMessages = False
                response = "Debugging off"
            else:
                response = "I don't understand.  Try 'help'."

            if response:
                message = domish.Element(('jabber:client', 'message'))
                message['to'] = JID(iq['from']).full()
                message.addElement('body', content=response)
                self.xmlStream.send(message)




class XMPPNotificationFactory(xmlstream.XmlStreamFactory, LoggingMixIn):

    def __init__(self, notifier, settings, reactor=None):
        self.notifier = notifier
        self.settings = settings
        self.jid = settings['JID']
        self.keepAliveSeconds = settings.get('KeepAliveSeconds', 120)
        self.xmlStream = None
        self.presenceCall = None
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor

        xmlstream.XmlStreamFactory.__init__(self,
            BasicAuthenticator(JID(self.jid), settings['Password']))

        self.addBootstrap(xmlstream.STREAM_CONNECTED_EVENT, self.connected)
        self.addBootstrap(xmlstream.STREAM_END_EVENT, self.disconnected)
        self.addBootstrap(xmlstream.INIT_FAILED_EVENT, self.initFailed)

        self.addBootstrap(xmlstream.STREAM_AUTHD_EVENT, self.authenticated)
        self.addBootstrap(BasicAuthenticator.INVALID_USER_EVENT,
            self.authFailed)
        self.addBootstrap(BasicAuthenticator.AUTH_FAILED_EVENT,
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
        if self.xmlStream is not None:
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
    for settings in config.Notifications["Services"]:
        if (settings["Service"] == "twistedcaldav.notify.XMPPNotifierService"
            and settings["Enabled"]):
            results['enabled'] = True
            results['service'] = settings['ServiceAddress']
            results['host'] = config.ServerHostName
            results['port'] = config.SSLPort or config.HTTPPort

    return results

def getPubSubPath(uri, pubSubConfiguration):
    return ("/Public/CalDAV/%s/%d/%s/" % (pubSubConfiguration['host'],
        pubSubConfiguration['port'], uri.strip("/")))

def getPubSubXMPPURI(uri, pubSubConfiguration):
    return "xmpp:%s?pubsub;node=%s" % (pubSubConfiguration['service'],
        getPubSubPath(uri, pubSubConfiguration))

#
# Notification Server service config
#

class NotificationOptions(Options):
    optParameters = [[
        "config", "f", "/etc/caldavd/caldavd.plist", "Path to configuration file."
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
        parseConfig(self['config'])
        config.updateDefaults(self.overrides)


class NotificationServiceMaker(object):
    implements(IPlugin, service.IServiceMaker)

    tapname = "caldav_notifier"
    description = "Notification Server"
    options = NotificationOptions

    def makeService(self, options):

        multiService = service.MultiService()

        notifiers = []
        for settings in config.Notifications["Services"]:
            if settings["Enabled"]:
                notifier = namedClass(settings["Service"])(settings)
                notifier.setServiceParent(multiService)
                notifiers.append(notifier)

        internet.TCPServer(
            config.Notifications["InternalNotificationPort"],
            InternalNotificationFactory(notifiers,
                delaySeconds=config.Notifications["CoalesceSeconds"])
        ).setServiceParent(multiService)

        return multiService


class SimpleLineNotifierService(service.Service):

    def __init__(self, settings):
        self.notifier = SimpleLineNotifier(settings)
        self.server = internet.TCPServer(settings["Port"],
            SimpleLineNotificationFactory(self.notifier))

    def enqueue(self, uri):
        self.notifier.enqueue(uri)

    def startService(self):
        self.server.startService()

    def stopService(self):
        self.server.stopService()


class XMPPNotifierService(service.Service):

    def __init__(self, settings):
        self.notifier = XMPPNotifier(settings)
        self.client = internet.TCPClient(settings["Host"], settings["Port"],
            XMPPNotificationFactory(self.notifier, settings))

    def enqueue(self, uri):
        self.notifier.enqueue(uri)

    def startService(self):
        self.client.startService()

    def stopService(self):
        self.client.stopService()

