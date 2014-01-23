##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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


from twext.python.log import Logger
from txweb2 import responsecode, server, http
from txdav.xml import element as davxml
from txweb2.http import HTTPError, StatusResponse
from txweb2.resource import WrapperResource

from twisted.internet.defer import inlineCallbacks, returnValue, maybeDeferred

from twistedcaldav.config import config

__all__ = [
    "LinkResource",
]

# FIXME: copied from resource.py to avoid circular dependency
class CalDAVComplianceMixIn(object):
    def davComplianceClasses(self):
        return (
            tuple(super(CalDAVComplianceMixIn, self).davComplianceClasses())
            + config.CalDAVComplianceClasses
        )

"""
A resource that is a soft-link to another.
"""

class LinkResource(CalDAVComplianceMixIn, WrapperResource):
    """
    This is similar to a WrapperResource except that we locate our resource dynamically. We need to deal with the
    case of a missing underlying resource (broken link) as indicated by self._linkedResource being None.
    """
    log = Logger()

    def __init__(self, parent, link_url):
        self.parent = parent
        self.linkURL = link_url
        self.loopDetect = set()
        super(LinkResource, self).__init__(self.parent.principalCollections())


    @inlineCallbacks
    def linkedResource(self, request):

        if not hasattr(self, "_linkedResource"):
            if self.linkURL in self.loopDetect:
                raise HTTPError(StatusResponse(responsecode.LOOP_DETECTED, "Recursive link target: %s" % (self.linkURL,)))
            else:
                self.loopDetect.add(self.linkURL)
            self._linkedResource = (yield request.locateResource(self.linkURL))
            self.loopDetect.remove(self.linkURL)

        if self._linkedResource is None:
            raise HTTPError(StatusResponse(responsecode.NOT_FOUND, "Missing link target: %s" % (self.linkURL,)))

        returnValue(self._linkedResource)


    def isCollection(self):
        return True if hasattr(self, "_linkedResource") else False


    def resourceType(self):
        return self._linkedResource.resourceType() if hasattr(self, "_linkedResource") else davxml.ResourceType.link


    def locateChild(self, request, segments):

        def _defer(result):
            if result is None:
                return (self, server.StopTraversal)
            else:
                return (result, segments)
        d = self.linkedResource(request)
        d.addCallback(_defer)
        return d


    @inlineCallbacks
    def renderHTTP(self, request):
        linked_to = (yield self.linkedResource(request))
        if linked_to:
            returnValue(linked_to)
        else:
            returnValue(http.StatusResponse(responsecode.OK, "Link resource with missing target: %s" % (self.linkURL,)))


    def getChild(self, name):
        return self._linkedResource.getChild(name) if hasattr(self, "_linkedResource") else None


    @inlineCallbacks
    def hasProperty(self, property, request):
        hosted = (yield self.linkedResource(request))
        result = (yield hosted.hasProperty(property, request)) if hosted else False
        returnValue(result)


    @inlineCallbacks
    def readProperty(self, property, request):
        hosted = (yield self.linkedResource(request))
        result = (yield hosted.readProperty(property, request)) if hosted else None
        returnValue(result)


    @inlineCallbacks
    def writeProperty(self, property, request):
        hosted = (yield self.linkedResource(request))
        result = (yield hosted.writeProperty(property, request)) if hosted else None
        returnValue(result)



class LinkFollowerMixIn(object):

    @inlineCallbacks
    def locateChild(self, req, segments):

        self._inside_locateChild = True
        resource, path = (yield maybeDeferred(super(LinkFollowerMixIn, self).locateChild, req, segments))
        while isinstance(resource, LinkResource):
            linked_to = (yield resource.linkedResource(req))
            if linked_to is None:
                break
            resource = linked_to

        returnValue((resource, path))
