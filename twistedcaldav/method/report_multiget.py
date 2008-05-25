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
CalDAV multiget report
"""

__all__ = ["report_urn_ietf_params_xml_ns_caldav_calendar_multiget"]

from urllib import unquote

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.element.base import dav_namespace
from twisted.web2.dav.http import ErrorResponse, MultiStatusResponse
from twisted.web2.dav.resource import AccessDeniedError
from twisted.web2.dav.util import joinURL
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.method import report_common
from twistedcaldav.log import Logger

log = Logger()

max_number_of_multigets = 5000

@inlineCallbacks
def report_urn_ietf_params_xml_ns_caldav_calendar_multiget(self, request, multiget):
    """
    Generate a multiget REPORT.
    (CalDAV-access-09, section 7.7)
    """

    # Verify root element
    if multiget.qname() != (caldav_namespace, "calendar-multiget"):
        raise ValueError("{CalDAV:}calendar-multiget expected as root element, not %s." % (multiget.sname(),))

    # Make sure target resource is of the right type
    if not self.isCollection():
        parent = yield self.locateParent(request, request.uri)
        if not parent.isPseudoCalendarCollection():
            log.err("calendar-multiget report is not allowed on a resource outside of a calendar collection %s" % (self,))
            raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Must be calendar resource"))

    responses = []

    propertyreq = multiget.property
    resources  = multiget.resources
    
    if propertyreq.qname() == ("DAV:", "allprop"):
        propertiesForResource = report_common.allPropertiesForResource

    elif propertyreq.qname() == ("DAV:", "propname"):
        propertiesForResource = report_common.propertyNamesForResource

    elif propertyreq.qname() == ("DAV:", "prop"):
        propertiesForResource = report_common.propertyListForResource
        
        # Verify that any calendar-data element matches what we can handle
        result, message, _ignore = report_common.validPropertyListCalendarDataTypeVersion(propertyreq)
        if not result:
            log.err(message)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data")))
    else:
        raise AssertionError("We shouldn't be here")

    # Check size of results is within limit
    if len(resources) > max_number_of_multigets:
        log.err("Too many results in multiget report: %d" % len(resources))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (dav_namespace, "number-of-matches-within-limits")))

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
        filteredaces = yield self.inheritedACEsforChildren(request)
    
        # Check for disabled access
        if filteredaces is None:
            disabled = True
            
        # Check private events access status
        isowner = yield self.isOwner(request)

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
        def doCalendarResponse():
            # Verify that requested resources are immediate children of the request-URI
            valid_names = []
            for href in resources:
                resource_uri = str(href)
                name = unquote(resource_uri[resource_uri.rfind("/") + 1:])
                if not self._isChildURI(request, resource_uri) or self.getChild(name) is None:
                    responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                else:
                    valid_names.append(name)
            if not valid_names:
                returnValue(None)
        
            # Verify that valid requested resources are calendar objects
            exists_names = tuple(self.index().resourcesExist(valid_names))
            checked_names = []
            for name in valid_names:
                if name not in exists_names:
                    href = davxml.HRef.fromString(joinURL(request.uri, name))
                    responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                else:
                    checked_names.append(name)
            if not checked_names:
                returnValue(None)
            
            # Now determine which valid resources are readable and which are not
            ok_resources = []
            bad_resources = []
            yield self.findChildrenFaster(
                "1",
                request,
                lambda x, y: ok_resources.append((x, y)),
                lambda x, y: bad_resources.append((x, y)),
                checked_names,
                (davxml.Read(),),
                inherited_aces=filteredaces
            )

            # Get properties for all valid readable resources
            for resource, href in ok_resources:
                yield report_common.responseForHref(request, responses, davxml.HRef.fromString(href), resource, None, propertiesForResource, propertyreq, isowner=isowner)
    
            # Indicate error for all valid non-readable resources
            for ignore_resource, href in bad_resources:
                responses.append(davxml.StatusResponse(davxml.HRef.fromString(href), davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
    
        if requestURIis == "calendar":
            yield doCalendarResponse()
        else:
            for href in resources:
    
                resource_uri = str(href)
    
                # Do href checks
                if requestURIis == "calendar":
                    pass
        
                # TODO: we can optimize this one in a similar manner to the calendar case
                elif requestURIis == "collection":
                    name = unquote(resource_uri[resource_uri.rfind("/") + 1:])
                    if not self._isChildURI(request, resource_uri, False):
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                        continue
     
                    child = yield request.locateResource(resource_uri)
    
                    if not child or not child.exists():
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                        continue
    
                    parent = yield child.locateParent(request, resource_uri)
    
                    if not parent.isCalendarCollection() or not parent.index().resourceExists(name):
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
                        filteredaces = yield parent.inheritedACEsforChildren(request)

                        # Check private events access status
                        isowner = yield parent.isOwner(request)
                else:
                    name = unquote(resource_uri[resource_uri.rfind("/") + 1:])
                    if (resource_uri != request.uri) or not self.exists():
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                        continue
    
                    parent = yield self.locateParent(request, resource_uri)
    
                    if not parent.isPseudoCalendarCollection() or not parent.index().resourceExists(name):
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                        continue
                    child = self
            
                    # Do some optimisation of access control calculation by determining any inherited ACLs outside of
                    # the child resource loop and supply those to the checkPrivileges on each child.
                    filteredaces = yield parent.inheritedACEsforChildren(request)

                    # Check private events access status
                    isowner = yield parent.isOwner(request)
        
                # Check privileges - must have at least DAV:read
                try:
                    yield child.checkPrivileges(request, (davxml.Read(),), inherited_aces=filteredaces)
                except AccessDeniedError:
                    responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                    continue
        
                yield report_common.responseForHref(request, responses, href, child, None, propertiesForResource, propertyreq, isowner=isowner)

    returnValue(MultiStatusResponse(responses))
