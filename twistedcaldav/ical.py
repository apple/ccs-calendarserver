# -*- test-case-name: twistedcaldav.test.test_icalendar -*-
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
iCalendar Utilities
"""

__all__ = [
    "InvalidICalendarDataError",
    "iCalendarProductID",
    "allowedComponents",
    "Property",
    "Component",
    "tzexpand",
]

import cStringIO as StringIO
import codecs
import heapq
import itertools

from twext.python.log import Logger
from twext.web2.stream import IStream
from twext.web2.dav.util import allDataFromStream

from twistedcaldav.config import config
from twistedcaldav.dateops import timeRangesOverlap, normalizeForIndex, differenceDateTime
from twistedcaldav.instance import InstanceList
from twistedcaldav.scheduling.cuaddress import normalizeCUAddr
from twistedcaldav.timezones import hasTZ, TimezoneException

from pycalendar import definitions
from pycalendar.attribute import PyCalendarAttribute
from pycalendar.calendar import PyCalendar
from pycalendar.componentbase import PyCalendarComponentBase
from pycalendar.datetime import PyCalendarDateTime
from pycalendar.duration import PyCalendarDuration
from pycalendar.exceptions import PyCalendarError
from pycalendar.period import PyCalendarPeriod
from pycalendar.property import PyCalendarProperty
from pycalendar.timezone import PyCalendarTimezone
from pycalendar.utcoffsetvalue import PyCalendarUTCOffsetValue

log = Logger()

iCalendarProductID = "-//CALENDARSERVER.ORG//NONSGML Version 1//EN"

allowedComponents = (
    "VEVENT",
    "VTODO",
    "VTIMEZONE",
    #"VJOURNAL",
    "VFREEBUSY",
    #"VAVAILABILITY",
)

# 2445 default values and parameters
# Structure: propname: (<default value>, <parameter defaults dict>)

normalizeProps = {
    "CALSCALE":     ("GREGORIAN", {"VALUE": "TEXT"}),
    "METHOD":       (None, {"VALUE": "TEXT"}),
    "PRODID":       (None, {"VALUE": "TEXT"}),
    "VERSION":      (None, {"VALUE": "TEXT"}),
    "ATTACH":       (None, {"VALUE": "URI"}),
    "CATEGORIES":   (None, {"VALUE": "TEXT"}),
    "CLASS":        (None, {"VALUE": "TEXT"}),
    "COMMENT":      (None, {"VALUE": "TEXT"}),
    "DESCRIPTION":  (None, {"VALUE": "TEXT"}),
    "GEO":          (None, {"VALUE": "FLOAT"}),
    "LOCATION":     (None, {"VALUE": "TEXT"}),
    "PERCENT-COMPLETE": (None, {"VALUE": "INTEGER"}),
    "PRIORITY":     (0, {"VALUE": "INTEGER"}),
    "RESOURCES":    (None, {"VALUE": "TEXT"}),
    "STATUS":       (None, {"VALUE": "TEXT"}),
    "SUMMARY":      (None, {"VALUE": "TEXT"}),
    "COMPLETED":    (None, {"VALUE": "DATE-TIME"}),
    "DTEND":        (None, {"VALUE": "DATE-TIME"}),
    "DUE":          (None, {"VALUE": "DATE-TIME"}),
    "DTSTART":      (None, {"VALUE": "DATE-TIME"}),
    "DURATION":     (None, {"VALUE": "DURATION"}),
    "FREEBUSY":     (None, {"VALUE": "PERIOD"}),
    "TRANSP":       ("OPAQUE", {"VALUE": "TEXT"}),
    "TZID":         (None, {"VALUE": "TEXT"}),
    "TZNAME":       (None, {"VALUE": "TEXT"}),
    "TZOFFSETFROM": (None, {"VALUE": "UTC-OFFSET"}),
    "TZOFFSETTO":   (None, {"VALUE": "UTC-OFFSET"}),
    "TZURL":        (None, {"VALUE": "URI"}),
    "ATTENDEE":     (None, {
        "VALUE":          "CAL-ADDRESS",
        "CUTYPE":         "INDIVIDUAL",
        "ROLE":           "REQ-PARTICIPANT",
        "PARTSTAT":       "NEEDS-ACTION",
        "RSVP":           "FALSE",
        "SCHEDULE-AGENT": "SERVER",
    }),
    "CONTACT":      (None, {"VALUE": "TEXT"}),
    "ORGANIZER":    (None, {"VALUE": "CAL-ADDRESS"}),
    "RECURRENCE-ID": (None, {"VALUE": "DATE-TIME"}),
    "RELATED-TO":   (None, {"VALUE": "TEXT"}),
    "URL":          (None, {"VALUE": "URI"}),
    "UID":          (None, {"VALUE": "TEXT"}),
    "EXDATE":       (None, {"VALUE": "DATE-TIME"}),
    "EXRULE":       (None, {"VALUE": "RECUR"}),
    "RDATE":        (None, {"VALUE": "DATE-TIME"}),
    "RRULE":        (None, {"VALUE": "RECUR"}),
    "ACTION":       (None, {"VALUE": "TEXT"}),
    "REPEAT":       (0, {"VALUE": "INTEGER"}),
    "TRIGGER":      (None, {"VALUE": "DURATION"}),
    "CREATED":      (None, {"VALUE": "DATE-TIME"}),
    "DTSTAMP":      (None, {"VALUE": "DATE-TIME"}),
    "LAST-MODIFIED": (None, {"VALUE": "DATE-TIME"}),
    "SEQUENCE":     (0, {"VALUE": "INTEGER"}),
    "REQUEST-STATUS": (None, {"VALUE": "TEXT"}),
}

# transformations to apply to property values
normalizePropsValue = {
    "ATTENDEE":     normalizeCUAddr,
    "ORGANIZER":    normalizeCUAddr,
}

ignoredComponents = ("VTIMEZONE", "X-CALENDARSERVER-PERUSER",)

# Used for min/max time-range query limits
minDateTime = PyCalendarDateTime(1900, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
maxDateTime = PyCalendarDateTime(2100, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))

class InvalidICalendarDataError(ValueError):
    pass

class Property (object):
    """
    iCalendar Property
    """
    def __init__(self, name, value, params={}, **kwargs):
        """
        @param name: the property's name
        @param value: the property's value
        @param params: a dictionary of parameters, where keys are parameter names and
            values are (possibly empty) lists of parameter values.
        """
        if name is None:
            assert value  is None
            assert params is None

            pyobj = kwargs["pycalendar"]

            if not isinstance(pyobj, PyCalendarProperty):
                raise TypeError("Not a PyCalendarProperty: %r" % (property,))

            self._pycalendar = pyobj
        else:
            # Convert params dictionary to list of lists format used by pycalendar
            self._pycalendar = PyCalendarProperty(name, value)
            for attrname, attrvalue in params.items():
                self._pycalendar.addAttribute(PyCalendarAttribute(attrname, attrvalue))

    def __str__ (self): return str(self._pycalendar)
    def __repr__(self): return "<%s: %r: %r>" % (self.__class__.__name__, self.name(), self.value())

    def __hash__(self):
        return hash(str(self))

    def __ne__(self, other): return not self.__eq__(other)
    def __eq__(self, other):
        if not isinstance(other, Property): return False
        return self._pycalendar == other._pycalendar

    def __gt__(self, other): return not (self.__eq__(other) or self.__lt__(other))
    def __lt__(self, other):
        my_name = self.name()
        other_name = other.name()

        if my_name < other_name: return True
        if my_name > other_name: return False

        return self.value() < other.value()

    def __ge__(self, other): return self.__eq__(other) or self.__gt__(other)
    def __le__(self, other): return self.__eq__(other) or self.__lt__(other)

    def duplicate(self):
        """
        Duplicate this object and all its contents.
        @return: the duplicated calendar.
        """
        return Property(None, None, None, pycalendar=self._pycalendar.duplicate())
        
    def name  (self): return self._pycalendar.getName()

    def value (self): return self._pycalendar.getValue().getValue()

    def strvalue (self): return str(self._pycalendar.getValue())

    def setValue(self, value):
        self._pycalendar.setValue(value)

    def parameterNames(self):
        """
        Returns a set containing parameter names for this property.
        """
        result = set()
        for pyattrlist in self._pycalendar.getAttributes().values():
            for pyattr in pyattrlist:
                result.add(pyattr.getName())
        return result

    def parameterValue(self, name, default=None):
        """
        Returns a single value for the given parameter.  Raises
        InvalidICalendarDataError if the parameter has more than one value.
        """
        try:
            return self._pycalendar.getAttributeValue(name)
        except KeyError:
            return default

    def hasParameter(self, paramname):
        return self._pycalendar.hasAttribute(paramname)

    def setParameter(self, paramname, paramvalue):
        self._pycalendar.replaceAttribute(PyCalendarAttribute(paramname, paramvalue))

    def removeParameter(self, paramname):
        self._pycalendar.removeAttributes(paramname)

    def removeAllParameters(self):
        self._pycalendar.setAttributes({})

    def removeParameterValue(self, paramname, paramvalue):
        
        for attr in tuple(self._pycalendar.getAttributes()):
            if attr.getName() == paramname:
                for value in attr.getValues():
                    if value == paramvalue:
                        if not attr.removeValue(value):
                            self._pycalendar.removeAttributes(paramname)

    def containsTimeRange(self, start, end, defaulttz=None):
        """
        Determines whether this property contains a date/date-time within the specified
        start/end period.
        The only properties allowed for this query are: COMPLETED, CREATED, DTSTAMP and
        LAST-MODIFIED (caldav -09).
        @param start: a L{PyCalendarDateTime} specifying the beginning of the given time span.
        @param end: a L{PyCalendarDateTime} specifying the end of the given time span.
            C{end} may be None, indicating that there is no end date.
        @param defaulttz: the default L{PyTimezone} to use in datetime comparisons.
        @return: True if the property's date/date-time value is within the given time range,
                 False if not, or the property is not an appropriate date/date-time value.
        """

        # Verify that property name matches the ones allowed
        allowedNames = ["COMPLETED", "CREATED", "DTSTAMP", "LAST-MODIFIED"]
        if self.name() not in allowedNames:
            return False
        
        # get date/date-time value
        dt = self._pycalendar.getValue().getValue()
        assert isinstance(dt, PyCalendarDateTime), "Not a date/date-time value: %r" % (self,)
        
        return timeRangesOverlap(dt, None, start, end, defaulttz)


class Component (object):
    """
    X{iCalendar} component.
    """

    # Private Event access levels.
    ACCESS_PROPERTY     = "X-CALENDARSERVER-ACCESS"
    ACCESS_PUBLIC       = "PUBLIC"
    ACCESS_PRIVATE      = "PRIVATE"
    ACCESS_CONFIDENTIAL = "CONFIDENTIAL"
    ACCESS_RESTRICTED   = "RESTRICTED"

    accessMap = {
        "PUBLIC"       : ACCESS_PUBLIC,
        "PRIVATE"      : ACCESS_PRIVATE,
        "CONFIDENTIAL" : ACCESS_CONFIDENTIAL,
        "RESTRICTED"   : ACCESS_RESTRICTED,
    }

    confidentialPropertiesMap = {
        "VCALENDAR": ("PRODID", "VERSION", "CALSCALE", ACCESS_PROPERTY),
        "VEVENT":    ("UID", "RECURRENCE-ID", "SEQUENCE", "DTSTAMP", "STATUS", "TRANSP", "DTSTART", "DTEND", "DURATION", "RRULE", "RDATE", "EXRULE", "EXDATE", ),
        "VTODO":     ("UID", "RECURRENCE-ID", "SEQUENCE", "DTSTAMP", "STATUS", "DTSTART", "COMPLETED", "DUE", "DURATION", "RRULE", "RDATE", "EXRULE", "EXDATE", ),
        "VJOURNAL":  ("UID", "RECURRENCE-ID", "SEQUENCE", "DTSTAMP", "STATUS", "DTSTART", "RRULE", "RDATE", "EXRULE", "EXDATE", ),
        "VFREEBUSY": ("UID", "DTSTAMP", "DTSTART", "DTEND", "DURATION", "FREEBUSY", ),
        "VTIMEZONE": None,
    }
    extraRestrictedProperties = ("SUMMARY", "LOCATION",)

    @classmethod
    def allFromString(clazz, string):
        """
        Just default to reading a single VCALENDAR
        """
        return clazz.fromString(string)

    @classmethod
    def allFromStream(clazz, stream):
        """
        Just default to reading a single VCALENDAR
        """
        return clazz.fromStream(stream)

    @classmethod
    def fromString(clazz, string):
        """
        Construct a L{Component} from a string.
        @param string: a string containing iCalendar data.
        @return: a L{Component} representing the first component described by
            C{string}.
        """
        if type(string) is unicode:
            string = string.encode("utf-8")
        else:
            # Valid utf-8 please
            string.decode("utf-8")
        
        # No BOMs please
        if string[:3] == codecs.BOM_UTF8:
            string = string[3:]

        return clazz.fromStream(StringIO.StringIO(string))

    @classmethod
    def fromStream(clazz, stream):
        """
        Construct a L{Component} from a stream.
        @param stream: a C{read()}able stream containing iCalendar data.
        @return: a L{Component} representing the first component described by
            C{stream}.
        """
        cal = PyCalendar()
        try:
            result = cal.parse(stream)
        except PyCalendarError:
            result = None
        if not result:
            stream.seek(0)
            raise InvalidICalendarDataError("%s" % (stream.read(),))
        return clazz(None, pycalendar=cal)

    @classmethod
    def fromIStream(clazz, stream):
        """
        Construct a L{Component} from a stream.
        @param stream: an L{IStream} containing iCalendar data.
        @return: a deferred returning a L{Component} representing the first
            component described by C{stream}.
        """
        #
        # FIXME:
        #   This reads the request body into a string and then parses it.
        #   A better solution would parse directly and incrementally from the
        #   request stream.
        #
        def parse(data): return clazz.fromString(data)
        return allDataFromStream(IStream(stream), parse)


    @classmethod
    def newCalendar(cls):
        """
        Create and return an empty C{VCALENDAR} component.

        @return: a new C{VCALENDAR} component with appropriate metadata
            properties already set (version, product ID).
        @rtype: an instance of this class
        """
        self = cls("VCALENDAR")
        self.addProperty(Property("VERSION", "2.0"))
        self.addProperty(Property("PRODID", iCalendarProductID))
        return self


    def __init__(self, name, **kwargs):
        """
        Use this constructor to initialize an empty L{Component}.
        To create a new L{Component} from X{iCalendar} data, don't use this
        constructor directly.  Use one of the factory methods instead.
        @param name: the name (L{str}) of the X{iCalendar} component type for the
            component.
        """
        if name is None:
            if "pycalendar" in kwargs:
                pyobj = kwargs["pycalendar"]

                if pyobj is not None:
                    if not isinstance(pyobj, PyCalendarComponentBase):
                        raise TypeError("Not a PyCalendarComponentBase: %r" % (pyobj,))

                self._pycalendar = pyobj
            else:
                raise AssertionError("name may not be None")

            # FIXME: _parent is not use internally, and appears to be used elsewhere,
            # even though it's names as a private variable.
            if "parent" in kwargs:
                parent = kwargs["parent"]
                
                if parent is not None:
                    if not isinstance(parent, Component):
                        raise TypeError("Not a Component: %r" % (parent,))
                    
                self._parent = parent
            else:
                self._parent = None
        else:
            # FIXME: figure out creating an arbitrary component
            self._pycalendar = PyCalendar(add_defaults=False) if name == "VCALENDAR" else PyCalendar.makeComponent(name, None)
            self._parent = None

    def __str__ (self):
        """
        NB This does not automatically include timezones in VCALENDAR objects.
        """
        return str(self._pycalendar)

    def __repr__(self):
        return "<%s: %r>" % (self.__class__.__name__, str(self._pycalendar))

    def __hash__(self):
        return hash(str(self))

    def __ne__(self, other):
        return not self.__eq__(other)

    def __eq__(self, other):
        if not isinstance(other, Component):
            return False
        return self._pycalendar == other._pycalendar

    def getTextWithTimezones(self, includeTimezones):
        """
        Return text representation and include timezones if the option is on
        """
        assert self.name() == "VCALENDAR", "Must be a VCALENDAR: %r" % (self,)
        
        return self._pycalendar.getText(includeTimezones=includeTimezones)

    # FIXME: Should this not be in __eq__?
    def same(self, other):
        return self._pycalendar == other._pycalendar
    
    def name(self):
        """
        @return: the name of the iCalendar type of this component.
        """
        return self._pycalendar.getType()

    def mainType(self):
        """
        Determine the primary type of iCal component in this calendar.
        @return: the name of the primary type.
        @raise: L{InvalidICalendarDataError} if there is more than one primary type.
        """
        assert self.name() == "VCALENDAR", "Must be a VCALENDAR: %r" % (self,)
        
        mtype = None
        for component in self.subcomponents():
            if component.name() in ignoredComponents:
                continue
            elif mtype and (mtype != component.name()):
                raise InvalidICalendarDataError("Component contains more than one type of primary type: %r" % (self,))
            else:
                mtype = component.name()
        
        return mtype
    
    def mainComponent(self, allow_multiple=False):
        """
        Return the primary iCal component in this calendar.
        @return: the L{Component} of the primary type.
        @raise: L{InvalidICalendarDataError} if there is more than one primary type.
        """
        assert self.name() == "VCALENDAR", "Must be a VCALENDAR: %r" % (self,)
        
        result = None
        for component in self.subcomponents():
            if component.name() in ignoredComponents:
                continue
            elif not allow_multiple and (result is not None):
                raise InvalidICalendarDataError("Calendar contains more than one primary component: %r" % (self,))
            else:
                result = component
                if allow_multiple:
                    break
        
        return result
    
    def masterComponent(self):
        """
        Return the master iCal component in this calendar.
        @return: the L{Component} for the master component,
            or C{None} if there isn't one.
        """
        assert self.name() == "VCALENDAR", "Must be a VCALENDAR: %r" % (self,)
        
        for component in self.subcomponents():
            if component.name() in ignoredComponents:
                continue
            if not component.hasProperty("RECURRENCE-ID"):
                return component
        
        return None
    
    def overriddenComponent(self, recurrence_id):
        """
        Return the overridden iCal component in this calendar matching the supplied RECURRENCE-ID property.
        This also returns the matching master component if recurrence_id is C{None}.

        @param recurrence_id: The RECURRENCE-ID property value to match.
        @type recurrence_id: L{PyCalendarDateTime}
        @return: the L{Component} for the overridden component,
            or C{None} if there isn't one.
        """
        assert self.name() == "VCALENDAR", "Must be a VCALENDAR: %r" % (self,)
        
        if isinstance(recurrence_id, str):
            recurrence_id = PyCalendarDateTime.parseText(recurrence_id) if recurrence_id else None

        for component in self.subcomponents():
            if component.name() in ignoredComponents:
                continue
            rid = component.getRecurrenceIDUTC()
            if rid and recurrence_id and rid == recurrence_id:
                return component
            elif rid is None and recurrence_id is None:
                return component
        
        return None
    
    def accessLevel(self, default=ACCESS_PUBLIC):
        """
        Return the access level for this component.
        @return: the access level for the calendar data.
        """
        assert self.name() == "VCALENDAR", "Must be a VCALENDAR: %r" % (self,)
        
        access = self.propertyValue(Component.ACCESS_PROPERTY)
        if access:
            access = access.upper()
        return Component.accessMap.get(access, default)
    
    def duplicate(self):
        """
        Duplicate this object and all its contents.
        @return: the duplicated calendar.
        """
        return Component(None, pycalendar=self._pycalendar.duplicate())
        
    def subcomponents(self):
        """
        @return: an iterable of L{Component} objects, one for each subcomponent
            of this component.
        """
        return (
            Component(None, pycalendar=c, parent=self)
            for c in self._pycalendar.getComponents()
        )

    def addComponent(self, component):
        """
        Adds a subcomponent to this component.
        @param component: the L{Component} to add as a subcomponent of this
            component.
        """
        self._pycalendar.addComponent(component._pycalendar)
        component._parent = self

    def removeComponent(self, component):
        """
        Removes a subcomponent from this component.
        @param component: the L{Component} to remove.
        """
        self._pycalendar.removeComponent(component._pycalendar)

    def hasProperty(self, name):
        """
        @param name: the name of the property whose existence is being tested.
        @return: True if the named property exists, False otherwise.
        """
        return self._pycalendar.hasProperty(name)

    def getProperty(self, name):
        """
        Get one property from the property list.
        @param name: the name of the property to get.
        @return: the L{Property} found or None.
        @raise: L{InvalidICalendarDataError} if there is more than one property of the given name.
        """
        properties = tuple(self.properties(name))
        if len(properties) == 1: return properties[0]
        if len(properties) > 1: raise InvalidICalendarDataError("More than one %s property in component %r" % (name, self))
        return None
        
    def properties(self, name=None):
        """
        @param name: if given and not C{None}, restricts the returned properties
            to those with the given C{name}.
        @return: an iterable of L{Property} objects, one for each property of
            this component.
        """
        properties = []
        if name is None:
            [properties.extend(i) for i in self._pycalendar.getProperties().values()]
        elif self._pycalendar.countProperty(name) > 0:
            properties = self._pycalendar.getProperties(name)

        return (
            Property(None, None, None, pycalendar=p)
            for p in properties
        )

    def propertyValue(self, name):
        properties = tuple(self.properties(name))
        if len(properties) == 1:
            return properties[0].value()
        if len(properties) > 1:
            raise InvalidICalendarDataError("More than one %s property in component %r" % (name, self))
        return None


    def getStartDateUTC(self):
        """
        Return the start date or date-time for the specified component
        converted to UTC.
        @param component: the Component whose start should be returned.
        @return: the L{PyCalendarDateTime} for the start.
        """
        dtstart = self.propertyValue("DTSTART")
        return dtstart.duplicateAsUTC() if dtstart is not None else None
 
    def getEndDateUTC(self):
        """
        Return the end date or date-time for the specified component,
        taking into account the presence or absence of DTEND/DURATION properties.
        The returned date-time is converted to UTC.
        @param component: the Component whose end should be returned.
        @return: the L{PyCalendarDateTime} for the end.
        """
        dtend = self.propertyValue("DTEND")
        if dtend is None:
            dtstart = self.propertyValue("DTSTART")
            duration = self.propertyValue("DURATION")
            if duration is not None:
                dtend = dtstart + duration

        return dtend.duplicateAsUTC() if dtend is not None else None

    def getDueDateUTC(self):
        """
        Return the due date or date-time for the specified component
        converted to UTC. Use DTSTART/DURATION if no DUE property.
        @param component: the Component whose start should be returned.
        @return: the L{PyCalendarDateTime} for the start.
        """
        due = self.propertyValue("DUE")
        if due is None:
            dtstart = self.propertyValue("DTSTART")
            duration = self.propertyValue("DURATION")
            if dtstart is not None and duration is not None:
                due = dtstart + duration

        return due.duplicateAsUTC() if due is not None else None
 
    def getCompletedDateUTC(self):
        """
        Return the completed date or date-time for the specified component
        converted to UTC.
        @param component: the Component whose start should be returned.
        @return: the datetime.date or datetime.datetime for the start.
        """
        completed = self.propertyValue("COMPLETED")
        return completed.duplicateAsUTC() if completed is not None else None
 
    def getCreatedDateUTC(self):
        """
        Return the created date or date-time for the specified component
        converted to UTC.
        @param component: the Component whose start should be returned.
        @return: the datetime.date or datetime.datetime for the start.
        """
        created = self.propertyValue("CREATED")
        return created.duplicateAsUTC() if created is not None else None
 
    def getRecurrenceIDUTC(self):
        """
        Return the recurrence-id for the specified component.
        @param component: the Component whose r-id should be returned.
        @return: the L{PyCalendarDateTime} for the r-id.
        """
        rid = self.propertyValue("RECURRENCE-ID")
        return rid.duplicateAsUTC() if rid is not None else None
 
    def getRange(self):
        """
        Determine whether a RANGE=THISANDFUTURE parameter is present
        on any RECURRENCE-ID property.
        @return: True if the parameter is present, False otherwise.
        """
        ridprop = self.getProperty("RECURRENCE-ID")
        if ridprop is not None:
            range = ridprop.parameterValue("RANGE")
            if range is not None:
                return (range == "THISANDFUTURE")

        return False
            
    def getTriggerDetails(self):
        """
        Return the trigger information for the specified alarm component.
        @param component: the Component whose start should be returned.
        @return: a tuple consisting of:
            trigger : the 'native' trigger value
            related : either True (for START) or False (for END)
            repeat : an integer for the REPEAT count
            duration: the repeat duration if present, otherwise None
        """
        assert self.name() == "VALARM", "Component is not a VAlARM: %r" % (self,)
        
        # The trigger value
        trigger = self.propertyValue("TRIGGER")
        if trigger is None:
            raise InvalidICalendarDataError("VALARM has no TRIGGER property: %r" % (self,))
        
        # The related parameter
        related = self.getProperty("TRIGGER").parameterValue("RELATED")
        if related is None:
            related = True
        else:
            related = (related == "START")
        
        # Repeat property
        repeat = self.propertyValue("REPEAT")
        if repeat is None: repeat = 0
        else: repeat = int(repeat)
        
        # Duration property
        duration = self.propertyValue("DURATION")

        if repeat > 0 and duration is None:
            raise InvalidICalendarDataError("VALARM has invalid REPEAT/DURATIOn properties: %r" % (self,))

        return (trigger, related, repeat, duration)
 
    def getRecurrenceSet(self):
        return self._pycalendar.getRecurrenceSet()

    def getEffectiveStartEnd(self):
        # Get the start/end range needed for instance comparisons

        if self.name() in ("VEVENT", "VJOURNAL",):
            return self.getStartDateUTC(), self.getEndDateUTC()
        elif self.name() == "VTODO":
            start = self.getStartDateUTC()
            due = self.getDueDateUTC()
            if start is None and due is not None:
                return due, due
            else:
                return start, due
        else:
            return None, None

    def getFBType(self):
        
        # Only VEVENTs block time
        if self.name() not in ("VEVENT", ):
            return "FREE"
        
        # Handle status
        status = self.propertyValue("STATUS")
        if status == "CANCELLED":
            return "FREE"
        elif status == "TENTATIVE":
            return "BUSY-TENTATIVE"
        else:
            return "BUSY"

    def addProperty(self, property):
        """
        Adds a property to this component.
        @param property: the L{Property} to add to this component.
        """
        self._pycalendar.addProperty(property._pycalendar)
        self._pycalendar.finalise()

    def removeProperty(self, property):
        """
        Remove a property from this component.
        @param property: the L{Property} to remove from this component.
        """
        self._pycalendar.removeProperty(property._pycalendar)
        self._pycalendar.finalise()

    def replaceProperty(self, property):
        """
        Add or replace a property in this component.
        @param property: the L{Property} to add or replace in this component.
        """
        
        # Remove all existing ones first
        self._pycalendar.removeProperties(property.name())
        self.addProperty(property)

    def timezoneIDs(self):
        """
        Returns the set of TZID parameter values appearing in any property in
        this component.
        @return: a set of strings, one for each unique TZID value.
        """
        result = set()

        for property in self.properties():
            tzid = property.parameterValue("TZID")
            if tzid is not None:
                result.add(tzid)
                break
        
        return result
    
    def timezones(self):
        """
        Returns the set of TZID's for each VTIMEZONE component.

        @return: a set of strings, one for each unique TZID value.
        """
        
        assert self.name() == "VCALENDAR", "Not a calendar: %r" % (self,)

        results = set()
        for component in self.subcomponents():
            if component.name() == "VTIMEZONE":
                results.add(component.propertyValue("TZID"))
        
        return results
    
    def truncateRecurrence(self, maximumCount):
        """
        Truncate RRULEs etc to make sure there are no more than the given number
        of instances.
 
        @param maximumCount: the maximum number of instances to allow
        @type maximumCount: C{int}
        @return: a C{bool} indicating whether a change was made or not
        """
        
        changed = False
        master = self.masterComponent()
        if master and master.isRecurring():
            rrules = master._pycalendar.getRecurrenceSet()
            if rrules:
                for rrule in rrules.getRules():
                    if rrule.getUseCount():
                        # Make sure COUNT is less than the limit
                        if rrule.getCount() > maximumCount:
                            rrule.setCount(maximumCount)
                            changed = True
                    elif rrule.getUseUntil():
                        # Need to figure out how to determine number of instances
                        # with this UNTIL and truncate if needed
                        start = master.getStartDateUTC()
                        diff = differenceDateTime(start, rrule.getUntil())
                        diff = diff.getDays() * 24 * 60 * 60 + diff.getSeconds()
                        
                        period = {
                            definitions.eRecurrence_YEARLY:   365 * 24 * 60 * 60,
                            definitions.eRecurrence_MONTHLY:  30 * 24 * 60 * 60,
                            definitions.eRecurrence_WEEKLY:   7 * 24 * 60 * 60,
                            definitions.eRecurrence_DAILY:    1 * 24 * 60 * 60,
                            definitions.eRecurrence_HOURLY:   60 * 60,
                            definitions.eRecurrence_MINUTELY: 60,
                            definitions.eRecurrence_SECONDLY: 1
                        }[rrule.getFreq()] * rrule.getInterval()
                        
                        if diff / period > maximumCount:
                            rrule.setUseUntil(False)
                            rrule.setUseCount(True)
                            rrule.setCount(maximumCount)
                            rrules.changed()
                            changed = True
                    else:
                        # For frequencies other than yearly we will truncate at our limit
                        if rrule.getFreq() != definitions.eRecurrence_YEARLY:
                            rrule.setUseCount(True)
                            rrule.setCount(maximumCount)
                            rrules.changed()
                            changed = True

        return changed

    def expand(self, start, end, timezone=None):
        """
        Expand the components into a set of new components, one for each
        instance in the specified range. Date-times are converted to UTC. A
        new calendar object is returned.
        @param start: the L{PyCalendarDateTime} for the start of the range.
        @param end: the L{PyCalendarDateTime} for the end of the range.
        @param timezone: the L{Component} the VTIMEZONE to use for floating/all-day.
        @return: the L{Component} for the new calendar with expanded instances.
        """
        
        pytz = PyCalendarTimezone(tzid=timezone.propertyValue("TZID")) if timezone else None

        # Create new calendar object with same properties as the original, but
        # none of the originals sub-components
        calendar = Component("VCALENDAR")
        for property in calendar.properties():
            calendar.removeProperty(property)
        for property in self.properties():
            calendar.addProperty(property)
        
        # Expand the instances and add each one
        instances = self.expandTimeRanges(end)
        first = True
        for key in instances:
            instance = instances[key]
            if timeRangesOverlap(instance.start, instance.end, start, end, pytz):
                calendar.addComponent(self.expandComponent(instance, first))
            first = False
        
        return calendar
    
    def expandComponent(self, instance, first):
        """
        Create an expanded component based on the instance provided.
        NB Expansion also requires UTC conversions.
        @param instance: an L{Instance} for the instance being expanded.
        @return: a new L{Component} for the expanded instance.
        """
        
        # Duplicate the component from the instance
        newcomp = instance.component.duplicate()
 
        # Strip out unwanted recurrence properties
        for property in tuple(newcomp.properties()):
            if property.name() in ["RRULE", "RDATE", "EXRULE", "EXDATE", "RECURRENCE-ID"]:
                newcomp.removeProperty(property)
        
        # Convert all datetime properties to UTC unless they are floating
        for property in newcomp.properties():
            value = property.value()
            if isinstance(value, PyCalendarDateTime) and value.local():
                property.removeParameter("TZID")
                property.setValue(value.duplicateAsUTC())
        
        # Now reset DTSTART, DTEND/DURATION
        for property in newcomp.properties("DTSTART"):
            property.setValue(instance.start)
        for property in newcomp.properties("DTEND"):
            property.setValue(instance.end)
        for property in newcomp.properties("DURATION"):
            property.setValue(instance.end - instance.start)
        
        # Add RECURRENCE-ID if not master instance
        if not instance.isMasterInstance():
            newcomp.addProperty(Property("RECURRENCE-ID", instance.rid))

        return newcomp

    def cacheExpandedTimeRanges(self, limit):
        """
        Expand instances up to the specified limit and cache the results in this object
        so we can return cached results in the future.
 
        @param limit: the max datetime to cache up to.
        @type limit: L{PyCalendarDateTime}
        """
        
        # Checked for cached values first
        if hasattr(self, "cachedInstances"):
            cachedLimit = self.cachedInstances.limit
            if cachedLimit is None or cachedLimit >= limit:
                # We have already fully expanded, or cached up to the requested time,
                # so return cached instances
                return self.cachedInstances
        
        self.cachedInstances = self.expandTimeRanges(limit)
        return self.cachedInstances

    def expandTimeRanges(self, limit, ignoreInvalidInstances=False):
        """
        Expand the set of recurrence instances for the components
        contained within this VCALENDAR component. We will assume
        that this component has already been validated as a CalDAV resource
        (i.e. only one type of component, all with the same UID)
        @param limit: L{PyCalendarDateTime} value representing the end of the expansion.
        @param ignoreInvalidInstances: C{bool} whether to ignore instance errors.
        @return: a set of Instances for each recurrence in the set.
        """
        
        componentSet = self.subcomponents()
        return self.expandSetTimeRanges(componentSet, limit, ignoreInvalidInstances)
    
    def expandSetTimeRanges(self, componentSet, limit, ignoreInvalidInstances=False):
        """
        Expand the set of recurrence instances up to the specified date limit.
        What we do is first expand the master instance into the set of generate
        instances. Then we merge the overridden instances, taking into account
        THISANDFUTURE and THISANDPRIOR.
        @param limit: L{PyCalendarDateTime} value representing the end of the expansion.
        @param componentSet: the set of components that are to make up the
                recurrence set. These MUST all be components with the same UID
                and type, forming a proper recurring set.
        @return: a set of Instances for each recurrence in the set.
        """
        
        # Set of instances to return
        instances = InstanceList(ignoreInvalidInstances=ignoreInvalidInstances)
        instances.expandTimeRanges(componentSet, limit)
        return instances

    def getComponentInstances(self):
        """
        Get the R-ID value for each component.
        
        @return: a tuple of recurrence-ids
        """
        
        # Extract appropriate sub-component if this is a VCALENDAR
        if self.name() == "VCALENDAR":
            result = ()
            for component in self.subcomponents():
                if component.name() not in ignoredComponents:
                    result += component.getComponentInstances()
            return result
        else:
            rid = self.getRecurrenceIDUTC()
            return (rid,)

    def isRecurring(self):
        """
        Check whether any recurrence properties are present in any component.
        """

        # Extract appropriate sub-component if this is a VCALENDAR
        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() not in ignoredComponents and component.isRecurring():
                    return True
        else:
            for propname in ("RRULE", "RDATE", "EXDATE", "RECURRENCE-ID",):
                if self.hasProperty(propname):
                    return True
        return False
        
    def isRecurringUnbounded(self):
        """
        Check for unbounded recurrence.
        """

        master = self.masterComponent()
        if master:
            rrules = master.properties("RRULE")
            for rrule in rrules:
                if not rrule.value().getUseCount() and not rrule.value().getUseUntil():
                    return True
        return False
        
    def deriveInstance(self, rid, allowCancelled=False):
        """
        Derive an instance from the master component that has the provided RECURRENCE-ID, but
        with all other properties, components etc from the master. If the requested override is
        currently marked as an EXDATE in the existing master, allow an option whereby the override
        is added as STATUS:CANCELLED and the EXDATE removed.

        @param rid: recurrence-id value
        @type rid: L{PyCalendarDateTime}
        @param allowCancelled: whether to allow a STATUS:CANCELLED override
        @type allowCancelled: C{bool}
        
        @return: L{Component} for newly derived instance, or None if not valid override
        """
        
        # Must have a master component
        master = self.masterComponent()
        if master is None:
            return None

        # TODO: Check that the recurrence-id is a valid instance
        # For now we just check that there is no matching EXDATE
        didCancel = False
        for exdate in tuple(master.properties("EXDATE")):
            for exdateValue in exdate.value():
                if exdateValue.getValue() == rid:
                    if allowCancelled:
                        exdate.value().remove(exdateValue)
                        if len(exdate.value()) == 0:
                            master.removeProperty(exdate)
                        didCancel = True

                        # We changed the instance set so remove any instance cache
                        if hasattr(self, "cachedInstances"):
                            delattr(self, "cachedInstances")
                        break
                    else:
                        # Cannot derive from an existing EXDATE
                        return None
        
        # Check whether recurrence-id matches an RDATE - if so it is OK
        rdates = set()
        for rdate in master.properties("RDATE"):
            rdates.update([item.getValue().duplicateAsUTC() for item in rdate.value()])
        if rid not in rdates:
            # Check whether we have a truncated RRULE
            rrules = master.properties("RRULE")
            if len(tuple(rrules)):
                limit = rid.duplicate()
                limit += PyCalendarDuration(days=365)
                instances = self.cacheExpandedTimeRanges(limit)
                rids = set([instances[key].rid for key in instances])
                instance_rid = normalizeForIndex(rid)
                if instance_rid not in rids:
                    # No match to a valid RRULE instance
                    return None
            else:
                # No RRULE and no match to an RDATE => error
                return None
        
        # Create the derived instance
        newcomp = master.duplicate()

        # Strip out unwanted recurrence properties
        for property in tuple(newcomp.properties()):
            if property.name() in ("RRULE", "RDATE", "EXRULE", "EXDATE", "RECURRENCE-ID",):
                newcomp.removeProperty(property)
        
        # New DTSTART is the RECURRENCE-ID we are deriving but adjusted to the
        # original DTSTART's localtime
        dtstart = newcomp.getProperty("DTSTART")
        if newcomp.hasProperty("DTEND"):
            dtend = newcomp.getProperty("DTEND")
            oldduration = dtend.value() - dtstart.value()
        
        newdtstartValue = rid.duplicate()
        if not dtstart.value().isDateOnly():
            if dtstart.value().local():
                newdtstartValue.adjustTimezone(dtstart.value().getTimezone())
        else:
            newdtstartValue.setDateOnly(True)
            
        dtstart.setValue(newdtstartValue)
        if newcomp.hasProperty("DTEND"):
            dtend.setValue(newdtstartValue + oldduration)

        newcomp.addProperty(Property("RECURRENCE-ID", dtstart.value(), params={}))
        
        if didCancel:
            newcomp.addProperty(Property("STATUS", "CANCELLED"))

        # After creating/changing a component we need to do this to keep PyCalendar happy
        newcomp._pycalendar.finalise()

        return newcomp
        
    def validInstances(self, rids):
        """
        Test whether the specified recurrence-ids are valid instances in this event.

        @param rid: recurrence-id values
        @type rid: iterable
        
        @return: C{set} of valid rids
        """
        
        valid = set()
        non_master_rids = [rid for rid in rids if rid is not None]
        if non_master_rids:
            highest_rid = max(non_master_rids)
            self.cacheExpandedTimeRanges(highest_rid + PyCalendarDuration(days=1))
        for rid in rids:
            if self.validInstance(rid, clear_cache=False):
                valid.add(rid)
        return valid

    def validInstance(self, rid, clear_cache=True):
        """
        Test whether the specified recurrence-id is a valid instance in this event.

        @param rid: recurrence-id value
        @type rid: L{PyCalendarDateTime}
        
        @return: C{bool}
        """
        
        # First check overridden instances already in this component
        if not hasattr(self, "cachedComponentInstances") or clear_cache:
            self.cachedComponentInstances = set(self.getComponentInstances())
        if rid in self.cachedComponentInstances:
            return True
            
        # Must have a master component
        if self.masterComponent() is None:
            return False

        # Get expansion
        instances = self.cacheExpandedTimeRanges(rid + PyCalendarDuration(days=1))
        new_rids = set([instances[key].rid for key in instances])
        return rid in new_rids

    def resourceUID(self):
        """
        @return: the UID of the subcomponents in this component.
        """
        assert self.name() == "VCALENDAR", "Not a calendar: %r" % (self,)

        if not hasattr(self, "_resource_uid"):
            for subcomponent in self.subcomponents():
                if subcomponent.name() not in ignoredComponents:
                    self._resource_uid = subcomponent.propertyValue("UID")
                    break
            else:
                self._resource_uid = None

        return self._resource_uid

    def resourceType(self):
        """
        @return: the name of the iCalendar type of the subcomponents in this
            component.
        """
        assert self.name() == "VCALENDAR", "Not a calendar: %r" % (self,)

        if not hasattr(self, "_resource_type"):
            has_timezone = False

            for subcomponent in self.subcomponents():
                name = subcomponent.name()
                if name == "VTIMEZONE":
                    has_timezone = True
                elif subcomponent.name() in ignoredComponents:
                    continue
                else:
                    self._resource_type = name
                    break
            else:
                if has_timezone:
                    self._resource_type = "VTIMEZONE"
                else:
                    raise InvalidICalendarDataError("No component type found for calendar component: %r" % (self,))

        return self._resource_type

    def stripKnownTimezones(self):
        """
        Remove timezones that this server knows about
        """
        
        changed = False
        for subcomponent in tuple(self.subcomponents()):
            if subcomponent.name() == "VTIMEZONE":
                tzid = subcomponent.propertyValue("TZID")
                try:
                    hasTZ(tzid)
                except TimezoneException:
                    # tzid not available - do not strip
                    pass
                else:
                    # tzid known - strip component out
                    self.removeComponent(subcomponent)
                    changed = True

        return changed

    def validCalendarData(self, doFix=True, doRaise=True):
        """
        @return: tuple of fixed, unfixed issues
        @raise InvalidICalendarDataError: if the given calendar data is not valid and
            cannot be fixed.
        """
        if self.name() != "VCALENDAR":
            log.debug("Not a calendar: %s" % (self,))
            raise InvalidICalendarDataError("Not a calendar")
        if not self.resourceType():
            log.debug("Unknown resource type: %s" % (self,))
            raise InvalidICalendarDataError("Unknown resource type")

        # Do underlying iCalendar library validation with data fix
        fixed, unfixed = self._pycalendar.validate(doFix=doFix)
        if unfixed:
            log.debug("Calendar data had unfixable problems:\n  %s" % ("\n  ".join(unfixed),))
            if doRaise:
                raise InvalidICalendarDataError("Calendar data had unfixable problems:\n  %s" % ("\n  ".join(unfixed),))
        if fixed:
            log.debug("Calendar data had fixable problems:\n  %s" % ("\n  ".join(fixed),))
        
        return fixed, unfixed

    def validCalendarForCalDAV(self, methodAllowed):
        """
        @param methodAllowed:     True if METHOD property is allowed, False otherwise.
        @raise InvalidICalendarDataError: if the given calendar component is not valid for
            use as a X{CalDAV} resource.
        """

        # Disallowed in CalDAV-Access-08, section 4.1
        if not methodAllowed and self.hasProperty("METHOD"):
            msg = "METHOD property is not allowed in CalDAV iCalendar data"
            log.debug(msg)
            raise InvalidICalendarDataError(msg)

        #
        # Must not contain more than one type of iCalendar component, except for
        # the required timezone components, and component UIDs must match
        #
        ctype            = None
        component_id     = None
        component_rids   = set()
        timezone_refs    = set()
        timezones        = set()
        got_master       = False
        #got_override     = False
        #master_recurring = False
        
        for subcomponent in self.subcomponents():
            if subcomponent.name() == "VTIMEZONE":
                timezones.add(subcomponent.propertyValue("TZID"))
            elif subcomponent.name() in ignoredComponents:
                continue
            else:
                if ctype is None:
                    ctype = subcomponent.name()
                else:
                    if ctype != subcomponent.name():
                        msg = "Calendar resources may not contain more than one type of calendar component (%s and %s found)" % (ctype, subcomponent.name())
                        log.debug(msg)
                        raise InvalidICalendarDataError(msg)
        
                if ctype not in allowedComponents:
                    msg = "Component type: %s not allowed" % (ctype,)
                    log.debug(msg)
                    raise InvalidICalendarDataError(msg)
                    
                uid = subcomponent.propertyValue("UID")
                if uid is None:
                    msg = "All components must have UIDs"
                    log.debug(msg)
                    raise InvalidICalendarDataError(msg)
                rid = subcomponent.getRecurrenceIDUTC()
                
                # Verify that UIDs are the same
                if component_id is None:
                    component_id = uid
                elif component_id != uid:
                    msg = "Calendar resources may not contain components with different UIDs (%s and %s found)" % (component_id, subcomponent.propertyValue("UID"))
                    log.debug(msg)
                    raise InvalidICalendarDataError(msg)

                # Verify that there is only one master component
                if rid is None:
                    if got_master:
                        msg = "Calendar resources may not contain components with the same UIDs and no Recurrence-IDs (%s and %s found)" % (component_id, subcomponent.propertyValue("UID"))
                        log.debug(msg)
                        raise InvalidICalendarDataError(msg)
                    else:
                        got_master = True
                        # master_recurring = subcomponent.hasProperty("RRULE") or subcomponent.hasProperty("RDATE")
                else:
                    pass # got_override = True
                            
                # Check that if an override is present then the master is recurring
                # Leopard iCal sometimes does this for overridden instances that an Attendee receives and
                # it creates a "fake" (invalid) master. We are going to skip this test here. Instead implicit
                # scheduling will verify the validity of the components and raise if they don't make sense.
                # If no scheduling is happening then we allow this - that may cause other clients to choke.
                # If it does we will have to reinstate this check but only after we have checked for implicit.
# UNCOMMENT OUT master_recurring AND got_override ASSIGNMENTS ABOVE
#                if got_override and got_master and not master_recurring:
#                    msg = "Calendar resources must have a recurring master component if there is an overridden one (%s)" % (subcomponent.propertyValue("UID"),)
#                    log.debug(msg)
#                    raise InvalidICalendarDataError(msg)
                
                # Check for duplicate RECURRENCE-IDs        
                if rid in component_rids:
                    msg = "Calendar resources may not contain components with the same Recurrence-IDs (%s)" % (rid,)
                    log.debug(msg)
                    raise InvalidICalendarDataError(msg)
                else:
                    component_rids.add(rid)

                timezone_refs.update(subcomponent.timezoneIDs())
        
        #
        # Make sure required timezone components are present
        #
        if not config.EnableTimezonesByReference:
            for timezone_ref in timezone_refs:
                if timezone_ref not in timezones:
                    msg = "Timezone ID %s is referenced but not defined: %s" % (timezone_ref, self,)
                    log.debug(msg)
                    raise InvalidICalendarDataError(msg)
        
        #
        # FIXME:
        #   This test is not part of the spec; it appears to be legal (but
        #   goofy?) to have extra timezone components.
        #
        for timezone in timezones:
            if timezone not in timezone_refs:
                log.debug(
                    "Timezone %s is not referenced by any non-timezone component" % (timezone,)
                )

        # Control character check - only HTAB, CR, LF allowed for characters in the range 0x00-0x1F
        s = str(self)
        if len(s.translate(None, "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0B\x0C\x0E\x0F\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1A\x1B\x1C\x1D\x1E\x1F")) != len(s):
            raise InvalidICalendarDataError("iCalendar contains illegal control character")

    def validOrganizerForScheduling(self):
        """
        Check that the ORGANIZER property is valid for scheduling 
        """
        
        organizers = self.getOrganizersByInstance()
        foundOrganizer = None
        foundRid = None
        missingRids = set()
        for organizer, rid in organizers:
            if organizer:
                if foundOrganizer:
                    if organizer != foundOrganizer:
                        # We have different ORGANIZERs in the same iCalendar object - this is an error
                        msg = "Only one ORGANIZER is allowed in an iCalendar object:\n%s" % (self,)
                        log.debug(msg)
                        raise InvalidICalendarDataError(msg)
                else:
                    foundOrganizer = organizer
                    foundRid = rid
            else:
                missingRids.add(rid)
        
        # If there are some components without an ORGANIZER we will fix the data
        if foundOrganizer and missingRids:
            log.debug("Fixing missing ORGANIZER properties")
            organizerProperty = self.overriddenComponent(foundRid).getProperty("ORGANIZER")
            for rid in missingRids:
                self.overriddenComponent(rid).addProperty(organizerProperty)

        return foundOrganizer

    def gettimezone(self):
        """
        Get the PyCalendarTimezone for a Timezone component.

        @return: L{PyCalendarTimezone} if this is a VTIMEZONE, otherwise None.
        """
        if self.name() == "VTIMEZONE":
            return PyCalendarTimezone(tzid=self._pycalendar.getID())
        elif self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() == "VTIMEZONE":
                    return component.gettimezone()
            else:
                return None
        else:
            return None

    ##
    # iTIP stuff
    ##
    
    def isValidMethod(self):
        """
        Verify that this calendar component has a valid iTIP METHOD property.
        
        @return: True if valid, False if not
        """
        
        try:
            method = self.propertyValue("METHOD")
            if method not in ("PUBLISH", "REQUEST", "REPLY", "ADD", "CANCEL", "REFRESH", "COUNTER", "DECLINECOUNTER"):
                return False
        except InvalidICalendarDataError:
            return False
        
        return True

    def isValidITIP(self):
        """
        Verify that this calendar component is valid according to iTIP.
        
        @return: True if valid, False if not
        """
        
        try:
            method = self.propertyValue("METHOD")
            if method not in ("PUBLISH", "REQUEST", "REPLY", "ADD", "CANCEL", "REFRESH", "COUNTER", "DECLINECOUNTER"):
                return False
            
            # First make sure components are all of the same time (excluding VTIMEZONE)
            self.validCalendarForCalDAV(methodAllowed=True)
            
            # Next we could check the iTIP status for each type of method/component pair, however
            # we can also leave that up to the server except for the REQUEST/VFREEBUSY case which
            # the server will handle itself.
            
            if (method == "REQUEST") and (self.mainType() == "VFREEBUSY"):
                # TODO: verify REQUEST/VFREEBUSY as being OK
                
                # Only one VFREEBUSY (actually multiple X-'s are allowed but we will reject)
                if len([c for c in self.subcomponents()]) != 1:
                    return False

        except InvalidICalendarDataError:
            return False
        
        return True
    
    def getOrganizer(self):
        """
        Get the organizer value. Works on either a VCALENDAR or on a component.
        
        @return: the string value of the Organizer property, or None
        """
        
        # Extract appropriate sub-component if this is a VCALENDAR
        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() not in ignoredComponents:
                    return component.getOrganizer()
        else:
            try:
                # Find the primary subcomponent
                return self.propertyValue("ORGANIZER")
            except InvalidICalendarDataError:
                pass

        return None

    def getOrganizersByInstance(self):
        """
        Get the organizer value for each instance.
        
        @return: a list of tuples of (organizer value, recurrence-id)
        """
        
        # Extract appropriate sub-component if this is a VCALENDAR
        if self.name() == "VCALENDAR":
            result = ()
            for component in self.subcomponents():
                if component.name() not in ignoredComponents:
                    result += component.getOrganizersByInstance()
            return result
        else:
            try:
                # Should be just one ORGANIZER
                org = self.propertyValue("ORGANIZER")
                rid = self.getRecurrenceIDUTC()
                return ((org, rid),)
            except InvalidICalendarDataError:
                pass

        return ()

    def getOrganizerProperty(self):
        """
        Get the organizer value. Works on either a VCALENDAR or on a component.
        
        @return: the string value of the Organizer property, or None
        """
        
        # Extract appropriate sub-component if this is a VCALENDAR
        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() not in ignoredComponents:
                    return component.getOrganizerProperty()
        else:
            try:
                # Find the primary subcomponent
                return self.getProperty("ORGANIZER")
            except InvalidICalendarDataError:
                pass

        return None

    def getOrganizerScheduleAgent(self):

        is_server = False
        organizerProp = self.getOrganizerProperty()
        if organizerProp.hasParameter("SCHEDULE-AGENT"):
            if organizerProp.parameterValue("SCHEDULE-AGENT") == "SERVER":
                is_server = True
        else:
            is_server = True

        return is_server

    def getAttendees(self):
        """
        Get the attendee value. Works on either a VCALENDAR or on a component.
        
        @param match: a C{list} of calendar user address strings to try and match.
        @return: a C{list} of the string values of the Attendee property, or None
        """
        
        # Extract appropriate sub-component if this is a VCALENDAR
        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() not in ignoredComponents:
                    return component.getAttendees()
        else:
            # Find the property values
            return [p.value() for p in self.properties("ATTENDEE")]

        return None

    def getAttendeesByInstance(self, makeUnique=False, onlyScheduleAgentServer=False):
        """
        Get the attendee values for each instance. Optionally remove duplicates.
        
        @param makeUnique: if C{True} remove duplicate ATTENDEEs in each component
        @type makeUnique: C{bool}
        @param onlyScheduleAgentServer: if C{True} only return ATETNDEEs with SCHEDULE-AGENT=SERVER set
        @type onlyScheduleAgentServer: C{bool}
        @return: a list of tuples of (organizer value, recurrence-id)
        """
        
        # Extract appropriate sub-component if this is a VCALENDAR
        if self.name() == "VCALENDAR":
            result = ()
            for component in self.subcomponents():
                if component.name() not in ignoredComponents:
                    result += component.getAttendeesByInstance(makeUnique, onlyScheduleAgentServer)
            return result
        else:
            result = ()
            attendees = set()
            rid = self.getRecurrenceIDUTC()
            for attendee in tuple(self.properties("ATTENDEE")):
                
                if onlyScheduleAgentServer:
                    if attendee.hasParameter("SCHEDULE-AGENT"):
                        if attendee.parameterValue("SCHEDULE-AGENT") != "SERVER":
                            continue

                cuaddr = attendee.value()
                if makeUnique and cuaddr in attendees:
                    self.removeProperty(attendee)
                else:
                    result += ((cuaddr, rid),)
                    attendees.add(cuaddr)
            return result

    def getAttendeeProperty(self, match):
        """
        Get the attendees matching a value. Works on either a VCALENDAR or on a component.
        
        @param match: a C{list} of calendar user address strings to try and match.
        @return: the matching Attendee property, or None
        """
        
        # Need to normalize http/https cu addresses
        test = set()
        for item in match:
            test.add(normalizeCUAddr(item))
        
        # Extract appropriate sub-component if this is a VCALENDAR
        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() not in ignoredComponents:
                    attendee = component.getAttendeeProperty(match)
                    if attendee is not None:
                        return attendee
        else:
            # Find the primary subcomponent
            for attendee in self.properties("ATTENDEE"):
                if normalizeCUAddr(attendee.value()) in test:
                    return attendee

        return None

    def getAttendeeProperties(self, match):
        """
        Get all the attendees matching a value in each component. Works on a VCALENDAR component only.
        
        @param match: a C{list} of calendar user address strings to try and match.
        @return: the string value of the Organizer property, or None
        """
        
        assert self.name() == "VCALENDAR", "Not a calendar: %r" % (self,)

        # Extract appropriate sub-component if this is a VCALENDAR
        results = []
        for component in self.subcomponents():
            if component.name() not in ignoredComponents:
                attendee = component.getAttendeeProperty(match)
                if attendee:
                    results.append(attendee)

        return results

    def getAllAttendeeProperties(self):
        """
        Yield all attendees as Property objects.  Works on either a VCALENDAR or
        on a component.
        @return: a generator yielding Property objects
        """

        # Extract appropriate sub-component if this is a VCALENDAR
        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() not in ignoredComponents:
                    for attendee in component.getAllAttendeeProperties():
                        yield attendee
        else:
            # Find the primary subcomponent
            for attendee in self.properties("ATTENDEE"):
                yield attendee


    def getMaskUID(self):
        """
        Get the X-CALENDARSEREVR-MASK-UID value. Works on either a VCALENDAR or on a component.
        
        @return: the string value of the X-CALENDARSEREVR-MASK-UID property, or None
        """
        
        # Extract appropriate sub-component if this is a VCALENDAR
        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() not in ignoredComponents:
                    return component.getMaskUID()
        else:
            try:
                # Find the primary subcomponent
                return self.propertyValue("X-CALENDARSERVER-MASK-UID")
            except InvalidICalendarDataError:
                pass

        return None

    def setParameterToValueForPropertyWithValue(self, paramname, paramvalue, propname, propvalue):
        """
        Add or change the parameter to the specified value on the property having the specified value.
        
        @param paramname: the parameter name
        @type paramname: C{str}
        @param paramvalue: the parameter value to set
        @type paramvalue: C{str}
        @param propname: the property name
        @type propname: C{str}
        @param propvalue: the property value to test
        @type propvalue: C{str} or C{None}
        """
        
        for component in self.subcomponents():
            if component.name() in ignoredComponents:
                continue
            for property in component.properties(propname):
                if propvalue is None or property.value() == propvalue:
                    property.setParameter(paramname, paramvalue)
    
    def hasPropertyInAnyComponent(self, properties):
        """
        Test for the existence of one or more properties in any component.
        
        @param properties: property name(s) to test for
        @type properties: C{list}, C{tuple} or C{str}
        """

        if isinstance(properties, str):
            properties = (properties,)
            
        for property in properties:
            if self.hasProperty(property):
                return True

        for component in self.subcomponents():
            if component.hasPropertyInAnyComponent(properties):
                return True

        return False

    def getFirstPropertyInAnyComponent(self, properties):
        """
        Get the first of any set of properties in any component.
        
        @param properties: property name(s) to test for
        @type properties: C{list}, C{tuple} or C{str}
        """

        if isinstance(properties, str):
            properties = (properties,)
            
        for property in properties:
            props = tuple(self.properties(property))
            if props:
                return props[0]

        for component in self.subcomponents():
            prop = component.getFirstPropertyInAnyComponent(properties)
            if prop:
                return prop

        return None

    def getAllPropertiesInAnyComponent(self, properties, depth=2):
        """
        Get the all of any set of properties in any component down to a
        specified depth.
        
        @param properties: property name(s) to test for
        @type properties: C{list}, C{tuple} or C{str}
        @param depth: how deep to go in looking at sub-components:
            0: do not go into sub-components, 1: go into one level of sub-components, 
            2: two levels (which is effectively all the levels supported in iCalendar)
        @type depth: int
        """

        results = []

        if isinstance(properties, str):
            properties = (properties,)
            
        for property in properties:
            props = tuple(self.properties(property))
            if props:
                results.extend(props)

        if depth > 0:
            for component in self.subcomponents():
                results.extend(component.getAllPropertiesInAnyComponent(properties, depth - 1))

        return results

    def hasPropertyValueInAllComponents(self, property):
        """
        Test for the existence of a property with a specific value in any sub-component.
        
        @param property: property to test for
        @type property: L{Property}
        """

        for component in self.subcomponents():
            if component.name() in ignoredComponents:
                continue
            found = component.getProperty(property.name())
            if not found or found.value() != property.value():
                return False

        return True

    def addPropertyToAllComponents(self, property):
        """
        Add a property to all top-level components except VTIMEZONE.

        @param property: the property to add
        @type property: L{Property}
        """
        
        for component in self.subcomponents():
            if component.name() in ignoredComponents:
                continue
            component.addProperty(property)

    def replacePropertyInAllComponents(self, property):
        """
        Replace a property in all components.
        @param property: the L{Property} to replace in this component.
        """
        
        for component in self.subcomponents():
            if component.name() in ignoredComponents:
                continue
            component.replaceProperty(property)
    
    def transferProperties(self, from_calendar, properties):
        """
        Transfer specified properties from old calendar into all components
        of this calendar, synthesizing any for new overridden instances.
 
        @param from_calendar: the old calendar to copy from
        @type from_calendar: L{Component}
        @param properties: the property names to copy over
        @type properties: C{tuple} or C{list}
        """

        assert from_calendar.name() == "VCALENDAR", "Not a calendar: %r" % (self,)
        
        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() in ignoredComponents:
                    continue
                component.transferProperties(from_calendar, properties)
        else:
            # Is there a matching component
            rid = self.getRecurrenceIDUTC()
            matched = from_calendar.overriddenComponent(rid)
            
            # If no match found, we are processing a new overridden instance so copy from the original master
            if not matched:
                matched = from_calendar.masterComponent()

            if matched:
                for propname in properties:
                    for prop in matched.properties(propname):
                        self.addProperty(prop)
            
    def attendeesView(self, attendees, onlyScheduleAgentServer=False):
        """
        Filter out any components that all attendees are not present in. Use EXDATEs
        on the master to account for changes.
        """

        assert self.name() == "VCALENDAR", "Not a calendar: %r" % (self,)
            
        # Modify any components that reference the attendee, make note of the ones that don't
        remove_components = []
        master_component = None
        removed_master = False
        for component in self.subcomponents():
            if component.name() in ignoredComponents:
                continue
            found_all_attendees = True
            for attendee in attendees:
                foundAttendee = component.getAttendeeProperty((attendee,))
                if foundAttendee is None:
                    found_all_attendees = False
                    break
                if onlyScheduleAgentServer:
                    if foundAttendee.hasParameter("SCHEDULE-AGENT"):
                        if foundAttendee.parameterValue("SCHEDULE-AGENT") != "SERVER":
                            found_all_attendees = False
                            break
            if not found_all_attendees:
                remove_components.append(component)
            if component.getRecurrenceIDUTC() is None:
                master_component = component
                if not found_all_attendees:
                    removed_master = True
                
        # Now remove the unwanted components - but we may need to EXDATE the master
        exdates = []
        for component in remove_components:
            rid = component.getRecurrenceIDUTC()
            if rid is not None:
                exdates.append(rid)
            self.removeComponent(component)
            
        if not removed_master and master_component is not None:
            for exdate in exdates:
                master_component.addProperty(Property("EXDATE", [exdate,]))
    
    def filterComponents(self, rids):
        
        # If master is in rids do nothing
        if not rids or "" in rids:
            return True
        
        assert self.name() == "VCALENDAR", "Not a calendar: %r" % (self,)
            
        # Remove components not in the list
        components = tuple(self.subcomponents())
        remaining = len(components)
        for component in components:
            if component.name() in ignoredComponents:
                remaining -= 1
                continue
            rid = component.getRecurrenceIDUTC()
            if (rid.getText() if rid else "") not in rids:
                self.removeComponent(component)
                remaining -= 1
                
        return remaining != 0
        
    def removeAllButOneAttendee(self, attendee):
        """
        Remove all ATTENDEE properties except for the one specified.
        """

        assert self.name() == "VCALENDAR", "Not a calendar: %r" % (self,)

        for component in self.subcomponents():
            if component.name() in ignoredComponents:
                continue
            [component.removeProperty(p) for p in tuple(component.properties("ATTENDEE")) if p.value().lower() != attendee.lower()]
            
    def removeAlarms(self):
        """
        Remove all Alarms components
        """

        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() in ignoredComponents:
                    continue
                component.removeAlarms()
        else:
            for component in tuple(self.subcomponents()):
                if component.name() == "VALARM":
                    self.removeComponent(component)
                
    def filterProperties(self, remove=None, keep=None, do_subcomponents=True):
        """
        Remove all properties that do not match the provided set.
        """

        if do_subcomponents:
            for component in self.subcomponents():
                component.filterProperties(remove, keep, do_subcomponents=False)
        else:
            if self.name() in ignoredComponents:
                return
            
            for p in tuple(self.properties()):
                if (keep and p.name() not in keep) or (remove and p.name() in remove):
                    self.removeProperty(p)
                
    def removeXComponents(self, keep_components=()):
        """
        Remove all X- properties except the specified ones
        """

        for component in tuple(self.subcomponents()):
            if component.name().startswith("X-") and component.name() not in keep_components:
                self.removeComponent(component)
            
    def removeXProperties(self, keep_properties=(), remove_x_parameters=True, do_subcomponents=True):
        """
        Remove all X- properties except the specified ones
        """

        if do_subcomponents and self.name() == "VCALENDAR":
            for component in self.subcomponents():
                component.removeXProperties(keep_properties, remove_x_parameters, do_subcomponents=False)
        else:
            if self.name() in ignoredComponents:
                return
            for p in tuple(self.properties()):
                xpname = p.name().startswith("X-")
                if xpname and p.name() not in keep_properties:
                    self.removeProperty(p)
                elif not xpname and remove_x_parameters:
                    for paramname in p.parameterNames():
                        if paramname.startswith("X-"):
                            p.removeParameter(paramname)
            
    def removePropertyParameters(self, property, params):
        """
        Remove all specified property parameters
        """

        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() in ignoredComponents:
                    continue
                component.removePropertyParameters(property, params)
        else:
            props = self.properties(property)
            for prop in props:
                for param in params:
                    prop.removeParameter(param)

    def removePropertyParametersByValue(self, property, paramvalues):
        """
        Remove all specified property parameters
        """

        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() in ignoredComponents:
                    continue
                component.removePropertyParametersByValue(property, paramvalues)
        else:
            props = self.properties(property)
            for prop in props:
                for param, value in paramvalues:
                    prop.removeParameterValue(param, value)

    def getITIPInfo(self):
        """
        Get property value details needed to synchronize iTIP components.
        
        @return: C{tuple} of (uid, seq, dtstamp, r-id) some of which may be C{None} if property does not exist
        """
        try:
            # Extract items from component
            uid = self.propertyValue("UID")
            seq = self.propertyValue("SEQUENCE")
            if seq:
                seq = int(seq)
            dtstamp = self.propertyValue("DTSTAMP")
            rid = self.propertyValue("RECURRENCE-ID")
            
        except ValueError:
            return (None, None, None, None)
        
        return (uid, seq, dtstamp, rid)

    @staticmethod
    def compareComponentsForITIP(component1, component2, use_dtstamp=True):
        """
        Compare synchronization information for two components to see if they match according to iTIP.
    
        @param component1: first component to check.
        @type component1: L{Component}
        @param component2: second component to check.
        @type component2: L{Component}
        @param use_dtstamp: whether DTSTAMP is used in addition to SEQUENCE.
        @type component2: C{bool}
        
        @return: 0, 1, -1 as per compareSyncInfo.
        """
        info1 = (None,) + Component.getITIPInfo(component1)
        info2 = (None,) + Component.getITIPInfo(component2)
        return Component.compareITIPInfo(info1, info2, use_dtstamp)
    
    @staticmethod
    def compareITIPInfo(info1, info2, use_dtstamp=True):
        """
        Compare two synchronization information records.
        
        @param info1: a C{tuple} as returned by L{getSyncInfo}.
        @param info2: a C{tuple} as returned by L{getSyncInfo}.
        @return: 1 if info1 > info2, 0 if info1 == info2, -1 if info1 < info2
        """
        
        _ignore_name1, uid1, seq1, dtstamp1, _ignore_rid1 = info1
        _ignore_name2, uid2, seq2, dtstamp2, _ignore_rid2 = info2
        
        # UIDs MUST match
        assert uid1 == uid2
        
        # Look for sequence
        if (seq1 is not None) and (seq2 is not None):
            if seq1 > seq2:
                return 1
            if seq1 < seq2:
                return -1
        elif (seq1 is not None) and (seq2 is None):
            return 1
        elif (seq1 is None) and (seq2 is not None):
            return -1
    
        # Look for DTSTAMP
        if use_dtstamp:
            if (dtstamp1 is not None) and (dtstamp2 is not None):
                if dtstamp1 > dtstamp2:
                    return 1
                if dtstamp1 < dtstamp2:
                    return -1
            elif (dtstamp1 is not None) and (dtstamp2 is None):
                return 1
            elif (dtstamp1 is None) and (dtstamp2 is not None):
                return -1
    
        return 0

    def needsiTIPSequenceChange(self, oldcalendar):
        """
        Compare this calendar with the old one and indicate whether the current one has SEQUENCE
        that is always greater than the old.
        """
        
        for component in self.subcomponents():
            if component.name() in ignoredComponents:
                continue
            oldcomponent = oldcalendar.overriddenComponent(component.getRecurrenceIDUTC())
            if oldcomponent is None:
                oldcomponent = oldcalendar.masterComponent()
                if oldcomponent is None:
                    continue
            newseq = component.propertyValue("SEQUENCE")
            if newseq is None:
                newseq = 0
            oldseq = oldcomponent.propertyValue("SEQUENCE")
            if oldseq is None:
                oldseq = 0
            if newseq <= oldseq:
                return True

        return False

    def bumpiTIPInfo(self, oldcalendar=None, doSequence=False):
        """
        Change DTSTAMP and optionally SEQUENCE on all components.
        """
        
        if doSequence:
            
            def maxSequence(calendar):
                seqs = calendar.getAllPropertiesInAnyComponent("SEQUENCE", depth=1)
                return max(seqs, key=lambda x:x.value()).value() if seqs else 0

            # Determine value to bump to from old calendar (if exists) or self
            newseq = maxSequence(oldcalendar if oldcalendar is not None else self) + 1                
                
            # Bump all components
            self.replacePropertyInAllComponents(Property("SEQUENCE", newseq))
        
        self.replacePropertyInAllComponents(Property("DTSTAMP", PyCalendarDateTime.getNowUTC()))
            
    def normalizeAll(self):
        
        # Normalize all properties
        for prop in tuple(self.properties()):
            result = normalizeProps.get(prop.name())
            if result:
                default_value, default_params = result
            else:
                # Assume default VALUE is TEXT
                default_value = None
                default_params = {"VALUE": "TEXT"}
            
            # Remove any default parameters
            for name in prop.parameterNames():
                value = prop.parameterValue(name)
                if value == default_params.get(name):
                    prop.removeParameter(name)
            
            # If there are no parameters, remove the property if it has the default value
            if len(prop.parameterNames()) == 0:
                if default_value is not None and prop.value() == default_value:
                    self.removeProperty(prop)
                    continue

            # Otherwise look for value normalization
            normalize_function = normalizePropsValue.get(prop.name())
            if normalize_function:
                prop.setValue(normalize_function(prop.value()))

        # Do datetime/rrule normalization
        self.normalizeDateTimes()

        # Do to all sub-components too
        for component in self.subcomponents():
            component.normalizeAll()

    def normalizeDateTimes(self):
        """
        Normalize various datetime properties into UTC and handle DTEND/DURATION variants in such
        a way that we can compare objects with slight differences.
        
        Also normalize the RRULE value parts.
        
        Strictly speaking we should not need to do this as clients should not be messing with
        these properties - i.e. they should round trip them. Unfortunately some do...
        """
        
        # TODO: what about VJOURNAL and VTODO?
        if self.name() == "VEVENT":
            
            # Basic time properties
            dtstart = self.getProperty("DTSTART")
            dtend = self.getProperty("DTEND")
            duration = self.getProperty("DURATION")
            
            timeRange = PyCalendarPeriod(
                start    = dtstart.value(),
                end      = dtend.value()    if dtend is not None else None,
                duration = duration.value() if duration is not None else None,
            )

            # Have to fake the TZID value here when we convert date-times to UTC
            # as we need to know what the original one was
            if dtstart.hasParameter("TZID"):
                dtstart.setParameter("_TZID", dtstart.parameterValue("TZID"))
                dtstart.removeParameter("TZID")
            dtstart.value().adjustToUTC()
            if dtend is not None:
                if dtend.hasParameter("TZID"):
                    dtend.setParameter("_TZID", dtend.parameterValue("TZID"))
                    dtend.removeParameter("TZID")
                dtend.value().adjustToUTC()
            elif duration is not None:
                self.removeProperty(duration)
                self.addProperty(Property("DTEND", timeRange.getEnd().duplicateAsUTC()))

            rdates = self.properties("RDATE")
            for rdate in rdates:
                if rdate.hasParameter("TZID"):
                    rdate.setParameter("_TZID", rdate.parameterValue("TZID"))
                    rdate.removeParameter("TZID")
                for value in rdate.value():
                    value.getValue().adjustToUTC()

            exdates = self.properties("EXDATE")
            for exdate in exdates:
                if exdate.hasParameter("TZID"):
                    exdate.setParameter("_TZID", exdate.parameterValue("TZID"))
                    exdate.removeParameter("TZID")
                for value in exdate.value():
                    value.getValue().adjustToUTC()

            rid = self.getProperty("RECURRENCE-ID")
            if rid is not None:
                rid.removeParameter("TZID")
                rid.setValue(rid.value().duplicateAsUTC())

            # Recurrence rules - we need to normalize the order of the value parts
#            for rrule in self._pycalendar.getRecurrenceSet().getRules():
#                indexedTokens = {}
#                indexedTokens.update([valuePart.split("=") for valuePart in rrule.value().split(";")])
#                sortedValue = ";".join(["%s=%s" % (key, value,) for key, value in sorted(indexedTokens.iteritems(), key=lambda x:x[0])])
#                rrule.setValue(sortedValue)

    def normalizePropertyValueLists(self, propname):
        """
        Convert properties that have a list of values into single properties, to make it easier
        to do comparisons between two ical objects.
        """
        
        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() in ignoredComponents:
                    continue
                component.normalizePropertyValueLists(propname)
        else:
            for prop in tuple(self.properties(propname)):
                if type(prop.value()) is list and len(prop.value()) > 1:
                    self.removeProperty(prop)
                    for value in prop.value():
                        self.addProperty(Property(propname, [value.getValue(),]))

    def normalizeAttachments(self):
        """
        Remove any ATTACH properties that relate to a dropbox.
        """
        
        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() in ignoredComponents:
                    continue
                component.normalizeAttachments()
        else:
            dropboxPrefix = self.propertyValue("X-APPLE-DROPBOX")
            if dropboxPrefix is None:
                return
            for attachment in tuple(self.properties("ATTACH")):
                valueType = attachment.parameterValue("VALUE")
                if valueType in (None, "URI"):
                    dataValue = attachment.value()
                    if dataValue.find(dropboxPrefix) != -1:
                        self.removeProperty(attachment)

    def normalizeCalendarUserAddresses(self, lookupFunction, toUUID=True):
        """
        Do the ORGANIZER/ATTENDEE property normalization.

        @param lookupFunction: function returning full name, guid, CUAs for a given CUA
        @type lookupFunction: L{Function}
        """
        for component in self.subcomponents():
            if component.name() in ignoredComponents:
                continue
            for prop in itertools.chain(
                component.properties("ORGANIZER"),
                component.properties("ATTENDEE")
            ):

                # Check that we can lookup this calendar user address - if not
                # we cannot do anything with it
                cuaddr = normalizeCUAddr(prop.value())
                name, guid, cuaddrs = lookupFunction(cuaddr)
                if guid is None:
                    continue

                # Get any EMAIL parameter
                oldemail = prop.parameterValue("EMAIL")
                if oldemail:
                    oldemail = "mailto:%s" % (oldemail,)

                if toUUID:
                    # Always re-write value to urn:uuid
                    prop.setValue("urn:uuid:%s" % (guid,))
                    
                # If it is already a non-UUID address leave it be
                elif cuaddr.startswith("urn:uuid:"):
                    if oldemail:
                        # Use the EMAIL parameter if it exists
                        newaddr = oldemail
                    else:
                        # Pick the first mailto, or failing that the first http, or failing that the first one
                        first_mailto = None
                        first_http = None
                        first = None
                        for addr in cuaddrs:
                            if addr.startswith("mailto:"):
                                first_mailto = addr
                                break
                            elif addr.startswith("http:"):
                                if not first_http:
                                    first_http = addr
                            elif not first:
                                first = addr
                        
                        if first_mailto:
                            newaddr = first_mailto
                        elif first_http:
                            newaddr = first_http
                        elif first:
                            newaddr = first
                        else:
                            newaddr = None
                    
                    # Make the change
                    if newaddr:
                        prop.setValue(newaddr)

                # Always re-write the CN parameter
                if name:
                    prop.setParameter("CN", name)
                else:
                    prop.removeParameter("CN")

                # Re-write the EMAIL if its value no longer matches
                if oldemail and oldemail not in cuaddrs or oldemail is None and toUUID:
                    if cuaddr.startswith("mailto:") and cuaddr in cuaddrs:
                        email = cuaddr[7:]
                    else:
                        for addr in cuaddrs:
                            if addr.startswith("mailto:"):
                                email = addr[7:]
                                break
                        else:
                            email = None

                    if email:
                        prop.setParameter("EMAIL", email)
                    else:
                        prop.removeParameter("EMAIL")


    def allPerUserUIDs(self):
        
        results = set()
        for component in self.subcomponents():
            if component.name() == "X-CALENDARSERVER-PERUSER":
                results.add(component.propertyValue("X-CALENDARSERVER-PERUSER-UID"))
        return results

    def perUserTransparency(self, rid):
        
        # We will create a cache of all user/rid/transparency values as we will likely
        # be calling this a lot
        if not hasattr(self, "_perUserTransparency"):
            self._perUserTransparency = {}
            
            # Do per-user data
            for component in self.subcomponents():
                if component.name() == "X-CALENDARSERVER-PERUSER":
                    uid = component.propertyValue("X-CALENDARSERVER-PERUSER-UID")
                    for subcomponent in component.subcomponents():
                        if subcomponent.name() == "X-CALENDARSERVER-PERINSTANCE":
                            instancerid = subcomponent.propertyValue("RECURRENCE-ID")
                            transp = subcomponent.propertyValue("TRANSP") == "TRANSPARENT"                                
                            self._perUserTransparency.setdefault(uid, {})[instancerid] = transp
                elif component.name() not in ignoredComponents:
                    instancerid = component.propertyValue("RECURRENCE-ID")
                    transp = component.propertyValue("TRANSP") == "TRANSPARENT"                    
                    self._perUserTransparency.setdefault("", {})[instancerid] = transp

        # Now lookup in cache
        results = []
        for uid, cachedRids in sorted(self._perUserTransparency.items(), key=lambda x:x[0]):
            lookupRid = rid
            if lookupRid not in cachedRids:
                lookupRid = None
            if lookupRid in cachedRids:
                results.append((uid, cachedRids[lookupRid],))
            else:
                results.append((uid, False,))     
        
        return tuple(results)

##
# Timezones
##

def tzexpand(tzdata, start, end):
    """
    Expand a timezone to get onset/utc-offset observance tuples within the specified
    time range.

    @param tzdata: the iCalendar data containing a VTIMEZONE.
    @type tzdata: C{str}
    @param start: date for the start of the expansion.
    @type start: C{date}
    @param end: date for the end of the expansion.
    @type end: C{date}
    
    @return: a C{list} of tuples of (C{datetime}, C{str})
    """
    
    icalobj = Component.fromString(tzdata)
    tzcomp = None
    for comp in icalobj.subcomponents():
        if comp.name() == "VTIMEZONE":
            tzcomp = comp
            break
    else:
        raise InvalidICalendarDataError("No VTIMEZONE component in %s" % (tzdata,))

    tzexpanded = tzcomp._pycalendar.expandAll(start, end)
    
    results = []
    
    # Always need to ensure the start appears in the result
    start.setDateOnly(False)
    if tzexpanded:
        if start != tzexpanded[0][0]:
            results.append((str(start), PyCalendarUTCOffsetValue(tzexpanded[0][1]).getText(),))
    else:
        results.append((str(start), PyCalendarUTCOffsetValue(tzcomp._pycalendar.getTimezoneOffsetSeconds(start)).getText(),))
    for tzstart, _ignore_tzoffsetfrom, tzoffsetto in tzexpanded:
        results.append((
            tzstart.getText(),
            PyCalendarUTCOffsetValue(tzoffsetto).getText(),
        ))
    
    return results

def tzexpandlocal(tzdata, start, end):
    """
    Expand a timezone to get onset(local)/utc-offset-from/utc-offset-to/name observance tuples within the specified
    time range.

    @param tzdata: the iCalendar data containing a VTIMEZONE.
    @type tzdata: L{PyCalendar}
    @param start: date for the start of the expansion.
    @type start: C{date}
    @param end: date for the end of the expansion.
    @type end: C{date}
    
    @return: a C{list} of tuples
    """
    
    icalobj = Component(None, pycalendar=tzdata)
    tzcomp = None
    for comp in icalobj.subcomponents():
        if comp.name() == "VTIMEZONE":
            tzcomp = comp
            break
    else:
        raise InvalidICalendarDataError("No VTIMEZONE component in %s" % (tzdata,))

    tzexpanded = tzcomp._pycalendar.expandAll(start, end, with_name=True)
    
    results = []
    
    # Always need to ensure the start appears in the result
    start.setDateOnly(False)
    if tzexpanded:
        if start != tzexpanded[0][0]:
            results.append((
                str(start),
                PyCalendarUTCOffsetValue(tzexpanded[0][1]).getText(),
                PyCalendarUTCOffsetValue(tzexpanded[0][1]).getText(),
                tzexpanded[0][3],
            ))
    else:
        results.append((
            str(start),
            PyCalendarUTCOffsetValue(tzcomp._pycalendar.getTimezoneOffsetSeconds(start)).getText(),
            PyCalendarUTCOffsetValue(tzcomp._pycalendar.getTimezoneOffsetSeconds(start)).getText(),
            tzcomp.getTZName(),
        ))
    for tzstart, tzoffsetfrom, tzoffsetto, name in tzexpanded:
        results.append((
            tzstart.getText(),
            PyCalendarUTCOffsetValue(tzoffsetfrom).getText(),
            PyCalendarUTCOffsetValue(tzoffsetto).getText(),
            name,
        ))
    
    return results

##
# Utilities
##

#
# This function is from "Python Cookbook, 2d Ed., by Alex Martelli, Anna
# Martelli Ravenscroft, and David Ascher (O'Reilly Media, 2005) 0-596-00797-3."
#
def merge(*iterables):
    """
    Merge sorted iterables into one sorted iterable.
    @param iterables: arguments are iterables which yield items in sorted order.
    @return: an iterable of all items generated by every iterable in
    C{iterables} in sorted order.
    """
    heap = []
    for iterable in iterables:
        iterator = iter(iterable)
        for value in iterator:
            heap.append((value, iterator))
            break
    heapq.heapify(heap)
    while heap:
        value, iterator = heap[0]
        yield value
        for value in iterator:
            heapq.heapreplace(heap, (value, iterator))
            break
        else:
            heapq.heappop(heap)
