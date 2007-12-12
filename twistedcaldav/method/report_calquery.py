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
CalDAV calendar-query report
"""

__all__ = ["report_urn_ietf_params_xml_ns_caldav_calendar_query"]

from twisted.internet.defer import deferredGenerator, succeed, waitForDeferred
from twisted.python import log
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.element.base import dav_namespace
from twisted.web2.dav.http import ErrorResponse, MultiStatusResponse
from twisted.web2.dav.method.report import NumberOfMatchesWithinLimits
from twisted.web2.dav.util import joinURL
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.method import report_common

import urllib

max_number_of_results = 1000

def report_urn_ietf_params_xml_ns_caldav_calendar_query(self, request, calendar_query):
    """
    Generate a calendar-query REPORT.
    (CalDAV-access-09, section 7.6)
    """

    # Verify root element
    if calendar_query.qname() != (caldav_namespace, "calendar-query"):
        raise ValueError("{CalDAV:}calendar-query expected as root element, not %s." % (calendar_query.sname(),))

    if not self.isCollection():
        parent = waitForDeferred(self.locateParent(request, request.uri))
        yield parent
        parent = parent.getResult()
        if not parent.isPseudoCalendarCollection():
            log.err("calendar-query report is not allowed on a resource outside of a calendar collection %s" % (self,))
            raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Must be calendar collection or calendar resource"))

    responses = []

    filter = calendar_query.filter
    query  = calendar_query.query

    assert query is not None
    
    # Get the original timezone provided in the query, if any, and validate it now
    query_tz = calendar_query.timezone
    if query_tz is not None and not query_tz.valid():
        log.err("CalDAV:timezone must contain one VTIMEZONE component only: %s" % (query_tz,))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-calendar-data")))
    if query_tz:
        filter.settimezone(query_tz)

    if query.qname() == ("DAV:", "allprop"):
        propertiesForResource = report_common.allPropertiesForResource
        generate_calendar_data = False

    elif query.qname() == ("DAV:", "propname"):
        propertiesForResource = report_common.propertyNamesForResource
        generate_calendar_data = False

    elif query.qname() == ("DAV:", "prop"):
        propertiesForResource = report_common.propertyListForResource
        
        # Verify that any calendar-data element matches what we can handle
        result, message, generate_calendar_data = report_common.validPropertyListCalendarDataTypeVersion(query)
        if not result:
            log.err(message)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "supported-calendar-data")))
        
    else:
        raise AssertionError("We shouldn't be here")

    # Verify that the filter element is valid
    if (filter is None) or not filter.valid():
        log.err("Invalid filter element: %r" % (filter,))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "valid-filter")))

    matchcount = [0]
    def doQuery(calresource, uri):
        """
        Run a query on the specified calendar collection
        accumulating the query responses.
        @param calresource: the L{CalDAVFile} for a calendar collection.
        @param uri: the uri for the calendar collecton resource.
        """
        
        def queryCalendarObjectResource(resource, uri, name, calendar, query_ok = False):
            """
            Run a query on the specified calendar.
            @param resource: the L{CalDAVFile} for the calendar.
            @param uri: the uri of the resource.
            @param name: the name of the resource.
            @param calendar: the L{Component} calendar read from the resource.
            """
            
            if query_ok or filter.match(calendar):
                # Check size of results is within limit
                matchcount[0] += 1
                if matchcount[0] > max_number_of_results:
                    raise NumberOfMatchesWithinLimits

                if name:
                    href = davxml.HRef.fromString(joinURL(uri, name))
                else:
                    href = davxml.HRef.fromString(uri)
            
                return report_common.responseForHref(request, responses, href, resource, calendar, propertiesForResource, query)
            else:
                return succeed(None)
    
        # Check whether supplied resource is a calendar or a calendar object resource
        if calresource.isPseudoCalendarCollection():
            # Get the timezone property from the collection if one was not set in the query,
            # and store in the query filter for later use
            has_prop = waitForDeferred(calresource.hasProperty((caldav_namespace, "calendar-timezone"), request))
            yield has_prop
            has_prop = has_prop.getResult()
            if query_tz is None and has_prop:
                tz = waitForDeferred(calresource.readProperty((caldav_namespace, "calendar-timezone"), request))
                yield tz
                tz = tz.getResult()
                filter.settimezone(tz)

            # Do some optimisation of access control calculation by determining any inherited ACLs outside of
            # the child resource loop and supply those to the checkPrivileges on each child.
            filteredaces = waitForDeferred(calresource.inheritedACEsforChildren(request))
            yield filteredaces
            filteredaces = filteredaces.getResult()
        
            # Check for disabled access
            if filteredaces is not None:
                # See whether the filter is valid for an index only query
                index_query_ok = calresource.index().searchValid(filter)
            
                # Get list of children that match the search and have read access
                names = [name for name, ignore_uid, ignore_type in calresource.index().search(filter)]
                if not names:
                    yield None
                    return
                  
                # Now determine which valid resources are readable and which are not
                ok_resources = []
                d = calresource.findChildrenFaster(
                    "1",
                    request,
                    lambda x, y: ok_resources.append((x, y)),
                    None,
                    names,
                    (davxml.Read(),),
                    inherited_aces=filteredaces
                )
                x = waitForDeferred(d)
                yield x
                x.getResult()
                
                for child, child_uri in ok_resources:
                    child_uri_name = child_uri[child_uri.rfind("/") + 1:]
                    child_path_name = urllib.unquote(child_uri_name)
                    
                    if generate_calendar_data or not index_query_ok:
                        calendar = calresource.iCalendar(child_path_name)
                        assert calendar is not None, "Calendar %s is missing from calendar collection %r" % (child_uri_name, self)
                    else:
                        calendar = None
                    
                    d = waitForDeferred(queryCalendarObjectResource(child, uri, child_uri_name, calendar, query_ok = index_query_ok))
                    yield d
                    d.getResult()
        else:
            # Get the timezone property from the collection if one was not set in the query,
            # and store in the query object for later use
            if query_tz is None:

                parent = waitForDeferred(calresource.locateParent(request, uri))
                yield parent
                parent = parent.getResult()
                assert parent is not None and parent.isPseudoCalendarCollection()

                has_prop = waitForDeferred(parent.hasProperty((caldav_namespace, "calendar-timezone"), request))
                yield has_prop
                has_prop = has_prop.getResult()
                if has_prop:
                    tz = waitForDeferred(parent.readProperty((caldav_namespace, "calendar-timezone"), request))
                    yield tz
                    tz = tz.getResult()
                    filter.settimezone(tz)

            calendar = calresource.iCalendar()
            d = waitForDeferred(queryCalendarObjectResource(calresource, uri, None, calendar))
            yield d
            d.getResult()

    doQuery = deferredGenerator(doQuery)

    # Run report taking depth into account
    try:
        depth = request.headers.getHeader("depth", "0")
        d = waitForDeferred(report_common.applyToCalendarCollections(self, request, request.uri, depth, doQuery, (davxml.Read(),)))
        yield d
        d.getResult()
    except NumberOfMatchesWithinLimits:
        log.err("Too many matching components in calendar-query report")
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (dav_namespace, "number-of-matches-within-limits")))
    
    yield MultiStatusResponse(responses)

report_urn_ietf_params_xml_ns_caldav_calendar_query = deferredGenerator(report_urn_ietf_params_xml_ns_caldav_calendar_query)
