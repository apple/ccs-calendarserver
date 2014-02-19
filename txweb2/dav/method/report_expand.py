# -*- test-case-name: txweb2.dav.test.test_report_expand -*-
##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
##

"""
WebDAV expand-property report
"""

__all__ = ["report_DAV__expand_property"]

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.failure import Failure

from twext.python.log import Logger
from txweb2 import responsecode
from txdav.xml import element
from txdav.xml.element import dav_namespace
from txweb2.dav.http import statusForFailure, MultiStatusResponse
from txweb2.dav.method import prop_common
from txweb2.dav.method.propfind import propertyName
from txweb2.dav.resource import AccessDeniedError
from txweb2.dav.util import parentForURL
from txweb2.http import HTTPError, StatusResponse

log = Logger()


@inlineCallbacks
def report_DAV__expand_property(self, request, expand_property):
    """
    Generate an expand-property REPORT. (RFC 3253, section 3.8)
    
    TODO: for simplicity we will only support one level of expansion.
    """
    # Verify root element
    if not isinstance(expand_property, element.ExpandProperty):
        raise ValueError("%s expected as root element, not %s."
                         % (element.ExpandProperty.sname(), expand_property.sname()))

    # Only handle Depth: 0
    depth = request.headers.getHeader("depth", "0")
    if depth != "0":
        log.error("Non-zero depth is not allowed: %s" % (depth,))
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "Depth %s not allowed" % (depth,)))
    
    #
    # Get top level properties to expand and make sure we only have one level
    #
    properties = {}

    for property in expand_property.children:
        namespace = property.attributes.get("namespace", dav_namespace)
        name      = property.attributes.get("name", "")
        
        # Make sure children have no children
        props_to_find = []
        for child in property.children:
            if child.children:
                log.error("expand-property REPORT only supports single level expansion")
                raise HTTPError(StatusResponse(
                    responsecode.NOT_IMPLEMENTED,
                    "expand-property REPORT only supports single level expansion"
                ))
            child_namespace = child.attributes.get("namespace", dav_namespace)
            child_name      = child.attributes.get("name", "")
            props_to_find.append((child_namespace, child_name))

        properties[(namespace, name)] = props_to_find

    #
    # Generate the expanded responses status for each top-level property
    #
    properties_by_status = {
        responsecode.OK        : [],
        responsecode.NOT_FOUND : [],
    }
    
    filteredaces = None
    lastParent = None

    for qname in properties.iterkeys():
        try:
            prop = (yield self.readProperty(qname, request))
            
            # Form the PROPFIND-style DAV:prop element we need later
            props_to_return = element.PropertyContainer(*properties[qname])

            # Now dereference any HRefs
            responses = []
            for href in prop.children:
                if isinstance(href, element.HRef):
                    
                    # Locate the Href resource and its parent
                    resource_uri = str(href)
                    child = (yield request.locateResource(resource_uri))
    
                    if not child or not child.exists():
                        responses.append(element.StatusResponse(href, element.Status.fromResponseCode(responsecode.NOT_FOUND)))
                        continue
                    parent = (yield request.locateResource(parentForURL(resource_uri)))
    
                    # Check privileges on parent - must have at least DAV:read
                    try:
                        yield parent.checkPrivileges(request, (element.Read(),))
                    except AccessDeniedError:
                        responses.append(element.StatusResponse(href, element.Status.fromResponseCode(responsecode.FORBIDDEN)))
                        continue
                    
                    # Cache the last parent's inherited aces for checkPrivileges optimization
                    if lastParent != parent:
                        lastParent = parent
                
                        # Do some optimisation of access control calculation by determining any inherited ACLs outside of
                        # the child resource loop and supply those to the checkPrivileges on each child.
                        filteredaces = (yield parent.inheritedACEsforChildren(request))

                    # Check privileges - must have at least DAV:read
                    try:
                        yield child.checkPrivileges(request, (element.Read(),), inherited_aces=filteredaces)
                    except AccessDeniedError:
                        responses.append(element.StatusResponse(href, element.Status.fromResponseCode(responsecode.FORBIDDEN)))
                        continue
            
                    # Now retrieve all the requested properties on the HRef resource
                    yield prop_common.responseForHref(
                        request,
                        responses,
                        href,
                        child,
                        prop_common.propertyListForResource,
                        props_to_return,
                    )
            
            prop.children = responses
            properties_by_status[responsecode.OK].append(prop)
        except:
            f = Failure()

            log.error("Error reading property %r for resource %s: %s" % (qname, request.uri, f.value))

            status = statusForFailure(f, "getting property: %s" % (qname,))
            if status not in properties_by_status: properties_by_status[status] = []
            properties_by_status[status].append(propertyName(qname))

    # Build the overall response
    propstats = [
        element.PropertyStatus(
            element.PropertyContainer(*properties_by_status[status]),
            element.Status.fromResponseCode(status)
        )
        for status in properties_by_status if properties_by_status[status]
    ]

    returnValue(MultiStatusResponse((element.PropertyStatusResponse(element.HRef(request.uri), *propstats),)))
