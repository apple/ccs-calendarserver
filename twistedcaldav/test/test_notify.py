##
# Copyright (c) 2008-2012 Apple Inc. All rights reserved.
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

from twisted.internet.task import Clock
from twisted.words.protocols.jabber.client import IQ
from twisted.words.protocols.jabber.error import StanzaError
from twistedcaldav.notify import *
from twistedcaldav.config import Config
from twistedcaldav.stdconfig import DEFAULT_CONFIG, PListConfigProvider
from twistedcaldav.test.util import TestCase


class StubResource(object):

    def __init__(self, id):
        self._id = id

    def resourceID(self):
        return self._id



class NotifierTests(TestCase):

    def test_notifier(self):
        enabledConfig = Config(PListConfigProvider(DEFAULT_CONFIG))
        enabledConfig.Notifications["Enabled"] = True
        notifier = Notifier(None, id="test")

        self.assertEquals(notifier._ids, {"default": "test"})
        clone = notifier.clone(label="alt", id="altID")
        self.assertEquals("altID", clone.getID(label="alt"))
        self.assertEquals(clone._ids, {
            "default" : "test",
            "alt"     : "altID",
        })
        self.assertEquals("test", notifier.getID())
        self.assertEquals(notifier._ids, {
            "default" : "test",
        })
        self.assertEquals(None, notifier.getID(label="notthere"))

        notifier = Notifier(None, id="urn:uuid:foo")
        self.assertEquals("foo", notifier.getID())

        notifier.disableNotify()
        self.assertEquals(notifier._notify, False)
        notifier.enableNotify(None)
        self.assertEquals(notifier._notify, True)

        notifier = Notifier(None, id="test", prefix="CalDAV")
        self.assertEquals("CalDAV|test", notifier.getID())



class NotificationClientFactoryTests(TestCase):

    def setUp(self):
        TestCase.setUp(self)
        self.client = StubNotificationClient(None, None)
        self.factory = NotificationClientFactory(self.client)
        self.factory.protocol = StubNotificationClientProtocol

    def test_connect(self):
        self.assertEquals(self.factory.isReady(), False)
        protocol = self.factory.buildProtocol(None)
        protocol.connectionMade()
        self.assertEquals(self.client.observers, set([protocol]))
        self.assertEquals(self.factory.isReady(), True)

        protocol.connectionLost(None)
        self.assertEquals(self.client.observers, set())
        self.assertEquals(self.factory.isReady(), False)


class StubNotificationClient(object):

    def __init__(self, host, port, reactor=None):
        self.lines = []
        self.observers = set()

    def send(self, op, id):
        self.lines.append(id)

    def addObserver(self, observer):
        self.observers.add(observer)

    def removeObserver(self, observer):
        self.observers.remove(observer)

    def connectionMade(self):
        pass

    def clear(self):
        self.lines = []

class StubNotificationClientProtocol(object):

    def __init__(self):
        self.lines = []

    def sendLine(self, line):
        self.lines.append(line)

    def connectionMade(self):
        self.client.addObserver(self)
        self.factory.connectionMade()

    def connectionLost(self, reason):
        self.client.removeObserver(self)
        self.factory.connected = False


class NotifierFactoryTests(TestCase):

    def setUp(self):
        TestCase.setUp(self)
        self.client = NotifierFactory(None, None, reactor=Clock())
        self.client.factory = StubNotificationClientFactory()

    def test_sendWhileNotConnected(self):
        self.client.send("update", "a")
        self.assertEquals(self.client.queued, set(["update a"]))

    def test_sendWhileConnected(self):
        protocol = StubNotificationClientProtocol()
        self.client.addObserver(protocol)
        self.client.factory.connected = True
        self.client.send("update", "a")
        self.assertEquals(self.client.queued, set())
        self.assertEquals(protocol.lines, ["update a"])

    def test_sendQueue(self):
        self.client.send("update", "a")
        self.assertEquals(self.client.queued, set(["update a"]))
        protocol = StubNotificationClientProtocol()
        self.client.addObserver(protocol)
        self.client.factory.connected = True
        self.client.connectionMade()
        self.assertEquals(protocol.lines, ["update a"])
        self.assertEquals(self.client.queued, set())


class StubNotificationClientFactory(object):

    def __init__(self):
        self.connected = False

    def isReady(self):
        return self.connected


