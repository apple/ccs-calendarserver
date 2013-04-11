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

import json
import struct
import time
from calendarserver.push.applepush import (
    ApplePushNotifierService, APNProviderProtocol
)
from calendarserver.push.util import validToken, TokenHistory
from twistedcaldav.test.util import TestCase
from twisted.internet.defer import inlineCallbacks, succeed
from twisted.internet.task import Clock
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
            "Enabled" : True,
            "SubscriptionURL" : "apn",
            "SubscriptionPurgeSeconds" : 24 * 60 * 60,
            "SubscriptionPurgeIntervalSeconds" : 24 * 60 * 60,
            "ProviderHost" : "gateway.push.apple.com",
            "ProviderPort" : 2195,
            "FeedbackHost" : "feedback.push.apple.com",
            "FeedbackPort" : 2196,
            "FeedbackUpdateSeconds" : 300,
            "EnableStaggering" : True,
            "StaggerSeconds" : 3,
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
            yield txn.addAPNSubscription("", "", "", "", "", "")
        except InvalidSubscriptionValues:
            pass
        try:
            yield txn.addAPNSubscription("", "1", "2", "3", "", "")
        except InvalidSubscriptionValues:
            pass

        token = "2d0d55cd7f98bcb81c6e24abcdc35168254c7846a43e2828b1ba5a8f82e219df"
        token2 = "3d0d55cd7f98bcb81c6e24abcdc35168254c7846a43e2828b1ba5a8f82e219df"
        key1 = "/CalDAV/calendars.example.com/user01/calendar/"
        timestamp1 = 1000
        uid = "D2256BCC-48E2-42D1-BD89-CBA1E4CCDFFB"
        userAgent = "test agent"
        ipAddr = "127.0.0.1"
        yield txn.addAPNSubscription(token, key1, timestamp1, uid, userAgent, ipAddr)
        yield txn.addAPNSubscription(token2, key1, timestamp1, uid, userAgent, ipAddr)

        key2 = "/CalDAV/calendars.example.com/user02/calendar/"
        timestamp2 = 3000
        yield txn.addAPNSubscription(token, key2, timestamp2, uid, userAgent, ipAddr)

        subscriptions = (yield txn.apnSubscriptionsBySubscriber(uid))
        self.assertTrue([token, key1, timestamp1, userAgent, ipAddr] in subscriptions)
        self.assertTrue([token, key2, timestamp2, userAgent, ipAddr] in subscriptions)
        self.assertTrue([token2, key1, timestamp1, userAgent, ipAddr] in subscriptions)

        # Verify an update to a subscription with a different uid takes on
        # the new uid
        timestamp3 = 5000
        uid2 = "D8FFB335-9D36-4CE8-A3B9-D1859E38C0DA"
        yield txn.addAPNSubscription(token, key2, timestamp3, uid2, userAgent, ipAddr)
        subscriptions = (yield txn.apnSubscriptionsBySubscriber(uid))
        self.assertTrue([token, key1, timestamp1, userAgent, ipAddr] in subscriptions)
        self.assertFalse([token, key2, timestamp3, userAgent, ipAddr] in subscriptions)
        subscriptions = (yield txn.apnSubscriptionsBySubscriber(uid2))
        self.assertTrue([token, key2, timestamp3, userAgent, ipAddr] in subscriptions)
        # Change it back
        yield txn.addAPNSubscription(token, key2, timestamp2, uid, userAgent, ipAddr)

        yield txn.commit()

        # Set up the service
        clock = Clock()
        service = (yield ApplePushNotifierService.makeService(settings,
            self.store, testConnectorClass=TestConnector, reactor=clock))
        self.assertEquals(set(service.providers.keys()), set(["CalDAV", "CardDAV"]))
        self.assertEquals(set(service.feedbacks.keys()), set(["CalDAV", "CardDAV"]))

        # First, enqueue a notification while we have no connection, in this
        # case by doing it prior to startService()

        # Notification arrives from calendar server
        dataChangedTimestamp = 1354815999
        txn = self.store.newTransaction()
        yield service.enqueue(txn, "/CalDAV/calendars.example.com/user01/calendar/",
            dataChangedTimestamp=dataChangedTimestamp)
        yield txn.commit()

        # The notifications should be in the queue
        self.assertTrue(((token, key1), dataChangedTimestamp) in service.providers["CalDAV"].queue)
        self.assertTrue(((token2, key1), dataChangedTimestamp) in service.providers["CalDAV"].queue)

        # Start the service, making the connection which should service the
        # queue
        service.startService()

        # The queue should be empty
        self.assertEquals(service.providers["CalDAV"].queue, [])

        # Verify data sent to APN
        providerConnector = service.providers["CalDAV"].testConnector
        rawData = providerConnector.transport.data
        self.assertEquals(len(rawData), 183)
        data = struct.unpack("!BIIH32sH", rawData[:45])
        self.assertEquals(data[0], 1) # command
        self.assertEquals(data[4].encode("hex"), token.replace(" ", "")) # token
        payloadLength = data[5]
        payload = struct.unpack("%ds" % (payloadLength,),
            rawData[45:])
        payload = json.loads(payload[0])
        self.assertEquals(payload["key"], u"/CalDAV/calendars.example.com/user01/calendar/")
        self.assertEquals(payload["dataChangedTimestamp"], dataChangedTimestamp)
        self.assertTrue("pushRequestSubmittedTimestamp" in payload)
        # Verify token history is updated
        self.assertTrue(token in [t for (_ignore_i, t) in providerConnector.service.protocol.history.history])
        self.assertTrue(token2 in [t for (_ignore_i, t) in providerConnector.service.protocol.history.history])

        #
        # Verify staggering behavior
        #

        # Reset sent data
        providerConnector.transport.data = None
        # Send notification while service is connected
        txn = self.store.newTransaction()
        yield service.enqueue(txn, "/CalDAV/calendars.example.com/user01/calendar/")
        yield txn.commit()
        clock.advance(1) # so that first push is sent
        self.assertEquals(len(providerConnector.transport.data), 183)
        # Reset sent data
        providerConnector.transport.data = None
        clock.advance(3) # so that second push is sent
        self.assertEquals(len(providerConnector.transport.data), 183)

        history = []

        def errorTestFunction(status, identifier):
            history.append((status, identifier))
            return succeed(None)

        # Simulate an error
        errorData = struct.pack("!BBI", APNProviderProtocol.COMMAND_ERROR, 1, 2)
        yield providerConnector.receiveData(errorData, fn=errorTestFunction)
        clock.advance(301)

        # Simulate multiple errors and dataReceived called
        # with amounts of data not fitting message boundaries
        # Send 1st 4 bytes
        history = []
        errorData = struct.pack("!BBIBBI",
            APNProviderProtocol.COMMAND_ERROR, 3, 4,
            APNProviderProtocol.COMMAND_ERROR, 5, 6,
        )
        yield providerConnector.receiveData(errorData[:4], fn=errorTestFunction)
        # Send remaining bytes
        yield providerConnector.receiveData(errorData[4:], fn=errorTestFunction)
        self.assertEquals(history, [(3, 4), (5, 6)])
        # Buffer is empty
        self.assertEquals(len(providerConnector.service.protocol.buffer), 0)

        # Sending 7 bytes
        yield providerConnector.receiveData("!" * 7, fn=errorTestFunction)
        # Buffer has 1 byte remaining
        self.assertEquals(len(providerConnector.service.protocol.buffer), 1)

        # Prior to feedback, there are 2 subscriptions
        txn = self.store.newTransaction()
        subscriptions = (yield txn.apnSubscriptionsByToken(token))
        yield txn.commit()
        self.assertEquals(len(subscriptions), 2)

        # Simulate feedback with a single token
        feedbackConnector = service.feedbacks["CalDAV"].testConnector
        timestamp = 2000
        binaryToken = token.decode("hex")
        feedbackData = struct.pack("!IH32s", timestamp, len(binaryToken),
            binaryToken)
        yield feedbackConnector.receiveData(feedbackData)

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
        yield feedbackConnector.receiveData(feedbackData[:10], fn=feedbackTestFunction)
        # Send remaining bytes
        yield feedbackConnector.receiveData(feedbackData[10:], fn=feedbackTestFunction)
        self.assertEquals(history, [(timestamp, token), (timestamp, token)])
        # Buffer is empty
        self.assertEquals(len(feedbackConnector.service.protocol.buffer), 0)

        # Sending 39 bytes
        yield feedbackConnector.receiveData("!" * 39, fn=feedbackTestFunction)
        # Buffer has 1 byte remaining
        self.assertEquals(len(feedbackConnector.service.protocol.buffer), 1)

        # The second subscription should now be gone
        txn = self.store.newTransaction()
        subscriptions = (yield txn.apnSubscriptionsByToken(token))
        yield txn.commit()
        self.assertEquals(subscriptions,
            [["/CalDAV/calendars.example.com/user02/calendar/", 3000, "D2256BCC-48E2-42D1-BD89-CBA1E4CCDFFB"]]
        )

        # Verify processError removes associated subscriptions and history
        # First find the id corresponding to token2
        for (id, t) in providerConnector.service.protocol.history.history:
            if t == token2:
                break

        yield providerConnector.service.protocol.processError(8, id)
        # The token for this identifier is gone
        self.assertTrue((id, token2) not in providerConnector.service.protocol.history.history)

        # All subscriptions for this token should now be gone
        txn = self.store.newTransaction()
        subscriptions = (yield txn.apnSubscriptionsByToken(token2))
        yield txn.commit()
        self.assertEquals(subscriptions, [])

        #
        # Verify purgeOldAPNSubscriptions
        #

        # Create two subscriptions, one old and one new
        txn = self.store.newTransaction()
        now = int(time.time())
        yield txn.addAPNSubscription(token2, key1, now - 2 * 24 * 60 * 60, uid, userAgent, ipAddr) # old
        yield txn.addAPNSubscription(token2, key2, now, uid, userAgent, ipAddr) # recent
        yield txn.commit()

        # Purge old subscriptions
        txn = self.store.newTransaction()
        yield txn.purgeOldAPNSubscriptions(now - 60 * 60)
        yield txn.commit()

        # Check that only the recent subscription remains
        txn = self.store.newTransaction()
        subscriptions = (yield txn.apnSubscriptionsByToken(token2))
        yield txn.commit()
        self.assertEquals(len(subscriptions), 1)
        self.assertEquals(subscriptions[0][0], key2)

        service.stopService()


    def test_validToken(self):
        self.assertTrue(validToken("2d0d55cd7f98bcb81c6e24abcdc35168254c7846a43e2828b1ba5a8f82e219df"))
        self.assertFalse(validToken("d0d55cd7f98bcb81c6e24abcdc35168254c7846a43e2828b1ba5a8f82e219df"))
        self.assertFalse(validToken("foo"))
        self.assertFalse(validToken(""))


    def test_TokenHistory(self):
        history = TokenHistory(maxSize=5)

        # Ensure returned identifiers increment
        for id, token in enumerate(("one", "two", "three", "four", "five"),
            start=1):
            self.assertEquals(id, history.add(token))
        self.assertEquals(len(history.history), 5)

        # History size never exceeds maxSize
        id = history.add("six")
        self.assertEquals(id, 6)
        self.assertEquals(len(history.history), 5)
        self.assertEquals(
            history.history,
            [(2, "two"), (3, "three"), (4, "four"), (5, "five"), (6, "six")]
        )
        id = history.add("seven")
        self.assertEquals(id, 7)
        self.assertEquals(len(history.history), 5)
        self.assertEquals(
            history.history,
            [(3, "three"), (4, "four"), (5, "five"), (6, "six"), (7, "seven")]
        )

        # Look up non-existent identifier
        token = history.extractIdentifier(9999)
        self.assertEquals(token, None)
        self.assertEquals(
            history.history,
            [(3, "three"), (4, "four"), (5, "five"), (6, "six"), (7, "seven")]
        )

        # Look up oldest identifier in history
        token = history.extractIdentifier(3)
        self.assertEquals(token, "three")
        self.assertEquals(
            history.history,
            [(4, "four"), (5, "five"), (6, "six"), (7, "seven")]
        )

        # Look up latest identifier in history
        token = history.extractIdentifier(7)
        self.assertEquals(token, "seven")
        self.assertEquals(
            history.history,
            [(4, "four"), (5, "five"), (6, "six")]
        )

        # Look up an identifier in the middle
        token = history.extractIdentifier(5)
        self.assertEquals(token, "five")
        self.assertEquals(
            history.history,
            [(4, "four"), (6, "six")]
        )



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
