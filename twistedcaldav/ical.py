##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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
    "iCalendarProductID",
    "allowedComponents",
    "Property",
    "Component",
    "FixedOffset",
    "parse_date",
    "parse_time",
    "parse_datetime",
    "parse_date_or_datetime",
    "parse_duration",
    "tzexpand",
]

from twisted.web2.dav.util import allDataFromStream
from twisted.web2.stream import IStream
from twistedcaldav.dateops import compareDateTime, normalizeToUTC, timeRangesOverlap
from twistedcaldav.scheduling.cuaddress import normalizeCUAddr
from twistedcaldav.instance import InstanceList
from twistedcaldav.log import Logger
from vobject import newFromBehavior, readComponents
from vobject.base import Component as vComponent, ContentLine as vContentLine, ParseError as vParseError
from vobject.icalendar import TimezoneComponent, dateTimeToString, deltaToOffset, getTransition, stringToDate, stringToDateTime, stringToDurations, utc
import cStringIO as StringIO
import datetime
import heapq

log = Logger()

iCalendarProductID = "-//CALENDARSERVER.ORG//NONSGML Version 1//EN"

allowedComponents = (
    "VEVENT",
    "VTODO",
    "VTIMEZONE",
    "VJOURNAL",
    "VFREEBUSY",
    #"VAVAILABILITY",
)

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

            vobj = kwargs["vobject"]

            if not isinstance(vobj, vContentLine):
                raise TypeError("Not a vContentLine: %r" % (property,))

            self._vobject = vobj
        else:
            # Convert params dictionary to list of lists format used by vobject
            lparams = [[key] + lvalue for key, lvalue in params.items()]
            self._vobject = vContentLine(name, lparams, value, isNative=True)

    def __str__ (self): return self._vobject.serialize()
    def __repr__(self): return "<%s: %r: %r>" % (self.__class__.__name__, self.name(), self.value())

    def __hash__(self):
        return hash(str(self))

    def __ne__(self, other): return not self.__eq__(other)
    def __eq__(self, other):
        if not isinstance(other, Property): return False
        return self.name() == other.name() and self.value() == other.value() and self.params() == other.params()

    def __gt__(self, other): return not (self.__eq__(other) or self.__lt__(other))
    def __lt__(self, other):
        my_name = self.name()
        other_name = other.name()

        if my_name < other_name: return True
        if my_name > other_name: return False

        return self.value() < other.value()

    def __ge__(self, other): return self.__eq__(other) or self.__gt__(other)
    def __le__(self, other): return self.__eq__(other) or self.__lt__(other)

    def name  (self): return self._vobject.name

    def value (self): return self._vobject.value
    def setValue(self, value):
        self._vobject.value = value

    def params(self):
        """
        Returns a mapping object containing parameters for this property.

        Keys are parameter names, values are sequences containing
        values for the named parameter.
        """
        return self._vobject.params

    def paramValue(self, name):
        """
        Returns a single value for the given parameter.  Raises
        ValueError if the parameter has more than one value.
        """
        values = self._vobject.params.get(name, [None,])
        assert type(values) is list, "vobject returned non-list value for parameter %r in property %r" % (name, self)
        if len(values) != 1:
            raise ValueError("Not exactly one %s value in property %r" % (name, self))
        return values[0]

    def containsTimeRange(self, start, end, tzinfo=None):
        """
        Determines whether this property contains a date/date-time within the specified
        start/end period.
        The only properties allowed for this query are: COMPLETED, CREATED, DTSTAMP and
        LAST-MODIFIED (caldav -09).
        @param start: a L{datetime.datetime} or L{datetime.date} specifying the
            beginning of the given time span.
        @param end: a L{datetime.datetime} or L{datetime.date} specifying the
            end of the given time span.  C{end} may be None, indicating that
            there is no end date.
        @param tzinfo: the default L{datetime.tzinfo} to use in datetime comparisons.
        @return: True if the property's date/date-time value is within the given time range,
                 False if not, or the property is not an appropriate date/date-time value.
        """

        # Verify that property name matches the ones allowed
        allowedNames = ["COMPLETED", "CREATED", "DTSTAMP", "LAST-MODIFIED"]
        if self.name() not in allowedNames:
            return False
        
        # get date/date-time value
        dt = self.value()
        assert isinstance(dt, datetime.date), "Not a date/date-time value: %r" % (self,)
        
        return timeRangesOverlap(dt, None, start, end, tzinfo)

    def transformAllFromNative(self):
        transformed = self._vobject.isNative
        if transformed:
            self._vobject = self._vobject.transformFromNative()
            self._vobject.transformChildrenFromNative()
        return transformed
        
    def transformAllToNative(self):
        transformed = not self._vobject.isNative
        if transformed:
            self._vobject = self._vobject.transformToNative()
            self._vobject.transformChildrenToNative()
        return transformed

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
    def fromString(clazz, string):
        """
        Construct a L{Component} from a string.
        @param string: a string containing iCalendar data.
        @return: a L{Component} representing the first component described by
            C{string}.
        """
        if type(string) is unicode:
            string = string.encode("utf-8")
        return clazz.fromStream(StringIO.StringIO(string))

    @classmethod
    def fromStream(clazz, stream):
        """
        Construct a L{Component} from a stream.
        @param stream: a C{read()}able stream containing iCalendar data.
        @return: a L{Component} representing the first component described by
            C{stream}.
        """
        try:
            return clazz(None, vobject=readComponents(stream, findBegin=False).next())
        except UnicodeDecodeError, e:
            stream.seek(0)
            raise ValueError("%s: %s" % (e, stream.read()))
        except vParseError, e:
            raise ValueError(e)
        except StopIteration, e:
            raise ValueError(e)

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

    def __init__(self, name, **kwargs):
        """
        Use this constructor to initialize an empty L{Component}.
        To create a new L{Component} from X{iCalendar} data, don't use this
        constructor directly.  Use one of the factory methods instead.
        @param name: the name (L{str}) of the X{iCalendar} component type for the
            component.
        """
        if name is None:
            if "vobject" in kwargs:
                vobj = kwargs["vobject"]

                if vobj is not None:
                    if not isinstance(vobj, vComponent):
                        raise TypeError("Not a vComponent: %r" % (vobj,))

                self._vobject = vobj
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
            self._vobject = newFromBehavior(name)
            self._parent = None

    def __str__ (self): return self._vobject.serialize()
    def __repr__(self): return "<%s: %r>" % (self.__class__.__name__, str(self._vobject))

    def __hash__(self):
        return hash(str(self))

    def __ne__(self, other): return not self.__eq__(other)
    def __eq__(self, other):
        if not isinstance(other, Component):
            return False

        my_properties = set(self.properties())
        for property in other.properties():
            if property in my_properties:
                my_properties.remove(property)
            else:
                return False
        if my_properties:
            return False

        my_subcomponents = set(self.subcomponents())
        for subcomponent in other.subcomponents():
            for testcomponent in my_subcomponents:
                if subcomponent == testcomponent:
                    my_subcomponents.remove(testcomponent)
                    break
            else:
                return False
        if my_subcomponents:
            return False

        return True

    # FIXME: Should this not be in __eq__?
    def same(self, other):
        return self._vobject == other._vobject
    
    def name(self):
        """
        @return: the name of the iCalendar type of this component.
        """
        return self._vobject.name

    def setBehavior(self, behavior):
        """
        Set the behavior of the underlying iCal object.
        @param behavior: the behavior type to set.
        """
        self._vobject.setBehavior(behavior)

    def mainType(self):
        """
        Determine the primary type of iCal component in this calendar.
        @return: the name of the primary type.
        @raise: L{ValueError} if there is more than one primary type.
        """
        assert self.name() == "VCALENDAR", "Must be a VCALENDAR: %r" % (self,)
        
        type = None
        for component in self.subcomponents():
            if component.name() == "VTIMEZONE":
                continue
            elif type and (type != component.name()):
                raise ValueError("Component contains more than one type of primary type: %r" % (self,))
            else:
                type = component.name()
        
        return type
    
    def mainComponent(self, allow_multiple=False):
        """
        Return the primary iCal component in this calendar.
        @return: the L{Component} of the primary type.
        @raise: L{ValueError} if there is more than one primary type.
        """
        assert self.name() == "VCALENDAR", "Must be a VCALENDAR: %r" % (self,)
        
        result = None
        for component in self.subcomponents():
            if component.name() == "VTIMEZONE":
                continue
            elif not allow_multiple and (result is not None):
                raise ValueError("Calendar contains more than one primary component: %r" % (self,))
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
            if component.name() == "VTIMEZONE":
                continue
            if not component.hasProperty("RECURRENCE-ID"):
                return component
        
        return None
    
    def overriddenComponent(self, recurrence_id):
        """
        Return the overridden iCal component in this calendar matching the supplied RECURRENCE-ID property.

        @param recurrence_id: The RECURRENCE-ID property value to match.
        @type recurrence_id: L{datetime.datetime} or L{datetime.date}
        @return: the L{Component} for the overridden component,
            or C{None} if there isn't one.
        """
        assert self.name() == "VCALENDAR", "Must be a VCALENDAR: %r" % (self,)
        
        for component in self.subcomponents():
            if component.name() == "VTIMEZONE":
                continue
            rid = component.getRecurrenceIDUTC()
            if rid and recurrence_id and compareDateTime(rid, recurrence_id) == 0:
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
        return Component(None, vobject=vComponent.duplicate(self._vobject))
        
    def subcomponents(self):
        """
        @return: an iterable of L{Component} objects, one for each subcomponent
            of this component.
        """
        return (
            Component(None, vobject=c, parent=self)
            for c in self._vobject.getChildren()
            if isinstance(c, vComponent)
        )

    def addComponent(self, component):
        """
        Adds a subcomponent to this component.
        @param component: the L{Component} to add as a subcomponent of this
            component.
        """
        self._vobject.add(component._vobject)
        component._parent = self

    def removeComponent(self, component):
        """
        Removes a subcomponent from this component.
        @param component: the L{Component} to remove.
        """
        self._vobject.remove(component._vobject)

    def hasProperty(self, name):
        """
        @param name: the name of the property whose existence is being tested.
        @return: True if the named property exists, False otherwise.
        """
        try:
            return len(self._vobject.contents[name.lower()]) > 0
        except KeyError:
            return False

    def getProperty(self, name):
        """
        Get one property from the property list.
        @param name: the name of the property to get.
        @return: the L{Property} found or None.
        @raise: L{ValueError} if there is more than one property of the given name.
        """
        properties = tuple(self.properties(name))
        if len(properties) == 1: return properties[0]
        if len(properties) > 1: raise ValueError("More than one %s property in component %r" % (name, self))
        return None
        
    def properties(self, name=None):
        """
        @param name: if given and not C{None}, restricts the returned properties
            to those with the given C{name}.
        @return: an iterable of L{Property} objects, one for each property of
            this component.
        """
        if name is None:
            properties = self._vobject.getChildren()
        else:
            try:
                properties = self._vobject.contents[name.lower()]
            except KeyError:
                return ()

        return (
            Property(None, None, None, vobject=p)
            for p in properties
            if isinstance(p, vContentLine)
        )

    def propertyValue(self, name):
        properties = tuple(self.properties(name))
        if len(properties) == 1:
            return properties[0].value()
        if len(properties) > 1:
            raise ValueError("More than one %s property in component %r" % (name, self))
        return None


    def propertyNativeValue(self, name):
        """
        Return the native property value for the named property in the supplied component.
        NB Assumes a single property exists in the component.
        @param name: the name of the property whose value is required
        @return: the native property value
        """
        properties = tuple(self.properties(name))

        if len(properties) == 1:
            transormed = properties[0].transformAllToNative()
    
            result = properties[0].value()
    
            if transormed:
                properties[0].transformAllFromNative()
                
            return result

        elif len(properties) > 1:
            raise ValueError("More than one %s property in component %r" % (name, self))
        else:
            return None

    def getStartDateUTC(self):
        """
        Return the start date or date-time for the specified component
        converted to UTC.
        @param component: the Component whose start should be returned.
        @return: the datetime.date or datetime.datetime for the start.
        """
        dtstart = self.propertyNativeValue("DTSTART")
        if dtstart is not None:
            return normalizeToUTC(dtstart)
        else:
            return None
 
    def getEndDateUTC(self):
        """
        Return the end date or date-time for the specified component,
        taking into account the presence or absence of DTEND/DURATION properties.
        The returned date-time is converted to UTC.
        @param component: the Component whose end should be returned.
        @return: the datetime.date or datetime.datetime for the end.
        """
        dtend = self.propertyNativeValue("DTEND")
        if dtend is None:
            dtstart = self.propertyNativeValue("DTSTART")
            duration = self.propertyNativeValue("DURATION")
            if duration is not None:
                dtend = dtstart + duration

        if dtend is not None:
            return normalizeToUTC(dtend)
        else:
            return None

    def getDueDateUTC(self):
        """
        Return the due date or date-time for the specified component
        converted to UTC. Use DTSTART/DURATION if no DUE property.
        @param component: the Component whose start should be returned.
        @return: the datetime.date or datetime.datetime for the start.
        """
        due = self.propertyNativeValue("DUE")
        if due is None:
            dtstart = self.propertyNativeValue("DTSTART")
            duration = self.propertyNativeValue("DURATION")
            if dtstart is not None and duration is not None:
                due = dtstart + duration

        if due is not None:
            return normalizeToUTC(due)
        else:
            return None
 
    def getRecurrenceIDUTC(self):
        """
        Return the recurrence-id for the specified component.
        @param component: the Component whose r-id should be returned.
        @return: the datetime.date or datetime.datetime for the r-id.
        """
        rid = self.propertyNativeValue("RECURRENCE-ID")

        if rid is not None:
            return normalizeToUTC(rid)
        else:
            return None
 
    def getRange(self):
        """
        Determine whether a RANGE=THISANDFUTURE parameter is present
        on any RECURRENCE-ID property.
        @return: True if the parameter is present, False otherwise.
        """
        ridprop = self.getProperty("RECURRENCE-ID")
        if ridprop is not None:
            range = ridprop.paramValue("RANGE")
            if range is not None:
                return (range == "THISANDFUTURE")

        return False
            
    def getTriggerDetails(self):
        """
        Return the trigger information for the specified alarm component.
        @param component: the Component whose start should be returned.
        @return: ta tuple consisting of:
            trigger : the 'native' trigger value (either datetime.date or datetime.timedelta)
            related : either True (for START) or False (for END)
            repeat : an integer for the REPEAT count
            duration: the repeat duration if present, otherwise None
        """
        assert self.name() == "VALARM", "Component is not a VAlARM: %r" % (self,)
        
        # The trigger value
        trigger = self.propertyNativeValue("TRIGGER")
        if trigger is None:
            raise ValueError("VALARM has no TRIGGER property: %r" % (self,))
        
        # The related parameter
        related = self.getProperty("TRIGGER").paramValue("RELATED")
        if related is None:
            related = True
        else:
            related = (related == "START")
        
        # Repeat property
        repeat = self.propertyNativeValue("REPEAT")
        if repeat is None: repeat = 0
        else: repeat = int(repeat)
        
        # Duration property
        duration = self.propertyNativeValue("DURATION")

        if repeat > 0 and duration is None:
            raise ValueError("VALARM has invalid REPEAT/DURATIOn properties: %r" % (self,))

        return (trigger, related, repeat, duration)
 
    def getRRuleSet(self, addRDate = False):
        self.transformAllToNative()
        return self._vobject.getrruleset(addRDate)

    def addProperty(self, property):
        """
        Adds a property to this component.
        @param property: the L{Property} to add to this component.
        """
        self._vobject.add(property._vobject)

    def removeProperty(self, property):
        """
        Remove a property from this component.
        @param property: the L{Property} to remove from this component.
        """
        self._vobject.remove(property._vobject)

    def replaceProperty(self, property):
        """
        Add or replace a property in this component.
        @param property: the L{Property} to add or replace in this component.
        """
        
        # Remove all existing ones first
        for removeit in tuple(self.properties(property.name())):
            self.removeProperty(removeit)
        self.addProperty(property)

    def timezoneIDs(self):
        """
        Returns the set of TZID parameter values appearing in any property in
        this component.
        @return: a set of strings, one for each unique TZID value.
        """
        result = set()

        for property in self.properties():
            for propertyname in ("TZID", "X-VOBJ-ORIGINAL-TZID"):
                tzid = property.paramValue(propertyname)
                if tzid is not None:
                    result.add(tzid)
                    break
            else:
                items = property.value()
                if type(items) is not list:
                    items = [items]
                for item in items:
                    tzinfo = getattr(item, 'tzinfo', None)
                    tzid = TimezoneComponent.pickTzid(tzinfo)
                    if tzid is not None:
                        result.add(tzid)
        
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
    
    def expand(self, start, end, timezone=None):
        """
        Expand the components into a set of new components, one for each
        instance in the specified range. Date-times are converted to UTC. A
        new calendar object is returned.
        @param start: the L{datetime.datetime} for the start of the range.
        @param end: the L{datetime.datetime} for the end of the range.
        @param timezone: the L{Component} the VTIMEZONE to use for floating/all-day.
        @return: the L{Component} for the new calendar with expanded instances.
        """
        
        tzinfo = timezone.gettzinfo() if timezone else None

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
            if timeRangesOverlap(instance.start, instance.end, start, end, tzinfo):
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
            if isinstance(value, datetime.datetime) and value.tzinfo is not None:
                property.setValue(value.astimezone(utc))
        
        # Now reset DTSTART, DTEND/DURATION
        for property in newcomp.properties("DTSTART"):
            property.setValue(instance.start)
        for property in newcomp.properties("DTEND"):
            property.setValue(instance.end)
        for property in newcomp.properties("DURATION"):
            property.setValue(instance.end - instance.start)
        
        # Add RECURRENCE-ID if not first instance
        if not first:
            newcomp.addProperty(Property("RECURRENCE-ID", instance.rid))
            newcomp.transformAllToNative()

        return newcomp

    def expandTimeRanges(self, limit):
        """
        Expand the set of recurrence instances for the components
        contained within this VCALENDAR component. We will assume
        that this component has already been validated as a CalDAV resource
        (i.e. only one type of component, all with the same UID)
        @param limit: datetime.date value representing the end of the expansion.
        @return: a set of Instances for each recurrence in the set.
        """
        
        componentSet = self.subcomponents()
        return self.expandSetTimeRanges(componentSet, limit)
    
    def expandSetTimeRanges(self, componentSet, limit):
        """
        Expand the set of recurrence instances up to the specified date limit.
        What we do is first expand the master instance into the set of generate
        instances. Then we merge the overridden instances, taking into account
        THISANDFUTURE and THISANDPRIOR.
        @param limit: datetime.date value representing the end of the expansion.
        @param componentSet: the set of components that are to make up the
                recurrence set. These MUST all be components with the same UID
                and type, forming a proper recurring set.
        @return: a set of Instances for each recurrence in the set.
        """
        
        # Set of instances to return
        instances = InstanceList()
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
                if component.name() != "VTIMEZONE":
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
                if component.name() != "VTIMEZONE" and component.isRecurring():
                    return True
        else:
            for propname in ("RRULE", "RDATE", "EXDATE", "RECUURENCE-ID",):
                if self.hasProperty(propname):
                    return True
        return False
        
    def deriveInstance(self, rid):
        """
        Derive an instance from the master component that has the provided RECURRENCE-ID, but
        with all other properties, components etc from the master.

        @param rid: recurrence-id value
        @type rid: L{datetime.datetime}
        """
        
        # Must have a master component
        master = self.masterComponent()
        if master is None:
            return None

        # TODO: Check that the recurrence-id is a valid instance
        
        # Create the derived instance
        newcomp = master.duplicate()

        # Strip out unwanted recurrence properties
        for property in tuple(newcomp.properties()):
            if property.name() in ["RRULE", "RDATE", "EXRULE", "EXDATE", "RECURRENCE-ID"]:
                newcomp.removeProperty(property)
        
        # Adjust times
        offset = rid - newcomp.getStartDateUTC()
        dtstart = newcomp.getProperty("DTSTART")
        dtstart.setValue(dtstart.value() + offset)
        if newcomp.hasProperty("DTEND"):
            dtend = newcomp.getProperty("DTEND")
            dtend.setValue(dtend.value() + offset)
        newcomp.addProperty(Property("RECURRENCE-ID", dtstart.value()))
            
        return newcomp
        
    def resourceUID(self):
        """
        @return: the UID of the subcomponents in this component.
        """
        assert self.name() == "VCALENDAR", "Not a calendar: %r" % (self,)

        if not hasattr(self, "_resource_uid"):
            for subcomponent in self.subcomponents():
                if subcomponent.name() != "VTIMEZONE":
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
                else:
                    self._resource_type = name
                    break
            else:
                if has_timezone:
                    self._resource_type = "VTIMEZONE"
                else:
                    raise ValueError("No component type found for calendar component: %r" % (self,))

        return self._resource_type

    def validCalendarForCalDAV(self):
        """
        @raise ValueError: if the given calendar data is not valid.
        """
        if self.name() != "VCALENDAR": raise ValueError("Not a calendar")
        if not self.resourceType(): raise ValueError("Unknown resource type")

        version = self.propertyValue("VERSION")
        if version != "2.0": raise ValueError("Not a version 2.0 iCalendar (version=%s)" % (version,))

    def validateForCalDAV(self):
        """
        @raise ValueError: if the given calendar component is not valid for
            use as a X{CalDAV} resource.
        """
        self.validCalendarForCalDAV()

        # Disallowed in CalDAV-Access-08, section 4.1
        if self.hasProperty("METHOD"):
            raise ValueError("METHOD property is not allowed in CalDAV iCalendar data")

        self.validateComponentsForCalDAV(False)

    def validateComponentsForCalDAV(self, method):
        """
        @param method:     True if METHOD property is allowed, False otherwise.
        @raise ValueError: if the given calendar component is not valid for
            use as a X{CalDAV} resource.
        """
        #
        # Must not contain more than one type of iCalendar component, except for
        # the required timezone components, and component UIDs must match
        #
        ctype         = None
        component_id  = None
        timezone_refs = set()
        timezones     = set()
        got_master    = False
        
        for subcomponent in self.subcomponents():
            # Disallowed in CalDAV-Access-08, section 4.1
            if not method and subcomponent.hasProperty("METHOD"):
                raise ValueError("METHOD property is not allowed in CalDAV iCalendar data")
        
            if subcomponent.name() == "VTIMEZONE":
                timezones.add(subcomponent.propertyValue("TZID"))
            else:
                if ctype is None:
                    ctype = subcomponent.name()
                else:
                    if ctype != subcomponent.name():
                        raise ValueError("Calendar resources may not contain more than one type of calendar " +
                                         "component (%s and %s found)" % (ctype, subcomponent.name()))
        
                if ctype not in allowedComponents:
                    raise ValueError("Component type: %s not allowed" % (ctype,))
                    
                uid = subcomponent.propertyValue("UID")
                if uid is None:
                    raise ValueError("All components must have UIDs")
                    
                if component_id is None:
                    component_id = uid
                else:
                    if component_id != uid:
                        raise ValueError("Calendar resources may not contain components with different UIDs " +
                                         "(%s and %s found)" % (component_id, subcomponent.propertyValue("UID")))
                    elif subcomponent.propertyValue("Recurrence-ID") is None:
                        if got_master:
                            raise ValueError("Calendar resources may not contain components with the same UIDs and no Recurrence-IDs" +
                                             "(%s and %s found)" % (component_id, subcomponent.propertyValue("UID")))
                        else:
                            got_master = True
        
                timezone_refs.update(subcomponent.timezoneIDs())
        
        #
        # Make sure required timezone components are present
        #
        for timezone_ref in timezone_refs:
            if timezone_ref not in timezones:
                raise ValueError("Timezone ID %s is referenced but not defined" % (timezone_ref,))
        
        #
        # FIXME:
        #   This test is not part of the spec; it appears to be legal (but
        #   goofy?) to have extra timezone components.
        #
        for timezone in timezones:
            if timezone not in timezone_refs:
                #raise ValueError(
                log.msg(
                    "Timezone %s is not referenced by any non-timezone component" % (timezone,)
                )

    def transformAllFromNative(self):
        self._vobject = self._vobject.transformFromNative()
        self._vobject.transformChildrenFromNative(False)
        
    def transformAllToNative(self):
        self._vobject = self._vobject.transformToNative()
        self._vobject.transformChildrenToNative()

    def gettzinfo(self):
        """
        Get the tzinfo for a Timezone component.

        @return: L{datetime.tzinfo} if this is a VTIMEZONE, otherwise None.
        """
        if self.name() == "VTIMEZONE":
            return self._vobject.gettzinfo()
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
        except ValueError:
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
            self.validateComponentsForCalDAV(True)
            
            # Next we could check the iTIP status for each type of method/component pair, however
            # we can also leave that up to the server except for the REQUEST/VFREEBUSY case which
            # the server will handle itself.
            
            if (method == "REQUEST") and (self.mainType() == "VFREEBUSY"):
                # TODO: verify REQUEST/VFREEBUSY as being OK
                
                # Only one VFREEBUSY (actually multiple X-'s are allowed but we will reject)
                if len([c for c in self.subcomponents()]) != 1:
                    return False

        except ValueError:
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
                if component.name() != "VTIMEZONE":
                    return component.getOrganizer()
        else:
            try:
                # Find the primary subcomponent
                return self.propertyValue("ORGANIZER")
            except ValueError:
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
                if component.name() != "VTIMEZONE":
                    result += component.getOrganizersByInstance()
            return result
        else:
            try:
                # Should be just one ORGANIZER
                org = self.propertyValue("ORGANIZER")
                rid = self.getRecurrenceIDUTC()
                if org:
                    return ((org, rid),)
            except ValueError:
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
                if component.name() != "VTIMEZONE":
                    return component.getOrganizerProperty()
        else:
            try:
                # Find the primary subcomponent
                return self.getProperty("ORGANIZER")
            except ValueError:
                pass

        return None

    def getAttendees(self):
        """
        Get the organizer value. Works on either a VCALENDAR or on a component.
        
        @param match: a C{list} of calendar user address strings to try and match.
        @return: a C{list} of the string values of the Attendee property, or None
        """
        
        # Extract appropriate sub-component if this is a VCALENDAR
        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() != "VTIMEZONE":
                    return component.getAttendees()
        else:
            # Find the property values
            return [p.value() for p in self.properties("ATTENDEE")]

        return None

    def getAttendeesByInstance(self):
        """
        Get the organizer value for each instance.
        
        @return: a list of tuples of (organizer value, recurrence-id)
        """
        
        # Extract appropriate sub-component if this is a VCALENDAR
        if self.name() == "VCALENDAR":
            result = ()
            for component in self.subcomponents():
                if component.name() != "VTIMEZONE":
                    result += component.getAttendeesByInstance()
            return result
        else:
            result = ()
            rid = self.getRecurrenceIDUTC()
            for attendee in self.properties("ATTENDEE"):
                result += ((attendee.value(), rid),)
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
                if component.name() != "VTIMEZONE":
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
            if component.name() != "VTIMEZONE":
                attendee = component.getAttendeeProperty(match)
                if attendee:
                    results.append(attendee)

        return results

    def getMaskUID(self):
        """
        Get the X-CALENDARSEREVR-MASK-UID value. Works on either a VCALENDAR or on a component.
        
        @return: the string value of the X-CALENDARSEREVR-MASK-UID property, or None
        """
        
        # Extract appropriate sub-component if this is a VCALENDAR
        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() != "VTIMEZONE":
                    return component.getMaskUID()
        else:
            try:
                # Find the primary subcomponent
                return self.propertyValue("X-CALENDARSERVER-MASK-UID")
            except ValueError:
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
            if component.name() == "VTIMEZONE":
                continue
            for property in component.properties(propname):
                if propvalue is None or property.value() == propvalue:
                    property.params()[paramname] = [paramvalue]
    
    def hasPropertyInAnyComponent(self, properties):
        """
        Test for the existence of one or more properties in any component.
        
        @param properties: property names to test for
        @type properties: C{list} or C{tuple}
        """

        for property in properties:
            if self.hasProperty(property):
                return True

        for component in self.subcomponents():
            if component.hasPropertyInAnyComponent(properties):
                return True

        return False

    def addPropertyToAllComponents(self, property):
        """
        Add a property to all top-level components except VTIMEZONE.

        @param property: the property to add
        @type property: L{Property}
        """
        
        for component in self.subcomponents():
            if component.name() == "VTIMEZONE":
                continue
            component.addProperty(property)

    def replacePropertyInAllComponents(self, property):
        """
        Replace a property in all components.
        @param property: the L{Property} to replace in this component.
        """
        
        for component in self.subcomponents():
            if component.name() == "VTIMEZONE":
                continue
            component.replaceProperty(property)
    
    def transferProperties(self, from_calendar, properties):
        """
        Transfer specified properties from old calendar into all components
        of this calendar, synthesizing any for new overridden instances.
 
        @param from_calendar: the old calendar to copy from
        @type from_calendar: L{Component}
        @param properties: the property names to copy over
        @type properties: C{typle} or C{list}
        """

        assert from_calendar.name() == "VCALENDAR", "Not a calendar: %r" % (self,)
        
        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() == "VTIMEZONE":
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
            
    def attendeesView(self, attendees):
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
            if component.name() == "VTIMEZONE":
                continue
            found_all_attendees = True
            for attendee in attendees:
                if component.getAttendeeProperty((attendee,)) is None:
                    found_all_attendees = False
                    break
            if not found_all_attendees:
                remove_components.append(component)
            if component.getRecurrenceIDUTC() is None:
                master_component = component
                if not found_all_attendees:
                    removed_master = True
                
        # Now remove the unwanted components - but we may need to exdate the master
        exdates = []
        for component in remove_components:
            rid = component.getRecurrenceIDUTC()
            if rid is not None:
                exdates.append(rid)
            self.removeComponent(component)
            
        if not removed_master and master_component is not None:
            for exdate in exdates:
                master_component.addProperty(Property("EXDATE", (exdate,)))
    
    def filterComponents(self, rids):
        
        # If master is in rids do nothing
        if not rids or "" in rids:
            return True
        
        assert self.name() == "VCALENDAR", "Not a calendar: %r" % (self,)
            
        # Remove components not in the list
        components = tuple(self.subcomponents())
        remaining = len(components)
        for component in components:
            if component.name() == "VTIMEZONE":
                remaining -= 1
                continue
            rid = component.getRecurrenceIDUTC()
            if (dateTimeToString(rid) if rid else "") not in rids:
                self.removeComponent(component)
                remaining -= 1
                
        return remaining != 0
        
    def removeAllButOneAttendee(self, attendee):
        """
        Remove all ATTENDEE properties except for the one specified.
        """

        assert self.name() == "VCALENDAR", "Not a calendar: %r" % (self,)

        for component in self.subcomponents():
            if component.name() == "VTIMEZONE":
                continue
            [component.removeProperty(p) for p in tuple(component.properties("ATTENDEE")) if p.value().lower() != attendee.lower()]
            
    def removeAlarms(self):
        """
        Remove all Alarms components
        """

        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() == "VTIMEZONE":
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
            if self.name() == "VTIMEZONE":
                return
            
            for p in tuple(self.properties()):
                if (keep and p.name() not in keep) or (remove and p.name() in remove):
                    self.removeProperty(p)
                
    def removeXProperties(self, keep_properties=(), do_subcomponents=True):
        """
        Remove all X- properties except the specified ones
        """

        if do_subcomponents:
            for component in self.subcomponents():
                component.removeXProperties(keep_properties, do_subcomponents=False)
        else:
            if self.name() == "VTIMEZONE":
                return
            for p in tuple(self.properties()):
                if p.name().startswith("X-") and p.name() not in keep_properties:
                    self.removeProperty(p)
            
    def removePropertyParameters(self, property, params):
        """
        Remove all specified property parameters
        """

        assert self.name() == "VCALENDAR", "Not a calendar: %r" % (self,)

        for component in self.subcomponents():
            if component.name() == "VTIMEZONE":
                continue
            props = component.properties(property)
            for prop in props:
                for param in params:
                    try:
                        del prop.params()[param]
                    except KeyError:
                        pass

    def removePropertyParametersByValue(self, property, paramvalues):
        """
        Remove all specified property parameters
        """

        assert self.name() == "VCALENDAR", "Not a calendar: %r" % (self,)

        for component in self.subcomponents():
            if component.name() == "VTIMEZONE":
                continue
            props = component.properties(property)
            for prop in props:
                for param, value in paramvalues:
                    try:
                        prop.params()[param].remove(value)
                        if len(prop.params()[param]) == 0:
                            del prop.params()[param]
                    except KeyError:
                        pass
                    except ValueError:
                        pass

    def normalizePropertyValueLists(self, propname):
        """
        Convert properties that have a list of values into single properties, to make it easier
        to do comparisons between two ical objects.
        """
        
        assert self.name() == "VCALENDAR", "Not a calendar: %r" % (self,)

        for component in self.subcomponents():
            if component.name() == "VTIMEZONE":
                continue
            for prop in tuple(component.properties(propname)):
                if type(prop.value()) is list and len(prop.value()) > 1:
                    component.removeProperty(prop)
                    for value in prop.value():
                        component.addProperty(Property(propname, [value,]))

