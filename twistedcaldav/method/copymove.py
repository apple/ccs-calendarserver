##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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

from twisted.python import log
from twisted.web2 import responsecode
from twisted.web2.http import StatusResponse
from twisted.web2.dav import davxml
from twisted.web2.dav.filter.location import addlocation
from twisted.web2.dav.http import ErrorResponse

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
    result, sourcecal, destination_uri, destination, destinationcal = checkForCalendarAction(self, request)
    if not result or not destinationcal:
        # Do default WebDAV action
        return super(CalDAVFile, self).http_COPY(request)

    #
    # Check authentication and access controls
    #
    self.securityCheck(request, (davxml.Read(),), recurse=True)

    if destination.exists():
        destination.securityCheck(request, (davxml.WriteContent(), davxml.WriteProperties()), recurse=True)
    else:
        destparent = self.locateParent(request, destination_uri)
        destparent.securityCheck(request, (davxml.Bind(),))

    # Check for existing destination resource
    overwrite = request.headers.getHeader("overwrite", True)
    if destination.exists() and not overwrite:
        log.err("Attempt to copy onto existing file without overwrite flag enabled: %s"
                % (destination.fp.path,))
        return StatusResponse(
            responsecode.PRECONDITION_FAILED,
            "Destination %s already exists." % (destination_uri,)
        )

    # Checks for copying a calendar collection
    if self.isCalendarCollection():
        log.err("Attempt to copy a calendar collection into another calendar collection %s" % destination)
        return ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "calendar-collection-location-ok"))

    # We also do not allow regular collections in calendar collections
    if self.isCollection():
        log.err("Attempt to copy a collection into a calendar collection")
        return StatusResponse(
            responsecode.NOT_ALLOWED,
            "Cannot create collection within special collection %s" % (destination,)
        )

    # May need to add a location header
    addlocation(request, destination_uri)

    return storeCalendarObjectResource(
        request = request,
        source = self,
        source_uri = request.uri,
        sourceparent = self.locateParent(request, request.uri),
        sourcecal = sourcecal,
        destination = destination,
        destination_uri = destination_uri,
        destinationparent = destination.locateParent(request, destination_uri),
        destinationcal = destinationcal,
   )

def http_MOVE(self, request):
    """
    Special handling of MOVE request if parent is a calendar collection.
    When moving we may need to remove the index entry for the source resource
    since its effectively being deleted. We do need to do an index update for
    the destination if its a calendar collection
    """
    result, sourcecal, destination_uri, destination, destinationcal = checkForCalendarAction(self, request)
    if not result:
        # Do default WebDAV action
        return super(CalDAVFile, self).http_MOVE(request)
        
    #
    # Check authentication and access controls
    #
    parent = self.locateParent(request, request.uri)
    parent.securityCheck(request, (davxml.Unbind(),))

    if destination.exists():
        destination.securityCheck(request, (davxml.Bind(), davxml.Unbind()), recurse=True)
    else:
        destparent = self.locateParent(request, destination_uri)
        destparent.securityCheck(request, (davxml.Bind(),))

    # Check for existing destination resource
    overwrite = request.headers.getHeader("overwrite", True)
    if destination.exists() and not overwrite:
        log.err("Attempt to copy onto existing file without overwrite flag enabled: %s"
                % (destination.fp.path,))
        return StatusResponse(
            responsecode.PRECONDITION_FAILED,
            "Destination %s already exists." % (destination_uri,)
        )

    if destinationcal:
        # Checks for copying a calendar collection
        if self.isCalendarCollection():
            log.err("Attempt to copy a calendar collection into another calendar collection %s" % destination)
            return ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "calendar-collection-location-ok"))
    
        # We also do not allow regular collections in calendar collections
        if self.isCollection():
            log.err("Attempt to copy a collection into a calendar collection")
            return StatusResponse(
                responsecode.NOT_ALLOWED,
                "Cannot create collection within special collection %s" % (destination,)
            )

    # May need to add a location header
    addlocation(request, destination_uri)

    return storeCalendarObjectResource(
        request = request,
        source = self,
        source_uri = request.uri,
        sourceparent = self.locateParent(request, request.uri),
        sourcecal = sourcecal,
        destination = destination,
        destination_uri = destination_uri,
        destinationparent = destination.locateParent(request, destination_uri),
        destinationcal = destinationcal,
        deletesource = True,
   )

def checkForCalendarAction(self, request):
    """
    Check to see whether the source or destination of the copy/move
    is a calendar collection, since we need to do special processing
    if that is the case.
    @return: tuple::
        result:      True if special CalDAV processing required, False otherwise
                     NB If there is any type of error with the request, return False
                     and allow normal COPY/MOVE processing to return the error.
        sourcecal:   True if source is in a calendar collection, False otherwise
        destination_uri: The URI of the destination resource
        destination: CalDAVFile of destination if special proccesing required,
        None otherwise
        destinationcal: True if the destination is in a calendar collection,
                        False otherwise
        
    """
    
    result = False
    sourcecal = False
    destination = None
    destinationcal = False
    
    # Check the source path first
    if not self.fp.exists():
        return False, False, None, None, False

    # Check for parent calendar collection
    parent = self.locateParent(request, request.uri)
    if isCalendarCollectionResource(parent):
        result = True
        sourcecal = True
    
    #
    # Find the destination resource
    #
    destination_uri = request.headers.getHeader("destination")

    if not destination_uri:
        return False, False, None, None, False
    
    try:
        destination = self.locateSiblingResource(request, destination_uri)
    except ValueError:
        return False, False, None, None, False

    # Check for parent calendar collection
    destination_uri = urlsplit(destination_uri)[2]
    parent = destination.locateParent(request, destination_uri)
    if isCalendarCollectionResource(parent):
        result = True
        destinationcal = True

    return result, sourcecal, destination_uri, destination, destinationcal
