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

from twisted.internet.defer import inlineCallbacks, returnValue

from twistedcaldav.extensions import DAVResource
from twistedcaldav.resource import CalDAVComplianceMixIn
from twistedcaldav.sharing import SharedCollectionMixin

__all__ = [
    "SharedCalendarResource",
]

"""
Sharing behavior
"""

class SharedCalendarResource(CalDAVComplianceMixIn, SharedCollectionMixin, DAVResource, LoggingMixIn):
    """
    This is similar to a WrapperResource except that we locate our shared calendar resource dynamically. 
    """
    
    def __init__(self, parent, share):
        self.parent = parent
        self.share = share
        super(SharedCalendarResource, self).__init__(self.parent.principalCollections())

    @inlineCallbacks
    def hostedResource(self, request):
        
        if not hasattr(self, "_hostedResource"):
            self._hostedResource = (yield request.locateResource(self.share.hosturl))
            ownerPrincipal = (yield self.parent.ownerPrincipal(request))
            self._hostedResource.setVirtualShare(ownerPrincipal, self.share)
        returnValue(self._hostedResource)

    def isCollection(self):
        return True

    def locateChild(self, request, segments):
        
        def _defer(result):
            return (result, segments)
        d = self.hostedResource(request)
        d.addCallback(_defer)
        return d

    def renderHTTP(self, request):
        return self.hostedResource(request)

    def getChild(self, name):
        return self._hostedResource.getChild(name)

    @inlineCallbacks
    def hasProperty(self, property, request):
        hosted = (yield self.hostedResource(request))
        result = (yield hosted.hasProperty(property, request))
        returnValue(result)

    @inlineCallbacks
    def readProperty(self, property, request):
        hosted = (yield self.hostedResource(request))
        result = (yield hosted.readProperty(property, request))
        returnValue(result)

    @inlineCallbacks
    def writeProperty(self, property, request):
        hosted = (yield self.hostedResource(request))
        result = (yield hosted.writeProperty(property, request))
        returnValue(result)
