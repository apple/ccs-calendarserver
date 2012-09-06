##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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
    "SharedCollectionResource",
]

from twext.web2.http import HTTPError, StatusResponse
from twext.web2 import responsecode

from twisted.internet.defer import inlineCallbacks, returnValue

from twistedcaldav.linkresource import LinkResource


"""
Sharing behavior
"""

class SharedCollectionResource(LinkResource):
    """
    This is similar to a LinkResource except that we locate our shared collection resource dynamically.
    """
    
    def __init__(self, parent, share):
        self.share = share
        super(SharedCollectionResource, self).__init__(parent, self.share.hosturl)

    @inlineCallbacks
    def linkedResource(self, request):
        """
        Resolve the share host url to the underlying resource (set to be a virtual share).
        """
        
        if not hasattr(self, "_linkedResource"):
            self._linkedResource = (yield request.locateResource(self.share.hosturl))
            
            if self._linkedResource is not None:
                # FIXME: this is awkward - because we are "mutating" this object into a virtual share
                # we must not cache the resource at this URL, otherwise an access of the owner's resource
                # will return the same virtually shared one which would be wrong.
                request._forgetResource(self._linkedResource, self.share.hosturl)
    
                ownerPrincipal = (yield self.parent.ownerPrincipal(request))
                self._linkedResource.setVirtualShare(ownerPrincipal, self.share)
            else:
                raise HTTPError(StatusResponse(responsecode.NOT_FOUND, "Missing link target: %s" % (self.linkURL,)))

        returnValue(self._linkedResource)
