##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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

"""
CalDAV DELETE method.
"""

__all__ = ["http_DELETE"]

from twext.python.log import Logger

from twisted.internet.defer import inlineCallbacks, returnValue
from twext.web2 import responsecode
from txdav.xml import element as davxml
from twext.web2.dav.util import parentForURL
from twext.web2.http import HTTPError

from twistedcaldav.method.delete_common import DeleteResource

log = Logger()

@inlineCallbacks
def http_DELETE(self, request):
    #
    # Override base DELETE request handling to ensure that the calendar
    # index file has the entry for the deleted calendar component removed.
    #

    raise AssertionError("Never use this")

    if not self.exists():
        log.err("Resource not found: %s" % (self,))
        raise HTTPError(responsecode.NOT_FOUND)

    depth = request.headers.getHeader("depth", "infinity")

    #
    # Check authentication and access controls
    #
    parentURL = parentForURL(request.uri)
    parent = (yield request.locateResource(parentURL))

    yield parent.authorize(request, (davxml.Unbind(),))

    # Do smart delete taking into account the need to do implicit CANCELs etc
    deleter = DeleteResource(request, self, request.uri, parent, depth)
    response = (yield deleter.run())

    returnValue(response)
