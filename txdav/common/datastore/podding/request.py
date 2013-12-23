##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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

from calendarserver.version import version

from twext.internet.gaiendpoint import GAIEndpoint
from twext.python.log import Logger
from twext.web2 import responsecode
from twext.web2.client.http import HTTPClientProtocol, ClientRequest
from twext.web2.dav.util import allDataFromStream
from twext.web2.http_headers import Headers, MimeType
from twext.web2.stream import MemoryStream

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.protocol import Factory

from twistedcaldav.accounting import accountingEnabledForCategory, \
    emitAccounting
from twistedcaldav.client.pool import _configuredClientContextFactory
from twistedcaldav.config import config
from twistedcaldav.util import utf8String

from cStringIO import StringIO
import base64
import json


log = Logger()



class ConduitRequest(object):
    """
    An HTTP request between pods. This is typically used to send and receive JSON data. However,
    for attachments, we need to send the actual attachment data as the request body, so in that
    case the JSON data is sent in an HTTP header.
    """

    def __init__(self, server, data, stream=None, stream_type=None):
        self.server = server
        self.data = json.dumps(data)
        self.stream = stream
        self.streamType = stream_type


    @inlineCallbacks
    def doRequest(self, txn):

        # Generate an HTTP client request
        try:
            if "xpod" not in txn.logItems:
                txn.logItems["xpod"] = 0
            txn.logItems["xpod"] += 1

            response = (yield self._processRequest())

            if accountingEnabledForCategory("xPod"):
                self.loggedResponse = yield self.logResponse(response)
                emitAccounting("xPod", "", self.loggedRequest + "\n" + self.loggedResponse, "POST")

            if response.code in (responsecode.OK,):
                data = (yield allDataFromStream(response.stream))
                data = json.loads(data)
            else:
                raise ValueError("Incorrect cross-pod response status code: {}".format(response.code))

        except Exception as e:
            # Request failed
            log.error("Could not do cross-pod request : {request} {ex}", request=self, ex=e)
            raise ValueError("Failed cross-pod request: {}".format(e))

        returnValue(data)


    @inlineCallbacks
    def logRequest(self, request):
        """
        Log an HTTP request.
        """

        iostr = StringIO()
        iostr.write(">>>> Request start\n\n")
        if hasattr(request, "clientproto"):
            protocol = "HTTP/{:d}.{:d}".format(request.clientproto[0], request.clientproto[1])
        else:
            protocol = "HTTP/1.1"
        iostr.write("{} {} {}\n".format(request.method, request.uri, protocol))
        for name, valuelist in request.headers.getAllRawHeaders():
            for value in valuelist:
                # Do not log authorization details
                if name not in ("Authorization",):
                    iostr.write("{}: {}\n".format(name, value))
                else:
                    iostr.write("{}: xxxxxxxxx\n".format(name))
        iostr.write("\n")

        # We need to play a trick with the request stream as we can only read it once. So we
        # read it, store the value in a MemoryStream, and replace the request's stream with that,
        # so the data can be read again. Note if we are sending an attachment, we won't log
        # the attachment data as we do not want to read it all into memory.
        if self.stream is None:
            data = (yield allDataFromStream(request.stream))
            iostr.write(data)
            request.stream = MemoryStream(data if data is not None else "")
            request.stream.doStartReading = None
        else:
            iostr.write("<<Stream Type: {}>>\n".format(self.streamType))

        iostr.write("\n\n>>>> Request end\n")
        returnValue(iostr.getvalue())


    @inlineCallbacks
    def logResponse(self, response):
        """
        Log an HTTP request.
        """
        iostr = StringIO()
        iostr.write(">>>> Response start\n\n")
        code_message = responsecode.RESPONSES.get(response.code, "Unknown Status")
        iostr.write("HTTP/1.1 {:d} {}\n".format(response.code, code_message))
        for name, valuelist in response.headers.getAllRawHeaders():
            for value in valuelist:
                # Do not log authorization details
                if name not in ("WWW-Authenticate",):
                    iostr.write("{}: {}\n".format(name, value))
                else:
                    iostr.write("{}: xxxxxxxxx\n".format(name))
        iostr.write("\n")

        # We need to play a trick with the response stream to ensure we don't mess it up. So we
        # read it, store the value in a MemoryStream, and replace the response's stream with that,
        # so the data can be read again.
        data = (yield allDataFromStream(response.stream))
        iostr.write(data)
        response.stream = MemoryStream(data if data is not None else "")
        response.stream.doStartReading = None

        iostr.write("\n\n>>>> Response end\n")
        returnValue(iostr.getvalue())


    @inlineCallbacks
    def _processRequest(self):
        """
        Process the request by sending it to the relevant server.

        @return: the HTTP response.
        @rtype: L{Response}
        """
        ssl, host, port, _ignore_path = self.server.details()
        path = "/" + config.Servers.ConduitName

        headers = Headers()
        headers.setHeader("Host", utf8String(host + ":{}".format(port)))
        if self.streamType:
            # For attachments we put the base64-encoded JSON data into a header
            headers.setHeader("Content-Type", self.streamType)
            headers.addRawHeader("XPOD", base64.b64encode(self.data))
        else:
            headers.setHeader("Content-Type", MimeType("application", "json", params={"charset": "utf-8", }))
        headers.setHeader("User-Agent", "CalendarServer/{}".format(version))
        headers.addRawHeader(*self.server.secretHeader())

        from twisted.internet import reactor
        f = Factory()
        f.protocol = HTTPClientProtocol
        ep = GAIEndpoint(reactor, host, port, _configuredClientContextFactory() if ssl else None)
        proto = (yield ep.connect(f))

        request = ClientRequest("POST", path, headers, self.stream if self.stream is not None else self.data)

        if accountingEnabledForCategory("xPod"):
            self.loggedRequest = yield self.logRequest(request)

        response = (yield proto.submitRequest(request))

        returnValue(response)
