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

__all__ = [
    "applyToCalendarCollections",
    "responseForHref",
    "allPropertiesForResource",
    "propertyNamesForResource",
    "propertyListForResource",
    "generateFreeBusyInfo",
    "processEventFreeBusy",
    "processFreeBusyFreeBusy",
    "buildFreeBusyResult",
]

from twisted.python import log
from twisted.python.failure import Failure
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.element.base import WebDAVElement
from twisted.web2.dav.http import statusForFailure
from twisted.web2.dav.method.propfind import propertyName
from twisted.web2.dav.method.report import NumberOfMatchesWithinLimits
from twisted.web2.dav.method.report import max_number_of_matches
from twisted.web2.dav.util import joinURL

from twistedcaldav import caldavxml
from twistedcaldav import constants
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.dateops import clipPeriod, normalizePeriodList, timeRangesOverlap
from twistedcaldav.ical import Component
from twistedcaldav.ical import Property

from vobject.icalendar import utc

import datetime
import md5
import time

def applyToCalendarCollections(resource, request, request_uri, depth, apply, privileges):
    """
    Run an operation on all calendar collections, starting at the specified
    root, to the specified depth. This involves scanning the URI hierarchy
    down from the root. Return a MultiStatus element of all responses.
    
    @param request: the L{IRequest} for the current request.
    @param resource: the L{CalDAVFile} representing the root to start scanning
        for calendar collections.
    @param depth: the depth to do the scan.
    @param apply: the function to apply to each calendar collection located
        during the scan.
    @param privileges: the privileges that must exist on the calendar collection.
    """

    # First check the privilege on this resource
    error = resource.checkAccess(request, privileges)
    if error:
        return

    # When scanning we only go down as far as a calendar collection - not into one
    if resource.isPseudoCalendarCollection():
        resources = [(resource, request_uri)]
        doJoin = False
    elif not resource.isCollection():
        resources = [(resource, request_uri)]
        doJoin = False
    else:
        resources = []
        resources.extend(resource.findCalendarCollectionsWithPrivileges(depth, privileges, request))
        doJoin = True
        
    for calresource, uri in resources:
        if doJoin:
            uri = joinURL(request_uri, uri)
        apply(calresource, uri)

def responseForHref(request, responses, href, resource, calendar, propertiesForResource, propertyreq):
    """
    Create an appropriate property status response for the given resource.

    @param request: the L{IRequest} for the current request.
    @param responses: the list of responses to append the result of this method to.
    @param href: the L{HRef} element of the resource being targetted.
    @param resource: the L{CalDAVFile} for the targetted resource.
    @param calendar: the L{Component} for the calendar for the resource. This may be None
                     if the calendar has not already been read in, in which case the resource
                     will be used to get the calendar if needed.
    @param propertiesForResource: the method to use to get the list of properties to return.
    @param propertyreq: the L{PropertyContainer} element for the properties of interest.
    """

    properties_by_status = propertiesForResource(request, propertyreq, resource, calendar)
    
    for status in properties_by_status:
        properties = properties_by_status[status]
        if properties:
            responses.append(
                davxml.PropertyStatusResponse(
                    href,
                    davxml.PropertyStatus(
                        davxml.PropertyContainer(*properties),
                        davxml.Status.fromResponseCode(status)
                    )
                )
            )

def allPropertiesForResource(request, prop, resource, calendar=None): #@UnusedVariable
    """
    Return all (non-hidden) properties for the specified resource.
    @param request: the L{IRequest} for the current request.
    @param prop: the L{PropertyContainer} element for the properties of interest.
    @param resource: the L{CalDAVFile} for the targetted resource.
    @param calendar: the L{Component} for the calendar for the resource. This may be None
                     if the calendar has not already been read in, in which case the resource
                     will be used to get the calendar if needed.
    @return: a map of OK and NOT FOUND property values.
    """
    props = resource.listAllprop(request)

    return _namedPropertiesForResource(request, props, resource, calendar)

