##
# Copyrightg (c) 2006-2012 Apple Inc. All rights reserved.
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
CalDAV COPY and MOVE methods.
"""

__all__ = ["http_COPY", "http_MOVE"]

from urlparse import urlsplit

from twisted.internet.defer import inlineCallbacks, returnValue
from twext.web2 import responsecode
from twext.web2.filter.location import addLocation
from txdav.xml import element as davxml
from twext.web2.dav.http import ErrorResponse
from twext.web2.dav.util import parentForURL
from twext.web2.http import StatusResponse, HTTPError

from twext.python.log import Logger

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.method.put_common import StoreCalendarObjectResource
from twistedcaldav.method.copymove_contact import (
    maybeCOPYContact, maybeMOVEContact, KEEP_GOING
)

from twistedcaldav.resource import isCalendarCollectionResource,\
    isPseudoCalendarCollectionResource, CalDAVResource,\
    isAddressBookCollectionResource

log = Logger()

@inlineCallbacks
def http_COPY(self, request):
    """
    Special handling of COPY request if parents are calendar collections.
    When copying we do not have to worry about the source resource as it
    is not being changed in any way. We do need to do an index update for
    the destination if its a calendar collection.
    """

    # Copy of calendar collections isn't allowed.
    if isPseudoCalendarCollectionResource(self):
        returnValue(responsecode.FORBIDDEN)

    result, sourcecal, sourceparent, destination_uri, destination, destinationcal, destinationparent = (yield checkForCalendarAction(self, request))
    if not result or not destinationcal:
        # Check with CardDAV first (XXX might want to check EnableCardDAV switch?)
        result = yield maybeCOPYContact(self, request)
        if result is KEEP_GOING:
            result = yield super(CalDAVResource, self).http_COPY(request)
        returnValue(result)

    #
    # Check authentication and access controls
    #
    yield self.authorize(request, (davxml.Read(),), recurse=True)

    if destination.exists():
        yield destination.authorize(request, (davxml.WriteContent(), davxml.WriteProperties()), recurse=True)
    else:
        destparent = (yield request.locateResource(parentForURL(destination_uri)))
        yield destparent.authorize(request, (davxml.Bind(),))

    # Check for existing destination resource
    overwrite = request.headers.getHeader("overwrite", True)
    if destination.exists() and not overwrite:
        log.err("Attempt to copy onto existing resource without overwrite flag enabled: %s"
                % (destination,))
        raise HTTPError(StatusResponse(
            responsecode.PRECONDITION_FAILED,
            "Destination %s already exists." % (destination_uri,))
        )

    # Checks for copying a calendar collection
    if self.isCalendarCollection():
        log.err("Attempt to copy a calendar collection into another calendar collection %s" % destination)
        raise HTTPError(ErrorResponse(
            responsecode.FORBIDDEN,
            (caldav_namespace, "calendar-collection-location-ok"),
            "Cannot copy calendar collection inside another calendar collection",
        ))

    # We also do not allow regular collections in calendar collections
    if self.isCollection():
        log.err("Attempt to copy a collection into a calendar collection")
        raise HTTPError(StatusResponse(
            responsecode.FORBIDDEN,
            "Cannot create collection within special collection %s" % (destination,))
        )

    # May need to add a location header
    addLocation(request, destination_uri)

    storer = StoreCalendarObjectResource(
        request = request,
        source = self,
        source_uri = request.uri,
        sourceparent = sourceparent,
        sourcecal = sourcecal,
        destination = destination,
        destination_uri = destination_uri,
        destinationparent = destinationparent,
        destinationcal = destinationcal,
    )
    result = (yield storer.run())
    returnValue(result)

@inlineCallbacks
def http_MOVE(self, request):
    """
    Special handling of MOVE request if parent is a calendar collection.
    When moving we may need to remove the index entry for the source resource
    since its effectively being deleted. We do need to do an index update for
    the destination if its a calendar collection
    """
    result, sourcecal, sourceparent, destination_uri, destination, destinationcal, destinationparent = (yield checkForCalendarAction(self, request))
    if not result:
        is_calendar_collection = isPseudoCalendarCollectionResource(self)
        defaultCalendarType = (yield self.isDefaultCalendar(request)) if is_calendar_collection else None
        is_addressbook_collection = isAddressBookCollectionResource(self)
        defaultAddressBook = (yield self.isDefaultAddressBook(request)) if is_addressbook_collection else False

        if not is_calendar_collection:
            result = yield maybeMOVEContact(self, request)
            if result is not KEEP_GOING:
                returnValue(result)

        # Do default WebDAV action
        result = (yield super(CalDAVResource, self).http_MOVE(request))
        
        if result == responsecode.NO_CONTENT:
            if is_calendar_collection:
                # Do some clean up
                yield self.movedCalendar(request, defaultCalendarType, destination, destination_uri)
            elif is_addressbook_collection:
                # Do some clean up
                yield self.movedAddressBook(request, defaultAddressBook, destination, destination_uri)

        returnValue(result)
        
    #
    # Check authentication and access controls
    #
    parent = (yield request.locateResource(parentForURL(request.uri)))
    yield parent.authorize(request, (davxml.Unbind(),))

    if destination.exists():
        yield destination.authorize(request, (davxml.Bind(), davxml.Unbind()), recurse=True)
    else:
        destparent = (yield request.locateResource(parentForURL(destination_uri)))
        yield destparent.authorize(request, (davxml.Bind(),))

    # Check for existing destination resource
    overwrite = request.headers.getHeader("overwrite", True)
    if destination.exists() and not overwrite:
        log.err("Attempt to copy onto existing resource without overwrite flag enabled: %s"
                % (destination,))
        raise HTTPError(StatusResponse(
            responsecode.PRECONDITION_FAILED,
            "Destination %s already exists." % (destination_uri,)
        ))

    if destinationcal:
        # Checks for copying a calendar collection
        if self.isCalendarCollection():
            log.err("Attempt to move a calendar collection into another calendar collection %s" % destination)
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "calendar-collection-location-ok"),
                "Cannot move calendar collection inside another calendar collection",
            ))
    
        # We also do not allow regular collections in calendar collections
        if self.isCollection():
            log.err("Attempt to move a collection into a calendar collection")
            raise HTTPError(StatusResponse(
                responsecode.FORBIDDEN,
                "Cannot create collection within special collection %s" % (destination,)
            ))

    # May need to add a location header
    addLocation(request, destination_uri)

    storer = StoreCalendarObjectResource(
        request = request,
        source = self,
        source_uri = request.uri,
        sourceparent = sourceparent,
        sourcecal = sourcecal,
        deletesource = True,
        destination = destination,
        destination_uri = destination_uri,
        destinationparent = destinationparent,
        destinationcal = destinationcal,
    )
    result = (yield storer.run())
    returnValue(result)

@inlineCallbacks
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
        destination:      CalDAVResource of destination if special processing required,
        None otherwise
        destinationcal:   True if the destination is in a calendar collection,
            False otherwise
        destinationparent:The parent resource for the destination
        
    """
    
    result = False
    sourcecal = False
    destinationcal = False
    
    # Check the source path first
    if not self.exists():
        log.err("Resource not found: %s" % (self,))
        raise HTTPError(StatusResponse(
            responsecode.NOT_FOUND,
            "Source resource %s not found." % (request.uri,)
        ))

    # Check for parent calendar collection
    sourceparent = (yield request.locateResource(parentForURL(request.uri)))
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
    
    destination = (yield request.locateResource(destination_uri))

    # Check for parent calendar collection
    destination_uri = urlsplit(destination_uri)[2]
    destinationparent = (yield request.locateResource(parentForURL(destination_uri)))
    if isCalendarCollectionResource(destinationparent):
        result = True
        destinationcal = True

    returnValue((result, sourcecal, sourceparent, destination_uri, destination, destinationcal, destinationparent))