class CoalescerTests(TestCase):

    def setUp(self):
        TestCase.setUp(self)
        self.clock = Clock()
        self.notifier = StubNotifier()
        self.coalescer = Coalescer([self.notifier], reactor=self.clock)

    def test_delayedNotifications(self):
        self.coalescer.add("update", "A")
        self.assertEquals(self.notifier.notifications, [])
        self.clock.advance(5)
        self.assertEquals(self.notifier.notifications, ["A"])

    def test_removeDuplicates(self):
        self.coalescer.add("update", "A")
        self.coalescer.add("update", "A")
        self.clock.advance(5)
        self.assertEquals(self.notifier.notifications, ["A"])


class StubNotifier(object):

    def __init__(self):
        self.notifications = []
        self.observers = set()
        self.playbackHistory = []

    def enqueue(self, op, id):
        self.notifications.append(id)

    def playback(self, protocol, old_seq):
        self.playbackHistory.append((protocol, old_seq))

    def addObserver(self, observer):
        self.observers.add(observer)

    def removeObserver(self, observer):
        self.observers.remove(observer)


class SimpleLineNotifierTests(TestCase):

    def setUp(self):
        TestCase.setUp(self)
        self.clock = Clock()
        self.notifier = SimpleLineNotifier(None)
        self.coalescer = Coalescer([self.notifier], reactor=self.clock)

    def test_initialConnection(self):
        protocol = StubProtocol()
        self.notifier.addObserver(protocol)
        self.notifier.connectionMade(protocol)
        self.assertEquals(protocol.lines, ["0"])

    def test_subsequentConnection(self):
        protocol = StubProtocol()
        self.notifier.addObserver(protocol)
        self.notifier.connectionMade(protocol)
        protocol.lines = []
        self.notifier.connectionMade(protocol)
        self.assertEquals(protocol.lines, [])

    def test_send(self):
        protocol = StubProtocol()
        self.notifier.addObserver(protocol)
        self.notifier.enqueue("update", "A")
        self.assertEquals(protocol.lines, ["1 A"])

    def test_incrementSequence(self):
        protocol = StubProtocol()
        self.notifier.addObserver(protocol)
        self.notifier.enqueue("update", "A")
        self.notifier.enqueue("update", "B")
        self.assertEquals(protocol.lines, ["1 A", "2 B"])

    def test_addObserver(self):
        protocol = StubProtocol()
        self.notifier.addObserver(protocol)
        self.notifier.enqueue("update", "A")
        self.assertEquals(protocol.lines, ["1 A"])

    def test_removeObserver(self):
        protocol = StubProtocol()
        self.notifier.addObserver(protocol)
        self.notifier.removeObserver(protocol)
        self.notifier.enqueue("update", "A")
        self.assertEquals(protocol.lines, [])

    def test_multipleObservers(self):
        protocol1 = StubProtocol()
        protocol2 = StubProtocol()
        self.notifier.addObserver(protocol1)
        self.notifier.addObserver(protocol2)
        self.notifier.enqueue("update", "A")
        self.assertEquals(protocol1.lines, ["1 A"])
        self.assertEquals(protocol2.lines, ["1 A"])

    def test_duplicateObservers(self):
        protocol = StubProtocol()
        self.notifier.addObserver(protocol)
        self.notifier.addObserver(protocol)
        self.notifier.enqueue("update", "A")
        self.assertEquals(protocol.lines, ["1 A"])

    def test_playback(self):
        self.notifier.enqueue("update", "A")
        self.notifier.enqueue("update", "B")
        self.notifier.enqueue("update", "C")
        protocol = StubProtocol()
        self.notifier.addObserver(protocol)
        self.notifier.playback(protocol, 1)
        self.assertEquals(protocol.lines, ["2 B", "3 C"])

    def test_reset(self):
        self.notifier.enqueue("update", "A")
        self.assertEquals(self.notifier.history, {"A" : 1})
        self.assertEquals(self.notifier.latestSeq, 1)
        self.notifier.reset()
        self.assertEquals(self.notifier.history, {})
        self.assertEquals(self.notifier.latestSeq, 0)
        

