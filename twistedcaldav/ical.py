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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
iCalendar Utilities
"""

__all__ = [
    "Property",
    "Component",
    "FixedOffset",
    "parse_date",
    "parse_time",
    "parse_datetime",
    "parse_date_or_datetime",
    "parse_duration",
]

import datetime
import cStringIO as StringIO

from vobject import newFromBehavior, readComponents
from vobject.base import Component as vComponent
from vobject.base import ContentLine as vContentLine
from vobject.base import ParseError as vParseError
from vobject.icalendar import TimezoneComponent
from vobject.icalendar import stringToDate, stringToDateTime, stringToDurations
from vobject.icalendar import utc

from twisted.python import log
from twisted.web2.stream import IStream
from twisted.web2.dav.util import allDataFromStream

from twistedcaldav.dateops import normalizeToUTC, timeRangesOverlap
from twistedcaldav.instance import InstanceList

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

    def __hash__(self): return hash((self.name(), self.value()))

    def __ne__(self, other): return not self.__eq__(other)
    def __eq__(self, other):
        if not isinstance(other, Property): return False
        return self.name() == other.name() and self.value() == other.value()

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

    def params(self): return self._vobject.params

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
            return clazz(None, vobject=readComponents(stream).next())
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
        return hash(tuple(sorted(self.properties())))

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
            if subcomponent in my_subcomponents:
                my_subcomponents.remove(subcomponent)
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
        Set the behavior of the underlying iCal obtecy.
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
    
    def mainComponent(self):
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
            elif (result is not None):
                raise ValueError("Calendar contains more than one primary component: %r" % (self,))
            else:
                result = component
        
        return result
    
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
        if len(properties) == 1: return properties[0].value()
        if len(properties) > 1: raise ValueError("More than one %s property in component %r" % (name, self))
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
            if "RANGE" in ridprop.params():
                return (ridprop.params()["RANGE"][0] == "THISANDFUTURE")

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
        triggerProperty = self.getProperty("TRIGGER")
        if "RELATED" in triggerProperty.params():
            related = (triggerProperty.params()["RELATED"][0] == "START")
        else:
            related = True
        
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

    def timezoneIDs(self):
        """
        Returns the set of TZID parameter values appearing in any property in
        this component.
        @return: a set of strings, one for each unique TZID value.
        """
        result = set()
        for property in self.properties():
            if property.params().get('TZID'):
                result.update(property.params().get('TZID'))
            elif property.params().get('X-VOBJ-ORIGINAL-TZID'):
                result.add(property.params().get('X-VOBJ-ORIGINAL-TZID'))
            else:
                if type(property.value()) == list:
                    for item in property.value():
                        tzinfo = getattr(item, 'tzinfo', None)
                        tzid = TimezoneComponent.pickTzid(tzinfo)
                        if tzid: result.add(tzid)
                else:
                    tzinfo = getattr(property.value(), 'tzinfo', None)
                    tzid = TimezoneComponent.pickTzid(tzinfo)
                    if tzid: result.add(tzid)
        
        return result
    
    def expand(self, start, end):
        """
        Expand the components into a set of new components, one for each
        instance in the specified range. Date-times are converted to UTC. A
        new calendar object is returned.
        @param start: the L{datetime.datetime} for the start of the range.
        @param end: the L{datetime.datetime} for the end of the range.
        @return: the L{Component} for the new calendar with expanded instances.
        """
        
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
            if timeRangesOverlap(instance.start, instance.end, start, end):
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
        for property in newcomp.properties():
            if property.name() in ["RRULE", "RDATE", "EXRULE", "EXDATE", "RECURRENCE-ID"]:
                newcomp.removeProperty(property)
        
        # Convert all datetime properties to UTC
        for property in newcomp.properties():
            if isinstance(property.value(), datetime.datetime):
                property.setValue(property.value().astimezone(utc))
        
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

    def resourceUID(self):
        """
        @return: the UID of the subcomponents in this component.
        """
        assert self.name() == "VCALENDAR", "Not a calendar: %r" % (self,)

        if not hasattr(self, "_resource_uid"):
            has_timezone = False

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
                        raise ValueError("Calendar resources may not contain components with the same UIDs and no Recurrence-IDs" +
                                         "(%s and %s found)" % (component_id, subcomponent.propertyValue("UID")))
        
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

    def getAttendeeProperty(self, match):
        """
        Get the attendees matching a value. Works on either a VCALENDAR or on a component.
        
        @param match: a C{list} of calendar user address strings to try and match.
        @return: the string value of the Organizer property, or None
        """
        
        # FIXME: we should really have a URL class and have it manage comparisons
        # in a sensible fashion.
        def _normalizeCUAddress(addr):
            if addr.startswith("/") or addr.startswith("http:") or addr.startswith("https:"):
                return addr.rstrip("/")
            else:
                return addr

        # Need to normalize http/https cu addresses
        test = set()
        for item in match:
           test.add(_normalizeCUAddress(item))
        
        # Extract appropriate sub-component if this is a VCALENDAR
        if self.name() == "VCALENDAR":
            for component in self.subcomponents():
                if component.name() != "VTIMEZONE":
                    return component.getAttendeeProperty(match)
        else:
            # Find the primary subcomponent
            for p in self.properties("ATTENDEE"):
                if _normalizeCUAddress(p.value()) in test:
                    return p

        return None

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
# Utilities
##

#
# This function is from "Python Cookbook, 2d Ed., by Alex Martelli, Anna
# Martelli Ravenscroft, and Davis Ascher (O'Reilly Media, 2005) 0-596-00797-3."
#
import heapq
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
