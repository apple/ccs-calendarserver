##
# Copyright (c) 2005-2011 Apple Inc. All rights reserved.
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

from twext.internet.ssl import ChainingOpenSSLContextFactory
from twext.python.log import Logger, LoggingMixIn
from twext.python.log import LoggingMixIn
from twext.web2 import responsecode
from twext.web2.http import Response
from twext.web2.http_headers import MimeType
from twext.web2.resource import Resource
from twext.web2.server import parsePOSTData
from twisted.application import service
from twisted.internet import reactor, protocol
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.protocol import ClientFactory, ReconnectingClientFactory
import OpenSSL
import struct
import time

"""
ApplePushNotifierService is a MultiService responsible for setting up the
APN provider and feedback connections.  Once connected, calling its enqueue( )
method sends notifications to any device token which is subscribed to the
enqueued key.

The Apple Push Notification protocol is described here:

http://developer.apple.com/library/ios/#documentation/NetworkingInternet/Conceptual/RemoteNotificationsPG/CommunicatingWIthAPS/CommunicatingWIthAPS.html
"""


log = Logger()


class ApplePushNotifierService(service.MultiService, LoggingMixIn):

    @classmethod
    def makeService(cls, settings, store, testConnectorClass=None,
        reactor=None):

        service = cls()

        service.store = store
        service.providers = {}
        service.feedbacks = {}
        service.dataHost = settings["DataHost"]

        for protocol in ("CalDAV", "CardDAV"):

            providerTestConnector = None
            feedbackTestConnector = None
            if testConnectorClass is not None:
                providerTestConnector = testConnectorClass()
                feedbackTestConnector = testConnectorClass()

            provider = APNProviderService(
                settings["ProviderHost"],
                settings["ProviderPort"],
                settings[protocol]["CertificatePath"],
                settings[protocol]["PrivateKeyPath"],
                testConnector=providerTestConnector,
                reactor=reactor,
            )
            provider.setServiceParent(service)
            service.providers[protocol] = provider
            service.log_info("APNS %s topic: %s" %
                (protocol, settings[protocol]["Topic"]))

            feedback = APNFeedbackService(
                service.store,
                settings["FeedbackUpdateSeconds"],
                settings["FeedbackHost"],
                settings["FeedbackPort"],
                settings[protocol]["CertificatePath"],
                settings[protocol]["PrivateKeyPath"],
                testConnector=feedbackTestConnector,
                reactor=reactor,
            )
            feedback.setServiceParent(service)
            service.feedbacks[protocol] = feedback

        return service


    @inlineCallbacks
    def enqueue(self, op, id):

        try:
            protocol, id = id.split("|", 1)
        except ValueError:
            # id has no protocol, so we can't do anything with it
            self.log_error("Notification id '%s' is missing protocol" % (id,))
            return

        provider = self.providers.get(protocol, None)
        if provider is not None:
            key = "/%s/%s/%s/" % (protocol, self.dataHost, id)

            # Look up subscriptions for this key
            txn = self.store.newTransaction()
            subscriptions = (yield txn.apnSubscriptionsByKey(key))
            yield txn.commit() # TODO: Glyph, needed?

            for token, guid in subscriptions:
                self.log_debug("Sending APNS: token='%s' key='%s' guid='%s'" %
                    (token, key, guid))
                provider.sendNotification(token, key)



