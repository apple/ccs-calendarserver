##
# Copyright (c) 2006-2012 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks, returnValue,\
    maybeDeferred

from twext.python.log import Logger
from twext.web2 import responsecode
from twext.web2.dav.http import MultiStatusResponse
from twext.web2.dav.http import ErrorResponse
from twext.web2.dav.method.report import NumberOfMatchesWithinLimits
from twext.web2.dav.util import joinURL
from twext.web2.http import HTTPError, StatusResponse

from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import caldav_namespace, MaxInstances
from twistedcaldav.config import config
from txdav.common.icommondatastore import IndexedSearchException,\
    ConcurrentModification
from twistedcaldav.instance import TooManyInstancesError
from twistedcaldav.method import report_common
from twistedcaldav.query import calendarqueryfilter

from txdav.caldav.icalendarstore import TimeRangeLowerLimit, TimeRangeUpperLimit
from txdav.xml import element as davxml

log = Logger()

@inlineCallbacks
def report_urn_ietf_params_xml_ns_caldav_calendar_query(self, request, calendar_query):
    """
    Generate a calendar-query REPORT.
    (CalDAV-access-09, section 7.6)
    """

    # Verify root element
    if calendar_query.qname() != (caldav_namespace, "calendar-query"):
        raise ValueError("{CalDAV:}calendar-query expected as root element, not %s." % (calendar_query.sname(),))

    if not self.isCollection():
        parent = (yield self.locateParent(request, request.uri))
        if not parent.isPseudoCalendarCollection():
            log.err("calendar-query report is not allowed on a resource outside of a calendar collection %s" % (self,))
            raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Must be calendar collection or calendar resource"))

    responses = []

    xmlfilter = calendar_query.filter
    filter = calendarqueryfilter.Filter(xmlfilter)
    props  = calendar_query.props

    assert props is not None
    
    # Get the original timezone provided in the query, if any, and validate it now
    query_timezone = None
    query_tz = calendar_query.timezone
    if query_tz is not None and not query_tz.valid():
        msg = "CalDAV:timezone must contain one VTIMEZONE component only: %s" % (query_tz,)
        log.err(msg)
        raise HTTPError(ErrorResponse(
            responsecode.FORBIDDEN,
            (caldav_namespace, "valid-calendar-data"),
            "Invalid calendar-data",
        ))
    if query_tz:
        filter.settimezone(query_tz)
        query_timezone = tuple(calendar_query.timezone.calendar().subcomponents())[0]

    if props.qname() == ("DAV:", "allprop"):
        propertiesForResource = report_common.allPropertiesForResource
        generate_calendar_data = False

    elif props.qname() == ("DAV:", "propname"):
        propertiesForResource = report_common.propertyNamesForResource
        generate_calendar_data = False

    elif props.qname() == ("DAV:", "prop"):
        propertiesForResource = report_common.propertyListForResource
        
        # Verify that any calendar-data element matches what we can handle
        result, message, generate_calendar_data = report_common.validPropertyListCalendarDataTypeVersion(props)
        if not result:
            log.err(message)
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (caldav_namespace, "supported-calendar-data"),
                "Invalid calendar-data",
            ))
        
    else:
        raise AssertionError("We shouldn't be here")

    # Verify that the filter element is valid
    if (filter is None) or not filter.valid():
        log.err("Invalid filter element: %r" % (xmlfilter,))
        raise HTTPError(ErrorResponse(
            responsecode.FORBIDDEN,
            (caldav_namespace, "valid-filter"),
            "Invalid filter element",
        ))

    matchcount = [0]
    max_number_of_results = [config.MaxQueryWithDataResults if generate_calendar_data else None,]
    
    @inlineCallbacks
    def doQuery(calresource, uri):
        """
        Run a query on the specified calendar collection
        accumulating the query responses.
        @param calresource: the L{CalDAVResource} for a calendar collection.
        @param uri: the uri for the calendar collection resource.
        """
        
        @inlineCallbacks
        def queryCalendarObjectResource(resource, uri, name, calendar, timezone, query_ok=False, isowner=True):
            """
            Run a query on the specified calendar.
            @param resource: the L{CalDAVResource} for the calendar.
            @param uri: the uri of the resource.
            @param name: the name of the resource.
            @param calendar: the L{Component} calendar read from the resource.
            """
            
            # Handle private events access restrictions
            if not isowner:
                access = resource.accessMode
            else:
                access = None

            if query_ok or filter.match(calendar, access):
                # Check size of results is within limit
                matchcount[0] += 1
                if max_number_of_results[0] is not None and matchcount[0] > max_number_of_results[0]:
                    raise NumberOfMatchesWithinLimits(max_number_of_results[0])

                if name:
                    href = davxml.HRef.fromString(joinURL(uri, name))
                else:
                    href = davxml.HRef.fromString(uri)
            
                try:
                    yield report_common.responseForHref(request, responses, href, resource, propertiesForResource, props, isowner, calendar=calendar, timezone=timezone)
                except ConcurrentModification:
                    # This can happen because of a race-condition between the
                    # time we determine which resources exist and the deletion
                    # of one of these resources in another request.  In this
                    # case, we ignore the now missing resource rather
                    # than raise an error for the entire report.
                    log.err("Missing resource during query: %s" % (href,))
    
        # Check whether supplied resource is a calendar or a calendar object resource
        if calresource.isPseudoCalendarCollection():
            # Get the timezone property from the collection if one was not set in the query,
            # and store in the query filter for later use
            has_prop = (yield calresource.hasProperty((caldav_namespace, "calendar-timezone"), request))
            timezone = query_timezone
            if query_tz is None and has_prop:
                tz = (yield calresource.readProperty((caldav_namespace, "calendar-timezone"), request))
                filter.settimezone(tz)
                timezone = tuple(tz.calendar().subcomponents())[0]

            # Do some optimization of access control calculation by determining any inherited ACLs outside of
            # the child resource loop and supply those to the checkPrivileges on each child.
            filteredaces = (yield calresource.inheritedACEsforChildren(request))

            # Check private events access status
            isowner = (yield calresource.isOwner(request))

            # Check for disabled access
            if filteredaces is not None:
                index_query_ok = True
                try:
                    # Get list of children that match the search and have read
                    # access
                    records = yield maybeDeferred(calresource.index().indexedSearch, filter)
                except IndexedSearchException:
                    records = yield maybeDeferred(calresource.index().bruteForceSearch)
                    index_query_ok = False
                names = [name for name, ignore_uid, ignore_type in records]

                if not names:
                    returnValue(True)
                  
                # Now determine which valid resources are readable and which are not
                ok_resources = []
                yield calresource.findChildrenFaster(
                    "1",
                    request,
                    lambda x, y: ok_resources.append((x, y)),
                    None,
                    names,
                    (davxml.Read(),),
                    inherited_aces=filteredaces
                )
                
                for child, child_uri in ok_resources:
                    child_uri_name = child_uri[child_uri.rfind("/") + 1:]
                    
                    if generate_calendar_data or not index_query_ok:
                        calendar = (yield child.iCalendarForUser(request))
                        assert calendar is not None, "Calendar %s is missing from calendar collection %r" % (child_uri_name, self)
                    else:
                        calendar = None
                    
                    yield queryCalendarObjectResource(child, uri, child_uri_name, calendar, timezone, query_ok = index_query_ok, isowner=isowner)
        else:
            # Get the timezone property from the collection if one was not set in the query,
            # and store in the query object for later use
            timezone = query_timezone
            if query_tz is None:

                parent = (yield calresource.locateParent(request, uri))
                assert parent is not None and parent.isPseudoCalendarCollection()

                has_prop = (yield parent.hasProperty((caldav_namespace, "calendar-timezone"), request))
                if has_prop:
                    tz = (yield parent.readProperty((caldav_namespace, "calendar-timezone"), request))
                    filter.settimezone(tz)
                    timezone = tuple(tz.calendar().subcomponents())[0]

            # Check private events access status
            isowner = (yield calresource.isOwner(request))

            calendar = (yield calresource.iCalendarForUser(request))
            yield queryCalendarObjectResource(calresource, uri, None, calendar, timezone)

        returnValue(True)

    # Run report taking depth into account
    try:
        depth = request.headers.getHeader("depth", "0")
        yield report_common.applyToCalendarCollections(self, request, request.uri, depth, doQuery, (davxml.Read(),))
    except TooManyInstancesError, ex:
        log.err("Too many instances need to be computed in calendar-query report")
        raise HTTPError(ErrorResponse(
            responsecode.FORBIDDEN,
            MaxInstances.fromString(str(ex.max_allowed)),
            "Too many instances",
        ))
    except NumberOfMatchesWithinLimits:
        log.err("Too many matching components in calendar-query report")
        raise HTTPError(ErrorResponse(
            responsecode.FORBIDDEN,
            davxml.NumberOfMatchesWithinLimits(),
            "Too many components",
        ))
    except TimeRangeLowerLimit, e:
        raise HTTPError(ErrorResponse(
            responsecode.FORBIDDEN,
            caldavxml.MinDateTime(),
            "Time-range value too far in the past. Must be on or after %s." % (str(e.limit),)
        ))
    except TimeRangeUpperLimit, e:
        raise HTTPError(ErrorResponse(
            responsecode.FORBIDDEN,
            caldavxml.MaxDateTime(),
            "Time-range value too far in the future. Must be on or before %s." % (str(e.limit),)
        ))
    
    if not hasattr(request, "extendedLogItems"):
        request.extendedLogItems = {}
    request.extendedLogItems["responses"] = len(responses)

    returnValue(MultiStatusResponse(responses))
