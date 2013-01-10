##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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
iCalendar Recurrence Expansion Utilities
"""

from twistedcaldav.config import config
from twistedcaldav.dateops import normalizeForIndex, differenceDateTime

from pycalendar.datetime import PyCalendarDateTime
from pycalendar.duration import PyCalendarDuration
from pycalendar.period import PyCalendarPeriod
from pycalendar.timezone import PyCalendarTimezone

class TooManyInstancesError(Exception):
    def __init__(self):
        Exception.__init__(self)
        self.max_allowed = config.MaxAllowedInstances

    def __repr__(self):
        return "<%s max:%s>" % (self.__class__.__name__, self.max_allowed)

class InvalidOverriddenInstanceError(Exception):
    def __init__(self, rid):
        Exception.__init__(self)
        self.rid = rid

    def __repr__(self):
        return "<%s invalid:%s>" % (self.__class__.__name__, self.rid)

class Instance(object):
    
    def __init__(self, component, start = None, end = None, rid = None, overridden = False, future = False):
        self.component = component
        self.start = component.getStartDateUTC() if start is None else start
        self.end = component.getEndDateUTC() if end is None else end
        self.rid = self.start if rid is None else rid
        self.overridden = overridden
        self.future = future
        
    def getAlarmTriggers(self):
        """
        Get the set of alarm triggers for this instance.
        @return: a set containing the UTC datetime's of each trigger in each alarm
        """
        triggers = set()
        
        for alarm in [x for x in self.component.subcomponents() if x.name() == "VALARM"]:
            (trigger, related, repeat, duration)  = alarm.getTriggerDetails()
            
            # Handle relative vs absolute triggers
            if isinstance(trigger, PyCalendarDateTime):
                # Absolute trigger
                start = trigger
            else:
                # Relative trigger
                start = (self.start if related else self.end) + trigger
            triggers.add(start)
            
            # Handle repeats
            if repeat > 0:
                tstart = start.duplicate()
                for _ignore in xrange(1, repeat+1):
                    tstart += duration
                    triggers.add(tstart)
        
        return triggers
    
    def isMasterInstance(self):
        return not self.overridden and self.start == self.component.getStartDateUTC()

class InstanceList(object):
    
    def __init__(self, ignoreInvalidInstances=False, normalizeFunction=normalizeForIndex):
        self.instances = {}
        self.limit = None
        self.lowerLimit = None
        self.ignoreInvalidInstances = ignoreInvalidInstances
        self.normalizeFunction = normalizeFunction
        
    def __iter__(self):
        # Return keys in sorted order via iterator
        for i in sorted(self.instances.keys()):
            yield i

    def __getitem__(self, key):
        return self.instances[key]

    def expandTimeRanges(self, componentSet, limit, lowerLimit=None):
        """
        Expand the set of recurrence instances up to the specified date limit.
        What we do is first expand the master instance into the set of generate
        instances. Then we merge the overridden instances, taking into account
        THISANDFUTURE and THISANDPRIOR.
        @param componentSet: the set of components that are to make up the
                recurrence set. These MUST all be components with the same UID
                and type, forming a proper recurring set.
        @param limit: L{PyCalendarDateTime} value representing the end of the expansion.
        """
        
        # Look at each component type
        got_master = False
        overrides = []
        for component in componentSet:
            if component.name() == "VEVENT":
                if component.hasProperty("RECURRENCE-ID"):
                    overrides.append(component)
                else:
                    self._addMasterEventComponent(component, lowerLimit, limit)
                    got_master = True
            elif component.name() == "VTODO":
                if component.hasProperty("RECURRENCE-ID"):
                    overrides.append(component)
                else:
                    self._addMasterToDoComponent(component, lowerLimit, limit)
                    got_master = True
            elif component.name() == "VJOURNAL":
                #TODO: VJOURNAL
                raise NotImplementedError("VJOURNAL recurrence expansion not supported yet")
            elif component.name() == "VFREEBUSY":
                self._addFreeBusyComponent(component, lowerLimit, limit)
            elif component.name() == "VAVAILABILITY":
                self._addAvailabilityComponent(component, lowerLimit, limit)
            elif component.name() == "AVAILABLE":
                if component.hasProperty("RECURRENCE-ID"):
                    overrides.append(component)
                else:
                    # AVAILABLE components are just like VEVENT components
                    self._addMasterEventComponent(component, lowerLimit, limit)
                    got_master = True
            
        for component in overrides:
            if component.name() == "VEVENT":
                self._addOverrideEventComponent(component, lowerLimit, limit, got_master)
            elif component.name() == "VTODO":
                self._addOverrideToDoComponent(component, lowerLimit, limit, got_master)
            elif component.name() == "VJOURNAL":
                #TODO: VJOURNAL
                raise NotImplementedError("VJOURNAL recurrence expansion not supported yet")
            elif component.name() == "AVAILABLE":
                # AVAILABLE components are just like VEVENT components
                self._addOverrideEventComponent(component, lowerLimit, limit, got_master)

    def addInstance(self, instance):
        """
        Add the supplied instance to the map.
        @param instance: the instance to add
        """

        self.instances[str(instance.rid)] = instance
        
        # Check for too many instances
        if config.MaxAllowedInstances and len(self.instances) > config.MaxAllowedInstances:
            raise TooManyInstancesError()

    def _getMasterEventDetails(self, component):
        """
        Logic here comes from RFC4791 Section 9.9
        """

        start = component.getStartDateUTC()
        if start is None:
            return None
        rulestart = component.propertyValue("DTSTART")

        end = component.getEndDateUTC()
        duration = None
        if end is None:
            if not start.isDateOnly():
                # Timed event with zero duration
                duration = PyCalendarDuration(days=0)
            else:
                # All day event default duration is one day
                duration = PyCalendarDuration(days=1)
            end = start + duration
        else:
            duration = differenceDateTime(start, end)
        
        return (rulestart, start, end, duration,)

    def _addMasterEventComponent(self, component, lowerLimit, upperlimit):
        """
        Add the specified master VEVENT Component to the instance list, expanding it
        within the supplied time range.
        @param component: the Component to expand
        @param limit: the end L{PyCalendarDateTime} for expansion
        """
        
        details = self._getMasterEventDetails(component)
        if details is None:
            return
        rulestart, start, end, duration = details

        self._addMasterComponent(component, lowerLimit, upperlimit, rulestart, start, end, duration)

    def _addOverrideEventComponent(self, component, lowerLimit, upperlimit, got_master):
        """
        Add the specified overridden VEVENT Component to the instance list, replacing 
        the one generated by the master component.
        @param component: the overridden Component.
        @param got_master: whether a master component has already been expanded.
        """
        
        #TODO: This does not take into account THISANDPRIOR - only THISANDFUTURE
        
        details = self._getMasterEventDetails(component)
        if details is None:
            return
        _ignore_rulestart, start, end, _ignore_duration = details

        self._addOverrideComponent(component, lowerLimit, upperlimit, start, end, got_master)

    def _getMasterToDoDetails(self, component):
        """
        Logic here comes from RFC4791 Section 9.9
        """

        dtstart = component.getStartDateUTC()
        dtend = component.getEndDateUTC()
        dtdue = component.getDueDateUTC()

        # DTSTART and DURATION or DUE case
        if dtstart is not None:
            rulestart = component.propertyValue("DTSTART")
            start = dtstart
            if dtend is not None:
                end = dtend
            elif dtdue is not None:
                end = dtdue
            else:
                end = dtstart
        
        # DUE case
        elif dtdue is not None:
            rulestart = component.propertyValue("DUE")
            start = end = dtdue
        
        # Fall back to COMPLETED or CREATED - cannot be recurring
        else:
            rulestart = None
            from twistedcaldav.ical import maxDateTime, minDateTime
            dtcreated = component.getCreatedDateUTC()
            dtcompleted = component.getCompletedDateUTC()
            if dtcompleted:
                end = dtcompleted
                start = dtcreated if dtcreated else end
            elif dtcreated:
                start = dtcreated
                end = maxDateTime
            else:
                start = minDateTime
                end = maxDateTime

        duration = differenceDateTime(start, end)

        return (rulestart, start, end, duration,)

    def _addMasterToDoComponent(self, component, lowerLimit, upperlimit):
        """
        Add the specified master VTODO Component to the instance list, expanding it
        within the supplied time range.
        @param component: the Component to expand
        @param limit: the end L{PyCalendarDateTime} for expansion
        """
        details = self._getMasterToDoDetails(component)
        if details is None:
            return
        rulestart, start, end, duration = details

        self._addMasterComponent(component, lowerLimit, upperlimit, rulestart, start, end, duration)

    def _addOverrideToDoComponent(self, component, lowerLimit, upperlimit, got_master):
        """
        Add the specified overridden VTODO Component to the instance list, replacing 
        the one generated by the master component.
        @param component: the overridden Component.
        @param got_master: whether a master component has already been expanded.
        """
        
        #TODO: This does not take into account THISANDPRIOR - only THISANDFUTURE
        
        details = self._getMasterToDoDetails(component)
        if details is None:
            return
        _ignore_rulestart, start, end, _ignore_duration = details

        self._addOverrideComponent(component, lowerLimit, upperlimit, start, end, got_master)

    def _addMasterComponent(self, component, lowerLimit, upperlimit, rulestart, start, end, duration):
        
        rrules = component.getRecurrenceSet()
        if rrules is not None and rulestart is not None:
            # Do recurrence set expansion
            expanded = []
            # Begin expansion far in the past because there may be RDATEs earlier
            # than the master DTSTART, and if we exclude those, the associated
            # overridden instances will cause an InvalidOverriddenInstance.
            limited = rrules.expand(rulestart,
                PyCalendarPeriod(PyCalendarDateTime(1900,1,1), upperlimit), expanded)
            for startDate in expanded:
                startDate = self.normalizeFunction(startDate)
                endDate = startDate + duration
                if lowerLimit is None or endDate >= lowerLimit:
                    self.addInstance(Instance(component, startDate, endDate))
                else:
                    self.lowerLimit = lowerLimit
            if limited:
                self.limit = upperlimit
        else:
            # Always add main instance if included in range.
            if start < upperlimit:
                if lowerLimit is None or end >= lowerLimit:
                    start = self.normalizeFunction(start)
                    end = self.normalizeFunction(end)
                    self.addInstance(Instance(component, start, end))
                else:
                    self.lowerLimit = lowerLimit
            else:
                self.limit = upperlimit
    
    def _addOverrideComponent(self, component, lowerLimit, upperlimit, start, end, got_master):

        # Get the recurrence override info
        rid = component.getRecurrenceIDUTC()
        range = component.getRange()
        
        # Now add this instance, effectively overriding the one with the matching R-ID
        start = self.normalizeFunction(start)
        end = self.normalizeFunction(end)
        rid = self.normalizeFunction(rid)

        # Make sure start is within the limit
        if start > upperlimit and rid > upperlimit:
            return
        if lowerLimit is not None and end < lowerLimit and rid < lowerLimit:
            return

        # Make sure override RECURRENCE-ID is a valid instance of the master
        if got_master:
            if str(rid) not in self.instances and rid < upperlimit and (lowerLimit is None or rid >= lowerLimit):
                if self.ignoreInvalidInstances:
                    return
                else:
                    raise InvalidOverriddenInstanceError(str(rid))
        
        self.addInstance(Instance(component, start, end, rid, True, range))
        
        # Handle THISANDFUTURE if present
        if range:
            # Iterate over all the instances after this one, replacing those
            # with a version based on this override component
            
            # We need to account for a time shift in the overridden component by
            # applying that shift to the future instances as well
            timeShift = (start != rid)
            if timeShift:
                offsetTime = start - rid
                newDuration = end - start
        
            # First get sorted instance keys greater than the current components R-ID
            for key in sorted(x for x in self.instances.keys() if x > str(rid)):
                oldinstance = self.instances[key]
                
                # Do not override instance that is already overridden
                if oldinstance.overridden:
                    continue
                
                # Determine the start/end of the new instance
                originalStart = oldinstance.rid
                start = oldinstance.start
                end = oldinstance.end
                
                if timeShift:
                    start += offsetTime
                    end = start + newDuration
                
                # Now replacing existing entry with the new one
                self.addInstance(Instance(component, start, end, originalStart, False, False))

    def _addFreeBusyComponent(self, component, lowerLimit, upperlimit):
        """
        Add the specified master VFREEBUSY Component to the instance list, expanding it
        within the supplied time range.
        @param component: the Component to expand
        @param limit: the end L{PyCalendarDateTime} for expansion
        """

        start = component.getStartDateUTC()
        end = component.getEndDateUTC()
        if end is None and start is not None:
            raise ValueError("VFREEBUSY component must have both DTSTART and DTEND: %r" % (component, ))

        # If the free busy is beyond the end of the range we want, ignore it
        if start is not None and start >= upperlimit:
            return

        # If the free busy is before the start of the range we want, ignore it
        if lowerLimit is not None and end is not None and end < lowerLimit:
            return            

        # Now look at each FREEBUSY property
        for fb in component.properties("FREEBUSY"):
            # Look at each period in the property
            assert isinstance(fb.value(), list), "FREEBUSY property does not contain a list of values: %r" % (fb,)
            for period in fb.value():
                # Ignore if period starts after limit
                period = period.getValue()
                if period.getStart() >= upperlimit:
                    continue
                start = self.normalizeFunction(period.getStart())
                end = self.normalizeFunction(period.getEnd())
                self.addInstance(Instance(component, start, end))

    def _addAvailabilityComponent(self, component, lowerLimit, upperlimit):
        """
        Add the specified master VAVAILABILITY Component to the instance list, expanding it
        within the supplied time range. VAVAILABILITY components are not recurring, they have an
        optional DTSTART and DTEND/DURATION defining a single time-range which may be bounded
        depending on the presence of the properties. If unbounded at one or both ends, we will
        set the time to 1/1/1900 in the past and 1/1/3000 in the future.
        @param component: the Component to expand
        @param limit: the end L{PyCalendarDateTime} for expansion
        """

        start = component.getStartDateUTC()
        if start is not None and start >= upperlimit:
            # If the availability is beyond the end of the range we want, ignore it
            return
        if start is None:
            start = PyCalendarDateTime(1900, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
        start = self.normalizeFunction(start)

        end = component.getEndDateUTC()
        if lowerLimit is not None and end is not None and end < lowerLimit:
            # If the availability is before the start of the range we want, ignore it
            return            
        if end is None:
            end = PyCalendarDateTime(2100, 1, 1, 0, 0, 0, tzid=PyCalendarTimezone(utc=True))
        end = self.normalizeFunction(end)

        self.addInstance(Instance(component, start, end))