class SimpleLineNotificationFactoryTests(TestCase):

    def test_buildProtocol(self):
        notifier = StubNotifier()
        factory = SimpleLineNotificationFactory(notifier)
        protocol = factory.buildProtocol(None)
        self.assertEquals(protocol.notifier, notifier)
        self.assertIn(protocol, notifier.observers)


class SimpleLineNotificationProtocolTests(TestCase):

    def setUp(self):
        TestCase.setUp(self)
        self.notifier = StubNotifier()
        self.protocol = SimpleLineNotificationProtocol()
        self.protocol.notifier = self.notifier
        self.protocol.transport = StubTransport()
        self.notifier.addObserver(self.protocol)

    def test_connectionLost(self):
        self.protocol.connectionLost(None)
        self.assertNotIn(self.protocol, self.notifier.observers)

    def test_lineReceived(self):
        self.protocol.lineReceived("2")
        self.assertEquals(self.notifier.playbackHistory, [(self.protocol, 2)])

    def test_lineReceivedInvalid(self):
        self.protocol.lineReceived("bogus")
        self.assertEquals(self.notifier.playbackHistory, [])



class StubProtocol(object):

    def __init__(self):
        self.lines = []

    def sendLine(self, line):
        self.lines.append(line)


class StubTransport(object):

    def getPeer(self):
        return "peer"






class StubXmlStream(object):

    def __init__(self):
        self.elements = []

    def send(self, element):
        self.elements.append(element)

    def addOnetimeObserver(self, *args, **kwds):
        pass

    def addObserver(self, *args, **kwds):
        pass


class StubFailure(object):

    def __init__(self, value):
        self.value = value