def propertyNamesForResource(request, prop, resource, calendar=None): #@UnusedVariable
    """
    Return property names for all properties on the specified resource.
    @param request: the L{IRequest} for the current request.
    @param prop: the L{PropertyContainer} element for the properties of interest.
    @param resource: the L{CalDAVFile} for the targetted resource.
    @param calendar: the L{Component} for the calendar for the resource. This may be None
                     if the calendar has not already been read in, in which case the resource
                     will be used to get the calendar if needed.
    @return: a map of OK and NOT FOUND property values.
    """
    properties_by_status = {
        responsecode.OK: [propertyName(p) for p in resource.listProperties(request)]
    }
    
    return properties_by_status

def propertyListForResource(request, prop, resource, calendar=None):
    """
    Return the specified properties on the specified resource.
    @param request: the L{IRequest} for the current request.
    @param prop: the L{PropertyContainer} element for the properties of interest.
    @param resource: the L{CalDAVFile} for the targetted resource.
    @param calendar: the L{Component} for the calendar for the resource. This may be None
                     if the calendar has not already been read in, in which case the resource
                     will be used to get the calendar if needed.
    @return: a map of OK and NOT FOUND property values.
    """
    
    return _namedPropertiesForResource(request, prop.children, resource, calendar)

def validPropertyListCalendarDataTypeVersion(prop):
    """
    If the supplied prop element includes a calendar-data element, verify that
    the type/version on that matches what we can handle..

    @param prop: the L{PropertyContainer} element for the properties of interest.
    @return:     a tuple: (True/False if the calendar-data element is one we can handle or not present,
                           error message).
    """
    
    result = True
    message = ""
    for property in prop.children:
        if isinstance(property, caldavxml.CalendarData):
            if not property.verifyTypeVersion([("text/calendar", "2.0")]):
                result = False
                message = "Calendar-data element type/version not supported: content-type: %s, version: %s" % (property.content_type,property.version)
            break

    return result, message

def _namedPropertiesForResource(request, props, resource, calendar=None):
    """
    Return the specified properties on the specified resource.
    @param request: the L{IRequest} for the current request.
    @param props: a list of property elements or qname tuples for the properties of interest.
    @param resource: the L{CalDAVFile} for the targetted resource.
    @param calendar: the L{Component} for the calendar for the resource. This may be None
                     if the calendar has not already been read in, in which case the resource
                     will be used to get the calendar if needed.
    @return: a map of OK and NOT FOUND property values.
    """
    properties_by_status = {
        responsecode.OK        : [],
        responsecode.NOT_FOUND : [],
    }
    
    for property in props:
        if isinstance(property, caldavxml.CalendarData):
            if calendar:
                propvalue = property.elementFromCalendar(calendar)
            else:
                propvalue = property.elementFromResource(resource)
            if propvalue is None:
                raise ValueError("Invalid CalDAV:calendar-data for request: %r" % (property,))
            properties_by_status[responsecode.OK].append(propvalue)
            continue
    
        if isinstance(property, WebDAVElement):
            qname = property.qname()
        else:
            qname = property
    
        if qname in resource.listProperties(request):
            try:
                properties_by_status[responsecode.OK].append(resource.readProperty(qname, request))
            except:
                f = Failure()
    
                log.err("Error reading property %r for resource %s: %s" % (qname, request.uri, f.value))
    
                status = statusForFailure(f, "getting property: %s" % (qname,))
                if status not in properties_by_status: properties_by_status[status] = []
                properties_by_status[status].append(propertyName(qname))
        else:
            log.err("Can't find property %r for resource %s" % (qname, request.uri))
            properties_by_status[responsecode.NOT_FOUND].append(propertyName(qname))
    
    return properties_by_status
    
