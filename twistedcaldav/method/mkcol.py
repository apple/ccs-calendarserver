##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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
CalDAV MKCOL method.
"""

__all__ = ["http_MKCOL"]

from twisted.web2 import responsecode
from twisted.web2.http import StatusResponse

from twistedcaldav.resource import isPseudoCalendarCollectionResource

def http_MKCOL(self, request):
    #
    # Don't allow DAV collections in a calendar collection
    #
    def gotParent(parent):
        if parent is not None:
            return StatusResponse(
                responsecode.FORBIDDEN,
                "Cannot create collection within calendar collection %s" % (parent,)
            )

        return super(CalDAVFile, self).http_MKCOL(request)

    d = self._checkParents(request, isPseudoCalendarCollectionResource)
    d.addCallback(gotParent)
    return d
