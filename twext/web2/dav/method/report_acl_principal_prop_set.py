# -*- test-case-name: twext.web2.dav.test.test_report_expand -*-
##
# Copyright (c) 2006-2013 Apple Computer, Inc. All rights reserved.
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
WebDAV acl-prinicpal-prop-set report
"""

__all__ = ["report_DAV__acl_principal_prop_set"]

from twisted.internet.defer import deferredGenerator, waitForDeferred

from twext.python.log import Logger
from twext.web2 import responsecode
from twext.web2.http import HTTPError, StatusResponse
from txdav.xml import element as davxml
from twext.web2.dav.http import ErrorResponse
from twext.web2.dav.http import MultiStatusResponse
from twext.web2.dav.method import prop_common
from twext.web2.dav.method.report import NumberOfMatchesWithinLimits
from twext.web2.dav.method.report import max_number_of_matches

log = Logger()


def report_DAV__acl_principal_prop_set(self, request, acl_prinicpal_prop_set):
    """
    Generate an acl-prinicpal-prop-set REPORT. (RFC 3744, section 9.2)
    """
    # Verify root element
    if not isinstance(acl_prinicpal_prop_set, davxml.ACLPrincipalPropSet):
        raise ValueError("%s expected as root element, not %s."
                         % (davxml.ACLPrincipalPropSet.sname(), acl_prinicpal_prop_set.sname()))

    # Depth must be "0"
    depth = request.headers.getHeader("depth", "0")
    if depth != "0":
        log.error("Error in prinicpal-prop-set REPORT, Depth set to %s" % (depth,))
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "Depth %s not allowed" % (depth,)))
    
    #
    # Check authentication and access controls
    #
    x = waitForDeferred(self.authorize(request, (davxml.ReadACL(),)))
    yield x
    x.getResult()

    # Get a single DAV:prop element from the REPORT request body
    propertiesForResource = None
    propElement = None
    for child in acl_prinicpal_prop_set.children:
        if child.qname() == ("DAV:", "prop"):
            if propertiesForResource is not None:
                log.error("Only one DAV:prop element allowed")
                raise HTTPError(StatusResponse(
                    responsecode.BAD_REQUEST,
                    "Only one DAV:prop element allowed"
                ))
            propertiesForResource = prop_common.propertyListForResource
            propElement = child

    if propertiesForResource is None:
        log.error("Error in acl-principal-prop-set REPORT, no DAV:prop element")
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "No DAV:prop element"))

    # Enumerate principals on ACL in current resource
    principals = []

    acl = waitForDeferred(self.accessControlList(request))
    yield acl
    acl = acl.getResult()

    for ace in acl.children:
        resolved = waitForDeferred(self.resolvePrincipal(ace.principal.children[0], request))
        yield resolved
        resolved = resolved.getResult()
        if resolved is not None and resolved not in principals:
            principals.append(resolved)

    # Run report for each referenced principal
    try:
        responses = []
        matchcount = 0
        for principal in principals:
            # Check size of results is within limit
            matchcount += 1
            if matchcount > max_number_of_matches:
                raise NumberOfMatchesWithinLimits(max_number_of_matches)

            resource = waitForDeferred(request.locateResource(str(principal)))
            yield resource
            resource = resource.getResult()

            if resource is not None:
                #
                # Check authentication and access controls
                #
                x = waitForDeferred(resource.authorize(request, (davxml.Read(),)))
                yield x
                try:
                    x.getResult()
                except HTTPError:
                    responses.append(davxml.StatusResponse(
                        principal,
                        davxml.Status.fromResponseCode(responsecode.FORBIDDEN)
                    ))
                else:
                    d = waitForDeferred(prop_common.responseForHref(
                        request,
                        responses,
                        principal,
                        resource,
                        propertiesForResource,
                        propElement
                    ))
                    yield d
                    d.getResult()
            else:
                log.error("Requested principal resource not found: %s" % (str(principal),))
                responses.append(davxml.StatusResponse(
                    principal,
                    davxml.Status.fromResponseCode(responsecode.NOT_FOUND)
                ))

    except NumberOfMatchesWithinLimits:
        log.error("Too many matching components")
        raise HTTPError(ErrorResponse(
            responsecode.FORBIDDEN,
            davxml.NumberOfMatchesWithinLimits()
        ))

    yield MultiStatusResponse(responses)

report_DAV__acl_principal_prop_set = deferredGenerator(report_DAV__acl_principal_prop_set)
