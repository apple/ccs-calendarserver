# -*- test-case-name: twext.web2.dav.test.test_report_expand -*-
##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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
WebDAV prinicpal-property-search report
"""

__all__ = ["report_DAV__principal_property_search"]

from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.internet.defer import inlineCallbacks, returnValue

from twext.python.log import Logger
from twext.web2 import responsecode
from twext.web2.http import HTTPError, StatusResponse
from txdav.xml.base import PCDATAElement
from txdav.xml import element
from txdav.xml.element import dav_namespace
from twext.web2.dav.http import ErrorResponse, MultiStatusResponse
from twext.web2.dav.method import prop_common
from twext.web2.dav.method.report import NumberOfMatchesWithinLimits
from twext.web2.dav.method.report import max_number_of_matches
from twext.web2.dav.resource import isPrincipalResource

from twistedcaldav import customxml
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.config import config

log = Logger()


@inlineCallbacks
def report_DAV__principal_property_search(self, request,
    principal_property_search):
    """
    Generate a principal-property-search REPORT. (RFC 3744, section 9.4)
    Overrides twisted implementation, targeting only directory-enabled
    searching.
    """
    # Verify root element
    if not isinstance(principal_property_search, element.PrincipalPropertySearch):
        msg = "%s expected as root element, not %s." % (element.PrincipalPropertySearch.sname(), principal_property_search.sname())
        log.warn(msg)
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))

    # Should we AND (the default) or OR (if test="anyof")?
    testMode = principal_property_search.attributes.get("test", "allof")
    if testMode not in ("allof", "anyof"):
        msg = "Bad XML: unknown value for test attribute: %s" % (testMode,)
        log.warn(msg)
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))
    operand = "and" if testMode == "allof" else "or"

    # Are we narrowing results down to a single CUTYPE?
    cuType = principal_property_search.attributes.get("type", None)
    if cuType not in ("INDIVIDUAL", "GROUP", "RESOURCE", "ROOM", None):
        msg = "Bad XML: unknown value for type attribute: %s" % (cuType,)
        log.warn(msg)
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))

    # Only handle Depth: 0
    depth = request.headers.getHeader("depth", "0")
    if depth != "0":
        log.err("Error in principal-property-search REPORT, Depth set to %s" % (depth,))
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "Depth %s not allowed" % (depth,)))

    # Get any limit value from xml
    clientLimit = None

    # Get a single DAV:prop element from the REPORT request body
    propertiesForResource = None
    propElement = None
    propertySearches = []
    applyTo = False
    for child in principal_property_search.children:
        if child.qname() == (dav_namespace, "prop"):
            propertiesForResource = prop_common.propertyListForResource
            propElement = child

        elif child.qname() == (dav_namespace,
            "apply-to-principal-collection-set"):
            applyTo = True

        elif child.qname() == (dav_namespace, "property-search"):
            props = child.childOfType(element.PropertyContainer)
            props.removeWhitespaceNodes()

            match = child.childOfType(element.Match)
            caseless = match.attributes.get("caseless", "yes")
            if caseless not in ("yes", "no"):
                msg = "Bad XML: unknown value for caseless attribute: %s" % (caseless,)
                log.warn(msg)
                raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))
            caseless = (caseless == "yes")
            matchType = match.attributes.get("match-type", u"contains").encode("utf-8")
            if matchType not in ("starts-with", "contains", "equals"):
                msg = "Bad XML: unknown value for match-type attribute: %s" % (matchType,)
                log.warn(msg)
                raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))

            # Ignore any query strings under three letters
            matchText = str(match)
            if len(matchText) >= 3:
                propertySearches.append((props.children, matchText, caseless, matchType))

        elif child.qname() == (calendarserver_namespace, "limit"):
            try:
                nresults = child.childOfType(customxml.NResults)
                clientLimit = int(str(nresults))
            except (TypeError, ValueError,):
                msg = "Bad XML: unknown value for <limit> element"
                log.warn(msg)
                raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, msg))

    # Run report
    resultsWereLimited = None
    resources = []
    if applyTo or not hasattr(self, "directory"):
        for principalCollection in self.principalCollections():
            uri = principalCollection.principalCollectionURL()
            resource = (yield request.locateResource(uri))
            if resource:
                resources.append((resource, uri))
    else:
        resources.append((self, request.uri))

    # We need to access a directory service
    principalCollection = resources[0][0]
    if not hasattr(principalCollection, "directory"):
        # Use Twisted's implementation instead in this case
        result = orig_report_DAV__principal_property_search(self, request, principal_property_search)
        returnValue(result)

    dir = principalCollection.directory

    # See if we can take advantage of the directory
    fields = []
    nonDirectorySearches = []
    for props, match, caseless, matchType in propertySearches:
        nonDirectoryProps = []
        for prop in props:
            try:
                fieldName, match = principalCollection.propertyToField(
                    prop, match)
            except ValueError, e:
                raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, str(e)))
            if fieldName:
                fields.append((fieldName, match, caseless, matchType))
            else:
                nonDirectoryProps.append(prop)
        if nonDirectoryProps:
            nonDirectorySearches.append((nonDirectoryProps, match,
                caseless, matchType))

    matchingResources = []
    matchcount = 0

    # nonDirectorySearches are ignored
    if fields:

        records = (yield dir.recordsMatchingFieldsWithCUType(fields,
            operand=operand, cuType=cuType))

        for record in records:
            resource = principalCollection.principalForRecord(record)
            if resource:
                matchingResources.append(resource)

                # We've determined this is a matching resource
                matchcount += 1
                if clientLimit is not None and matchcount >= clientLimit:
                    resultsWereLimited = ("client", matchcount)
                    break
                if matchcount >= config.MaxPrincipalSearchReportResults:
                    resultsWereLimited = ("server", matchcount)
                    break

    # Generate the response
    responses = []
    for resource in matchingResources:
        url = resource.url()
        yield prop_common.responseForHref(
            request,
            responses,
            element.HRef.fromString(url),
            resource,
            propertiesForResource,
            propElement
        )

    if resultsWereLimited is not None:
        if resultsWereLimited[0] == "server":
            log.err("Too many matching resources in "
                    "principal-property-search report")
        responses.append(element.StatusResponse(
            element.HRef.fromString(request.uri),
            element.Status.fromResponseCode(
                responsecode.INSUFFICIENT_STORAGE_SPACE
            ),
            element.Error(element.NumberOfMatchesWithinLimits()),
            element.ResponseDescription("Results limited by %s at %d"
                                       % resultsWereLimited),
        ))
    returnValue(MultiStatusResponse(responses))

@deferredGenerator
def orig_report_DAV__principal_property_search(self, request, principal_property_search):
    """
    Generate a principal-property-search REPORT. (RFC 3744, section 9.4)
    """

    # Verify root element
    if not isinstance(principal_property_search, element.PrincipalPropertySearch):
        raise ValueError("%s expected as root element, not %s."
                         % (element.PrincipalPropertySearch.sname(), principal_property_search.sname()))

    # Only handle Depth: 0
    depth = request.headers.getHeader("depth", "0")
    if depth != "0":
        log.err("Error in prinicpal-property-search REPORT, Depth set to %s" % (depth,))
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "Depth %s not allowed" % (depth,)))
    
    # Get a single DAV:prop element from the REPORT request body
    propertiesForResource = None
    propElement = None
    propertySearches = []
    applyTo = False
    for child in principal_property_search.children:
        if child.qname() == (dav_namespace, "prop"):
            propertiesForResource = prop_common.propertyListForResource
            propElement = child
        elif child.qname() == (dav_namespace, "apply-to-principal-collection-set"):
            applyTo = True
        elif child.qname() == (dav_namespace, "property-search"):
            props = child.childOfType(element.PropertyContainer)
            props.removeWhitespaceNodes()
            match = child.childOfType(element.Match)
            propertySearches.append((props.children, str(match).lower()))
    
    def nodeMatch(node, match):
        """
        See if the content of the supplied node matches the supplied text.
        Try to follow the matching guidance in rfc3744 section 9.4.1.
        @param prop:  the property element to match.
        @param match: the text to match against.
        @return:      True if the property matches, False otherwise.
        """
        node.removeWhitespaceNodes()
        for child in node.children:
            if isinstance(child, PCDATAElement):
                comp = str(child).lower()
                if comp.find(match) != -1:
                    return True
            else:
                return nodeMatch(child, match)
        else:
            return False
        
    @deferredGenerator
    def propertySearch(resource, request):
        """
        Test the resource to see if it contains properties matching the
        property-search specification in this report.
        @param resource: the L{DAVFile} for the resource to test.
        @param request:  the current request.
        @return:         True if the resource has matching properties, False otherwise.
        """
        for props, match in propertySearches:
            # Test each property
            for prop in props:
                try:
                    propvalue = waitForDeferred(resource.readProperty(prop.qname(), request))
                    yield propvalue
                    propvalue = propvalue.getResult()
                    if propvalue and not nodeMatch(propvalue, match):
                        yield False
                        return
                except HTTPError:
                    # No property => no match
                    yield False
                    return
        
        yield True

    # Run report
    try:
        resources = []
        responses = []
        matchcount = 0

        if applyTo:
            for principalCollection in self.principalCollections():
                uri = principalCollection.principalCollectionURL()
                resource = waitForDeferred(request.locateResource(uri))
                yield resource
                resource = resource.getResult()
                if resource:
                    resources.append((resource, uri))
        else:
            resources.append((self, request.uri))

        # Loop over all collections and principal resources within
        for resource, ruri in resources:

            # Do some optimisation of access control calculation by determining any inherited ACLs outside of
            # the child resource loop and supply those to the checkPrivileges on each child.
            filteredaces = waitForDeferred(resource.inheritedACEsforChildren(request))
            yield filteredaces
            filteredaces = filteredaces.getResult()

            children = []
            d = waitForDeferred(resource.findChildren("infinity", request, lambda x, y: children.append((x,y)),
                                                      privileges=(element.Read(),), inherited_aces=filteredaces))
            yield d
            d.getResult()

            for child, uri in children:
                if isPrincipalResource(child):
                    d = waitForDeferred(propertySearch(child, request))
                    yield d
                    d = d.getResult()
                    if d:
                        # Check size of results is within limit
                        matchcount += 1
                        if matchcount > max_number_of_matches:
                            raise NumberOfMatchesWithinLimits(max_number_of_matches)
    
                        d = waitForDeferred(prop_common.responseForHref(
                            request,
                            responses,
                            element.HRef.fromString(uri),
                            child,
                            propertiesForResource,
                            propElement
                        ))
                        yield d
                        d.getResult()

    except NumberOfMatchesWithinLimits:
        log.err("Too many matching components in prinicpal-property-search report")
        raise HTTPError(ErrorResponse(
            responsecode.FORBIDDEN,
            element.NumberOfMatchesWithinLimits()
        ))

    yield MultiStatusResponse(responses)
