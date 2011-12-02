# -*- test-case-name: twext.web2.dav.test.test_prop.PROP.test_PROPFIND -*-
##
# Copyright (c) 2005-2011 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
WebDAV PROPFIND method
"""

__all__ = [
    "http_PROPFIND",
    "propertyName",
]

from twisted.python.failure import Failure
from twisted.internet.defer import deferredGenerator, waitForDeferred

from twext.python.log import Logger
from twext.web2.http import HTTPError
from twext.web2 import responsecode
from twext.web2.http import StatusResponse
from twext.web2.dav import davxml
from twext.web2.dav.http import MultiStatusResponse, statusForFailure,\
    ErrorResponse
from twext.web2.dav.util import normalizeURL, davXMLFromStream

log = Logger()


def http_PROPFIND(self, request):
    """
    Respond to a PROPFIND request. (RFC 2518, section 8.1)
    """
    if not self.exists():
        log.err("File not found: %s" % (self,))
        raise HTTPError(responsecode.NOT_FOUND)

    #
    # Check authentication and access controls
    #
    x = waitForDeferred(self.authorize(request, (davxml.Read(),)))
    yield x
    x.getResult()

    #
    # Read request body
    #
    try:
        doc = waitForDeferred(davXMLFromStream(request.stream))
        yield doc
        doc = doc.getResult()
    except ValueError, e:
        log.err("Error while handling PROPFIND body: %s" % (e,))
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, str(e)))

    if doc is None:
        # No request body means get all properties.
        search_properties = "all"
    else:
        #
        # Parse request
        #
        find = doc.root_element
        if not isinstance(find, davxml.PropertyFind):
            error = ("Non-%s element in PROPFIND request body: %s"
                     % (davxml.PropertyFind.sname(), find))
            log.err(error)
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, error))

        container = find.children[0]

        if isinstance(container, davxml.AllProperties):
            # Get all properties
            search_properties = "all"
        elif isinstance(container, davxml.PropertyName):
            # Get names only
            search_properties = "names"
        elif isinstance(container, davxml.PropertyContainer):
            properties = container.children
            search_properties = [(p.namespace, p.name) for p in properties]
        else:
            raise AssertionError("Unexpected element type in %s: %s"
                                 % (davxml.PropertyFind.sname(), container))

    #
    # Generate XML output stream
    #
    request_uri = request.uri
    depth = request.headers.getHeader("depth", "infinity")
    
    # By policy we will never allow a depth:infinity propfind
    if depth == "infinity":
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, davxml.PropfindFiniteDepth()))

    xml_responses = []

    # FIXME: take advantage of the new generative properties of findChildren

    my_url = normalizeURL(request_uri)
    if self.isCollection() and not my_url.endswith("/"):
        my_url += "/"

    # Do some optimisation of access control calculation by determining any inherited ACLs outside of
    # the child resource loop and supply those to the checkPrivileges on each child.
    filtered_aces = waitForDeferred(self.inheritedACEsforChildren(request))
    yield filtered_aces
    filtered_aces = filtered_aces.getResult()

    resources = [(self, my_url)]

    d = self.findChildren(depth, request, lambda x, y: resources.append((x, y)), (davxml.Read(),), inherited_aces=filtered_aces)
    x = waitForDeferred(d)
    yield x
    x.getResult()

    for resource, uri in resources:
        if search_properties is "names":
            try:
                resource_properties = waitForDeferred(resource.listProperties(request))
                yield resource_properties
                resource_properties = resource_properties.getResult()
            except:
                log.err("Unable to get properties for resource %r" % (resource,))
                raise

            properties_by_status = {
                responsecode.OK: [propertyName(p) for p in resource_properties]
            }
        else:
            properties_by_status = {
                responsecode.OK        : [],
                responsecode.NOT_FOUND : [],
            }

            if search_properties is "all":
                properties_to_enumerate = waitForDeferred(resource.listAllprop(request))
                yield properties_to_enumerate
                properties_to_enumerate = properties_to_enumerate.getResult()
            else:
                properties_to_enumerate = search_properties

            for property in properties_to_enumerate:
                has = waitForDeferred(resource.hasProperty(property, request))
                yield has
                has = has.getResult()
                if has:
                    try:
                        resource_property = waitForDeferred(resource.readProperty(property, request))
                        yield resource_property
                        resource_property = resource_property.getResult()
                    except:
                        f = Failure()

                        log.err("Error reading property %r for resource %s: %s" % (property, uri, f.value))

                        status = statusForFailure(f, "getting property: %s" % (property,))
                        if status not in properties_by_status:
                            properties_by_status[status] = []
                        properties_by_status[status].append(propertyName(property))
                    else:
                        if resource_property is not None:
                            properties_by_status[responsecode.OK].append(resource_property)
                        else:
                            properties_by_status[responsecode.NOT_FOUND].append(propertyName(property))
                else:
                    properties_by_status[responsecode.NOT_FOUND].append(propertyName(property))

        propstats = []

        for status in properties_by_status:
            properties = properties_by_status[status]
            if not properties: continue

            xml_status    = davxml.Status.fromResponseCode(status)
            xml_container = davxml.PropertyContainer(*properties)
            xml_propstat  = davxml.PropertyStatus(xml_container, xml_status)

            propstats.append(xml_propstat)

        xml_resource = davxml.HRef(uri)
        xml_response = davxml.PropertyStatusResponse(xml_resource, *propstats)

        xml_responses.append(xml_response)

    #
    # Return response
    #
    yield MultiStatusResponse(xml_responses)

http_PROPFIND = deferredGenerator(http_PROPFIND)

##
# Utilities
##

def propertyName(name):
    property_namespace, property_name = name
    pname = davxml.WebDAVUnknownElement()
    pname.namespace = property_namespace
    pname.name = property_name
    return pname
