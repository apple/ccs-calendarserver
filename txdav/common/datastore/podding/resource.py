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

import json

from twext.web2 import responsecode
from twext.web2.dav.noneprops import NonePropertyStore
from twext.web2.dav.util import allDataFromStream
from twext.web2.http import Response, HTTPError, StatusResponse, JSONResponse
from twext.web2.http_headers import MimeType

from twisted.internet.defer import succeed, returnValue, inlineCallbacks

from twistedcaldav.extensions import DAVResource, \
    DAVResourceWithoutChildrenMixin
from twistedcaldav.resource import ReadOnlyNoCopyResourceMixIn
from twistedcaldav.scheduling_store.caldav.resource import \
    deliverSchedulePrivilegeSet

from txdav.xml import element as davxml
from txdav.caldav.datastore.scheduling.ischedule.localservers import Servers

__all__ = [
    "ConduitResource",
]

class ConduitResource(ReadOnlyNoCopyResourceMixIn, DAVResourceWithoutChildrenMixin, DAVResource):
    """
    Podding cross-pod RPC conduit resource.

    Extends L{DAVResource} to provide cross-pod RPC functionality.
    """

    def __init__(self, parent, store):
        """
        @param parent: the parent resource of this one.
        """
        assert parent is not None

        DAVResource.__init__(self, principalCollections=parent.principalCollections())

        self.parent = parent
        self.store = store


    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties


    def etag(self):
        return succeed(None)


    def checkPreconditions(self, request):
        return None


    def resourceType(self):
        return davxml.ResourceType.ischeduleinbox


    def contentType(self):
        return MimeType.fromString("text/html; charset=utf-8")


    def isCollection(self):
        return False


    def isCalendarCollection(self):
        return False


    def isPseudoCalendarCollection(self):
        return False


    def principalForCalendarUserAddress(self, address):
        for principalCollection in self.principalCollections():
            principal = principalCollection.principalForCalendarUserAddress(address)
            if principal is not None:
                return principal
        return None


    def render(self, request):
        output = """<html>
<head>
<title>Podding Conduit Resource</title>
</head>
<body>
<h1>Podding Conduit Resource.</h1>
</body
</html>"""

        response = Response(200, {}, output)
        response.headers.setHeader("content-type", MimeType("text", "html"))
        return response


    @inlineCallbacks
    def http_POST(self, request):
        """
        The server-to-server POST method.
        """

        # Check shared secret
        if not Servers.getThisServer().checkSharedSecret(request.headers):
            self.log.error("Invalid shared secret header in cross-pod request")
            raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Not authorized to make this request"))

        # Check content first
        contentType = request.headers.getHeader("content-type")

        if "{}/{}".format(contentType.mediaType, contentType.mediaSubtype) != "application/json":
            self.log.error("MIME type {mime} not allowed in request", mime=contentType)
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "MIME type {} not allowed in request".format(contentType)))

        body = (yield allDataFromStream(request.stream))
        try:
            j = json.loads(body)
        except ValueError as e:
            self.log.error("Invalid JSON data in request: {ex}\n{body}", ex=e, body=body)
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "Invalid JSON data in request: {}\n{}".format(e, body)))

        # Must have a dict with an "action" key
        try:
            action = j["action"]
        except (KeyError, TypeError) as e:
            self.log.error("JSON data must have an object as its root with an 'action' attribute: {ex}\n{json}", ex=e, json=j)
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "JSON data must have an object as its root with an 'action' attribute: {}\n{}".format(e, j,)))

        if action == "ping":
            result = {"result": "ok"}
            response = JSONResponse(responsecode.OK, result)
            returnValue(response)

        method = "recv_{}".format(action)
        if not hasattr(self.store.conduit, method):
            self.log.error("Unsupported action: {action}", action=action)
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "Unsupported action: {}".format(action)))

        # Need a transaction to work with
        txn = self.store.newTransaction(repr(request))

        # Do the POST processing treating this as a non-local schedule
        try:
            result = (yield getattr(self.store.conduit, method)(txn, j))
        except Exception as e:
            yield txn.abort()
            self.log.error("Failed action: {action}, {ex}", action=action, ex=e)
            raise HTTPError(StatusResponse(responsecode.INTERNAL_SERVER_ERROR, "Failed action: {}, {}".format(action, e)))

        yield txn.commit()

        response = JSONResponse(responsecode.OK, result)
        returnValue(response)


    ##
    # ACL
    ##

    def supportedPrivileges(self, request):
        return succeed(deliverSchedulePrivilegeSet)


    def defaultAccessControlList(self):
        privs = (
            davxml.Privilege(davxml.Read()),
        )

        return davxml.ACL(
            # DAV:Read for all principals (includes anonymous)
            davxml.ACE(
                davxml.Principal(davxml.All()),
                davxml.Grant(*privs),
                davxml.Protected(),
            ),
        )