class APNProviderProtocol(protocol.Protocol, LoggingMixIn):
    """
    Implements the Provider portion of APNS
    """

    # Sent by provider
    COMMAND_SIMPLE   = 0
    COMMAND_ENHANCED = 1

    # Received by provider
    COMMAND_ERROR    = 8

    # Returned only for an error.  Successful notifications get no response.
    STATUS_CODES = {
        0   : "No errors encountered",
        1   : "Processing error",
        2   : "Missing device token",
        3   : "Missing topic",
        4   : "Missing payload",
        5   : "Invalid token size",
        6   : "Invalid topic size",
        7   : "Invalid payload size",
        8   : "Invalid token",
        255 : "None (unknown)",
    }

    def makeConnection(self, transport):
        self.identifier = 0
        # self.log_debug("ProviderProtocol makeConnection")
        protocol.Protocol.makeConnection(self, transport)

    def connectionMade(self):
        self.log_debug("ProviderProtocol connectionMade")
        # TODO: glyph review
        # Store a reference to ourself on the factory so the service can
        # later call us
        self.factory.connection = self
        # self.sendNotification(TOKEN, "xyzzy")

    def connectionLost(self, reason=None):
        # self.log_debug("ProviderProtocol connectionLost: %s" % (reason,))
        # TODO: glyph review
        # Clear the reference to us from the factory
        self.factory.connection = None

    def dataReceived(self, data):
        self.log_debug("ProviderProtocol dataReceived %d bytes" % (len(data),))
        command, status, identifier = struct.unpack("!BBI", data)
        if command == self.COMMAND_ERROR:
            self.processError(status, identifier)

    def processError(self, status, identifier):
        msg = self.STATUS_CODES.get(status, "Unknown status code")
        self.log_debug("ProviderProtocol processError %d on identifier %d: %s" % (status, identifier, msg))
        # TODO: do we want to retry after certain errors?

    def sendNotification(self, token, node):
        try:
            binaryToken = token.replace(" ", "").decode("hex")
        except:
            self.log_error("Invalid APN token in database: %s" % (token,))
            return

        self.identifier += 1
        payload = '{"key" : "%s"}' % (node,)
        payloadLength = len(payload)
        self.log_debug("ProviderProtocol sendNotification identifier=%d payload=%s" % (self.identifier, payload))

        self.transport.write(
            struct.pack("!BIIH32sH%ds" % (payloadLength,),
                self.COMMAND_ENHANCED,  # Command
                self.identifier,        # Identifier
                0,                      # Expiry
                32,                     # Token Length
                binaryToken,            # Token
                payloadLength,          # Payload Length
                payload,                # Payload in JSON format
            )
        )


class APNProviderFactory(ReconnectingClientFactory, LoggingMixIn):

    protocol = APNProviderProtocol

    def buildProtocol(self, addr):
        p = self.protocol()
        # TODO: glyph review
        # Give protocol a back-reference to factory so it can set/clear
        # the "connection" reference on the factory
        p.factory = self
        return p

    def clientConnectionLost(self, connector, reason):
        # self.log_info("Connection to APN server lost: %s" % (reason,))
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        self.log_error("Unable to connect to APN server: %s" % (reason,))
        self.connected = False
        ReconnectingClientFactory.clientConnectionFailed(self, connector,
            reason)


class APNConnectionService(service.Service, LoggingMixIn):

    def __init__(self, host, port, certPath, keyPath, chainPath="",
        sslMethod="TLSv1_METHOD", testConnector=None, reactor=None):

        self.host = host
        self.port = port
        self.certPath = certPath
        self.keyPath = keyPath
        self.chainPath = chainPath
        self.sslMethod = sslMethod
        self.testConnector = testConnector

        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor

    def connect(self, factory):
        if self.testConnector is not None:
            # For testing purposes
            self.testConnector.connect(self, factory)
        else:
            context = ChainingOpenSSLContextFactory(
                self.keyPath,
                self.certPath,
                certificateChainFile=self.chainPath,
                sslmethod=getattr(OpenSSL.SSL, self.sslMethod)
            )
            reactor.connectSSL(self.host, self.port, factory, context)


class APNProviderService(APNConnectionService):

    def __init__(self, host, port, certPath, keyPath, chainPath="",
        sslMethod="TLSv1_METHOD", testConnector=None, reactor=None):

        APNConnectionService.__init__(self, host, port, certPath, keyPath,
            chainPath="", sslMethod=sslMethod,
            testConnector=testConnector, reactor=reactor)

    def startService(self):
        self.log_debug("APNProviderService startService")
        self.factory = APNProviderFactory()
        self.connect(self.factory)

    def stopService(self):
        self.log_debug("APNProviderService stopService")

    def sendNotification(self, token, key):
        # TODO: glyph review
        # Service has reference to factory has reference to protocol instance
        connection = getattr(self.factory, "connection", None)
        if connection is None:
            self.log_debug("APNProviderService sendNotification has no connection")
        else:
            self.log_debug("APNProviderService sendNotification: %s %s" %
                (token, key))
            connection.sendNotification(token, key)


