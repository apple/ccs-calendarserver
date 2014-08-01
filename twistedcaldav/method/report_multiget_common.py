##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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
CalDAV/CardDAV multiget report
"""

__all__ = ["multiget_common"]

from twext.python.log import Logger
from twisted.internet.defer import inlineCallbacks, returnValue
from twistedcaldav import carddavxml
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.carddavxml import carddav_namespace
from twistedcaldav.config import config
from twistedcaldav.method import report_common
from twistedcaldav.method.report_common import COLLECTION_TYPE_CALENDAR, \
    COLLECTION_TYPE_ADDRESSBOOK
from txdav.carddav.datastore.query.filter import Filter
from txdav.common.icommondatastore import ConcurrentModification
from txdav.xml import element as davxml
from txdav.xml.base import dav_namespace
from txweb2 import responsecode
from txweb2.dav.http import ErrorResponse, MultiStatusResponse
from txweb2.dav.resource import AccessDeniedError
from txweb2.http import HTTPError, StatusResponse
from urllib import unquote

log = Logger()

@inlineCallbacks
def multiget_common(self, request, multiget, collection_type):
    """
    Generate a multiget REPORT.
    """

    # Make sure target resource is of the right type
    if not self.isCollection():
        parent = (yield self.locateParent(request, request.uri))

        if collection_type == COLLECTION_TYPE_CALENDAR:
            if not parent.isPseudoCalendarCollection():
                log.error("calendar-multiget report is not allowed on a resource outside of a calendar collection {res}", res=self)
                raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Must be calendar resource"))
        elif collection_type == COLLECTION_TYPE_ADDRESSBOOK:
            if not parent.isAddressBookCollection():
                log.error("addressbook-multiget report is not allowed on a resource outside of an address book collection {res}", res=self)
                raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Must be address book resource"))

    responses = []

    propertyreq = multiget.property
    resources = multiget.resources

    if not hasattr(request, "extendedLogItems"):
        request.extendedLogItems = {}
    request.extendedLogItems["rcount"] = len(resources)

    hasData = False
    if propertyreq.qname() == ("DAV:", "allprop"):
        propertiesForResource = report_common.allPropertiesForResource

    elif propertyreq.qname() == ("DAV:", "propname"):
        propertiesForResource = report_common.propertyNamesForResource

    elif propertyreq.qname() == ("DAV:", "prop"):
        propertiesForResource = report_common.propertyListForResource

        if collection_type == COLLECTION_TYPE_CALENDAR:
            # Verify that any calendar-data element matches what we can handle
            result, message, hasData = report_common.validPropertyListCalendarDataTypeVersion(propertyreq)
            precondition = (caldav_namespace, "supported-calendar-data")
        elif collection_type == COLLECTION_TYPE_ADDRESSBOOK:
            # Verify that any address-data element matches what we can handle
            result, message, hasData = report_common.validPropertyListAddressDataTypeVersion(propertyreq)
            precondition = (carddav_namespace, "supported-address-data")
        else:
            result = True
        if not result:
            log.error(message)
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                precondition,
                "Invalid object data element",
            ))
    else:
        raise AssertionError("We shouldn't be here")

    # Check size of results is within limit when data property requested
    if hasData and len(resources) > config.MaxMultigetWithDataHrefs:
        log.error("Too many resources in multiget report: {count}", count=len(resources))
        raise HTTPError(ErrorResponse(
            responsecode.FORBIDDEN,
            davxml.NumberOfMatchesWithinLimits(),
            "Too many resources",
        ))

    """
    Three possibilities exist:

        1. The request-uri is a calendar collection, in which case all the hrefs
        MUST be one-level below that collection and must be calendar object resources.

        2. The request-uri is a regular collection, in which case all the hrefs
        MUST be children of that (at any depth) but MUST also be calendar object
        resources (i.e. immediate child of a calendar collection).

        3. The request-uri is a resource, in which case there MUST be
        a single href equal to the request-uri, and MUST be a calendar
        object resource.
    """

    disabled = False
    if self.isPseudoCalendarCollection():
        requestURIis = "calendar"

        # Do some optimisation of access control calculation by determining any inherited ACLs outside of
        # the child resource loop and supply those to the checkPrivileges on each child.
        filteredaces = (yield self.inheritedACEsforChildren(request))

        # Check for disabled access
        if filteredaces is None:
            disabled = True

        # Check private events access status
        isowner = (yield self.isOwner(request))

    elif self.isAddressBookCollection():
        requestURIis = "addressbook"

        # Do some optimisation of access control calculation by determining any inherited ACLs outside of
        # the child resource loop and supply those to the checkPrivileges on each child.
        filteredaces = (yield self.inheritedACEsforChildren(request))

        # Check for disabled access
        if filteredaces is None:
            disabled = True
        isowner = None

    elif self.isCollection():
        requestURIis = "collection"
        filteredaces = None
        lastParent = None
        isowner = None
    else:
        requestURIis = "resource"
        filteredaces = None
        isowner = None

    if not disabled:

        @inlineCallbacks
        def doResponse():

            # Special for addressbooks
            if collection_type == COLLECTION_TYPE_ADDRESSBOOK:
                if self.isDirectoryBackedAddressBookCollection():
                    result = (yield doDirectoryAddressBookResponse())
                    returnValue(result)

            # Verify that requested resources are immediate children of the request-URI
            valid_names = []
            for href in resources:
                resource_uri = str(href)
                name = unquote(resource_uri[resource_uri.rfind("/") + 1:])
                if not self._isChildURI(request, resource_uri):
                    responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.BAD_REQUEST)))
                else:
                    valid_names.append(name)
            if not valid_names:
                returnValue(None)

            # Now determine which valid resources are readable and which are not
            ok_resources = []
            bad_resources = []
            missing_resources = []
            unavailable_resources = []
            yield self.findChildrenFaster(
                "1",
                request,
                lambda x, y: ok_resources.append((x, y)),
                lambda x, y: bad_resources.append((x, y)),
                lambda x: missing_resources.append(x),
                lambda x: unavailable_resources.append(x),
                valid_names,
                (davxml.Read(),),
                inherited_aces=filteredaces
            )

            # Get properties for all valid readable resources
            for resource, href in ok_resources:
                try:
                    yield report_common.responseForHref(
                        request, responses, davxml.HRef.fromString(href),
                        resource, propertiesForResource, propertyreq,
                        isowner=isowner
                    )
                except ValueError:
                    log.error("Invalid calendar resource during multiget: {href}", href=href)
                    responses.append(davxml.StatusResponse(
                        davxml.HRef.fromString(href),
                        davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                except ConcurrentModification:
                    # This can happen because of a race-condition between the
                    # time we determine which resources exist and the deletion
                    # of one of these resources in another request.  In this
                    # case, return a 404 for the now missing resource rather
                    # than raise an error for the entire report.
                    log.error("Missing resource during multiget: {href}", href=href)
                    responses.append(davxml.StatusResponse(
                        davxml.HRef.fromString(href),
                        davxml.Status.fromResponseCode(responsecode.NOT_FOUND)
                    ))

            # Indicate error for all valid non-readable resources
            for ignore_resource, href in bad_resources:
                responses.append(davxml.StatusResponse(davxml.HRef.fromString(href), davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))

            # Indicate error for all missing/unavailable resources
            for href in missing_resources:
                responses.append(davxml.StatusResponse(davxml.HRef.fromString(href), davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
            for href in unavailable_resources:
                responses.append(davxml.StatusResponse(davxml.HRef.fromString(href), davxml.Status.fromResponseCode(responsecode.SERVICE_UNAVAILABLE)))

        @inlineCallbacks
        def doDirectoryAddressBookResponse():

            directoryAddressBookLock = None
            try:
                # Verify that requested resources are immediate children of the request-URI
                # and get vCardFilters ;similar to "normal" case below but do not call getChild()
                vCardFilters = []
                valid_hrefs = []
                for href in resources:
                    resource_uri = str(href)
                    resource_name = unquote(resource_uri[resource_uri.rfind("/") + 1:])
                    if self._isChildURI(request, resource_uri) and resource_name.endswith(".vcf") and len(resource_name) > 4:
                        valid_hrefs.append(href)
                        textMatchElement = carddavxml.TextMatch.fromString(resource_name[:-4])
                        textMatchElement.attributes["match-type"] = "equals" # do equals compare. Default is "contains"
                        vCardFilters.append(carddavxml.PropertyFilter(
                            textMatchElement,
                            name="UID", # attributes
                        ))
                    else:
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))

                # exit if not valid
                if not vCardFilters or not valid_hrefs:
                    returnValue(None)

                addressBookFilter = carddavxml.Filter(*vCardFilters)
                addressBookFilter = Filter(addressBookFilter)

                # get vCards and filter
                limit = config.DirectoryAddressBook.MaxQueryResults
                results, limited = (yield self.doAddressBookDirectoryQuery(addressBookFilter, propertyreq, limit, defaultKind=None))
                if limited:
                    log.error("Too many results in multiget report: {count}", count=len(resources))
                    raise HTTPError(ErrorResponse(
                        responsecode.FORBIDDEN,
                        (dav_namespace, "number-of-matches-within-limits"),
                        "Too many results",
                    ))

                for href in valid_hrefs:
                    matchingResource = None
                    for vCardResource in results:
                        if href == vCardResource.hRef(): # might need to compare urls instead - also case sens ok?
                            matchingResource = vCardResource
                            break

                    if matchingResource:
                        yield report_common.responseForHref(request, responses, href, matchingResource, propertiesForResource, propertyreq, vcard=matchingResource.vCard())
                    else:
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
            finally:
                if directoryAddressBookLock:
                    yield directoryAddressBookLock.release()

        if requestURIis == "calendar" or requestURIis == "addressbook":
            yield doResponse()
        else:
            for href in resources:

                resource_uri = str(href)

                # Do href checks
                if requestURIis == "calendar":
                    pass
                elif requestURIis == "addressbook":
                    pass

                # TODO: we can optimize this one in a similar manner to the calendar case
                elif requestURIis == "collection":
                    name = unquote(resource_uri[resource_uri.rfind("/") + 1:])
                    if not self._isChildURI(request, resource_uri, False):
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                        continue

                    child = (yield request.locateResource(resource_uri))

                    if not child or not child.exists():
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                        continue

                    parent = (yield child.locateParent(request, resource_uri))

                    if collection_type == COLLECTION_TYPE_CALENDAR:
                        if not parent.isCalendarCollection() or not (yield parent.resourceExists(name)):
                            responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                            continue
                    elif collection_type == COLLECTION_TYPE_ADDRESSBOOK:
                        if not parent.isAddressBookCollection() or not (yield parent.resourceExists(name)):
                            responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                            continue

                    # Check privileges on parent - must have at least DAV:read
                    try:
                        yield parent.checkPrivileges(request, (davxml.Read(),))
                    except AccessDeniedError:
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                        continue

                    # Cache the last parent's inherited aces for checkPrivileges optimization
                    if lastParent != parent:
                        lastParent = parent

                        # Do some optimisation of access control calculation by determining any inherited ACLs outside of
                        # the child resource loop and supply those to the checkPrivileges on each child.
                        filteredaces = (yield parent.inheritedACEsforChildren(request))

                        # Check private events access status
                        isowner = (yield parent.isOwner(request))
                else:
                    name = unquote(resource_uri[resource_uri.rfind("/") + 1:])
                    if (resource_uri != request.uri) or not self.exists():
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                        continue

                    parent = (yield self.locateParent(request, resource_uri))

                    if collection_type == COLLECTION_TYPE_CALENDAR:
                        if not parent.isPseudoCalendarCollection() or not (yield parent.resourceExists(name)):
                            responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                            continue
                    elif collection_type == COLLECTION_TYPE_ADDRESSBOOK:
                        if not parent.isAddressBookCollection() or not (yield parent.resourceExists(name)):
                            responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                            continue
                    child = self

                    # Do some optimisation of access control calculation by determining any inherited ACLs outside of
                    # the child resource loop and supply those to the checkPrivileges on each child.
                    filteredaces = (yield parent.inheritedACEsforChildren(request))

                    # Check private events access status
                    isowner = (yield parent.isOwner(request))

                # Check privileges - must have at least DAV:read
                try:
                    yield child.checkPrivileges(request, (davxml.Read(),), inherited_aces=filteredaces)
                except AccessDeniedError:
                    responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                    continue

                yield report_common.responseForHref(request, responses, href, child, propertiesForResource, propertyreq, isowner=isowner)

    returnValue(MultiStatusResponse(responses))
