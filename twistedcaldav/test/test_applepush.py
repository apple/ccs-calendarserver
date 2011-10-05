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
    ApplePushNotifierService, APNProviderService
)
from twistedcaldav.test.util import TestCase
from twisted.internet.defer import inlineCallbacks
import struct

class ApplePushNotifierServiceTests(TestCase):

    @inlineCallbacks
    def test_makeService(self):

        settings = {
            "Service" : "twistedcaldav.applepush.ApplePushNotifierService",
            "Enabled" : True,
            "SubscriptionURL" : "apn",
            "DataHost" : "calendars.example.com",
            "ProviderHost" : "gateway.push.apple.com",
            "ProviderPort" : 2195,
            "FeedbackHost" : "feedback.push.apple.com",
            "FeedbackPort" : 2196,
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
        service = (yield ApplePushNotifierService.makeService(settings, None))
        self.assertEquals(set(service.providers.keys()), set(["CalDAV","CardDAV"]))
        self.assertEquals(set(service.feedbacks.keys()), set(["CalDAV","CardDAV"]))


    def test_provider(self):
        """
        Sending a notification writes to the transport
        """
        testConnector = TestConnector()
        service = APNProviderService("example.com", 1234, "caldav.cer",
            "caldav.pem", testConnector=testConnector)
        service.startService()

        token = "b23b2d34 096f7f3c 7989970c 2d7a074f 50ebebfd 8702ed98 3657ada4 39432e23"
        key = "/CalDAV/user01/calendar"
        service.sendNotification(token, key)

        # Verify data sent
        self.assertEquals(len(testConnector.transport.data), 80)
        data = struct.unpack("!BIIH32sH", testConnector.getData()[:45])
        self.assertEquals(data[0], 1) # command
        self.assertEquals(data[4].encode("hex"), token.replace(" ", "")) # token
        payloadLength = data[5]
        payload = struct.unpack("%ds" % (payloadLength,),
            testConnector.getData()[45:])
        self.assertEquals(payload[0], '{"key" : "%s"}' % (key,))


class TestConnector(object):

    def connect(self, service, factory):
        service.protocol = factory.buildProtocol(None)
        service.connected = 1
        self.transport = StubTransport()
        service.protocol.makeConnection(self.transport)

    def getData(self):
        return self.transport.data


class StubTransport(object):

    def __init__(self):
        self.data = None

    def write(self, data):
        self.data = data