class APNFeedbackProtocol(protocol.Protocol, LoggingMixIn):
    """
    Implements the Feedback portion of APNS
    """

    def connectionMade(self):
        self.log_debug("FeedbackProtocol connectionMade")

    def dataReceived(self, data):
        self.log_debug("FeedbackProtocol dataReceived %d bytes" % (len(data),))
        timestamp, tokenLength, binaryToken = struct.unpack("!IH32s", data)
        token = binaryToken.encode("hex")
        self.processFeedback(timestamp, token)

    @inlineCallbacks
    def processFeedback(self, timestamp, token):
        self.log_debug("FeedbackProtocol processFeedback time=%d token=%s" %
            (timestamp, token))
        txn = self.store.newTransaction()
        subscriptions = (yield txn.apnSubscriptionsByToken(token))

        for key, modified, guid in subscriptions:
            if timestamp > modified:
                self.log_debug("FeedbackProtocol removing subscription: %s %s" %
                    (token, key))
                yield txn.removeAPNSubscription(token, key)
        yield txn.commit()


class APNFeedbackFactory(ClientFactory, LoggingMixIn):

    protocol = APNFeedbackProtocol

    def __init__(self, store):
        self.store = store

    def buildProtocol(self, addr):
        p = self.protocol()
        # TODO: glyph review
        # Give protocol a back-reference to factory so it can set/clear
        # the "connection" reference on the factory
        p.factory = self
        p.store = self.store
        return p

    def clientConnectionFailed(self, connector, reason):
        self.log_error("Unable to connect to APN feedback server: %s" %
            (reason,))
        self.connected = False
        ClientFactory.clientConnectionFailed(self, connector, reason)


class APNFeedbackService(APNConnectionService):

    def __init__(self, store, updateSeconds, host, port, certPath, keyPath,
        chainPath="", sslMethod="TLSv1_METHOD", testConnector=None,
        reactor=None):

        APNConnectionService.__init__(self, host, port, certPath, keyPath,
            chainPath="", sslMethod=sslMethod,
            testConnector=testConnector, reactor=reactor)

        self.store = store
        self.updateSeconds = updateSeconds

    def startService(self):
        self.log_debug("APNFeedbackService startService")
        self.factory = APNFeedbackFactory(self.store)
        self.checkForFeedback()

    def stopService(self):
        self.log_debug("APNFeedbackService stopService")
        if self.nextCheck is not None:
            self.nextCheck.cancel()

    def checkForFeedback(self):
        self.nextCheck = None
        self.log_debug("APNFeedbackService checkForFeedback")
        self.connect(self.factory)
        self.nextCheck = self.reactor.callLater(self.updateSeconds,
            self.checkForFeedback)

class APNSubscriptionResource(Resource):

    # method can be GET or POST
    # params are "token" (device token) and "key" (push key), e.g.:
    # token=2d0d55cd7f98bcb81c6e24abcdc35168254c7846a43e2828b1ba5a8f82e219df
    # key=/CalDAV/calendar.example.com/E0B38B00-4166-11DD-B22C-A07C87F02F6A/

    def __init__(self, store):
        self.store = store
        # TODO: add authentication

    def http_GET(self, request):
        return self.processSubscription(None, request.args)

    def http_POST(self, request):
        return parsePOSTData(request).addCallback(
            self.processSubscription, request.args)

    @inlineCallbacks
    def processSubscription(self, ignored, args):
        token = args.get("token", None)
        key = args.get("key", None)
        if key and token:
            key = key[0]
            token = token[0].replace(" ", "")
            yield self.addSubscription(token, key)
            code = responsecode.OK
            msg = None
        else:
            code = responsecode.BAD_REQUEST
            msg = "Invalid request: both 'token' and 'key' must be provided"

        returnValue(self.renderResponse(code, body=msg))

    @inlineCallbacks
    def addSubscription(self, token, key):
        now = int(time.time()) # epoch seconds
        txn = self.store.newTransaction()
        # TODO: use actual guid
        yield txn.addAPNSubscription(token, key, now, "xyzzy")
        # subscriptions = (yield txn.apnSubscriptionsByToken(token))
        # print subscriptions
        yield txn.commit()

    def renderResponse(self, code, body=None):
        response = Response(code, {}, body)
        response.headers.setHeader("content-type", MimeType("text", "html"))
        return response
