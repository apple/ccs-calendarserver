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
CalDAV COPY and MOVE methods.
"""

__all__ = ["http_COPY", "http_MOVE"]

from urlparse import urlsplit

from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.python import log
from twisted.web2 import responsecode
from twisted.web2.filter.location import addLocation
from twisted.web2.dav import davxml
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.util import parentForURL
from twisted.web2.http import StatusResponse, HTTPError

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.method.put_common import storeCalendarObjectResource
from twistedcaldav.resource import isCalendarCollectionResource

def http_COPY(self, request):
    """
    Special handling of COPY request if parents are calendar collections.
    When copying we do not have to worry about the source resource as it
    is not being changed in any way. We do need to do an index update for
    the destination if its a calendar collection.
    """

    r = waitForDeferred(checkForCalendarAction(self, request))
    yield r
    result, sourcecal, sourceparent, destination_uri, destination, destinationcal, destinationparent = r.getResult()
    if not result or not destinationcal:
        # Do default WebDAV action
        d = waitForDeferred(super(CalDAVFile, self).http_COPY(request))
        yield d
        yield d.getResult()
        return

    #
    # Check authentication and access controls
    #
    x = waitForDeferred(self.authorize(request, (davxml.Read(),), recurse=True))
    yield x
    x.getResult()

    if destination.exists():
        x = waitForDeferred(destination.authorize(request, (davxml.WriteContent(), davxml.WriteProperties()), recurse=True))
        yield x
        x.getResult()
    else:
        destparent = waitForDeferred(request.locateResource(parentForURL(destination_uri)))
        yield destparent
        destparent = destparent.getResult()
 
        x = waitForDeferred(destparent.authorize(request, (davxml.Bind(),)))
        yield x
        x.getResult()

    # Check for existing destination resource
    overwrite = request.headers.getHeader("overwrite", True)
    if destination.exists() and not overwrite:
        log.err("Attempt to copy onto existing file without overwrite flag enabled: %s"
                % (destination.fp.path,))
        raise HTTPError(StatusResponse(
            responsecode.PRECONDITION_FAILED,
            "Destination %s already exists." % (destination_uri,))
        )

    # Checks for copying a calendar collection
    if self.isCalendarCollection():
        log.err("Attempt to copy a calendar collection into another calendar collection %s" % destination)
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "calendar-collection-location-ok")))

    # We also do not allow regular collections in calendar collections
    if self.isCollection():
        log.err("Attempt to copy a collection into a calendar collection")
        raise HTTPError(StatusResponse(
            responsecode.NOT_ALLOWED,
            "Cannot create collection within special collection %s" % (destination,))
        )

    # May need to add a location header
    addLocation(request, destination_uri)

    x = waitForDeferred(storeCalendarObjectResource(
        request = request,
        source = self,
        source_uri = request.uri,
        sourceparent = sourceparent,
        sourcecal = sourcecal,
        destination = destination,
        destination_uri = destination_uri,
        destinationparent = destinationparent,
        destinationcal = destinationcal,
    ))
    yield x
    yield x.getResult()

http_COPY = deferredGenerator(http_COPY)

def http_MOVE(self, request):
    """
    Special handling of MOVE request if parent is a calendar collection.
    When moving we may need to remove the index entry for the source resource
    since its effectively being deleted. We do need to do an index update for
    the destination if its a calendar collection
    """
    r = waitForDeferred(checkForCalendarAction(self, request))
    yield r
    result, sourcecal, sourceparent, destination_uri, destination, destinationcal, destinationparent = r.getResult()
    if not result:
        # Do default WebDAV action
        d = waitForDeferred(super(CalDAVFile, self).http_MOVE(request))
        yield d
        yield d.getResult()
        return
        
    #
    # Check authentication and access controls
    #
    parent = waitForDeferred(request.locateResource(parentForURL(request.uri)))
    yield parent
    parent = parent.getResult()

    x = waitForDeferred(parent.authorize(request, (davxml.Unbind(),)))
    yield x
    x.getResult()

    if destination.exists():
        x = waitForDeferred(destination.authorize(request, (davxml.Bind(), davxml.Unbind()), recurse=True))
        yield x
        x.getResult()
    else:
        destparent = waitForDeferred(request.locateResource(parentForURL(destination_uri)))
        yield destparent
        destparent = destparent.getResult()

        x = waitForDeferred(destparent.authorize(request, (davxml.Bind(),)))
        yield x
        x.getResult()

    # Check for existing destination resource
    overwrite = request.headers.getHeader("overwrite", True)
    if destination.exists() and not overwrite:
        log.err("Attempt to copy onto existing file without overwrite flag enabled: %s"
                % (destination.fp.path,))
        raise HTTPError(StatusResponse(
            responsecode.PRECONDITION_FAILED,
            "Destination %s already exists." % (destination_uri,)
        ))

    if destinationcal:
        # Checks for copying a calendar collection
        if self.isCalendarCollection():
            log.err("Attempt to copy a calendar collection into another calendar collection %s" % destination)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "calendar-collection-location-ok")))
    
        # We also do not allow regular collections in calendar collections
        if self.isCollection():
            log.err("Attempt to copy a collection into a calendar collection")
            raise HTTPError(StatusResponse(
                responsecode.NOT_ALLOWED,
                "Cannot create collection within special collection %s" % (destination,)
            ))

    # May need to add a location header
    addLocation(request, destination_uri)

    x = waitForDeferred(storeCalendarObjectResource(
        request = request,
        source = self,
        source_uri = request.uri,
        sourceparent = sourceparent,
        sourcecal = sourcecal,
        destination = destination,
        destination_uri = destination_uri,
        destinationparent = destinationparent,
        destinationcal = destinationcal,
        deletesource = True,
    ))
    yield x
    yield x.getResult()

http_MOVE = deferredGenerator(http_MOVE)

def checkForCalendarAction(self, request):
    """
    Check to see whether the source or destination of the copy/move
    is a calendar collection, since we need to do special processing
    if that is the case.
    @return: tuple::
        result:           True if special CalDAV processing required, False otherwise
                          NB If there is any type of error with the request, return False
                          and allow normal COPY/MOVE processing to return the error.
        sourcecal:        True if source is in a calendar collection, False otherwise
        sourceparent:     The parent resource for the source
        destination_uri:  The URI of the destination resource
        destination:      CalDAVFile of destination if special proccesing required,
        None otherwise
        destinationcal:   True if the destination is in a calendar collection,
                          False otherwise
        destinationparent:The parent resource for the destination
        
    """
    
    result = False
    sourcecal = False
    destinationcal = False
    
    # Check the source path first
    if not self.fp.exists():
        log.err("File not found: %s" % (self.fp.path,))
        raise HTTPError(StatusResponse(
            responsecode.NOT_FOUND,
            "Source resource %s not found." % (request.uri,)
        ))

    # Check for parent calendar collection
    sourceparent = waitForDeferred(request.locateResource(parentForURL(request.uri)))
    yield sourceparent
    sourceparent = sourceparent.getResult()
    if isCalendarCollectionResource(sourceparent):
        result = True
        sourcecal = True
    
    #
    # Find the destination resource
    #
    destination_uri = request.headers.getHeader("destination")

    if not destination_uri:
        msg = "No destination header in %s request." % (request.method,)
        log.err(msg)
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))
    
    destination = waitForDeferred(request.locateResource(destination_uri))
    yield destination
    destination = destination.getResult()

    # Check for parent calendar collection
    destination_uri = urlsplit(destination_uri)[2]
    destinationparent = waitForDeferred(request.locateResource(parentForURL(destination_uri)))
    yield destinationparent
    destinationparent = destinationparent.getResult()
    if isCalendarCollectionResource(destinationparent):
        result = True
        destinationcal = True

    yield (result, sourcecal, sourceparent, destination_uri, destination, destinationcal, destinationparent)

checkForCalendarAction = deferredGenerator(checkForCalendarAction)
