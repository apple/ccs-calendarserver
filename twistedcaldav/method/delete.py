##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
CalDAV DELETE method.
"""

__all__ = ["http_DELETE"]

import datetime

from twisted.web2 import responsecode
from twisted.web2.dav.util import parentForURL

from twistedcaldav import customxml
from twistedcaldav.resource import isPseudoCalendarCollectionResource

def http_DELETE(self, request):
    #
    # Override base DELETE request handling to ensure that the calendar
    # index file has the entry for the deleted calendar component removed.
    #
    def gotParent(parent):
        def gotResponse(response):
            if response == responsecode.NO_CONTENT:
                if isPseudoCalendarCollectionResource(parent):
                    index = parent.index()
                    index.deleteResource(self.fp.basename())
                    
                    # Change CTag on the parent calendar collection
                    parent.writeDeadProperty(customxml.GETCTag(str(datetime.datetime.now())))

            return response

        d = super(CalDAVFile, self).http_DELETE(request)
        d.addCallback(gotResponse)
        return d

    parentURL = parentForURL(request.uri)
    d = request.locateResource(parentURL)
    d.addCallback(gotParent)
    return d
