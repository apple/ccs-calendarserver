##
# Copyright (c) 2011-2013 Apple Inc. All rights reserved.
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
Object model of CALDAV:filter element used in an addressbook-query.
"""

__all__ = [
    "Filter",
]

from twext.python.log import Logger

from twistedcaldav.caldavxml import caldav_namespace, CalDAVTimeZoneElement
from twistedcaldav.dateops import timeRangesOverlap
from twistedcaldav.ical import Component, Property

from pycalendar.datetime import DateTime
from pycalendar.timezone import Timezone

log = Logger()


class FilterBase(object):
    """
    Determines which matching components are returned.
    """

    def __init__(self, xml_element):
        self.xmlelement = xml_element


    def match(self, item, access=None):
        raise NotImplementedError


    def valid(self, level=0):
        raise NotImplementedError



class Filter(FilterBase):
    """
    Determines which matching components are returned.
    """

    def __init__(self, xml_element):

        super(Filter, self).__init__(xml_element)

        # One comp-filter element must be present
        if len(xml_element.children) != 1 or xml_element.children[0].qname() != (caldav_namespace, "comp-filter"):
            raise ValueError("Invalid CALDAV:filter element: %s" % (xml_element,))

        self.child = ComponentFilter(xml_element.children[0])


    def match(self, component, access=None):
        """
        Returns True if the given calendar component matches this filter, False
        otherwise.
        """

        # We only care about certain access restrictions.
        if access not in (Component.ACCESS_CONFIDENTIAL, Component.ACCESS_RESTRICTED):
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
                    instances = component.expandTimeRanges(DateTime(2100, 1, 1, 0, 0, 0, tzid=Timezone(utc=True)), ignoreInvalidInstances=True)
            else:
                instances = component.expandTimeRanges(maxend, ignoreInvalidInstances=True)
        else:
            instances = None
        self.child.setInstances(instances)

        # <filter> contains exactly one <comp-filter>
        return self.child.match(component, access)


    def valid(self):
        """
        Indicate whether this filter element's structure is valid wrt iCalendar
        data object model.

        @return: True if valid, False otherwise
        """

        # Must have one child element for VCALENDAR
        return self.child.valid(0)


    def settimezone(self, tzelement):
        """
        Set the default timezone to use with this query.
        @param calendar: a L{Component} for the VCALENDAR containing the one
            VTIMEZONE that we want
        @return: the L{Timezone} derived from the VTIMEZONE or utc.
        """

        if tzelement is None:
            tz = None
        elif isinstance(tzelement, CalDAVTimeZoneElement):
            tz = tzelement.gettimezone()
        elif isinstance(tzelement, Component):
            tz = tzelement.gettimezone()
        if tz is None:
            tz = Timezone(utc=True)
        self.child.settzinfo(tz)
        return tz


    def getmaxtimerange(self):
        """
        Get the date farthest into the future in any time-range elements
        """

        return self.child.getmaxtimerange(None, False)


    def getmintimerange(self):
        """
        Get the date farthest into the past in any time-range elements. That is either
        the start date, or if start is not present, the end date.
        """

        return self.child.getmintimerange(None, False)



class FilterChildBase(FilterBase):
    """
    CalDAV filter element.
    """

    def __init__(self, xml_element):

        super(FilterChildBase, self).__init__(xml_element)

        qualifier = None
        filters = []

        for child in xml_element.children:
            qname = child.qname()

            if qname in (
                (caldav_namespace, "is-not-defined"),
                (caldav_namespace, "time-range"),
                (caldav_namespace, "text-match"),
            ):
                if qualifier is not None:
                    raise ValueError("Only one of CalDAV:time-range, CalDAV:text-match allowed")

                if qname == (caldav_namespace, "is-not-defined"):
                    qualifier = IsNotDefined(child)
                elif qname == (caldav_namespace, "time-range"):
                    qualifier = TimeRange(child)
                elif qname == (caldav_namespace, "text-match"):
                    qualifier = TextMatch(child)

            elif qname == (caldav_namespace, "comp-filter"):
                filters.append(ComponentFilter(child))
            elif qname == (caldav_namespace, "prop-filter"):
                filters.append(PropertyFilter(child))
            elif qname == (caldav_namespace, "param-filter"):
                filters.append(ParameterFilter(child))
            else:
                raise ValueError("Unknown child element: %s" % (qname,))

        if qualifier and isinstance(qualifier, IsNotDefined) and (len(filters) != 0):
            raise ValueError("No other tests allowed when CalDAV:is-not-defined is present")

        self.qualifier = qualifier
        self.filters = filters
        self.filter_name = xml_element.attributes["name"]
        if isinstance(self.filter_name, unicode):
            self.filter_name = self.filter_name.encode("utf-8")
        self.defined = not self.qualifier or not isinstance(qualifier, IsNotDefined)

        filter_test = xml_element.attributes.get("test", "allof")
        if filter_test not in ("anyof", "allof"):
            raise ValueError("Test must be only one of anyof, allof")
        self.filter_test = filter_test


    def match(self, item, access=None):
        """
        Returns True if the given calendar item (either a component, property or parameter value)
        matches this filter, False otherwise.
        """

        # Always return True for the is-not-defined case as the result of this will
        # be negated by the caller
        if not self.defined:
            return True

        if self.qualifier and not self.qualifier.match(item, access):
            return False

        if len(self.filters) > 0:
            allof = self.filter_test == "allof"
            for filter in self.filters:
                if allof != filter._match(item, access):
                    return not allof
            return allof
        else:
            return True



class ComponentFilter (FilterChildBase):
    """
    Limits a search to only the chosen component types.
    """

    def match(self, item, access):
        """
        Returns True if the given calendar item (which is a component)
        matches this filter, False otherwise.
        This specialization uses the instance matching option of the time-range filter
        to minimize instance expansion.
        """

        # Always return True for the is-not-defined case as the result of this will
        # be negated by the caller
        if not self.defined:
            return True

        if self.qualifier and not self.qualifier.matchinstance(item, self.instances):
            return False

        if len(self.filters) > 0:
            allof = self.filter_test == "allof"
            for filter in self.filters:
                if allof != filter._match(item, access):
                    return not allof
            return allof
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
                if subcomponent.name() != self.filter_name:
                    continue
            else:
                if subcomponent.name() not in self.filter_name:
                    continue
            if self.match(subcomponent, access):
                break
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
                log.info("Top-level comp-filter must be VCALENDAR, instead: %s" % (self.filter_name,))
                return False
        elif level == 1:
            # Disallow VCALENDAR, VALARM, STANDARD, DAYLIGHT, AVAILABLE at the top, everything else is OK
            if self.filter_name in ("VCALENDAR", "VALARM", "STANDARD", "DAYLIGHT", "AVAILABLE"):
                log.info("comp-filter wrong component type: %s" % (self.filter_name,))
                return False

            # time-range only on VEVENT, VTODO, VJOURNAL, VFREEBUSY, VAVAILABILITY
            if timerange and self.filter_name not in ("VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY", "VAVAILABILITY"):
                log.info("time-range cannot be used with component %s" % (self.filter_name,))
                return False
        elif level == 2:
            # Disallow VCALENDAR, VTIMEZONE, VEVENT, VTODO, VJOURNAL, VFREEBUSY, VAVAILABILITY at the top, everything else is OK
            if (self.filter_name in ("VCALENDAR", "VTIMEZONE", "VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY", "VAVAILABILITY")):
                log.info("comp-filter wrong sub-component type: %s" % (self.filter_name,))
                return False

            # time-range only on VALARM, AVAILABLE
            if timerange and self.filter_name not in ("VALARM", "AVAILABLE",):
                log.info("time-range cannot be used with sub-component %s" % (self.filter_name,))
                return False
        else:
            # Disallow all standard iCal components anywhere else
            if (self.filter_name in ("VCALENDAR", "VTIMEZONE", "VEVENT", "VTODO", "VJOURNAL", "VFREEBUSY", "VALARM", "STANDARD", "DAYLIGHT", "AVAILABLE")) or timerange:
                log.info("comp-filter wrong standard component type: %s" % (self.filter_name,))
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
        @param tzinfo: a L{Timezone} to use.
        """

        # Give tzinfo to any TimeRange we have
        if isinstance(self.qualifier, TimeRange):
            self.qualifier.settzinfo(tzinfo)

        # Pass down to sub components/properties
        for x in self.filters:
            x.settzinfo(tzinfo)


    def getmaxtimerange(self, currentMaximum, currentIsStartTime):
        """
        Get the date farthest into the future in any time-range elements

        @param currentMaximum: current future value to compare with
        @type currentMaximum: L{DateTime}
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


    def getmintimerange(self, currentMinimum, currentIsEndTime):
        """
        Get the date farthest into the past in any time-range elements. That is either
        the start date, or if start is not present, the end date.
        """

        # Give tzinfo to any TimeRange we have
        isEndTime = False
        if isinstance(self.qualifier, TimeRange):
            isEndTime = self.qualifier.start is None
            compareWith = self.qualifier.end if isEndTime else self.qualifier.start
            if currentMinimum is None or currentMinimum > compareWith:
                currentMinimum = compareWith
                currentIsEndTime = isEndTime

        # Pass down to sub components/properties
        for x in self.filters:
            currentMinimum, currentIsEndTime = x.getmintimerange(currentMinimum, currentIsEndTime)

        return currentMinimum, currentIsEndTime



class PropertyFilter (FilterChildBase):
    """
    Limits a search to specific properties.
    """

    def _match(self, component, access):
        # When access restriction is in force, we need to only allow matches against the properties
        # allowed by the access restriction level.
        if access:
            allowedProperties = Component.confidentialPropertiesMap.get(component.name(), None)
            if allowedProperties and access == Component.ACCESS_RESTRICTED:
                allowedProperties += Component.extraRestrictedProperties
        else:
            allowedProperties = None

        # At least one property must match (or is-not-defined is set)
        for property in component.properties():
            # Apply access restrictions, if any.
            if allowedProperties is not None and property.name().upper() not in allowedProperties:
                continue
            if property.name().upper() == self.filter_name.upper() and self.match(property, access):
                break
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
        if timerange and self.filter_name.upper() not in ("COMPLETED", "CREATED", "DTSTAMP", "LAST-MODIFIED"):
            log.info("time-range cannot be used with property %s" % (self.filter_name,))
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
        @param tzinfo: a L{Timezone} to use.
        """

        # Give tzinfo to any TimeRange we have
        if isinstance(self.qualifier, TimeRange):
            self.qualifier.settzinfo(tzinfo)


    def getmaxtimerange(self, currentMaximum, currentIsStartTime):
        """
        Get the date farthest into the future in any time-range elements

        @param currentMaximum: current future value to compare with
        @type currentMaximum: L{DateTime}
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


    def getmintimerange(self, currentMinimum, currentIsEndTime):
        """
        Get the date farthest into the past in any time-range elements. That is either
        the start date, or if start is not present, the end date.
        """

        # Give tzinfo to any TimeRange we have
        isEndTime = False
        if isinstance(self.qualifier, TimeRange):
            isEndTime = self.qualifier.start is None
            compareWith = self.qualifier.end if isEndTime else self.qualifier.start
            if currentMinimum is None or currentMinimum > compareWith:
                currentMinimum = compareWith
                currentIsEndTime = isEndTime

        return currentMinimum, currentIsEndTime



class ParameterFilter (FilterChildBase):
    """
    Limits a search to specific parameters.
    """

    def _match(self, property, access):

        # At least one parameter must match (or is-not-defined is set)
        result = not self.defined
        for parameterName in property.parameterNames():
            if parameterName.upper() == self.filter_name.upper() and self.match([property.parameterValue(parameterName)], access):
                result = self.defined
                break

        return result



class IsNotDefined (FilterBase):
    """
    Specifies that the named iCalendar item does not exist.
    """

    def match(self, component, access=None):
        # Oddly, this needs always to return True so that it appears there is
        # a match - but we then "negate" the result if is-not-defined is set.
        # Actually this method should never be called as we special case the
        # is-not-defined option.
        return True



class TextMatch (FilterBase):
    """
    Specifies a substring match on a property or parameter value.
    (CalDAV-access-09, section 9.6.4)
    """
    def __init__(self, xml_element):

        super(TextMatch, self).__init__(xml_element)

        self.text = str(xml_element)
        if "caseless" in xml_element.attributes:
            caseless = xml_element.attributes["caseless"]
            if caseless == "yes":
                self.caseless = True
            elif caseless == "no":
                self.caseless = False
        else:
            self.caseless = True

        if "negate-condition" in xml_element.attributes:
            negate = xml_element.attributes["negate-condition"]
            if negate == "yes":
                self.negate = True
            elif negate == "no":
                self.negate = False
        else:
            self.negate = False

        if "match-type" in xml_element.attributes:
            self.match_type = xml_element.attributes["match-type"]
            if self.match_type not in (
                "equals",
                "contains",
                "starts-with",
                "ends-with",
            ):
                self.match_type = "contains"
        else:
            self.match_type = "contains"


    def match(self, item, access):
        """
        Match the text for the item.
        If the item is a property, then match the property value,
        otherwise it may be a list of parameter values - try to match anyone of those
        """
        if item is None:
            return False

        if isinstance(item, Property):
            values = [item.strvalue()]
        else:
            values = item

        test = unicode(self.text, "utf-8")
        if self.caseless:
            test = test.lower()

        def _textCompare(s):
            if self.caseless:
                s = s.lower()

            if self.match_type == "equals":
                return s == test
            elif self.match_type == "contains":
                return s.find(test) != -1
            elif self.match_type == "starts-with":
                return s.startswith(test)
            elif self.match_type == "ends-with":
                return s.endswith(test)
            else:
                return False

        for value in values:
            # NB Its possible that we have a text list value which appears as a Python list,
            # so we need to check for that and iterate over the list.
            if isinstance(value, list):
                for subvalue in value:
                    if _textCompare(unicode(subvalue, "utf-8")):
                        return not self.negate
            else:
                if _textCompare(unicode(value, "utf-8")):
                    return not self.negate

        return self.negate



class TimeRange (FilterBase):
    """
    Specifies a time for testing components against.
    """

    def __init__(self, xml_element):

        super(TimeRange, self).__init__(xml_element)

        # One of start or end must be present
        if "start" not in xml_element.attributes and "end" not in xml_element.attributes:
            raise ValueError("One of 'start' or 'end' must be present in CALDAV:time-range")

        self.start = DateTime.parseText(xml_element.attributes["start"]) if "start" in xml_element.attributes else None
        self.end = DateTime.parseText(xml_element.attributes["end"]) if "end" in xml_element.attributes else None
        self.tzinfo = None


    def settzinfo(self, tzinfo):
        """
        Set the default timezone to use with this query.
        @param tzinfo: a L{Timezone} to use.
        """

        # Give tzinfo to any TimeRange we have
        self.tzinfo = tzinfo


    def valid(self, level=0):
        """
        Indicate whether the time-range is valid (must be date-time in UTC).

        @return:      True if valid, False otherwise
        """

        if self.start is not None and self.start.isDateOnly():
            log.info("start attribute in <time-range> is not a date-time: %s" % (self.start,))
            return False
        if self.end is not None and self.end.isDateOnly():
            log.info("end attribute in <time-range> is not a date-time: %s" % (self.end,))
            return False
        if self.start is not None and not self.start.utc():
            log.info("start attribute in <time-range> is not UTC: %s" % (self.start,))
            return False
        if self.end is not None and not self.end.utc():
            log.info("end attribute in <time-range> is not UTC: %s" % (self.end,))
            return False

        # No other tests
        return True


    def match(self, property, access=None):
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
