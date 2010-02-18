##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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
CalDAV XML Support.

This module provides XML utilities for use with CalDAV.

This API is considered private to static.py and is therefore subject to
change.

See draft spec: http://ietf.webdav.org/caldav/draft-dusseault-caldav.txt
"""

import datetime

from vobject.icalendar import utc, TimezoneComponent

from twext.web2.dav import davxml

from twext.log import Logger

from twistedcaldav.dateops import clipPeriod, timeRangesOverlap
from twistedcaldav.ical import Component as iComponent
from twistedcaldav.ical import Property as iProperty
from twistedcaldav.ical import parse_date_or_datetime

log = Logger()

##
# CalDAV objects
##

caldav_namespace = "urn:ietf:params:xml:ns:caldav"

caldav_full_compliance = (
    "calendar-access",
    "calendar-schedule",
    "calendar-auto-schedule",
    "calendar-availability",
    "inbox-availability",
)

caldav_implicit_compliance = (
    "calendar-access",
    "calendar-auto-schedule",
    "calendar-availability",
    "inbox-availability",
)

class CalDAVElement (davxml.WebDAVElement):
    """
    CalDAV XML element.
    """
    namespace = caldav_namespace

class CalDAVEmptyElement (davxml.WebDAVEmptyElement):
    """
    CalDAV element with no contents.
    """
    namespace = caldav_namespace

class CalDAVTextElement (davxml.WebDAVTextElement):
    """
    CalDAV element containing PCDATA.
    """
    namespace = caldav_namespace

class CalDAVTimeRangeElement (CalDAVEmptyElement):
    """
    CalDAV element containing a time range.
    """
    allowed_attributes = {
        "start": False,
        "end"  : False,
    }

    def __init__(self, *children, **attributes):
        super(CalDAVTimeRangeElement, self).__init__(*children, **attributes)

        # One of start or end must be present
        if "start" not in attributes and "end" not in attributes:
            raise ValueError("One of 'start' or 'end' must be present in CALDAV:time-range")
        
        self.start = parse_date_or_datetime(attributes["start"]) if "start" in attributes else None
        self.end = parse_date_or_datetime(attributes["end"]) if "end" in attributes else None

class CalDAVTimeZoneElement (CalDAVTextElement):
    """
    CalDAV element containing iCalendar data with a single VTIMEZONE component.
    """
    def __init__(self, *children, **attributes):
        super(CalDAVTimeZoneElement, self).__init__(*children, **attributes)

        # An error in the data needs to be reported as a pre-condition error rather than
        # an XML parse error. So this test is moved out of here into a separate method that
        # gets called and can cause the proper WebDAV DAV:error response.
        
        # TODO: Remove the comment above and commented code below once this has been properly tested.
#
#        try:
#            calendar = self.calendar()
#            if calendar is None: raise ValueError("No data")
#        except ValueError, e:
#            log.err("Invalid iCalendar data (%s): %r" % (calendar, e))
#            raise
#
#        found = False
#
#        for subcomponent in calendar.subcomponents():
#            if subcomponent.name() == "VTIMEZONE":
#                if found:
#                    raise ValueError("CalDAV:%s may not contain iCalendar data with more than one VTIMEZONE component" % (self.name,))
#                else:
#                    found = True
#            else:
#                # FIXME: Spec doesn't seem to really disallow this; it's unclear...
#                raise ValueError("%s component not allowed in CalDAV:timezone data" % (subcomponent.name(),))
#
#        if not found:
#            raise ValueError("CalDAV:%s must contain iCalendar data with a VTIMEZONE component" % (self.name,))

    def calendar(self):
        """
        Returns a calendar component derived from this element, which contains
        exactly one VTIMEZONE component.
        """
        return iComponent.fromString(str(self))

    def valid(self):
        """
        Determine whether the content of this element is a valid single VTIMEZONE component.
        
        @return: True if valid, False if not.
        """
        
        try:
            calendar = self.calendar()
            if calendar is None:
                return False
        except ValueError:
            return False

        found = False

        for subcomponent in calendar.subcomponents():
            if (
                subcomponent.name() == "VTIMEZONE" and
                isinstance(subcomponent._vobject, TimezoneComponent)
            ):
                if found:
                    return False
                else:
                    found = True
            else:
                return False

        return found
        
class CalDAVFilterElement (CalDAVElement):
    """
    CalDAV filter element.
    """
    def __init__(self, *children, **attributes):
        # FIXME: is-defined is obsoleted by CalDAV-access-09.  Filter it out here for compatibility.
        children = [c for c in children if c is not None and c.qname() != (caldav_namespace, "is-defined")]

        super(CalDAVFilterElement, self).__init__(*children, **attributes)

        qualifier = None
        filters = []

        for child in self.children:
            qname = child.qname()
            
            if qname in (
                (caldav_namespace, "is-not-defined"),
                (caldav_namespace, "time-range"),
                (caldav_namespace, "text-match"),
            ):
                if qualifier is not None:
                    raise ValueError("Only one of CalDAV:time-range, CalDAV:text-match allowed")
                qualifier = child

            else:
                filters.append(child)

        if qualifier and (qualifier.qname() == (caldav_namespace, "is-not-defined")) and (len(filters) != 0):
            raise ValueError("No other tests allowed when CalDAV:is-not-defined is present")
            
        self.qualifier   = qualifier
        self.filters     = filters
        self.filter_name = attributes["name"]
        if isinstance(self.filter_name, unicode):
            self.filter_name = self.filter_name.encode("utf-8")
        self.defined     = not self.qualifier or (self.qualifier.qname() != (caldav_namespace, "is-not-defined"))

    def match(self, item, access=None):
        """
        Returns True if the given calendar item (either a component, property or parameter value)
        matches this filter, False otherwise.
        """
        
        # Always return True for the is-not-defined case as the result of this will
        # be negated by the caller
        if not self.defined: return True

        if self.qualifier and not self.qualifier.match(item, access): return False

        if len(self.filters) > 0:
            for filter in self.filters:
                if filter._match(item, access):
                    return True
            return False
        else:
            return True

class CalendarHomeSet (CalDAVElement):
    """
    The calendar collections URLs for this principal's calendar user.
    (CalDAV-access, section 6.2.1)
    """
    name = "calendar-home-set"
    hidden = True

    allowed_children = { (davxml.dav_namespace, "href"): (0, None) }

class CalendarDescription (CalDAVTextElement):
    """
    Provides a human-readable description of what this calendar collection
    represents.
    (CalDAV-access-09, section 5.2.1)
    """
    name = "calendar-description"
    hidden = True
    # May be protected; but we'll let the client set this if they like.

class CalendarTimeZone (CalDAVTimeZoneElement):
    """
    Specifies a time zone on a calendar collection.
    (CalDAV-access-09, section 5.2.2)
    """
    name = "calendar-timezone"
    hidden = True

class SupportedCalendarComponentSet (CalDAVElement):
    """
    Provides a human-readable description of what this calendar collection
    represents.
    (CalDAV-access-09, section 5.2.3)
    """
    name = "supported-calendar-component-set"
    hidden = True
    protected = True

    allowed_children = { (caldav_namespace, "comp"): (0, None) }

class SupportedCalendarData (CalDAVElement):
    """
    Specifies restrictions on a calendar collection.
    (CalDAV-access-09, section 5.2.4)
    """
    name = "supported-calendar-data"
    hidden = True
    protected = True

    allowed_children = { (caldav_namespace, "calendar-data"): (0, None) }

class MaxResourceSize (CalDAVTextElement):
    """
    Specifies restrictions on a calendar collection.
    (CalDAV-access-15, section 5.2.5)
    """
    name = "max-resource-size"
    hidden = True
    protected = True

class MaxAttendeesPerInstance (CalDAVTextElement):
    """
    Specifies restrictions on a calendar collection.
    (CalDAV-access-15, section 5.2.9)
    """
    name = "max-attendees-per-instance"
    hidden = True
    protected = True

class Calendar (CalDAVEmptyElement):
    """
    Denotes a calendar collection.
    (CalDAV-access-09, sections 4.2 & 9.1)
    """
    name = "calendar"

class MakeCalendar (CalDAVElement):
    """
    Top-level element for request body in MKCALENDAR.
    (CalDAV-access-09, section 9.2)
    """
    name = "mkcalendar"

    allowed_children = { (davxml.dav_namespace, "set"): (0, 1) }

    child_types = { "WebDAVUnknownElement": (0, None) }

class MakeCalendarResponse (CalDAVElement):
    """
    Top-level element for response body in MKCALENDAR.
    (CalDAV-access-09, section 9.3)
    """
    name = "mkcalendar-response"

    allowed_children = { davxml.WebDAVElement: (0, None) }

class CalendarQuery (CalDAVElement):
    """
    Defines a report for querying calendar data.
    (CalDAV-access-09, section 9.4)
    """
    name = "calendar-query"

    allowed_children = {
        (davxml.dav_namespace, "allprop" ): (0, None),
        (davxml.dav_namespace, "propname"): (0, None),
        (davxml.dav_namespace, "prop"    ): (0, None),
        (caldav_namespace,     "timezone"): (0, 1),
        (caldav_namespace,     "filter"  ): (0, 1), # Actually (1, 1) unless element is empty
    }

    def __init__(self, *children, **attributes):
        super(CalendarQuery, self).__init__(*children, **attributes)

        query = None
        filter = None
        timezone = None

        for child in self.children:
            qname = child.qname()

            if qname in (
                (davxml.dav_namespace, "allprop" ),
                (davxml.dav_namespace, "propname"),
                (davxml.dav_namespace, "prop"    ),
            ):
                if query is not None:
                    raise ValueError("Only one of CalDAV:allprop, CalDAV:propname, CalDAV:prop allowed")
                query = child

            elif qname == (caldav_namespace, "filter"):
                filter = child

            elif qname ==(caldav_namespace, "timezone"):
                timezone = child

            else:
                raise AssertionError("We shouldn't be here")

        if len(self.children) > 0:
            if filter is None:
                raise ValueError("CALDAV:filter required")

        self.query  = query
        self.filter = filter
        self.timezone = timezone

class CalendarData (CalDAVElement):
    """
    Defines which parts of a calendar component object should be returned by a
    report.
    (CalDAV-access-09, section 9.5)
    """
    name = "calendar-data"

    allowed_children = {
        (caldav_namespace, "comp"                 ): (0, None),
        (caldav_namespace, "expand"               ): (0, 1),
        (caldav_namespace, "limit-recurrence-set" ): (0, 1),
        (caldav_namespace, "limit-freebusy-set"   ): (0, 1),
        davxml.PCDATAElement: (0, None),
    }
    allowed_attributes = {
        "content-type": False,
        "version"     : False,
    }

    @classmethod
    def fromCalendar(clazz, calendar):
        if isinstance(calendar, str):
            return clazz(davxml.PCDATAElement(calendar))
        elif isinstance(calendar, iComponent):
            assert calendar.name() == "VCALENDAR", "Not a calendar: %r" % (calendar,)
            return clazz(davxml.PCDATAElement(str(calendar)))
        else:
            raise ValueError("Not a calendar: %s" % (calendar,))

    def __init__(self, *children, **attributes):
        super(CalendarData, self).__init__(*children, **attributes)

        component      = None
        recurrence_set = None
        freebusy_set   = None
        data           = None

        for child in self.children:
            qname = child.qname()

            if qname == (caldav_namespace, "comp"):
                component = child

            elif qname in (
                (caldav_namespace, "expand"),
                (caldav_namespace, "limit-recurrence-set" ),
            ):
                if recurrence_set is not None:
                    raise ValueError("Only one of CalDAV:expand, CalDAV:limit-recurrence-set allowed")
                recurrence_set = child

            elif qname == (caldav_namespace, "limit-freebusy-set"):
                freebusy_set = child

            elif isinstance(child, davxml.PCDATAElement):
                if data is None:
                    data = child
                else:
                    data += child

            else: raise AssertionError("We shouldn't be here")

        self.component      = component
        self.recurrence_set = recurrence_set
        self.freebusy_set   = freebusy_set

        if data is not None:
            try:
                if component is not None:
                    raise ValueError("Only one of CalDAV:comp (%r) or PCDATA (%r) allowed"% (component, str(data)))
                if recurrence_set is not None:
                    raise ValueError("%s not allowed with PCDATA (%r)"% (recurrence_set, str(data)))
            except ValueError:
                if not data.isWhitespace(): raise
            else:
                # Since we've already combined PCDATA elements, we'd may as well
                # optimize them originals away
                self.children = (data,)

                # Verify that we have valid calendar data, but don't call
                # validateForCalDAV() on the result, since some responses may
                # require a calendar-data element with iCalendar data not meant
                # for use as a CalDAV resource.
                #try:
                #    self.calendar()
                #except ValueError, e:
                #    log.err("Invalid iCalendar data (%s): %r" % (e, data))
                #    raise

        if "content-type" in attributes:
            self.content_type = attributes["content-type"]
        else:
            self.content_type = "text/calendar"

        if "version" in attributes:
            self.version = attributes["version"]
        else:
            self.version = "2.0"

    def verifyTypeVersion(self, types_and_versions):
        """
        Make sure any content-type and version matches at least one of the supplied set.
        
        @param types_and_versions: a list of (content-type, version) tuples to test against.
        @return:                   True if there is at least one match, False otherwise.
        """
        for item in types_and_versions:
            if (item[0] == self.content_type) and (item[1] == self.version):
                return True
        
        return False

    def elementFromResource(self, resource, timezone=None):
        """
        Return a new CalendarData element comprised of the possibly filtered
        calendar data from the specified resource. If no filter is being applied
        read the data directly from the resource without parsing it. If a filter
        is required, parse the iCal data and filter using this CalendarData.
        @param resource: the resource whose calendar data is to be returned.
        @param timezone: the L{Component} the VTIMEZONE to use for floating/all-day.
        @return: an L{CalendarData} with the (filtered) calendar data.
        """
        return self.elementFromCalendar(resource.iCalendarText(), timezone)

    def elementFromCalendar(self, calendar, timezone=None):
        """
        Return a new CalendarData element comprised of the possibly filtered
        calendar.
        @param calendar: the calendar that is to be filtered and returned.
        @param timezone: the L{Component} the VTIMEZONE to use for floating/all-day.
        @return: an L{CalendarData} with the (filtered) calendar data.
        """
        
        # Check for filtering or not
        filtered = self.getFromICalendar(calendar, timezone)
        return CalendarData.fromCalendar(filtered)

    def elementFromResourceWithAccessRestrictions(self, resource, access, timezone=None):
        """
        Return a new CalendarData element comprised of the possibly filtered
        calendar data from the specified resource. If no filter is being applied
        read the data directly from the resource without parsing it. If a filter
        is required, parse the iCal data and filter using this CalendarData.
        
        Also, apply appropriate access restriction filtering to the data.

        @param resource: the resource whose calendar data is to be returned.
        @param access: private event access restriction level.
        @param timezone: the L{Component} the VTIMEZONE to use for floating/all-day.
        @return: an L{CalendarData} with the (filtered) calendar data.
        """
        return self.elementFromCalendarWithAccessRestrictions(resource.iCalendarText(), access, timezone)

    def elementFromCalendarWithAccessRestrictions(self, calendar, access, timezone=None):
        """
        Return a new CalendarData element comprised of the possibly filtered
        calendar.
        
        Also, apply appropriate access restriction filtering to the data.

        @param calendar: the calendar that is to be filtered and returned.
        @param access: private event access restriction level.
        @param timezone: the L{Component} the VTIMEZONE to use for floating/all-day.
        @return: an L{CalendarData} with the (filtered) calendar data.
        """
        
        # Do normal filtering first
        filtered_calendar = self.getFromICalendar(calendar, timezone)
        
        if access in (iComponent.ACCESS_CONFIDENTIAL, iComponent.ACCESS_RESTRICTED):
            # Create a CALDAV:calendar-data element with the appropriate iCalendar Component/Property
            # filter in place for the access restriction in use
            
            extra_access = ()
            if access == iComponent.ACCESS_RESTRICTED:
                extra_access = (
                    Property(name="SUMMARY"),
                    Property(name="LOCATION"),
                )

            filter = CalendarData(
                CalendarComponent(
                    
                    # VCALENDAR properties
                    Property(name="PRODID"),
                    Property(name="VERSION"),
                    Property(name="CALSCALE"),
                    Property(name=iComponent.ACCESS_PROPERTY),

                    # VEVENT
                    CalendarComponent(
                        Property(name="UID"),
                        Property(name="RECURRENCE-ID"),
                        Property(name="SEQUENCE"),
                        Property(name="DTSTAMP"),
                        Property(name="STATUS"),
                        Property(name="TRANSP"),
                        Property(name="DTSTART"),
                        Property(name="DTEND"),
                        Property(name="DURATION"),
                        Property(name="RRULE"),
                        Property(name="RDATE"),
                        Property(name="EXRULE"),
                        Property(name="EXDATE"),
                        *extra_access,
                        **{"name":"VEVENT"}
                    ),
                    
                    # VTODO
                    CalendarComponent(
                        Property(name="UID"),
                        Property(name="RECURRENCE-ID"),
                        Property(name="SEQUENCE"),
                        Property(name="DTSTAMP"),
                        Property(name="STATUS"),
                        Property(name="DTSTART"),
                        Property(name="COMPLETED"),
                        Property(name="DUE"),
                        Property(name="DURATION"),
                        Property(name="RRULE"),
                        Property(name="RDATE"),
                        Property(name="EXRULE"),
                        Property(name="EXDATE"),
                        *extra_access,
                        **{"name":"VTODO"}
                    ),
                    
                    # VJOURNAL
                    CalendarComponent(
                        Property(name="UID"),
                        Property(name="RECURRENCE-ID"),
                        Property(name="SEQUENCE"),
                        Property(name="DTSTAMP"),
                        Property(name="STATUS"),
                        Property(name="TRANSP"),
                        Property(name="DTSTART"),
                        Property(name="RRULE"),
                        Property(name="RDATE"),
                        Property(name="EXRULE"),
                        Property(name="EXDATE"),
                        *extra_access,
                        **{"name":"VJOURNAL"}
                    ),
                    
                    # VFREEBUSY
                    CalendarComponent(
                        Property(name="UID"),
                        Property(name="DTSTAMP"),
                        Property(name="DTSTART"),
                        Property(name="DTEND"),
                        Property(name="DURATION"),
                        Property(name="FREEBUSY"),
                        *extra_access,
                        **{"name":"VFREEBUSY"}
                    ),
                    
                    # VTIMEZONE
                    CalendarComponent(
                        AllProperties(),
                        AllComponents(),
                        name="VTIMEZONE",
                    ),
                    name="VCALENDAR",
                ),
            )

            # Now "filter" the resource calendar data through the CALDAV:calendar-data element
            return filter.elementFromCalendar(filtered_calendar, timezone)
        else:
            return CalendarData.fromCalendar(filtered_calendar)

    def getFromICalendar(self, calendar, timezone=None):
        """
        @param timezone: the L{Component} the VTIMEZONE to use for floating/all-day.

        Returns a calendar object containing the data in the given calendar
        which is specified by this CalendarData.
        """
        if calendar is None or isinstance(calendar, str) and not calendar:
            raise ValueError("Not a calendar: %r" % (calendar,))

        # Empty element: get all data
        if not self.children: return calendar

        # If we were passed a string, parse it out as a Component
        if isinstance(calendar, str):
            try:
                calendar = iComponent.fromString(calendar)
            except ValueError:
                raise ValueError("Not a calendar: %r" % (calendar,))

        if calendar is None or calendar.name() != "VCALENDAR":
            raise ValueError("Not a calendar: %r" % (calendar,))

        # Pre-process the calendar data based on expand and limit options
        if self.freebusy_set:
            calendar = self.limitFreeBusy(calendar)

        # Filter data based on any provided CALDAV:comp element, or use all current data
        if self.component is not None:
            calendar = self.component.getFromICalendar(calendar)
        
        # Post-process the calendar data based on the expand and limit options
        if self.recurrence_set:
            if isinstance(self.recurrence_set, LimitRecurrenceSet):
                calendar = self.limitRecurrence(calendar)
            elif isinstance(self.recurrence_set, Expand):
                calendar = self.expandRecurrence(calendar, timezone)
        
        return calendar

    def calendar(self):
        """
        Returns a calendar component derived from this element.
        """
        data = self.calendarData()
        if data:
            return iComponent.fromString(data)
        else:
            return None

    def calendarData(self):
        """
        Returns the calendar data derived from this element.
        """
        for data in self.children:
            if not isinstance(data, davxml.PCDATAElement):
                return None
            else:
                # We guaranteed in __init__() that there is only one child...
                break

        return str(data)

    def expandRecurrence(self, calendar, timezone=None):
        """
        Expand the recurrence set into individual items.
        @param calendar: the L{Component} for the calendar to operate on.
        @param timezone: the L{Component} the VTIMEZONE to use for floating/all-day.
        @return: the L{Component} for the result.
        """
        return calendar.expand(self.recurrence_set.start, self.recurrence_set.end, timezone)
    
    def limitRecurrence(self, calendar):
        """
        Limit the set of overridden instances returned to only those
        that are needed to describe the range of instances covered
        by the specified time range.
        @param calendar: the L{Component} for the calendar to operate on.
        @return: the L{Component} for the result.
        """
        raise NotImplementedError()
        return calendar
    
    def limitFreeBusy(self, calendar):
        """
        Limit the range of any FREEBUSY properties in the calendar, returning
        a new calendar if limits were applied, or the same one if no limits were applied.
        @param calendar: the L{Component} for the calendar to operate on.
        @return: the L{Component} for the result.
        """
        
        # First check for any VFREEBUSYs - can ignore limit if there are none
        if calendar.mainType() != "VFREEBUSY":
            return calendar
        
        # Create duplicate calendar and filter FREEBUSY properties
        calendar = calendar.duplicate()
        for component in calendar.subcomponents():
            if component.name() != "VFREEBUSY":
                continue
            for property in component.properties("FREEBUSY"):
                newvalue = []
                for period in property.value():
                    clipped = clipPeriod(period, (self.freebusy_set.start, self.freebusy_set.end))
                    if clipped:
                        newvalue.append(clipped)
                if len(newvalue):
                    property.setValue(newvalue)
                else:
                    component.removeProperty(property)
        return calendar

class CalendarComponent (CalDAVElement):
    """
    Defines which component types to return.
    (CalDAV-access-09, section 9.5.1)
    """
    name = "comp"

    allowed_children = {
        (caldav_namespace, "allcomp"): (0, 1),
        (caldav_namespace, "comp"   ): (0, None),
        (caldav_namespace, "allprop"): (0, 1),
        (caldav_namespace, "prop"   ): (0, None),
    }
    allowed_attributes = { "name": True }

    def __init__(self, *children, **attributes):
        super(CalendarComponent, self).__init__(*children, **attributes)

        components = None
        properties = None

        for child in self.children:
            qname = child.qname()

            if qname == (caldav_namespace, "allcomp"):
                if components is not None:
                    raise ValueError("CalDAV:allcomp and CalDAV:comp may not be combined")
                components = child

            elif qname == (caldav_namespace, "comp"):
                try:
                    components.append(child)
                except AttributeError:
                    if components is None:
                        components = [child]
                    else:
                        raise ValueError("CalDAV:allcomp and CalDAV:comp may not be combined")

            elif qname == (caldav_namespace, "allprop"):
                if properties is not None:
                    raise ValueError(
                        "CalDAV:allprop and CalDAV:prop may not be combined"
                    )
                properties = child

            elif qname == (caldav_namespace, "prop"):
                try:
                    properties.append(child)
                except AttributeError:
                    if properties is None:
                        properties = [child]
                    else:
                        raise ValueError("CalDAV:allprop and CalDAV:prop may not be combined")

            else:
                raise AssertionError("Unexpected element: %r" % (child,))

        self.components = components
        self.properties = properties
        self.type = self.attributes["name"]

    def getFromICalendar(self, component):
        """
        Returns a calendar component object containing the data in the given
        component which is specified by this CalendarComponent.
        """
        if self.type != component.name():
            raise ValueError("%s of type %r can't get data from component of type %r"
                             % (self.sname(), self.type, component.name()))

        result = iComponent(self.type)

        xml_components = self.components
        xml_properties = self.properties

        # Empty element means do all properties and components
        if xml_components is None and xml_properties is None:
            xml_components = AllComponents()
            xml_properties = AllProperties()

        if xml_components is not None:
            if xml_components == AllComponents():
                for ical_subcomponent in component.subcomponents():
                    result.addComponent(ical_subcomponent)
            else:
                for xml_subcomponent in xml_components:
                    for ical_subcomponent in component.subcomponents():
                        if ical_subcomponent.name() == xml_subcomponent.type:
                            result.addComponent(xml_subcomponent.getFromICalendar(ical_subcomponent))

        if xml_properties is not None:
            if xml_properties == AllProperties():
                for ical_property in component.properties():
                    result.addProperty(ical_property)
            else:
                for xml_property in xml_properties:
                    name = xml_property.property_name
                    for ical_property in component.properties(name):
                        result.addProperty(ical_property)

        return result

class AllComponents (CalDAVEmptyElement):
    """
    Specifies that all components shall be returned.
    (CalDAV-access-09, section 9.5.2)
    """
    name = "allcomp"

class AllProperties (CalDAVEmptyElement):
    """
    Specifies that all properties shall be returned.
    (CalDAV-access-09, section 9.5.3)
    """
    name = "allprop"

class Property (CalDAVEmptyElement):
    """
    Defines a property to return in a response.
    (CalDAV-access-09, section 9.5.4)
    """
    name = "prop"

    allowed_attributes = {
        "name"   : True,
        "novalue": False,
    }

    def __init__(self, *children, **attributes):
        super(Property, self).__init__(*children, **attributes)

        self.property_name = attributes["name"]

        if "novalue" in attributes:
            novalue = attributes["novalue"]
            if novalue == "yes":
                self.novalue = True
            elif novalue == "no":
                self.novalue = False
            else:
                raise ValueError("Invalid novalue: %r" % (novalue,))
        else:
            self.novalue = False

class Expand (CalDAVTimeRangeElement):
    """
    Specifies that the server should expand recurring components into separate
    instances.
    (CalDAV-access-09, section 9.5.5)
    """
    name = "expand"

class LimitRecurrenceSet (CalDAVTimeRangeElement):
    """
    Specifies a time range to limit the set of recurrence instances returned by
    the server.
    (CalDAV-access-09, section 9.5.6)
    """
    name = "limit-recurrence-set"

class LimitFreeBusySet (CalDAVTimeRangeElement):
    """
    Specifies a time range to limit the set of FREEBUSY properties returned by
    the server.
    (CalDAV-access-09, section 9.5.7)
    """
    name = "limit-freebusy-set"

class Filter (CalDAVElement):
    """
    Determines which matching components are returned.
    (CalDAV-access-09, section 9.6)
    """
    name = "filter"

    allowed_children = { (caldav_namespace, "comp-filter"): (1, 1) }

    def match(self, component, access=None):
        """
        Returns True if the given calendar component matches this filter, False
        otherwise.
        """
        
        # We only care about certain access restrictions.
        if access not in (iComponent.ACCESS_CONFIDENTIAL, iComponent.ACCESS_RESTRICTED):
            access = None

        # We need to prepare ourselves for a time-range query by pre-calculating
        # the set of instances up to the latest time-range limit. That way we can
        # avoid having to do some form of recurrence expansion for each query sub-part.
        maxend, isStartTime = self.getmaxtimerange()
        if maxend:
            if isStartTime:
                if component.isRecurringUnbounded():
                    # Unbounded recurrence is always within a start-only time-range
                    instances = None
                else:
                    # Expand the instances up to infinity
                    instances = component.expandTimeRanges(datetime.datetime(2100, 1, 1, 0, 0, 0, tzinfo=utc), ignoreInvalidInstances=True)
            else:
                instances = component.expandTimeRanges(maxend, ignoreInvalidInstances=True)
        else:
            instances = None
        self.children[0].setInstances(instances)

        # <filter> contains exactly one <comp-filter>
        return self.children[0].match(component, access)

    def valid(self):
        """
        Indicate whether this filter element's structure is valid wrt iCalendar
        data object model.
        
        @return: True if valid, False otherwise
        """
        
        # Must have one child element for VCALENDAR
        return self.children[0].valid(0)
        
    def settimezone(self, tzelement):
        """
        Set the default timezone to use with this query.
        @param calendar: a L{Component} for the VCALENDAR containing the one
            VTIMEZONE that we want
        @return: the L{datetime.tzinfo} derived from the VTIMEZONE or utc.
        """
        assert tzelement is None or isinstance(tzelement, CalDAVTimeZoneElement)

        if tzelement is not None:
            calendar = tzelement.calendar()
            if calendar is not None:
                for subcomponent in calendar.subcomponents():
                    if subcomponent.name() == "VTIMEZONE":
                        # <filter> contains exactly one <comp-filter>
                        tzinfo = subcomponent.gettzinfo()
                        self.children[0].settzinfo(tzinfo)
                        return tzinfo

        # Default to using utc tzinfo
        self.children[0].settzinfo(utc)
        return utc

    def getmaxtimerange(self):
        """
        Get the date farthest into the future in any time-range elements
        """
        
        return self.children[0].getmaxtimerange(None, False)

class ComponentFilter (CalDAVFilterElement):
    """
    Limits a search to only the chosen component types.
    (CalDAV-access-09, section 9.6.1)
    """
    name = "comp-filter"

    allowed_children = {
        (caldav_namespace, "is-defined"     ): (0, 1), # FIXME: obsoleted in CalDAV-access-09
        (caldav_namespace, "is-not-defined" ): (0, 1),
        (caldav_namespace, "time-range"     ): (0, 1),
        (caldav_namespace, "comp-filter"    ): (0, None),
        (caldav_namespace, "prop-filter"    ): (0, None),
    }
    allowed_attributes = { "name": True }

    def match(self, item, access):
        """
        Returns True if the given calendar item (which is a component)
        matches this filter, False otherwise.
        This specialization uses the instance matching option of the time-range filter
        to minimize instance expansion.
        """

        # Always return True for the is-not-defined case as the result of this will
        # be negated by the caller
        if not self.defined: return True

        if self.qualifier and not self.qualifier.matchinstance(item, self.instances): return False

        if len(self.filters) > 0:
            for filter in self.filters:
                if filter._match(item, access):
                    return True
            return False
        else:
            return True

    def _match(self, component, access):
        # At least one subcomponent must match (or is-not-defined is set)
        for subcomponent in component.subcomponents():
            # If access restrictions are in force, restrict matching to specific components only.
            # In particular do not match VALARM.
            if access and subcomponent.name() not in ("VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY", "VTIMEZONE",):
                continue
            
            # Try to match the component name
            if isinstance(self.filter_name, str):
                if subcomponent.name() != self.filter_name: continue
            else:
                if subcomponent.name() not in self.filter_name: continue
            if self.match(subcomponent, access): break
        else:
            return not self.defined
        return self.defined
        
    def setInstances(self, instances):
        """
        Give the list of instances to each comp-filter element.
        @param instances: the list of instances.
        """
        self.instances = instances
        for compfilter in [x for x in self.filters if isinstance(x, ComponentFilter)]:
            compfilter.setInstances(instances)
        
    def valid(self, level):
        """
        Indicate whether this filter element's structure is valid wrt iCalendar
        data object model.
        
        @param level: the nesting level of this filter element, 0 being the top comp-filter.
        @return:      True if valid, False otherwise
        """
        
        # Check for time-range
        timerange = self.qualifier and isinstance(self.qualifier, TimeRange)

        if level == 0:
            # Must have VCALENDAR at the top
            if (self.filter_name != "VCALENDAR") or timerange:
                log.msg("Top-level comp-filter must be VCALENDAR, instead: %s" % (self.filter_name,))
                return False
        elif level == 1:
            # Disallow VCALENDAR, VALARM, STANDARD, DAYLIGHT, AVAILABLE at the top, everything else is OK
            if self.filter_name in ("VCALENDAR", "VALARM", "STANDARD", "DAYLIGHT", "AVAILABLE"):
                log.msg("comp-filter wrong component type: %s" % (self.filter_name,))
                return False
            
            # time-range only on VEVENT, VTODO, VJOURNAL, VFREEBUSY, VAVAILABILITY
            if timerange and self.filter_name not in ("VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY", "VAVAILABILITY"):
                log.msg("time-range cannot be used with component %s" % (self.filter_name,))
                return False
        elif level == 2:
            # Disallow VCALENDAR, VTIMEZONE, VEVENT, VTODO, VJOURNAL, VFREEBUSY, VAVAILABILITY at the top, everything else is OK
            if (self.filter_name in ("VCALENDAR", "VTIMEZONE", "VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY", "VAVAILABILITY")):
                log.msg("comp-filter wrong sub-component type: %s" % (self.filter_name,))
                return False
            
            # time-range only on VALARM, AVAILABLE
            if timerange and self.filter_name not in ("VALARM", "AVAILABLE",):
                log.msg("time-range cannot be used with sub-component %s" % (self.filter_name,))
                return False
        else:
            # Disallow all standard iCal components anywhere else
            if (self.filter_name in ("VCALENDAR", "VTIMEZONE", "VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY", "VALARM", "STANDARD", "DAYLIGHT", "AVAILABLE")) or timerange:
                log.msg("comp-filter wrong standard component type: %s" % (self.filter_name,))
                return False
        
        # Test each property
        for propfilter in [x for x in self.filters if isinstance(x, PropertyFilter)]:
            if not propfilter.valid():
                return False

        # Test each component
        for compfilter in [x for x in self.filters if isinstance(x, ComponentFilter)]:
            if not compfilter.valid(level + 1):
                return False

        # Test the time-range
        if timerange:
            if not self.qualifier.valid():
                return False

        return True

    def settzinfo(self, tzinfo):
        """
        Set the default timezone to use with this query.
        @param tzinfo: a L{datetime.tzinfo} to use.
        """
        
        # Give tzinfo to any TimeRange we have
        if isinstance(self.qualifier, TimeRange):
            self.qualifier.settzinfo(tzinfo)
        
        # Pass down to sub components/properties
        for x in self.filters:
            x.settzinfo(tzinfo)

    def getmaxtimerange(self, currentMaximum, currentIsStartTime):
        """
        Get the date furthest into the future in any time-range elements
        
        @param currentMaximum: current future value to compare with
        @type currentMaximum: L{datetime.datetime}
        """
        
        # Give tzinfo to any TimeRange we have
        isStartTime = False
        if isinstance(self.qualifier, TimeRange):
            isStartTime = self.qualifier.end is None
            compareWith = self.qualifier.start if isStartTime else self.qualifier.end
            if currentMaximum is None or currentMaximum < compareWith:
                currentMaximum = compareWith
                currentIsStartTime = isStartTime
        
        # Pass down to sub components/properties
        for x in self.filters:
            currentMaximum, currentIsStartTime = x.getmaxtimerange(currentMaximum, currentIsStartTime)

        return currentMaximum, currentIsStartTime

class PropertyFilter (CalDAVFilterElement):
    """
    Limits a search to specific properties.
    (CalDAV-access-09, section 9.6.2)
    """
    name = "prop-filter"

    allowed_children = {
        (caldav_namespace, "is-defined"     ): (0, 1), # FIXME: obsoleted in CalDAV-access-09
        (caldav_namespace, "is-not-defined" ): (0, 1),
        (caldav_namespace, "time-range"     ): (0, 1),
        (caldav_namespace, "text-match"     ): (0, 1),
        (caldav_namespace, "param-filter"   ): (0, None),
    }
    allowed_attributes = { "name": True }

    def _match(self, component, access):
        # When access restriction is in force, we need to only allow matches against the properties
        # allowed by the access restriction level.
        if access:
            allowedProperties = iComponent.confidentialPropertiesMap.get(component.name(), None)
            if allowedProperties and access == iComponent.ACCESS_RESTRICTED:
                allowedProperties += iComponent.extraRestrictedProperties
        else:
            allowedProperties = None

        # At least one property must match (or is-not-defined is set)
        for property in component.properties():
            # Apply access restrictions, if any.
            if allowedProperties is not None and property.name() not in allowedProperties:
                continue
            if property.name() == self.filter_name and self.match(property, access): break
        else:
            return not self.defined
        return self.defined

    def valid(self):
        """
        Indicate whether this filter element's structure is valid wrt iCalendar
        data object model.
        
        @return:      True if valid, False otherwise
        """
        
        # Check for time-range
        timerange = self.qualifier and isinstance(self.qualifier, TimeRange)
        
        # time-range only on COMPLETED, CREATED, DTSTAMP, LAST-MODIFIED
        if timerange and self.filter_name not in ("COMPLETED", "CREATED", "DTSTAMP", "LAST-MODIFIED"):
            log.msg("time-range cannot be used with property %s" % (self.filter_name,))
            return False

        # Test the time-range
        if timerange:
            if not self.qualifier.valid():
                return False

        # No other tests
        return True

    def settzinfo(self, tzinfo):
        """
        Set the default timezone to use with this query.
        @param tzinfo: a L{datetime.tzinfo} to use.
        """
        
        # Give tzinfo to any TimeRange we have
        if isinstance(self.qualifier, TimeRange):
            self.qualifier.settzinfo(tzinfo)

    def getmaxtimerange(self, currentMaximum, currentIsStartTime):
        """
        Get the date furthest into the future in any time-range elements
        
        @param currentMaximum: current future value to compare with
        @type currentMaximum: L{datetime.datetime}
        """
        
        # Give tzinfo to any TimeRange we have
        isStartTime = False
        if isinstance(self.qualifier, TimeRange):
            isStartTime = self.qualifier.end is None
            compareWith = self.qualifier.start if isStartTime else self.qualifier.end
            if currentMaximum is None or currentMaximum < compareWith:
                currentMaximum = compareWith
                currentIsStartTime = isStartTime

        return currentMaximum, currentIsStartTime

class ParameterFilter (CalDAVFilterElement):
    """
    Limits a search to specific parameters.
    (CalDAV-access-09, section 9.6.3)
    """
    name = "param-filter"

    allowed_children = {
        (caldav_namespace, "is-defined"     ): (0, 1), # FIXME: obsoleted in CalDAV-access-09
        (caldav_namespace, "is-not-defined" ): (0, 1),
        (caldav_namespace, "text-match"     ): (0, 1),
    }
    allowed_attributes = { "name": True }

    def _match(self, property, access):
        # We have to deal with the problem that the 'Native' form of a property
        # will be missing the TZID parameter due to the conversion performed. Converting
        # to non-native for the entire calendar object causes problems elsewhere, so its
        # best to do it here for this one special case.
        if self.filter_name == "TZID":
            transformed = property.transformAllFromNative()
        else:
            transformed = False

        # At least one property must match (or is-not-defined is set)
        result = not self.defined
        for parameterName in property.params().keys():
            if parameterName == self.filter_name and self.match(property.params()[parameterName], access):
                result = self.defined
                break

        if transformed:
            property.transformAllToNative()
        return result

class IsDefined (CalDAVEmptyElement):
    """
    FIXME: Removed from spec.
    """
    name = "is-defined"

    def match(self, component, access):
        return component is not None

class IsNotDefined (CalDAVEmptyElement):
    """
    Specifies that the named iCalendar item does not exist.
    (CalDAV-access-11, section 9.6.4)
    """
    name = "is-not-defined"

    def match(self, component, access):
        # Oddly, this needs always to return True so that it appears there is
        # a match - but we then "negate" the result if is-not-defined is set.
        # Actually this method should never be called as we special case the
        # is-not-defined option.
        return True

class TextMatch (CalDAVTextElement):
    """
    Specifies a substring match on a property or parameter value.
    (CalDAV-access-09, section 9.6.4)
    """
    name = "text-match"

    def fromString(clazz, string, caseless=False): #@NoSelf
        if caseless:
            caseless = "yes"
        else:
            caseless = "no"

        if type(string) is str:
            return clazz(davxml.PCDATAElement(string), caseless=caseless)
        elif type(string) is unicode:
            return clazz(davxml.PCDATAElement(string.encode("utf-8")), caseless=caseless)
        else:
            return clazz(davxml.PCDATAElement(str(string)), caseless=caseless)

    fromString = classmethod(fromString)

    allowed_attributes = {
        "caseless": False,
        "negate-condition": False
    }

    def __init__(self, *children, **attributes):
        super(TextMatch, self).__init__(*children, **attributes)

        if "caseless" in attributes:
            caseless = attributes["caseless"]
            if caseless == "yes":
                self.caseless = True
            elif caseless == "no":
                self.caseless = False
        else:
            self.caseless = True

        if "negate-condition" in attributes:
            negate = attributes["negate-condition"]
            if negate == "yes":
                self.negate = True
            elif caseless == "no":
                self.negate = False
        else:
            self.negate = False

    def match(self, item, access):
        """
        Match the text for the item.
        If the item is a property, then match the property value,
        otherwise it may be a list of parameter values - try to match anyone of those
        """
        if item is None: return False

        if isinstance(item, iProperty):
            values = [item.value()]
        else:
            values = item

        test = unicode(str(self), "utf-8")
        if self.caseless:
            test = test.lower()

        def _textCompare(s):
            if self.caseless:
                if s.lower().find(test) != -1:
                    return True, not self.negate
            else:
                if s.find(test) != -1:
                    return True, not self.negate
            return False, False

        for value in values:
            # NB Its possible that we have a text list value which appears as a Python list,
            # so we need to check for that an iterate over the list.
            if isinstance(value, list):
                for subvalue in value:
                    matched, result = _textCompare(subvalue)
                    if matched:
                        return result
            else:
                matched, result = _textCompare(value)
                if matched:
                    return result
        
        return self.negate

class TimeZone (CalDAVTimeZoneElement):
    """
    Specifies a time zone component.
    (CalDAV-access-09, section 9.7)
    """
    name = "timezone"

class TimeRange (CalDAVTimeRangeElement):
    """
    Specifies a time for testing components against.
    (CalDAV-access-09, section 9.8)
    """
    name = "time-range"

    def __init__(self, *children, **attributes):
        super(TimeRange, self).__init__(*children, **attributes)
        self.tzinfo = None

    def settzinfo(self, tzinfo):
        """
        Set the default timezone to use with this query.
        @param tzinfo: a L{datetime.tzinfo} to use.
        """
        
        # Give tzinfo to any TimeRange we have
        self.tzinfo = tzinfo

    def valid(self):
        """
        Indicate whether the time-range is valid (must be date-time in UTC).
        
        @return:      True if valid, False otherwise
        """
        
        if self.start is not None and not isinstance(self.start, datetime.datetime):
            log.msg("start attribute in <time-range> is not a date-time: %s" % (self.start,))
            return False
        if self.end is not None and not isinstance(self.end, datetime.datetime):
            log.msg("end attribute in <time-range> is not a date-time: %s" % (self.end,))
            return False
        if self.start is not None and self.start.tzinfo != utc:
            log.msg("start attribute in <time-range> is not UTC: %s" % (self.start,))
            return False
        if self.end is not None and self.end.tzinfo != utc:
            log.msg("end attribute in <time-range> is not UTC: %s" % (self.end,))
            return False

        # No other tests
        return True

    def match(self, property, access):
        """
        NB This is only called when doing a time-range match on a property.
        """
        if property is None:
            return False
        else:
            return property.containsTimeRange(self.start, self.end, self.tzinfo)

    def matchinstance(self, component, instances):
        """
        Test whether this time-range element causes a match to the specified component
        using the specified set of instances to determine the expanded time ranges.
        @param component: the L{Component} to test.
        @param instances: the list of expanded instances.
        @return: True if the time-range query matches, False otherwise.
        """
        if component is None:
            return False
        
        assert instances is not None or self.end is None, "Failure to expand instance for time-range filter: %r" % (self,)
        
        # Special case open-ended unbounded
        if instances is None:
            if component.getRecurrenceIDUTC() is None:
                return True
            else:
                # See if the overridden component's start is past the start
                start, _ignore_end = component.getEffectiveStartEnd()
                if start is None:
                    return True
                else:
                    return start >= self.start

        # Handle alarms as a special case
        alarms = (component.name() == "VALARM")
        if alarms:
            testcomponent = component._parent
        else:
            testcomponent = component
            
        for key in instances:
            instance = instances[key]
            
            # First make sure components match
            if not testcomponent.same(instance.component):
                continue

            if alarms:
                # Get all the alarm triggers for this instance and test each one
                triggers = instance.getAlarmTriggers()
                for trigger in triggers:
                    if timeRangesOverlap(trigger, None, self.start, self.end, self.tzinfo):
                        return True
            else:
                # Regular instance overlap test
                if timeRangesOverlap(instance.start, instance.end, self.start, self.end, self.tzinfo):
                    return True

        return False

class CalendarMultiGet (CalDAVElement):
    """
    CalDAV report used to retrieve specific calendar component items via their
    URIs.
    (CalDAV-access-09, section 9.9)
    """
    name = "calendar-multiget"

    # To allow for an empty element in a supported-report-set property we need
    # to relax the child restrictions
    allowed_children = {
        (davxml.dav_namespace, "allprop" ): (0, 1),
        (davxml.dav_namespace, "propname"): (0, 1),
        (davxml.dav_namespace, "prop"    ): (0, 1),
        (davxml.dav_namespace, "href"    ): (0, None),    # Actually ought to be (1, None)
    }

    def __init__(self, *children, **attributes):
        super(CalendarMultiGet, self).__init__(*children, **attributes)

        property = None
        resources = []

        for child in self.children:
            qname = child.qname()

            if qname in (
                (davxml.dav_namespace, "allprop" ),
                (davxml.dav_namespace, "propname"),
                (davxml.dav_namespace, "prop"    ),
            ):
                if property is not None:
                    raise ValueError("Only one of DAV:allprop, DAV:propname, DAV:prop allowed")
                property = child

            elif qname == (davxml.dav_namespace, "href"):
                resources.append(child)

        self.property  = property
        self.resources = resources

class FreeBusyQuery (CalDAVElement):
    """
    CalDAV report used to generate a VFREEBUSY to determine busy time over a
    specific time range.
    (CalDAV-access-09, section 9.10)
    """
    name = "free-busy-query"

    # To allow for an empty element in a supported-report-set property we need
    # to relax the child restrictions
    allowed_children = { (caldav_namespace, "time-range" ): (0, 1) } # Actually ought to be (1, 1)

    def __init__(self, *children, **attributes):
        super(FreeBusyQuery, self).__init__(*children, **attributes)

        timerange = None

        for child in self.children:
            qname = child.qname()

            if qname == (caldav_namespace, "time-range"):
                if timerange is not None:
                    raise ValueError("Only one time-range element allowed in free-busy-query: %r" % (self,))
                timerange = child
            else:
                raise ValueError("Unknown element %r in free-busy-query: %r" % (child,self))

        self.timerange  = timerange

class ReadFreeBusy(CalDAVEmptyElement):
    """
    Privilege which allows the free busy report to be executed.
    (CalDAV-access, section 6.1.1)
    """
    name = "read-free-busy"
    
class NoUIDConflict(CalDAVElement):
    """
    CalDAV precondition used to indicate a UID conflict during PUT/COPY/MOVE.
    The conflicting resource href must be returned as a child.
    """
    name = "no-uid-conflict"

    allowed_children = { (davxml.dav_namespace, "href"): (1, 1) }
    
class NumberOfRecurrencesWithinLimits(CalDAVTextElement):
    """
    CalDAV precondition used to indicate that the server limits the number
    of instances a recurring component is allowed to have.
    """
    name = "number-of-recurrences-within-limits"

class SupportedFilter(CalDAVElement):
    """
    CalDAV precondition used to indicate an unsupported component type in a
    query filter.
    The conflicting filter elements are returned.
    """
    name = "supported-filter"

    allowed_children = {
        (caldav_namespace, "comp-filter" ): (0, None),
        (caldav_namespace, "prop-filter" ): (0, None),
        (caldav_namespace, "param-filter"): (0, None)
    }
    
##
# CalDAV Schedule objects
##

class CalendarUserAddressSet (CalDAVElement):
    """
    The list of calendar user addresses for this principal's calendar user.
    (CalDAV-schedule, section x.x.x)
    """
    name = "calendar-user-address-set"
    hidden = True

    allowed_children = { (davxml.dav_namespace, "href"): (0, None) }

class CalendarFreeBusySet (CalDAVElement):
    """
    The list of calendar URIs that contribute to free-busy for this principal's calendar user.
    This was defined in the old caldav scheduling spec but has been removed from the new one.
    We still need to support it for backwards compatibility.
    """
    name = "calendar-free-busy-set"
    hidden = True

    allowed_children = { (davxml.dav_namespace, "href"): (0, None) }

class ScheduleCalendarTransp (CalDAVElement):
    """
    Indicates whether a calendar should be used for freebusy lookups.
    """
    name = "schedule-calendar-transp"

    allowed_children = {
        (caldav_namespace,     "opaque"      ): (0, 1),
        (caldav_namespace,     "transparent" ): (0, 1),
    }

class Opaque (CalDAVEmptyElement):
    """
    Indicates that a calendar is used in freebusy lookups.
    """
    name = "opaque"

class Transparent (CalDAVEmptyElement):
    """
    Indicates that a calendar is not used in freebusy lookups.
    """
    name = "transparent"

class ScheduleDefaultCalendarURL (CalDAVElement):
    """
    A single href indicating which calendar is the default for scheduling.
    """
    name = "schedule-default-calendar-URL"

    allowed_children = { (davxml.dav_namespace, "href"): (0, 1) }

class ScheduleInboxURL (CalDAVElement):
    """
    A principal property to indicate the schedule INBOX for the principal.
    (CalDAV-schedule, section x.x.x)
    """
    name = "schedule-inbox-URL"
    hidden = True
    protected = True

    allowed_children = { (davxml.dav_namespace, "href"): (0, 1) }

class ScheduleOutboxURL (CalDAVElement):
    """
    A principal property to indicate the schedule OUTBOX for the principal.
    (CalDAV-schedule, section x.x.x)
    """
    name = "schedule-outbox-URL"
    hidden = True
    protected = True

    allowed_children = { (davxml.dav_namespace, "href"): (0, 1) }

class Originator (CalDAVElement):
    """
    A property on resources in schedule Inbox and Outbox indicating the Originator used
    for the SCHEDULE operation.
    (CalDAV-schedule, section x.x.x)
    """
    name = "originator"
    hidden = True
    protected = True

    allowed_children = { (davxml.dav_namespace, "href"): (0, 1) } # NB Minimum is zero because this is a property name

class Recipient (CalDAVElement):
    """
    A property on resources in schedule Inbox indicating the Recipients targeted
    by the SCHEDULE operation.
    (CalDAV-schedule, section x.x.x)
    
    The recipient for whom this response is for.
    (CalDAV-schedule, section x.x.x)
    """
    name = "recipient"
    hidden = True
    protected = True

    allowed_children = { (davxml.dav_namespace, "href"): (0, None) } # NB Minimum is zero because this is a property name

class ScheduleTag (CalDAVTextElement):
    """
    Property on scheduling resources.
    (CalDAV-schedule, section x.x.x)
    """
    name = "schedule-tag"
    hidden = True
    protected = True

class ScheduleInbox (CalDAVEmptyElement):
    """
    Denotes the resource type of a calendar schedule Inbox.
    (CalDAV-schedule-xx, section x.x.x)
    """
    name = "schedule-inbox"

class ScheduleOutbox (CalDAVEmptyElement):
    """
    Denotes the resource type of a calendar schedule Outbox.
    (CalDAV-schedule-xx, section x.x.x)
    """
    name = "schedule-outbox"

class ScheduleResponse (CalDAVElement):
    """
    The set of responses for a SCHEDULE method operation.
    (CalDAV-schedule-xx, section x.x.x)
    """
    name = "schedule-response"

    allowed_children = { (caldav_namespace, "response"): (0, None) }

class Response (CalDAVElement):
    """
    A response to an iTIP request against a specific recipient.
    (CalDAV-schedule-xx, section x.x.x)
    """
    name = "response"

    allowed_children = {
        (caldav_namespace,     "recipient"          ): (1, 1),
        (caldav_namespace,     "request-status"     ): (1, 1),
        (caldav_namespace,     "calendar-data"      ): (0, 1),
        (davxml.dav_namespace, "error"              ): (0, 1),        # 2518bis
        (davxml.dav_namespace, "responsedescription"): (0, 1)
    }

class RequestStatus (CalDAVTextElement):
    """
    The iTIP REQUEST-STATUS value for the iTIP operation.
    (CalDAV-schedule, section x.x.x)
    """
    name = "request-status"

class Schedule (CalDAVEmptyElement):
    """
    Privilege which allows the SCHEDULE method to be executed.
    (CalDAV-schedule, section x.x.x)
    """
    name = "schedule"
    
class ScheduleDeliver (CalDAVEmptyElement):
    """
    Privilege which controls scheduling messages going into the Inbox.
    (CalDAV-schedule, section x.x.x)
    """
    name = "schedule-deliver"
    
class ScheduleSend (CalDAVEmptyElement):
    """
    Privilege which controls the ability to send scheduling messages.
    (CalDAV-schedule, section x.x.x)
    """
    name = "schedule-send"
    
class CalendarUserType (CalDAVTextElement):
    """
    The CALDAV:calendar-user-type property from section 9.2.4 of caldav-sched-05
    """
    name = "calendar-user-type"
    protected = True

##
# Extensions to davxml.ResourceType
##

def _isCalendar(self): return bool(self.childrenOfType(Calendar))
davxml.ResourceType.isCalendar = _isCalendar
davxml.ResourceType.calendar = davxml.ResourceType(davxml.Collection(), Calendar())
davxml.ResourceType.scheduleInbox = davxml.ResourceType(davxml.Collection(), ScheduleInbox())
davxml.ResourceType.scheduleOutbox = davxml.ResourceType(davxml.Collection(), ScheduleOutbox())
