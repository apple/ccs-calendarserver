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

from calendarserver.push.applepush import (
    ApplePushNotifierService, APNProviderProtocol
)
from calendarserver.push.util import validToken
from twistedcaldav.test.util import TestCase
from twisted.internet.defer import inlineCallbacks, succeed
from twisted.internet.task import Clock
import struct
from txdav.common.datastore.test.util import buildStore, CommonCommonTests
from txdav.common.icommondatastore import InvalidSubscriptionValues

class ApplePushNotifierServiceTests(CommonCommonTests, TestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(ApplePushNotifierServiceTests, self).setUp()
        self.store = yield buildStore(self, None)

    @inlineCallbacks
    def test_ApplePushNotifierService(self):

        settings = {
            "Service" : "calendarserver.push.applepush.ApplePushNotifierService",
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
                "AuthorityChainPath" : "chain.pem",
                "Passphrase" : "",
                "Topic" : "caldav_topic",
            },
            "CardDAV" : {
                "CertificatePath" : "carddav.cer",
                "PrivateKeyPath" : "carddav.pem",
                "AuthorityChainPath" : "chain.pem",
                "Passphrase" : "",
                "Topic" : "carddav_topic",
            },
        }


        # Add subscriptions
        txn = self.store.newTransaction()

        # Ensure empty values don't get through
        try:
            yield txn.addAPNSubscription("", "", "", "")
        except InvalidSubscriptionValues:
            pass
        try:
            yield txn.addAPNSubscription("", "1", "2", "3")
        except InvalidSubscriptionValues:
            pass

        token = "2d0d55cd7f98bcb81c6e24abcdc35168254c7846a43e2828b1ba5a8f82e219df"
        key1 = "/CalDAV/calendars.example.com/user01/calendar/"
        timestamp1 = 1000
        uid = "D2256BCC-48E2-42D1-BD89-CBA1E4CCDFFB"
        yield txn.addAPNSubscription(token, key1, timestamp1, uid)

        key2 = "/CalDAV/calendars.example.com/user02/calendar/"
        timestamp2 = 3000
        yield txn.addAPNSubscription(token, key2, timestamp2, uid)
        yield txn.commit()

        # Set up the service
        clock = Clock()
        service = (yield ApplePushNotifierService.makeService(settings,
            self.store, testConnectorClass=TestConnector, reactor=clock))
        self.assertEquals(set(service.providers.keys()), set(["CalDAV","CardDAV"]))
        self.assertEquals(set(service.feedbacks.keys()), set(["CalDAV","CardDAV"]))

        # First, enqueue a notification while we have no connection, in this
        # case by doing it prior to startService()

        # Notification arrives from calendar server
        yield service.enqueue("update", "CalDAV|user01/calendar")

        # The notification should be in the queue
        self.assertEquals(service.providers["CalDAV"].queue, [(token, key1)])

        # Start the service, making the connection which should service the
        # queue
        service.startService()

        # The queue should be empty
        self.assertEquals(service.providers["CalDAV"].queue, [])

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

        def errorTestFunction(status, identifier):
            history.append((status, identifier))
            return succeed(None)

        # Simulate an error
        history = []
        errorData = struct.pack("!BBI", APNProviderProtocol.COMMAND_ERROR, 1, 2)
        yield connector.receiveData(errorData, fn=errorTestFunction)
        clock.advance(301)

        # Simulate multiple errors and dataReceived called
        # with amounts of data not fitting message boundaries
        # Send 1st 4 bytes
        history = []
        errorData = struct.pack("!BBIBBI",
            APNProviderProtocol.COMMAND_ERROR, 3, 4,
            APNProviderProtocol.COMMAND_ERROR, 5, 6,
        )
        yield connector.receiveData(errorData[:4], fn=errorTestFunction)
        # Send remaining bytes
        yield connector.receiveData(errorData[4:], fn=errorTestFunction)
        self.assertEquals(history, [(3, 4), (5, 6)])
        # Buffer is empty
        self.assertEquals(len(connector.service.protocol.buffer), 0)

        # Sending 7 bytes
        yield connector.receiveData("!" * 7, fn=errorTestFunction)
        # Buffer has 1 byte remaining
        self.assertEquals(len(connector.service.protocol.buffer), 1)


        # Prior to feedback, there are 2 subscriptions
        txn = self.store.newTransaction()
        subscriptions = (yield txn.apnSubscriptionsByToken(token))
        yield txn.commit()
        self.assertEquals(len(subscriptions), 2)


        # Simulate feedback with a single token
        connector = service.feedbacks["CalDAV"].testConnector
        timestamp = 2000
        binaryToken = token.decode("hex")
        feedbackData = struct.pack("!IH32s", timestamp, len(binaryToken),
            binaryToken)
        yield connector.receiveData(feedbackData)

        # Simulate feedback with multiple tokens, and dataReceived called
        # with amounts of data not fitting message boundaries
        history = []
        def feedbackTestFunction(timestamp, token):
            history.append((timestamp, token))
            return succeed(None)
        timestamp = 2000
        binaryToken = token.decode("hex")
        feedbackData = struct.pack("!IH32sIH32s",
            timestamp, len(binaryToken), binaryToken,
            timestamp, len(binaryToken), binaryToken,
            )
        # Send 1st 10 bytes
        yield connector.receiveData(feedbackData[:10], fn=feedbackTestFunction)
        # Send remaining bytes
        yield connector.receiveData(feedbackData[10:], fn=feedbackTestFunction)
        self.assertEquals(history, [(timestamp, token), (timestamp, token)])
        # Buffer is empty
        self.assertEquals(len(connector.service.protocol.buffer), 0)

        # Sending 39 bytes
        yield connector.receiveData("!" * 39, fn=feedbackTestFunction)
        # Buffer has 1 byte remaining
        self.assertEquals(len(connector.service.protocol.buffer), 1)

        # The second subscription should now be gone
        # Prior to feedback, there are 2 subscriptions
        txn = self.store.newTransaction()
        subscriptions = (yield txn.apnSubscriptionsByToken(token))
        yield txn.commit()
        self.assertEquals(len(subscriptions), 1)

    def test_validToken(self):
        self.assertTrue(validToken("2d0d55cd7f98bcb81c6e24abcdc35168254c7846a43e2828b1ba5a8f82e219df"))
        self.assertFalse(validToken("d0d55cd7f98bcb81c6e24abcdc35168254c7846a43e2828b1ba5a8f82e219df"))
        self.assertFalse(validToken("foo"))
        self.assertFalse(validToken(""))


class TestConnector(object):

    def connect(self, service, factory):
        self.service = service
        service.protocol = factory.buildProtocol(None)
        service.connected = 1
        self.transport = StubTransport()
        service.protocol.makeConnection(self.transport)

    def receiveData(self, data, fn=None):
        return self.service.protocol.dataReceived(data, fn=fn)


class StubTransport(object):

    def __init__(self):
        self.data = None

    def write(self, data):
        self.data = data
