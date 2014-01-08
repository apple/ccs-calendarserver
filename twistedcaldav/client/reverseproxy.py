##
# Copyright (c) 2009-2014 Apple Inc. All rights reserved.
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

__all__ = [
    "ReverseProxyResource",
]

from zope.interface.declarations import implements

from twext.web2 import iweb, responsecode
from twext.web2.client.http import ClientRequest
from twext.web2.http import StatusResponse, HTTPError
from twext.web2.resource import LeafResource

from twext.python.log import Logger

from twistedcaldav.client.pool import getHTTPClientPool
from twistedcaldav.config import config

class ReverseProxyResource(LeafResource):
    """
    A L{LeafResource} which always performs a reverse proxy operation.
    """
    log = Logger()

    implements(iweb.IResource)

    def __init__(self, poolID, *args, **kwargs):
        """

        @param poolID: idenitifier of the pool to use
        @type poolID: C{str}
        """

        self.poolID = poolID
        self._args = args
        self._kwargs = kwargs
        self.allowMultiHop = False


    def isCollection(self):
        return True


    def exists(self):
        return False


    def renderHTTP(self, request):
        """
        Do the reverse proxy request and return the response.

        @param request: the incoming request that needs to be proxied.
        @type request: L{Request}

        @return: Deferred L{Response}
        """

        self.log.info("%s %s %s" % (request.method, request.uri, "HTTP/%s.%s" % request.clientproto))

        # Check for multi-hop
        if not self.allowMultiHop:
            x_server = request.headers.getHeader("x-forwarded-server")
            if x_server:
                for item in x_server:
                    if item.lower() == config.ServerHostName.lower():
                        raise HTTPError(StatusResponse(responsecode.BAD_GATEWAY, "Too many x-forwarded-server hops"))

        clientPool = getHTTPClientPool(self.poolID)
        proxyRequest = ClientRequest(request.method, request.uri, request.headers, request.stream)

        # Need x-forwarded-(for|host|server) headers. First strip any existing ones out, then add ours
        proxyRequest.headers.removeHeader("x-forwarded-host")
        proxyRequest.headers.removeHeader("x-forwarded-for")
        proxyRequest.headers.removeHeader("x-forwarded-server")
        proxyRequest.headers.addRawHeader("x-forwarded-host", request.host)
        proxyRequest.headers.addRawHeader("x-forwarded-for", request.remoteAddr.host)
        proxyRequest.headers.addRawHeader("x-forwarded-server", config.ServerHostName)

        return clientPool.submitRequest(proxyRequest)