##
# Dates and date-times
##

class FixedOffset (datetime.tzinfo):
    """
    Fixed offset in minutes east from UTC.
    """
    def __init__(self, offset, name=None):
        self._offset = datetime.timedelta(minutes=offset)
        self._name   = name

    def utcoffset(self, dt): return self._offset
    def tzname   (self, dt): return self._name
    def dst      (self, dt): return datetime.timedelta(0)

def parse_date(date_string):
    """
    Parse an iCalendar-format DATE string.  (RFC 2445, section 4.3.4)
    @param date_string: an iCalendar-format DATE string.
    @return: a L{datetime.date} object for the given C{date_string}.
    """
    try:
        return stringToDate(date_string)
    except (vParseError, ValueError):
        raise ValueError("Invalid iCalendar DATE: %r" % (date_string,))

def parse_time(time_string):
    """
    Parse iCalendar-format TIME string.  (RFC 2445, section 4.3.12)
    @param time_string: an iCalendar-format TIME string.
    @return: a L{datetime.time} object for the given C{time_string}.
    """
    try:
        # Parse this as a fake date-time string by prepending date
        with_date = "20000101T" + time_string
        return stringToDateTime(with_date).time()
    except (vParseError, ValueError):
        raise ValueError("Invalid iCalendar TIME: %r" % (time_string,))