class XMPPNotifierTests(TestCase):

    xmppEnabledConfig = Config(PListConfigProvider(DEFAULT_CONFIG))
    xmppEnabledConfig.Notifications["Enabled"] = True
    xmppEnabledConfig.Notifications["Services"]["XMPPNotifier"]["Enabled"] = True
    xmppEnabledConfig.ServerHostName = "server.example.com"
    xmppEnabledConfig.HTTPPort = 80

    xmppDisabledConfig = Config(PListConfigProvider(DEFAULT_CONFIG))
    xmppDisabledConfig.Notifications["Services"]["XMPPNotifier"]["Enabled"] = False

    def setUp(self):
        TestCase.setUp(self)
        self.xmlStream = StubXmlStream()
        self.settings = { "ServiceAddress" : "pubsub.example.com",
            "NodeConfiguration" : { "pubsub#deliver_payloads" : "1" },
            "HeartbeatMinutes" : 30,
        }
        self.notifier = XMPPNotifier(self.settings, reactor=Clock(),
            configOverride=self.xmppEnabledConfig, heartbeat=False)
        self.notifier.streamOpened(self.xmlStream)

    def test_sendWhileConnected(self):
        self.notifier.enqueue("update", "test")

        iq = self.xmlStream.elements[1]
        self.assertEquals(iq.name, "iq")

        pubsubElement = list(iq.elements())[0]
        self.assertEquals(pubsubElement.name, "pubsub")
        self.assertEquals(pubsubElement.uri, "http://jabber.org/protocol/pubsub")

        publishElement = list(pubsubElement.elements())[0]
        self.assertEquals(publishElement.name, "publish")
        self.assertEquals(publishElement.uri, "http://jabber.org/protocol/pubsub")
        self.assertEquals(publishElement["node"],
            "/server.example.com/test/")

    def test_sendWhileNotConnected(self):
        notifier = XMPPNotifier(self.settings, reactor=Clock(),
            configOverride=self.xmppDisabledConfig)
        notifier.enqueue("update", "/principals/__uids__/test")
        self.assertEquals(len(self.xmlStream.elements), 1)

    def test_publishNewNode(self):
        self.notifier.publishNode("testNodeName")
        iq = self.xmlStream.elements[1]
        self.assertEquals(iq.name, "iq")

    def test_publishReponse400(self):
        failure = StubFailure(StanzaError("bad-request"))
        self.assertEquals(len(self.xmlStream.elements), 1)
        self.notifier.publishNodeFailure(failure, "testNodeName")
        self.assertEquals(len(self.xmlStream.elements), 2)
        iq = self.xmlStream.elements[1]
        self.assertEquals(iq.name, "iq")
        self.assertEquals(iq["type"], "get")

        pubsubElement = list(iq.elements())[0]
        self.assertEquals(pubsubElement.name, "pubsub")
        self.assertEquals(pubsubElement.uri,
            "http://jabber.org/protocol/pubsub#owner")
        configElement = list(pubsubElement.elements())[0]
        self.assertEquals(configElement.name, "configure")
        self.assertEquals(configElement["node"], "testNodeName")


    def test_publishReponse404(self):
        self.assertEquals(len(self.xmlStream.elements), 1)
        failure = StubFailure(StanzaError("item-not-found"))
        self.notifier.publishNodeFailure(failure, "testNodeName")
        self.assertEquals(len(self.xmlStream.elements), 2)
        iq = self.xmlStream.elements[1]
        self.assertEquals(iq.name, "iq")
        self.assertEquals(iq["type"], "set")

        pubsubElement = list(iq.elements())[0]
        self.assertEquals(pubsubElement.name, "pubsub")
        self.assertEquals(pubsubElement.uri,
            "http://jabber.org/protocol/pubsub")
        createElement = list(pubsubElement.elements())[0]
        self.assertEquals(createElement.name, "create")
        self.assertEquals(createElement["node"], "testNodeName")


    def test_configureResponse(self):

        def _getChild(element, name):
            for child in element.elements():
                if child.name == name:
                    return child
            return None

        response = IQ(self.xmlStream, type="result")
        pubsubElement = response.addElement("pubsub")
        configElement = pubsubElement.addElement("configure")
        formElement = configElement.addElement("x")
        formElement["type"] = "form"
        fields = [
            ( "unknown", "don't edit me", "text-single" ),
            ( "pubsub#deliver_payloads", "0", "boolean" ),
            ( "pubsub#persist_items", "0", "boolean" ),
        ]
        expectedFields = {
            "unknown" : "don't edit me",
            "pubsub#deliver_payloads" : "1",
            "pubsub#persist_items" : "1",
        }
        for field in fields:
            fieldElement = formElement.addElement("field")
            fieldElement["var"] = field[0]
            fieldElement["type"] = field[2]
            fieldElement.addElement("value", content=field[1])

        self.assertEquals(len(self.xmlStream.elements), 1)
        self.notifier.requestConfigurationFormSuccess(response, "testNodeName",
            False)
        self.assertEquals(len(self.xmlStream.elements), 2)

        iq = self.xmlStream.elements[1]
        self.assertEquals(iq.name, "iq")
        self.assertEquals(iq["type"], "set")

        pubsubElement = list(iq.elements())[0]
        self.assertEquals(pubsubElement.name, "pubsub")
        configElement = list(pubsubElement.elements())[0]
        self.assertEquals(configElement.name, "configure")
        self.assertEquals(configElement["node"], "testNodeName")
        formElement = list(configElement.elements())[0]
        self.assertEquals(formElement["type"], "submit")
        for field in formElement.elements():
            valueElement = _getChild(field, "value")
            if valueElement is not None:
                self.assertEquals(expectedFields[field["var"]],
                    str(valueElement))


    def test_sendHeartbeat(self):

        xmppConfig = Config(PListConfigProvider(DEFAULT_CONFIG))
        xmppConfig.Notifications["Enabled"] = True
        xmppConfig.Notifications["Services"]["XMPPNotifier"]["Enabled"] = True
        xmppConfig.ServerHostName = "server.example.com"
        xmppConfig.HTTPPort = 80

        clock = Clock()
        xmlStream = StubXmlStream()
        settings = { "ServiceAddress" : "pubsub.example.com", "JID" : "jid",
            "Password" : "password", "KeepAliveSeconds" : 5,
            "NodeConfiguration" : { "pubsub#deliver_payloads" : "1" },
            "HeartbeatMinutes" : 30 }
        notifier = XMPPNotifier(settings, reactor=clock, heartbeat=True,
            roster=False, configOverride=xmppConfig)
        factory = XMPPNotificationFactory(notifier, settings, reactor=clock,
            keepAlive=False)
        factory.connected(xmlStream)
        factory.authenticated(xmlStream)

        self.assertEquals(len(xmlStream.elements), 1)
        heartbeat = xmlStream.elements[0]
        self.assertEquals(heartbeat.name, "iq")

        clock.advance(1800)

        self.assertEquals(len(xmlStream.elements), 2)
        heartbeat = xmlStream.elements[1]
        self.assertEquals(heartbeat.name, "iq")

        factory.disconnected(xmlStream)
        clock.advance(1800)
        self.assertEquals(len(xmlStream.elements), 2)




