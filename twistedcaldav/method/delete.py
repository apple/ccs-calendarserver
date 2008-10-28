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
##

"""
CalDAV DELETE method.
"""

__all__ = ["http_DELETE"]

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web2 import responsecode
from twisted.web2.dav.util import parentForURL
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav.memcachelock import MemcacheLock, MemcacheLockTimeoutError
from twistedcaldav.resource import isCalendarCollectionResource
from twistedcaldav.scheduling.implicit import ImplicitScheduler

@inlineCallbacks
def http_DELETE(self, request):
    #
    # Override base DELETE request handling to ensure that the calendar
    # index file has the entry for the deleted calendar component removed.
    #

    # TODO: need to use transaction based delete on live scheduling object resources
    # as the iTIP operation may fail and may need to prevent the delete from happening.

    parentURL = parentForURL(request.uri)
    parent = (yield request.locateResource(parentURL))

    calendar = None
    isCalendarCollection = False
    isCalendarResource = False
    lock = None

    if self.exists():
        if isCalendarCollectionResource(parent):
            isCalendarResource = True
            calendar = self.iCalendar()
            lock = MemcacheLock("ImplicitUIDLock", calendar.resourceUID(), timeout=60.0)
            
        elif isCalendarCollectionResource(self):
            isCalendarCollection = True

    try:
        if lock:
            yield lock.acquire()

        response = (yield super(CalDAVFile, self).http_DELETE(request))
    
        if response == responsecode.NO_CONTENT:
            if isCalendarResource:
    
                index = parent.index()
                index.deleteResource(self.fp.basename())
    
                # Change CTag on the parent calendar collection
                yield parent.updateCTag()
    
                # Do scheduling
                scheduler = ImplicitScheduler()
                yield scheduler.doImplicitScheduling(request, self, calendar, True)
     
            elif isCalendarCollection:
                
                # Do some clean up
                yield self.deletedCalendar(request)
                
        if lock:
            yield lock.release()

    except MemcacheLockTimeoutError:
        raise HTTPError(StatusResponse(responsecode.CONFLICT, "Resource: %s currently in use on the server." % (self.uri,)))

    except Exception, e:
        if lock:
            yield lock.clean()
        raise e

    returnValue(response)
