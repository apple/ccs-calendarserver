##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
CalDAV X_APPLE_UNSUBSCRIBE method.
"""

__all__ = ["http_X_APPLE_UNSUBSCRIBE"]

from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.python import log
from twisted.web2 import responsecode
from twisted.web2.dav.element.base import twisted_dav_namespace
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav import customxml
from twistedcaldav.dropbox import DropBox

def http_X_APPLE_UNSUBSCRIBE(self, request):
    
    # Only for drop box collections
    if not DropBox.enabled or not self.isSpecialCollection(customxml.DropBox):
        log.err("Cannot x_apple_unsubscribe to resource %s" % (request.uri,))
        raise HTTPError(StatusResponse(
            responsecode.FORBIDDEN,
            "Cannot x_apple_unsubscribe to resource %s" % (request.uri,))
        )

    # We do not check any privileges. If a principal is subscribed we always allow them to
    # unsubscribe provided they have at least authenticated.
    d = waitForDeferred(self.authorize(request, ()))
    yield d
    d.getResult()
    authid = request.authnUser
    
    # Get current list of subscribed principals
    principals = []
    if self.hasDeadProperty(customxml.Subscribed):
        subs = self.readDeadProperty(customxml.Subscribed).children
        principals.extend(subs)
    
    # Error if attempt to subscribe more than once
    if authid not in principals:
        log.err("Cannot x_apple_unsubscribe from resource %s as principal %s is not currently subscribed" % (request.uri, repr(authid),))
        raise HTTPError(ErrorResponse(
            responsecode.FORBIDDEN,
            (twisted_dav_namespace, "principal-must-be-subscribed"))
        )

    principals.remove(authid)
    self.writeDeadProperty(customxml.Subscribed(*principals))

    yield responsecode.OK

http_X_APPLE_UNSUBSCRIBE = deferredGenerator(http_X_APPLE_UNSUBSCRIBE)