class XMPPNotificationFactoryTests(TestCase):

    def test_sendPresence(self):
        clock = Clock()
        xmlStream = StubXmlStream()
        settings = { "ServiceAddress" : "pubsub.example.com", "JID" : "jid",
            "NodeConfiguration" : { "pubsub#deliver_payloads" : "1" },
            "Password" : "password", "KeepAliveSeconds" : 5 }
        notifier = XMPPNotifier(settings, reactor=clock, heartbeat=False)
        factory = XMPPNotificationFactory(notifier, settings, reactor=clock)
        factory.connected(xmlStream)
        factory.authenticated(xmlStream)

        self.assertEquals(len(xmlStream.elements), 2)
        presence = xmlStream.elements[0]
        self.assertEquals(presence.name, "presence")
        iq = xmlStream.elements[1]
        self.assertEquals(iq.name, "iq")

        clock.advance(5)

        self.assertEquals(len(xmlStream.elements), 3)
        presence = xmlStream.elements[2]
        self.assertEquals(presence.name, "presence")

        factory.disconnected(xmlStream)
        clock.advance(5)
        self.assertEquals(len(xmlStream.elements), 3)



class ConfigurationTests(TestCase):

    def test_disabled(self):
        disabledConfig = Config(PListConfigProvider(DEFAULT_CONFIG))

        # Overall notifications are disabled
        disabledConfig.Notifications["Enabled"] = False
        conf = getPubSubConfiguration(disabledConfig)
        self.assertEquals(conf, { "enabled" : False, "host" : "" })
        conf = getXMPPSettings(disabledConfig)
        self.assertEquals(conf, None)

        # Overall notifications are enabled, but XMPP disabled
        disabledConfig.Notifications["Enabled"] = True
        settings = getXMPPSettings(disabledConfig)
        self.assertEquals(settings, None)

        # Overall notifications are enabled, XMPP enabled, but no APS
        service = disabledConfig.Notifications["Services"]["XMPPNotifier"]
        service.Enabled = True
        conf = getPubSubAPSConfiguration("CalDAV|foo", disabledConfig)
        self.assertEquals(conf, None)

    def test_enabled(self):
        enabledConfig = Config(PListConfigProvider(DEFAULT_CONFIG))
        enabledConfig.Notifications["Enabled"] = True
        service = enabledConfig.Notifications["Services"]["XMPPNotifier"]
        service.Enabled = True
        service.Host = "example.com"
        service.Port = 5222
        service.ServiceAddress = "pubsub.example.com"
        service.CalDAV.APSBundleID = "CalDAVAPSBundleID"
        service.CalDAV.SubscriptionURL = "CalDAVSubscriptionURL"
        conf = getPubSubConfiguration(enabledConfig)
        self.assertEquals(conf, {'heartrate': 30, 'service': 'pubsub.example.com', 'xmpp-server': 'example.com', 'enabled': True, 'host': '', 'port': 0} )
        conf = getPubSubAPSConfiguration("CalDAV|foo", enabledConfig)
        self.assertEquals(conf, {'SubscriptionURL': 'CalDAVSubscriptionURL', 'APSBundleID': 'CalDAVAPSBundleID', 'APSEnvironment' : 'PRODUCTION'} )
        conf = getPubSubAPSConfiguration("noprefix", enabledConfig)
        self.assertEquals(conf, None)
        conf = getPubSubAPSConfiguration("UnknownPrefix|foo", enabledConfig)
        self.assertEquals(conf, None)

    def test_allowedInRoster(self):
        """
        Our own JID is implicitly included in AllowedJIDs
        """
        settings = {
            "JID" : "test1@example.com",
            "AllowedJIDs" : ["test2@example.com"]
        }
        notifier = XMPPNotifier(settings, heartbeat=False)
        self.assertTrue(notifier.allowedInRoster("test1@example.com"))
        self.assertTrue(notifier.allowedInRoster("test2@example.com"))
        self.assertFalse(notifier.allowedInRoster("test3@example.com"))