def parse_datetime(datetime_string):
    """
    Parse iCalendar-format DATE-TIME string.  (RFC 2445, section 4.3.5)
    @param datetime_string: an iCalendar-format DATE-TIME string.
    @return: a L{datetime.datetime} object for the given C{datetime_string}.
    """
    try:
        return stringToDateTime(datetime_string)
    except (vParseError, ValueError):
        raise ValueError("Invalid iCalendar DATE-TIME: %r" % (datetime_string,))

def parse_date_or_datetime(date_string):
    """
    Parse iCalendar-format DATE or DATE-TIME string.  (RFC 2445, sections 4.3.4
    and 4.3.5)
    @param date_string: an iCalendar-format DATE or DATE-TIME string.
    @return: a L{datetime.date} or L{datetime.datetime} object for the given
        C{date_string}.
    """
    try:
        if len(date_string) == 8:
            return parse_date(date_string)
        else:
            return parse_datetime(date_string)
    except ValueError:
        raise ValueError("Invalid iCalendar DATE or DATE-TIME: %r" % (date_string,))

def parse_duration(duration_string):
    """
    Parse iCalendar-format DURATION string.  (RFC 2445, sections 4.3.6)
    @param duration_string: an iCalendar-format DURATION string.
    @return: a L{datetime.timedelta} object for the given C{duration_string}.
    """
    try:
        return stringToDurations(duration_string)[0]
    except (vParseError, ValueError):
        raise ValueError("Invalid iCalendar DURATION: %r" % (duration_string,))

