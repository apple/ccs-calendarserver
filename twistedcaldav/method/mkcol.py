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
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
CalDAV MKCOL method.
"""

__all__ = ["http_MKCOL"]

from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.util import parentForURL
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav import customxml

def http_MKCOL(self, request):
    #
    # Don't allow DAV collections in a calendar collection for now
    #
    def isNonCollectionParentResource(resource):
        try:
            resource = ICalDAVResource(resource)
        except TypeError:
            return False
        else:
            return resource.isPseudoCalendarCollection() or resource.isSpecialCollection(customxml.DropBox)

    parent = waitForDeferred(self._checkParents(request, isNonCollectionParentResource))
    yield parent
    parent = parent.getResult()
    if parent is not None:
        raise HTTPError(StatusResponse(
            responsecode.FORBIDDEN,
            "Cannot create collection within special collection %s" % (parent,))
        )

    d = waitForDeferred(super(CalDAVFile, self).http_MKCOL(request))
    yield d
    result = d.getResult()
    
    # Check for drop box creation and give it a special resource type
    from twistedcaldav.dropbox import DropBox
    if result == responsecode.CREATED and DropBox.enabled:
        parent = waitForDeferred(request.locateResource(parentForURL(request.uri)))
        yield parent
        parent = parent.getResult()
        if parent.isSpecialCollection(customxml.DropBoxHome):
             self.writeDeadProperty(davxml.ResourceType.dropbox)
    
    yield result

http_MKCOL = deferredGenerator(http_MKCOL)