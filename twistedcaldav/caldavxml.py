##
# Copyright (c) 2005-2011 Apple Inc. All rights reserved.
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

from pycalendar.datetime import PyCalendarDateTime

from twext.web2.dav import davxml

from twext.python.log import Logger

from twistedcaldav.config import config
from twistedcaldav.ical import Component as iComponent

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

caldav_query_extended_compliance = (
    "calendar-query-extended",
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
        
        self.start = PyCalendarDateTime.parseText(attributes["start"]) if "start" in attributes else None
        self.end = PyCalendarDateTime.parseText(attributes["end"]) if "end" in attributes else None

    def valid(self, level=0):
        """
        Indicate whether the time-range is valid (must be date-time in UTC).
        
        @return:      True if valid, False otherwise
        """
        
        if self.start is not None and self.start.isDateOnly():
            log.msg("start attribute in <time-range> is not a date-time: %s" % (self.start,))
            return False
        if self.end is not None and self.end.isDateOnly():
            log.msg("end attribute in <time-range> is not a date-time: %s" % (self.end,))
            return False
        if self.start is not None and not self.start.utc():
            log.msg("start attribute in <time-range> is not UTC: %s" % (self.start,))
            return False
        if self.end is not None and not self.end.utc():
            log.msg("end attribute in <time-range> is not UTC: %s" % (self.end,))
            return False

        # No other tests
        return True

class CalDAVTimeZoneElement (CalDAVTextElement):
    """
    CalDAV element containing iCalendar data with a single VTIMEZONE component.
    """

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
            if (subcomponent.name() == "VTIMEZONE"):
                if found:
                    return False
                else:
                    found = True
            else:
                return False

        return found
        
class CalendarHomeSet (CalDAVElement):
    """
    The calendar collections URLs for this principal's calendar user.
    (CalDAV-access, RFC 4791 section 6.2.1)
    """
    name = "calendar-home-set"
    hidden = True

    allowed_children = { (davxml.dav_namespace, "href"): (0, None) }

class CalendarDescription (CalDAVTextElement):
    """
    Provides a human-readable description of what this calendar collection
    represents.
    (CalDAV-access, RFC 4791 section 5.2.1)
    """
    name = "calendar-description"
    hidden = True
    # May be protected; but we'll let the client set this if they like.

class CalendarTimeZone (CalDAVTimeZoneElement):
    """
    Specifies a time zone on a calendar collection.
    (CalDAV-access, RFC 4791 section 5.2.2)
    """
    name = "calendar-timezone"
    hidden = True

class SupportedCalendarComponentSets (CalDAVElement):
    """
    Indicates what set of calendar components the server is willing to allow
    the client to use in MKCALENDAR.
    (CalDAV-extensions, draft-daboo-caldav-extensions section XXX)
    """
    name = "supported-calendar-component-sets"
    hidden = True
    protected = True

    allowed_children = { (caldav_namespace, "supported-calendar-component-set"): (0, None) }

class SupportedCalendarComponentSet (CalDAVElement):
    """
    Indicates what set of calendar components are allowed in a collection.
    (CalDAV-access, RFC 4791 section 5.2.3)
    """
    name = "supported-calendar-component-set"
    hidden = True
    protected = True

    allowed_children = { (caldav_namespace, "comp"): (0, None) }

class SupportedCalendarData (CalDAVElement):
    """
    Specifies restrictions on a calendar collection.
    (CalDAV-access, RFC 4791 section 5.2.4)
    """
    name = "supported-calendar-data"
    hidden = True
    protected = True

    allowed_children = { (caldav_namespace, "calendar-data"): (0, None) }

class MaxResourceSize (CalDAVTextElement):
    """
    Specifies restrictions on a calendar collection.
    (CalDAV-access, RFC 4791 section 5.2.5)
    """
    name = "max-resource-size"
    hidden = True
    protected = True

class MinDateTime (CalDAVTextElement):
    """
    Specifies restrictions on a calendar collection.
    (CalDAV-access, RFC 4791 section 5.2.6)
    """
    name = "min-date-time"
    hidden = True
    protected = True

class MaxDateTime (CalDAVTextElement):
    """
    Specifies restrictions on a calendar collection.
    (CalDAV-access, RFC 4791 section 5.2.7)
    """
    name = "max-date-time"
    hidden = True
    protected = True

class MaxInstances (CalDAVTextElement):
    """
    Specifies restrictions on a calendar collection.
    (CalDAV-access, RFC 4791 section 5.2.8)
    """
    name = "max-instances"
    hidden = True
    protected = True

class MaxAttendeesPerInstance (CalDAVTextElement):
    """
    Specifies restrictions on a calendar collection.
    (CalDAV-access, RFC 4791 section 5.2.9)
    """
    name = "max-attendees-per-instance"
    hidden = True
    protected = True

class Calendar (CalDAVEmptyElement):
    """
    Denotes a calendar collection.
    (CalDAV-access, RFC 4791 sections 4.2 & 9.1)
    """
    name = "calendar"

class MakeCalendar (CalDAVElement):
    """
    Top-level element for request body in MKCALENDAR.
    (CalDAV-access, RFC 4791 section 9.2)
    """
    name = "mkcalendar"

    allowed_children = { (davxml.dav_namespace, "set"): (0, 1) }

    child_types = { "WebDAVUnknownElement": (0, None) }

class MakeCalendarResponse (CalDAVElement):
    """
    Top-level element for response body in MKCALENDAR.
    (CalDAV-access, RFC 4791 section 9.3)
    """
    name = "mkcalendar-response"

    allowed_children = { davxml.WebDAVElement: (0, None) }

class CalendarQuery (CalDAVElement):
    """
    Defines a report for querying calendar data.
    (CalDAV-access, RFC 4791 section 9.5)
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

        props = None
        filter = None
        timezone = None

        for child in self.children:
            qname = child.qname()

            if qname in (
                (davxml.dav_namespace, "allprop" ),
                (davxml.dav_namespace, "propname"),
                (davxml.dav_namespace, "prop"    ),
            ):
                if props is not None:
                    raise ValueError("Only one of CalDAV:allprop, CalDAV:propname, CalDAV:prop allowed")
                props = child

            elif qname == (caldav_namespace, "filter"):
                filter = child

            elif qname ==(caldav_namespace, "timezone"):
                timezone = child

            else:
                raise AssertionError("We shouldn't be here")

        if len(self.children) > 0:
            if filter is None:
                raise ValueError("CALDAV:filter required")

        self.props  = props
        self.filter = filter
        self.timezone = timezone

class CalendarData (CalDAVElement):
    """
    Defines which parts of a calendar component object should be returned by a
    report.
    (CalDAV-access, RFC 4791 section 9.6)
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
            if not calendar:
                raise ValueError("Missing calendar data")
            return clazz(davxml.PCDATAElement(calendar))
        elif isinstance(calendar, iComponent):
            assert calendar.name() == "VCALENDAR", "Not a calendar: %r" % (calendar,)
            return clazz(davxml.PCDATAElement(calendar.getTextWithTimezones(includeTimezones=not config.EnableTimezonesByReference)))
        else:
            raise ValueError("Not a calendar: %s" % (calendar,))

    fromTextData = fromCalendar

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

    def calendar(self):
        """
        Returns a calendar component derived from this element.
        """
        data = self.calendarData()
        if data:
            return iComponent.fromString(data)
        else:
            return None

    generateComponent = calendar

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

    textData = calendarData

class CalendarComponent (CalDAVElement):
    """
    Defines which component types to return.
    (CalDAV-access, RFC 4791 section 9.6.1)
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
    (CalDAV-access, RFC 4791 section 9.6.2)
    """
    name = "allcomp"

class AllProperties (CalDAVEmptyElement):
    """
    Specifies that all properties shall be returned.
    (CalDAV-access, RFC 4791 section 9.6.3)
    """
    name = "allprop"

class Property (CalDAVEmptyElement):
    """
    Defines a property to return in a response.
    (CalDAV-access, RFC 4791 section 9.6.4)
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
    (CalDAV-access, RFC 4791 section 9.6.5)
    """
    name = "expand"

class LimitRecurrenceSet (CalDAVTimeRangeElement):
    """
    Specifies a time range to limit the set of recurrence instances returned by
    the server.
    (CalDAV-access, RFC 4791 section 9.6.6)
    """
    name = "limit-recurrence-set"

class LimitFreeBusySet (CalDAVTimeRangeElement):
    """
    Specifies a time range to limit the set of FREEBUSY properties returned by
    the server.
    (CalDAV-access, RFC 4791 section 9.6.7)
    """
    name = "limit-freebusy-set"

class Filter (CalDAVElement):
    """
    Determines which matching components are returned.
    (CalDAV-access, RFC 4791 section 9.7)
    """
    name = "filter"

    allowed_children = { (caldav_namespace, "comp-filter"): (1, 1) }

class ComponentFilter (CalDAVElement):
    """
    Limits a search to only the chosen component types.
    (CalDAV-access, RFC 4791 section 9.7.1)
    """
    name = "comp-filter"

    allowed_children = {
        (caldav_namespace, "is-not-defined" ): (0, 1),
        (caldav_namespace, "time-range"     ): (0, 1),
        (caldav_namespace, "comp-filter"    ): (0, None),
        (caldav_namespace, "prop-filter"    ): (0, None),
    }
    allowed_attributes = {
        "name": True,
        "test": False,
    }

class PropertyFilter (CalDAVElement):
    """
    Limits a search to specific properties.
    (CalDAV-access, RFC 4791 section 9.7.2)
    """
    name = "prop-filter"

    allowed_children = {
        (caldav_namespace, "is-not-defined" ): (0, 1),
        (caldav_namespace, "time-range"     ): (0, 1),
        (caldav_namespace, "text-match"     ): (0, 1),
        (caldav_namespace, "param-filter"   ): (0, None),
    }
    allowed_attributes = {
        "name": True,
        "test": False,
    }

class ParameterFilter (CalDAVElement):
    """
    Limits a search to specific parameters.
    (CalDAV-access, RFC 4791 section 9.7.3)
    """
    name = "param-filter"

    allowed_children = {
        (caldav_namespace, "is-not-defined" ): (0, 1),
        (caldav_namespace, "text-match"     ): (0, 1),
    }
    allowed_attributes = { "name": True }

class IsNotDefined (CalDAVEmptyElement):
    """
    Specifies that the named iCalendar item does not exist.
    (CalDAV-access, RFC 4791 section 9.7.4)
    """
    name = "is-not-defined"

class TextMatch (CalDAVTextElement):
    """
    Specifies a substring match on a property or parameter value.
    (CalDAV-access, RFC 4791 section 9.7.5)
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
        "negate-condition": False,
        "match-type": False,
    }

class TimeZone (CalDAVTimeZoneElement):
    """
    Specifies a time zone component.
    (CalDAV-access, RFC 4791 section 9.8)
    """
    name = "timezone"

class TimeRange (CalDAVTimeRangeElement):
    """
    Specifies a time for testing components against.
    (CalDAV-access, RFC 4791 section 9.9)
    """
    name = "time-range"

class CalendarMultiGet (CalDAVElement):
    """
    CalDAV report used to retrieve specific calendar component items via their
    URIs.
    (CalDAV-access, RFC 4791 section 9.10)
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
    (CalDAV-access, RFC 4791 section 9.11)
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
    (CalDAV-access, RFC 4791 section 6.1.1)
    """
    name = "read-free-busy"
    
class NoUIDConflict(CalDAVElement):
    """
    CalDAV precondition used to indicate a UID conflict during PUT/COPY/MOVE.
    The conflicting resource href must be returned as a child.
    """
    name = "no-uid-conflict"

    allowed_children = { (davxml.dav_namespace, "href"): (1, 1) }
    
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
# draft-daboo-valarm-extensions
##

caldav_default_alarms_compliance = (
    "calendar-default-alarms",
)

class DefaultAlarmBase (CalDAVTextElement):
    """
    Common behavior for default alarm properties.
    """

    calendartxt = None

    def calendar(self):
        """
        Returns a calendar component derived from this element, which contains
        exactly one VEVENT with the VALARM embedded component, or C{None} if empty.
        """
        valarm = str(self)
        return iComponent.fromString(self.calendartxt % str(self)) if valarm else None

    def valid(self):
        """
        Determine whether the content of this element is a valid single VALARM component or empty.
        
        @return: True if valid, False if not.
        """
        
        if str(self):
            try:
                calendar = self.calendar()
                if calendar is None:
                    return False
            except ValueError:
                return False
        
            # Make sure there is one alarm component
            try:
                valarm = tuple(tuple(calendar.subcomponents())[0].subcomponents())[0]
            except IndexError:
                return False
            if valarm.name().upper() != "VALARM":
                return False
        
        return True

class DefaultAlarmVEventDateTime (DefaultAlarmBase):

    name = "default-alarm-vevent-datetime"

    calendartxt = """
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:bogus
DTSTART:20111129T220000Z
DURATION:PT1H
DTSTAMP:20111129T220000Z
SUMMARY:bogus
%sEND:VEVENT
END:VCALENDAR
"""
    
class DefaultAlarmVEventDate (DefaultAlarmBase):

    name = "default-alarm-vevent-date"

    calendartxt = """
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:bogus
DTSTART:20111129
DURATION:PT1H
DTSTAMP:20111129T220000Z
SUMMARY:bogus
%sEND:VEVENT
END:VCALENDAR
"""
    
class DefaultAlarmVToDoDateTime (DefaultAlarmBase):

    name = "default-alarm-vtodo-datetime"
    

    calendartxt = """
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTODO
UID:bogus
DUE:20111129T220000Z
DTSTAMP:20111129T220000Z
SUMMARY:bogus
%sEND:VTODO
END:VCALENDAR
"""

class DefaultAlarmVToDoDate (DefaultAlarmBase):

    name = "default-alarm-vtodo-date"
    
    calendartxt = """
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VTODO
UID:bogus
DUE:20111129
DTSTAMP:20111129T220000Z
SUMMARY:bogus
%sEND:VTODO
END:VCALENDAR
"""

##
# Extensions to davxml.ResourceType
##

def _isCalendar(self): return bool(self.childrenOfType(Calendar))
davxml.ResourceType.isCalendar = _isCalendar
davxml.ResourceType.calendar = davxml.ResourceType(davxml.Collection(), Calendar())
davxml.ResourceType.scheduleInbox = davxml.ResourceType(davxml.Collection(), ScheduleInbox())
davxml.ResourceType.scheduleOutbox = davxml.ResourceType(davxml.Collection(), ScheduleOutbox())