def generateFreeBusyInfo(request, calresource, fbinfo, timerange, matchtotal, excludeuid=None):
    """
    Run a free busy report on the specified calendar collection
    accumulating the free busy info for later processing.
    @param request:     the L{IRequest} for the current request.
    @param calresource: the L{CalDAVFile} for a calendar collection.
    @param fbinfo:      the array of busy periods to update.
    @param timerange:   the L{TimeRange} for the query.
    @param matchtotal:  the running total for the number of matches.
    @param excludeuid:  the C{str} containing a UID value to exclude any components with that
        UID from contributing to free-busy.
    """
    
    # First check the privilege on this collection
    error = calresource.checkAccess(request, (caldavxml.ReadFreeBusy(),))
    if error:
        return matchtotal

    #
    # What we do is a fake calendar-query for VEVENT/VFREEBUSYs in the specified time-range.
    # We then take those results and merge them into one VFREEBUSY component
    # with appropriate FREEBUSY properties, and return that single item as iCal data.
    #

    # Create fake filter element to match time-range
    filter =  caldavxml.Filter(
                  caldavxml.ComponentFilter(
                      caldavxml.ComponentFilter(
                          timerange,
                          name="VEVENT",
                      ),
                      caldavxml.ComponentFilter(
                          timerange,
                          name="VFREEBUSY",
                      ),
                      name="VCALENDAR",
                   )
              )

    # Get the timezone property from the collection, and store in the query filter
    # for use during the query itself.
    if calresource.hasProperty((caldav_namespace, "calendar-timezone"), request):
        tz = calresource.readProperty((caldav_namespace, "calendar-timezone"), request)
    else:
        tz = None
    tzinfo = filter.settimezone(tz)

    # Do some optimisation of access control calculation by determining any inherited ACLs outside of
    # the child resource loop and supply those to the checkAccess on each child.
    filteredaces = calresource.inheritedACEsforChildren(request)

    for name, uid, type in calresource.index().search(filter): #@UnusedVariable
        
        # Ignore ones of this UID
        if excludeuid and (excludeuid == uid):
            continue

        # Check privileges - must have at least CalDAV:read-free-busy
        child = calresource.getChild(name)
        error = child.checkAccess(request, (caldavxml.ReadFreeBusy(),), inheritedaces=filteredaces)
        if error:
            continue

        calendar = calresource.iCalendar(name)
        assert calendar is not None, "Calendar %s is missing from calendar collection %r" % (name, calresource)
        
        if filter.match(calendar):
            # Check size of results is within limit
            matchtotal += 1
            if matchtotal > max_number_of_matches:
                raise NumberOfMatchesWithinLimits

            if calendar.mainType() == "VEVENT":
                processEventFreeBusy(calendar, fbinfo, timerange, tzinfo)
            elif calendar.mainType() == "VFREEBUSY":
                processFreeBusyFreeBusy(calendar, fbinfo, timerange)
            else:
                assert "Free-busy query returned unwanted component: %s in %r", (name, calresource,)
    
    return matchtotal

def processEventFreeBusy(calendar, fbinfo, timerange, tzinfo):
    """
    Extract free busy data from a VEVENT component.
    @param calendar: the L{Component} that is the VCALENDAR containing the VEVENT's.
    @param fbinfo: the tuple used to store the three types of fb data.
    @param timerange: the time range to restrict free busy data to.
    @param tzinfo: the L{datetime.tzinfo} for the timezone to use for floating/all-day events.
    """
    
    # Expand out the set of instances for the event with in the required range
    instances = calendar.expandTimeRanges(timerange.end)
    
    # Can only do timed events
    for key in instances:
        instance = instances[key]
        if not isinstance(instance.start, datetime.datetime):
            return
        break
    else:
        return
        
    for key in instances:
        instance = instances[key]

        # Apply a timezone to any floating times
        fbstart = instance.start
        if fbstart.tzinfo is None:
            fbstart = fbstart.replace(tzinfo=tzinfo)
        fbend = instance.end
        if fbend.tzinfo is None:
            fbend = fbend.replace(tzinfo=tzinfo)
        
        # Check TRANSP property of underlying component
        if instance.component.hasProperty("TRANSP"):
            # If its TRANSPARENT we always ignore it
            if instance.component.propertyValue("TRANSP") == "TRANSPARENT":
                continue
        
        # Determine status
        if instance.component.hasProperty("STATUS"):
            status = instance.component.propertyValue("STATUS")
        else:
            status = "CONFIRMED"
        
        # Ignore cancelled
        if status == "CANCELLED":
            continue

        # Clip period for this instance - use duration for period end if that
        # is what original component used
        if instance.component.hasProperty("DURATION"):
            period = (fbstart, fbend - fbstart)
        else:
            period = (fbstart, fbend)
        clipped = clipPeriod(period, (timerange.start, timerange.end))
        
        # Double check for overlap
        if clipped:
            if status == "TENTATIVE":
                fbinfo[1].append(clipped)
            else:
                fbinfo[0].append(clipped)

