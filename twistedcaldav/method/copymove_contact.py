##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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

__all__ = ["maybeCOPYContact", "maybeMOVEContact"]

from urlparse import urlsplit

from twisted.internet.defer import inlineCallbacks, returnValue
from twext.web2 import responsecode
from twext.web2.filter.location import addLocation
from txdav.xml import element as davxml
from twext.web2.dav.http import ErrorResponse
from twext.web2.dav.util import parentForURL
from twext.web2.http import StatusResponse, HTTPError

from twistedcaldav.carddavxml import carddav_namespace
from twistedcaldav.method.put_addressbook_common import StoreAddressObjectResource
from twistedcaldav.resource import isAddressBookCollectionResource
from twext.python.log import Logger

log = Logger()

KEEP_GOING = object()

@inlineCallbacks
def maybeCOPYContact(self, request):
    """
    Special handling of COPY request if parents are addressbook collections.
    When copying we do not have to worry about the source resource as it
    is not being changed in any way. We do need to do an index update for
    the destination if its an addressbook collection.
    """
    # Copy of addressbook collections isn't allowed.
    if isAddressBookCollectionResource(self):
        returnValue(responsecode.FORBIDDEN)

    result, sourceadbk, sourceparent, destination_uri, destination, destinationadbk, destinationparent = (yield checkForAddressBookAction(self, request))
    if not result or not destinationadbk:
        # Give up, do default action.
        
        returnValue(KEEP_GOING)

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

    # Checks for copying an addressbook collection
    if self.isAddressBookCollection():
        log.err("Attempt to copy an addressbook collection into another addressbook collection %s" % destination)
        raise HTTPError(ErrorResponse(
            responsecode.FORBIDDEN,
            (carddav_namespace, "addressbook-collection-location-ok"),
            "Cannot copy address book collection inside another address book collection",
        ))

    # We also do not allow regular collections in addressbook collections
    if self.isCollection():
        log.err("Attempt to copy a collection into an addressbook collection")
        raise HTTPError(StatusResponse(
            responsecode.FORBIDDEN,
            "Cannot create collection within special collection %s" % (destination,))
        )

    # May need to add a location header
    addLocation(request, destination_uri)

    storer = StoreAddressObjectResource(
        request = request,
        source = self,
        source_uri = request.uri,
        sourceparent = sourceparent,
        sourceadbk = sourceadbk,
        destination = destination,
        destination_uri = destination_uri,
        destinationparent = destinationparent,
        destinationadbk = destinationadbk,
    )
    result = (yield storer.run())
    returnValue(result)

@inlineCallbacks
def maybeMOVEContact(self, request):
    """
    Special handling of MOVE request if parent is an addressbook collection.
    When moving we may need to remove the index entry for the source resource
    since its effectively being deleted. We do need to do an index update for
    the destination if its an addressbook collection
    """
    result, sourceadbk, sourceparent, destination_uri, destination, destinationadbk, destinationparent = (yield checkForAddressBookAction(self, request))
    if not result or not destinationadbk:

        # Do default WebDAV action
        returnValue(KEEP_GOING)
        
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

    if destinationadbk:
        # Checks for copying an addressbook collection
        if self.isAddressBookCollection():
            log.err("Attempt to move an addressbook collection into another addressbook collection %s" % destination)
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (carddav_namespace, "addressbook-collection-location-ok"),
                "Cannot move address book collection inside another address book collection",
            ))
    
        # We also do not allow regular collections in addressbook collections
        if self.isCollection():
            log.err("Attempt to move a collection into an addressbook collection")
            raise HTTPError(StatusResponse(
                responsecode.FORBIDDEN,
                "Cannot create collection within special collection %s" % (destination,)
            ))

    # May need to add a location header
    addLocation(request, destination_uri)

    storer = StoreAddressObjectResource(
        request = request,
        source = self,
        source_uri = request.uri,
        sourceparent = sourceparent,
        sourceadbk = sourceadbk,
        deletesource = True,
        destination = destination,
        destination_uri = destination_uri,
        destinationparent = destinationparent,
        destinationadbk = destinationadbk,
    )
    result = (yield storer.run())
    returnValue(result)

@inlineCallbacks
def checkForAddressBookAction(self, request):
    """
    Check to see whether the source or destination of the copy/move
    is an addressbook collection, since we need to do special processing
    if that is the case.
    @return: tuple::
        result:           True if special CalDAV processing required, False otherwise
            NB If there is any type of error with the request, return False
            and allow normal COPY/MOVE processing to return the error.
        sourceadbk:        True if source is in an addressbook collection, False otherwise
        sourceparent:     The parent resource for the source
        destination_uri:  The URI of the destination resource
        destination:      CalDAVResource of destination if special processing required,
        None otherwise
        destinationadbk:   True if the destination is in an addressbook collection,
            False otherwise
        destinationparent:The parent resource for the destination
        
    """
    
    result = False
    sourceadbk = False
    destinationadbk = False
    
    # Check the source path first
    if not self.exists():
        log.err("Resource not found: %s" % (self,))
        raise HTTPError(StatusResponse(
            responsecode.NOT_FOUND,
            "Source resource %s not found." % (request.uri,)
        ))

    # Check for parent addressbook collection
    sourceparent = (yield request.locateResource(parentForURL(request.uri)))
    if isAddressBookCollectionResource(sourceparent):
        result = True
        sourceadbk = True
    
    #
    # Find the destination resource
    #
    destination_uri = request.headers.getHeader("destination")

    if not destination_uri:
        msg = "No destination header in %s request." % (request.method,)
        log.err(msg)
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))
    
    destination = (yield request.locateResource(destination_uri))

    # Check for parent addressbook collection
    destination_uri = urlsplit(destination_uri)[2]
    destinationparent = (yield request.locateResource(parentForURL(destination_uri)))
    if isAddressBookCollectionResource(destinationparent):
        result = True
        destinationadbk = True

    returnValue((result, sourceadbk, sourceparent, destination_uri, destination, destinationadbk, destinationparent))
