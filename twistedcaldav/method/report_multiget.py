##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
#
# This file contains Original Code and/or Modifications of Original Code
# as defined in and that are subject to the Apple Public Source License
# Version 2.0 (the 'License'). You may not use this file except in
# compliance with the License. Please obtain a copy of the License at
# http://www.opensource.apple.com/apsl/ and read it before using this
# file.
# 
# The Original Code and all software distributed under the License are
# distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
# EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
# INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
# Please see the License for the specific language governing rights and
# limitations under the License.
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
CalDAV multiget report
"""

__version__ = "0.0"

__all__ = ["report_urn_ietf_params_xml_ns_caldav_calendar_multiget"]

from twisted.python import log
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.element.base import dav_namespace
from twisted.web2.dav.http import ErrorResponse, MultiStatusResponse
from twisted.web2.dav.method.report import max_number_of_matches

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.method import report_common

def report_urn_ietf_params_xml_ns_caldav_calendar_multiget(self, request, multiget):
    """
    Generate a multiget REPORT.
    (CalDAV-access-09, section 7.7)
    """
    if not self.isCollection() and not self.locateParent(request, request.uri).isPseudoCalendarCollection():
        log.err("calendar-multiget report is not allowed on a resource outside of a calendar collection %s" % (self,))
        return responsecode.FORBIDDEN

    if multiget.qname() != (caldav_namespace, "calendar-multiget"):
        raise ValueError("{CalDAV:}calendar-multiget expected as root element, not %s." % (multiget.sname(),))

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
        result, message = report_common.validPropertyListCalendarDataTypeVersion(propertyreq)
        if not result:
            log.err(message)
            return ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data"))
    else:
        raise AssertionError("We shouldn't be here")

    # Check size of results is within limit
    if len(resources) > max_number_of_matches:
        log.err("Too many results in multiget report: %d" % len(resources))
        return ErrorResponse(responsecode.FORBIDDEN, (dav_namespace, "number-of-matches-within-limits"))

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
        # the child resource loop and supply those to the checkAccess on each child.
        filteredaces = self.inheritedACEsforChildren(request)
    
        # Check for disabled access
        if filteredaces is None:
            disabled = True

    elif self.isCollection():
        requestURIis = "collection"
        filteredaces = None
        lastParent = None
    else:
        requestURIis = "resource"
        filteredaces = None

    if not disabled:
        for href in resources:
            # Do href checks
            if requestURIis == "calendar":
                # Verify that href is an immediate child of the request URI and that resource exists.
                resource = str(href)
                name = resource[resource.rfind("/") + 1:]
                if not self._isChildURI(request, resource) or self.getChild(name) is None:
                    responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                    continue
                
                # Verify that we are dealing with a calendar object resource
                if not self.index().resourceExists(name):
                    responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_ALLOWED)))
                    continue
                
                child = self.getChild(name)
    
            elif requestURIis == "collection":
                resource = str(href)
                name = resource[resource.rfind("/") + 1:]
                if not self._isChildURI(request, resource, False):
                    responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                    continue
                child = self.locateSiblingResource(request, resource)
                if not child or not child.exists():
                    responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                    continue
                parent = child.locateParent(request, resource)
                if not parent.isCalendarCollection() or not parent.index().resourceExists(name):
                    responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_ALLOWED)))
                    continue
                
                # Check privileges on parent - must have at least DAV:read
                error = parent.checkAccess(request, (davxml.Read(),))
                if error:
                    responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_ALLOWED)))
                    continue
                
                # Cache the last parents inherited aces for checkAccess optimization
                if lastParent != parent:
                    lastParent = parent
            
                    # Do some optimisation of access control calculation by determining any inherited ACLs outside of
                    # the child resource loop and supply those to the checkAccess on each child.
                    filteredaces = parent.inheritedACEsforChildren(request)
    
            else:
                resource = str(href)
                name = resource[resource.rfind("/") + 1:]
                if (resource != request.uri) or not self.exists():
                    responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                    continue
                parent = self.locateParent(request, resource)
                if not parent.isPseudoCalendarCollection() or not parent.index().resourceExists(name):
                    responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_ALLOWED)))
                    continue
                child = self
        
                # Do some optimisation of access control calculation by determining any inherited ACLs outside of
                # the child resource loop and supply those to the checkAccess on each child.
                filteredaces = parent.inheritedACEsforChildren(request)
    
            # Check privileges - must have at least DAV:read
            error = child.checkAccess(request, (davxml.Read(),), inheritedaces=filteredaces)
            if error:
                responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_ALLOWED)))
                continue
    
            report_common.responseForHref(request, responses, href, child, None, propertiesForResource, propertyreq)

    return MultiStatusResponse(responses)