def processFreeBusyFreeBusy(calendar, fbinfo, timerange):
    """
    Extract FREEBUSY data from a VFREEBUSY component.
    @param calendar: the L{Component} that is the VCALENDAR containing the VFREEBUSY's.
    @param fbinfo: the tuple used to store the three types of fb data.
    @param timerange: the time range to restrict free busy data to.
    """
    
    for vfb in [x for x in calendar.subcomponents() if x.name() == "VFREEBUSY"]:
        # First check any start/end in the actual component
        start = vfb.getStartDateUTC()
        end = vfb.getEndDateUTC()
        if start and end:
            if not timeRangesOverlap(start, end, timerange.start, timerange.end):
                continue
        
        # Now look at each FREEBUSY property
        for fb in vfb.properties("FREEBUSY"):
            # Check the type
            if "FBTYPE" in fb.params():
                fbtype = fb.params()["FBTYPE"][0]
            else:
                fbtype = "BUSY"
            if fbtype == "FREE":
                continue
            
            # Look at each period in the propert
            assert isinstance(fb.value(), list), "FREEBUSY property does not contain a list of values: %r" % (fb,)
            for period in fb.value():
                # Clip period for this instance
                clipped = clipPeriod(period, (timerange.start, timerange.end))
                if clipped:
                    mapper = {"BUSY": 0, "BUSY-TENTATIVE": 1, "BUSY-UNAVAILABLE": 2}
                    fbinfo[mapper.get(fbtype, 0)].append(clipped)

def buildFreeBusyResult(fbinfo, timerange, organizer=None, attendee=None, uid=None):
    """
    Generate a VCALENDAR object containing a single VFREEBUSY that is the
    aggregate of the free busy info passed in.
    @param fbinfo:    the array of busy periods to use.
    @param timerange: the L{TimeRange} for the query.
    @param organizer: the L{Property} for the Organizer of the free busy request, or None.
    @param attendee:  the L{Property} for the Attendee responding to the free busy request, or None.
    @param uid:       the UID value from the free busy request.
    @return:          the L{Component} containing the calendar data.
    """
    
    # Merge overlapping time ranges in each fb info section
    normalizePeriodList(fbinfo[0])
    normalizePeriodList(fbinfo[1])
    normalizePeriodList(fbinfo[2])
    
    # Now build a new calendar object with the free busy info we have
    fbcalendar = Component("VCALENDAR")
    fbcalendar.addProperty(Property("PRODID", constants.ICALENDAR_PRODID))
    fb = Component("VFREEBUSY")
    fbcalendar.addComponent(fb)
    if organizer is not None:
        fb.addProperty(organizer)
    if attendee is not None:
        fb.addProperty(attendee)
    fb.addProperty(Property("DTSTART", timerange.start))
    fb.addProperty(Property("DTEND", timerange.end))
    fb.addProperty(Property("DTSTAMP", datetime.datetime.now(tz=utc)))
    if len(fbinfo[0]) != 0:
        fb.addProperty(Property("FREEBUSY", fbinfo[0], {"FBTYPE": ["BUSY"]}))
    if len(fbinfo[1]) != 0:
        fb.addProperty(Property("FREEBUSY", fbinfo[1], {"FBTYPE": ["BUSY-TENTATIVE"]}))
    if len(fbinfo[2]) != 0:
        fb.addProperty(Property("FREEBUSY", fbinfo[2], {"FBTYPE": ["BUSY-UNAVAILABLE"]}))
    if uid is not None:
        fb.addProperty(Property("UID", uid))
    else:
        uid = md5.new(str(fbcalendar) + str(time.time())).hexdigest()
        fb.addProperty(Property("UID", uid))

    return fbcalendar
