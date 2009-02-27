##
# Copyright (c) 2006-2009 Apple Inc. All rights reserved.
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
CalDAV DELETE behaviors.
"""

__all__ = ["DeleteResource"]

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web2 import responsecode
from twisted.web2.dav.fileop import delete
from twisted.web2.dav.http import ResponseQueue, MultiStatusResponse,\
    ErrorResponse
from twisted.web2.dav.util import joinURL
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.log import Logger
from twistedcaldav.memcachelock import MemcacheLock, MemcacheLockTimeoutError
from twistedcaldav.method.report_common import applyToCalendarCollections
from twistedcaldav.resource import isCalendarCollectionResource,\
    isPseudoCalendarCollectionResource
from twistedcaldav.scheduling.implicit import ImplicitScheduler

log = Logger()

class DeleteResource(object):
    
    def __init__(self, request, resource, resource_uri, parent, depth, internal_request=False):
        
        self.request = request
        self.resource = resource
        self.resource_uri = resource_uri
        self.parent = parent
        self.depth = depth
        self.internal_request = internal_request

    @inlineCallbacks
    def deleteResource(self, delresource, deluri, parent):
        """
        Delete a plain resource which may be a collection - but only one not containing
        calendar resources.

        @param delresource:
        @type delresource:
        @param deluri:
        @type deluri:
        @param parent:
        @type parent:
        """

        # Do quota checks before we start deleting things
        myquota = (yield delresource.quota(self.request))
        if myquota is not None:
            old_size = (yield delresource.quotaSize(self.request))
        else:
            old_size = 0
        
        # Do delete
        response = (yield delete(deluri, delresource.fp, self.depth))

        # Adjust quota
        if myquota is not None:
            yield delresource.quotaSizeAdjust(self.request, -old_size)

        if response == responsecode.NO_CONTENT:
            if isPseudoCalendarCollectionResource(parent):
                index = parent.index()
                index.deleteResource(delresource.fp.basename())

                # Change CTag on the parent calendar collection
                yield parent.updateCTag()
                
        returnValue(response)

    @inlineCallbacks
    def deleteCalendarResource(self, delresource, deluri, parent):
        """
        Delete a single calendar resource and do implicit scheduling actions if required.

        @param delresource:
        @type delresource:
        @param deluri:
        @type deluri:
        @param parent:
        @type parent:
        """

        # TODO: need to use transaction based delete on live scheduling object resources
        # as the iTIP operation may fail and may need to prevent the delete from happening.
    
        # Do quota checks before we start deleting things
        myquota = (yield delresource.quota(self.request))
        if myquota is not None:
            old_size = (yield delresource.quotaSize(self.request))
        else:
            old_size = 0
        
        scheduler = None
        lock = None
        if not self.internal_request:
            # Get data we need for implicit scheduling
            calendar = delresource.iCalendar()
            scheduler = ImplicitScheduler()
            do_implicit_action, _ignore = (yield scheduler.testImplicitSchedulingDELETE(self.request, delresource, calendar))
            if do_implicit_action:
                lock = MemcacheLock("ImplicitUIDLock", calendar.resourceUID(), timeout=60.0)

        try:
            if lock:
                yield lock.acquire()
    
            # Do delete
            response = (yield delete(deluri, delresource.fp, self.depth))

            # Adjust quota
            if myquota is not None:
                yield delresource.quotaSizeAdjust(self.request, -old_size)
    
            if response == responsecode.NO_CONTENT:
                index = parent.index()
                index.deleteResource(delresource.fp.basename())
    
                # Change CTag on the parent calendar collection
                yield parent.updateCTag()
    
                # Do scheduling
                if scheduler:
                    yield scheduler.doImplicitScheduling()
    
        except MemcacheLockTimeoutError:
            raise HTTPError(StatusResponse(responsecode.CONFLICT, "Resource: %s currently in use on the server." % (deluri,)))
    
        finally:
            if lock:
                yield lock.clean()
                
        returnValue(response)

    @inlineCallbacks
    def deleteCalendar(self, delresource, deluri, parent):
        """
        Delete an entire calendar collection by deleting each child resource in turn to
        ensure that proper implicit scheduling actions occur.
        
        This has to emulate the behavior in fileop.delete in that any errors need to be
        reported back in a multistatus response.
        """

        # Not allowed to delete the default calendar
        default = (yield delresource.isDefaultCalendar(self.request))
        if default:
            log.err("Cannot DELETE default calendar: %s" % (delresource,))
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "default-calendar-delete-allowed",)))

        if self.depth != "infinity":
            msg = "Client sent illegal depth header value for DELETE: %s" % (self.depth,)
            log.err(msg)
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))

        log.debug("Deleting calendar %s" % (delresource.fp.path,))

        errors = ResponseQueue(deluri, "DELETE", responsecode.NO_CONTENT)

        for childname in delresource.listChildren():

            childurl = joinURL(deluri, childname)
            child = (yield self.request.locateChildResource(delresource, childname))

            try:
                yield self.deleteCalendarResource(child, childurl, delresource)
            except:
                errors.add(childurl, responsecode.BAD_REQUEST)

        # Now do normal delete
        more_responses = (yield self.deleteResource(delresource, deluri, parent))
        
        if isinstance(more_responses, MultiStatusResponse):
            # Merge errors
            errors.responses.update(more_responses.children)                

        response = errors.response()
        
        if response == responsecode.NO_CONTENT:
            # Do some clean up
            yield delresource.deletedCalendar(self.request)

        returnValue(response)

    @inlineCallbacks
    def deleteCollection(self):
        """
        Delete a regular collection with special processing for any calendar collections
        contained within it.
        """
        if self.depth != "infinity":
            msg = "Client sent illegal depth header value for DELETE: %s" % (self.depth,)
            log.err(msg)
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))

        log.debug("Deleting collection %s" % (self.resource.fp.path,))

        errors = ResponseQueue(self.resource_uri, "DELETE", responsecode.NO_CONTENT)
 
        @inlineCallbacks
        def doDeleteCalendar(delresource, deluri):
            
            delparent = (yield delresource.locateParent(self.request, deluri))

            response = (yield self.deleteCalendar(delresource, deluri, delparent))

            if isinstance(response, MultiStatusResponse):
                # Merge errors
                errors.responses.update(response.children)                

            returnValue(True)

        yield applyToCalendarCollections(self.resource, self.request, self.resource_uri, self.depth, doDeleteCalendar, None)

        # Now do normal delete
        more_responses = (yield self.deleteResource(self.resource, self.resource_uri, self.parent))
        
        if isinstance(more_responses, MultiStatusResponse):
            # Merge errors
            errors.responses.update(more_responses.children)                

        response = errors.response()

        returnValue(response)
        
    @inlineCallbacks
    def run(self):

        if isCalendarCollectionResource(self.parent):
            response = (yield self.deleteCalendarResource(self.resource, self.resource_uri, self.parent))
            
        elif isCalendarCollectionResource(self.resource):
            response = (yield self.deleteCalendar(self.resource, self.resource_uri, self.parent))
        
        elif self.resource.isCollection():
            response = (yield self.deleteCollection())

        else:
            response = (yield self.deleteResource(self.resource, self.resource_uri, self.parent))

        returnValue(response)
