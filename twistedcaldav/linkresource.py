##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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

from twext.python.log import LoggingMixIn

from twisted.internet.defer import inlineCallbacks, returnValue, maybeDeferred

from twext.web2.http import HTTPError
from twext.web2 import responsecode
from twext.web2.resource import WrapperResource
from twistedcaldav.config import config
from twext.web2.dav import davxml

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

class LinkResource(CalDAVComplianceMixIn, WrapperResource, LoggingMixIn):
    """
    This is similar to a WrapperResource except that we locate our resource dynamically. 
    """
    
    def __init__(self, parent, link_url):
        self.parent = parent
        self.linkURL = link_url
        super(LinkResource, self).__init__(self.parent.principalCollections())

    @inlineCallbacks
    def linkedResource(self, request):
        
        if not hasattr(self, "_linkedResource"):
            self._linkedResource = (yield request.locateResource(self.linkURL))

        if self._linkedResource is None:
            raise HTTPError(responsecode.NOT_FOUND)
            
        returnValue(self._linkedResource)

    def isCollection(self):
        return True

    def resourceType(self):
        return self._linkedResource.resourceType() if hasattr(self, "_linkedResource") else davxml.ResourceType.link
        
    def locateChild(self, request, segments):
        
        def _defer(result):
            return (result, segments)
        d = self.linkedResource(request)
        d.addCallback(_defer)
        return d

    def renderHTTP(self, request):
        return self.linkedResource(request)

    def getChild(self, name):
        return self._linkedResource.getChild(name)

    @inlineCallbacks
    def hasProperty(self, property, request):
        hosted = (yield self.linkedResource(request))
        result = (yield hosted.hasProperty(property, request))
        returnValue(result)

    @inlineCallbacks
    def readProperty(self, property, request):
        hosted = (yield self.linkedResource(request))
        result = (yield hosted.readProperty(property, request))
        returnValue(result)

    @inlineCallbacks
    def writeProperty(self, property, request):
        hosted = (yield self.linkedResource(request))
        result = (yield hosted.writeProperty(property, request))
        returnValue(result)

class LinkFollowerMixIn(object):

    @inlineCallbacks
    def locateChild(self, req, segments):

        resource, path = (yield maybeDeferred(super(LinkFollowerMixIn, self).locateChild, req, segments))
        MAX_LINK_DEPTH = 10
        ctr = 0
        seenResource = set()
        while isinstance(resource, LinkResource):
            seenResource.add(resource)
            ctr += 1
            resource = (yield resource.linkedResource(req))
            
            if ctr > MAX_LINK_DEPTH or resource in seenResource:
                raise HTTPError(responsecode.LOOP_DETECTED)
        
        returnValue((resource, path))
        