_regex_duration = None

##
# Timezones
##

def tzexpand(tzdata, start, end):
    """
    Expand a timezone to get onset/utc-offset observance tuples withinthe specified
    time range.

    @param tzdata: the iCalendar data containing a VTIMEZONE.
    @type tzdata: C{str}
    @param start: date for the start of the expansion.
    @type start: C{date}
    @param end: date for the end of the expansion.
    @type end: C{date}
    
    @return: a C{list} of tuples of (C{datetime}, C{str})
    """
    
    start = datetime.datetime.fromordinal(start.toordinal())
    end = datetime.datetime.fromordinal(end.toordinal())
    icalobj = Component.fromString(tzdata)
    tzcomp = None
    for comp in icalobj.subcomponents():
        if comp.name() == "VTIMEZONE":
            tzcomp = comp
            break
    else:
        raise ValueError("No VTIMEZONE component in %s" % (tzdata,))

    tzinfo = tzcomp.gettzinfo()
    
    results = []
    
    # Get the start utc-offset - that is our first value
    results.append((dateTimeToString(start), deltaToOffset(tzinfo.utcoffset(start)),))
    last_dt = start
    
    while last_dt < end:
        # Get the transitions for the current year
        standard = getTransition("standard", last_dt.year, tzinfo)
        daylight = getTransition("daylight", last_dt.year, tzinfo)
        
        # Order the transitions
        if standard and daylight:
            if standard < daylight:
                first = standard
                second = daylight
            else:
                first = daylight
                second = standard
        elif standard:
            first = standard
            second = None
        else:
            first = daylight
            second = None
        
        for transition in (first, second):
            # Terminate if the next transition is outside the time range
            if transition and transition > end:
                break
            
            # If the next transition is after the last one, then add its info if
            # the utc-offset actually changed.
            if transition and transition > last_dt:
                utcoffset = deltaToOffset(tzinfo.utcoffset(transition + datetime.timedelta(days=1)))
                if utcoffset != results[-1][1]:
                    results.append((dateTimeToString(transition), utcoffset,))
                last_dt = transition
            
        # Bump last transition up to the start of the next year
        last_dt = datetime.datetime(last_dt.year + 1, 1, 1, 0, 0, 0)
        if last_dt >= end:
            break
    
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
