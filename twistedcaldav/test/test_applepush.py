##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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

from twistedcaldav.applepush import (
    ApplePushNotifierService, APNProviderService, APNProviderProtocol
)
from twistedcaldav.test.util import TestCase
from twisted.internet.defer import inlineCallbacks, succeed
from twisted.internet.task import Clock
import struct
import time

class ApplePushNotifierServiceTests(TestCase):

    @inlineCallbacks
    def test_ApplePushNotifierService(self):

        settings = {
            "Service" : "twistedcaldav.applepush.ApplePushNotifierService",
            "Enabled" : True,
            "SubscriptionURL" : "apn",
            "DataHost" : "calendars.example.com",
            "ProviderHost" : "gateway.push.apple.com",
            "ProviderPort" : 2195,
            "FeedbackHost" : "feedback.push.apple.com",
            "FeedbackPort" : 2196,
            "FeedbackUpdateSeconds" : 300,
            "CalDAV" : {
                "CertificatePath" : "caldav.cer",
                "PrivateKeyPath" : "caldav.pem",
                "Topic" : "caldav_topic",
            },
            "CardDAV" : {
                "CertificatePath" : "carddav.cer",
                "PrivateKeyPath" : "carddav.pem",
                "Topic" : "carddav_topic",
            },
        }


        # Add subscriptions
        store = StubStore()
        txn = store.newTransaction()
        token = "2d0d55cd7f98bcb81c6e24abcdc35168254c7846a43e2828b1ba5a8f82e219df"
        key1 = "/CalDAV/calendars.example.com/user01/calendar/"
        timestamp1 = 1000
        guid = "D2256BCC-48E2-42D1-BD89-CBA1E4CCDFFB"
        yield txn.addAPNSubscription(token, key1, timestamp1, guid)

        key2 = "/CalDAV/calendars.example.com/user02/calendar/"
        timestamp2 = 3000
        yield txn.addAPNSubscription(token, key2, timestamp2, guid)

        # Set up the service
        clock = Clock()
        service = (yield ApplePushNotifierService.makeService(settings, store,
            testConnectorClass=TestConnector, reactor=clock))
        self.assertEquals(set(service.providers.keys()), set(["CalDAV","CardDAV"]))
        self.assertEquals(set(service.feedbacks.keys()), set(["CalDAV","CardDAV"]))
        service.startService()

        # Notification arrives from calendar server
        service.enqueue("update", "CalDAV|user01/calendar")

        # Verify data sent to APN
        connector = service.providers["CalDAV"].testConnector
        rawData = connector.transport.data
        self.assertEquals(len(rawData), 103)
        data = struct.unpack("!BIIH32sH", rawData[:45])
        self.assertEquals(data[0], 1) # command
        self.assertEquals(data[4].encode("hex"), token.replace(" ", "")) # token
        payloadLength = data[5]
        payload = struct.unpack("%ds" % (payloadLength,),
            rawData[45:])
        self.assertEquals(payload[0], '{"key" : "%s"}' % (key1,))

        # Simulate an error
        errorData = struct.pack("!BBI", APNProviderProtocol.COMMAND_ERROR, 1, 1)
        connector.receiveData(errorData)
        clock.advance(301)

        # Prior to feedback, there are 2 subscriptions
        self.assertEquals(len(store.subscriptions), 2)

        # Simulate feedback
        timestamp = 2000
        connector = service.feedbacks["CalDAV"].testConnector
        binaryToken = token.decode("hex")
        feedbackData = struct.pack("!IH32s", timestamp, len(binaryToken),
            binaryToken)
        connector.receiveData(feedbackData)

        # The second subscription should now be gone
        self.assertEquals(len(store.subscriptions), 1)


class TestConnector(object):

    def connect(self, service, factory):
        self.service = service
        service.protocol = factory.buildProtocol(None)
        service.connected = 1
        self.transport = StubTransport()
        service.protocol.makeConnection(self.transport)

    def receiveData(self, data):
        self.service.protocol.dataReceived(data)


class StubTransport(object):

    def __init__(self):
        self.data = None

    def write(self, data):
        self.data = data


class StubStore(object):

    def __init__(self):
        self.subscriptions = []

    def newTransaction(self):
        return StubTransaction(self)


class StubTransaction(object):

    def __init__(self, store):
        self.store = store

    def apnSubscriptionsByKey(self, key):
        matches = []
        for subscription in self.store.subscriptions:
            if subscription.key == key:
                matches.append((subscription.token, subscription.guid))
        return succeed(matches)

    def apnSubscriptionsByToken(self, token):
        matches = []
        for subscription in self.store.subscriptions:
            if subscription.token == token:
                matches.append((subscription.key, subscription.timestamp,
                    subscription.guid))
        return succeed(matches)

    def addAPNSubscription(self, token, key, timestamp, guid):
        subscription = Subscription(token, key, timestamp, guid)
        self.store.subscriptions.append(subscription)
        return succeed(None)

    def removeAPNSubscription(self, token, key):
        matches = []
        for subscription in list(self.store.subscriptions):
            if subscription.token == token and subscription.key == key:
                self.store.subscriptions.remove(subscription)
        return succeed(None)

    def commit(self):
        pass


class Subscription(object):

    def __init__(self, token, key, timestamp, guid):
        self.token = token
        self.key = key
        self.timestamp = timestamp
        self.guid = guid
