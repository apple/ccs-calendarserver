##
# Copyright (c) 2006-2009 Apple Inc. All rights reserved.
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

import datetime

from twistedcaldav.dateops import normalizeForIndex, compareDateTime, differenceDateTime, periodEnd

from vobject.icalendar import utc

# The maximum number of instances we will expand out to.
# Raise a TooManyInstancesError exception if we exceed this.
max_allowed_instances = 1000

class TooManyInstancesError(Exception):
    def __init__(self):
        Exception.__init__(self)
        self.max_allowed = max_allowed_instances

    def __repr__(self):
        return "<%s max:%s>" % (self.__class__.__name__, self.max_allowed)

class InvalidOverriddenInstanceError(Exception):
    def __init__(self, rid):
        Exception.__init__(self)
        self.rid = rid

    def __repr__(self):
        return "<%s invalid:%s>" % (self.__class__.__name__, self.rid)

class Instance(object):
    
    __slots__ = ["component", "start", "end", "rid", "overridden", "future"]
    
    def __init__(self, component, start = None, end = None, rid = None, overridden = False, future = False):
        self.component = component
        if start is None:
            self.start = component.getStartDateUTC()
        else:
            self.start = start
        if end is None:
            self.end = component.getEndDateUTC()
        else:
            self.end = end
        if rid is None:
            self.rid = self.start
        else:
            self.rid = rid
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
            if isinstance(trigger, datetime.date):
                # Absolute trigger
                start = trigger
            else:
                # Relative trigger
                if related:
                    start = self.start + trigger
                else:
                    start = self.end + trigger
            triggers.add(start)
            
            # Handle repeats
            if repeat > 0:
                for i in xrange(1, repeat+1):
                    triggers.add(start + (duration * i))
        
        return triggers
    
class InstanceList(object):
    
    __slots__ = ["instances", "limit", "ignoreInvalidInstances",]
    
    def __init__(self, ignoreInvalidInstances=False):
        self.instances = {}
        self.limit = None
        self.ignoreInvalidInstances = ignoreInvalidInstances
        
    def __iter__(self):
        # Return keys in sorted order via iterator
        for i in sorted(self.instances.keys()):
            yield i

    def __getitem__(self, key):
        return self.instances[key]

    def expandTimeRanges(self, componentSet, limit):
        """
        Expand the set of recurrence instances up to the specified date limit.
        What we do is first expand the master instance into the set of generate
        instances. Then we merge the overridden instances, taking into account
        THISANDFUTURE and THISANDPRIOR.
        @param componentSet: the set of components that are to make up the
                recurrence set. These MUST all be components with the same UID
                and type, forming a proper recurring set.
        @param limit: datetime.date value representing the end of the expansion.
        """
        
        # Look at each component type
        got_master = False
        overrides = []
        for component in componentSet:
            if component.name() == "VEVENT":
                if component.hasProperty("RECURRENCE-ID"):
                    overrides.append(component)
                else:
                    self._addMasterEventComponent(component, limit)
                    got_master = True
            elif component.name() == "VTODO":
                if component.hasProperty("RECURRENCE-ID"):
                    overrides.append(component)
                else:
                    self._addMasterToDoComponent(component, limit)
                    got_master = True
            elif component.name() == "VJOURNAL":
                #TODO: VJOURNAL
                raise NotImplementedError("VJOURNAL recurrence expansion not supported yet")
            elif component.name() == "VFREEBUSY":
                self._addFreeBusyComponent(component, limit)
            elif component.name() == "VAVAILABILITY":
                self._addAvailabilityComponent(component, limit)
            elif component.name() == "AVAILABLE":
                if component.hasProperty("RECURRENCE-ID"):
                    overrides.append(component)
                else:
                    # AVAILABLE components are just like VEVENT components
                    self._addMasterEventComponent(component, limit)
                    got_master = True
            
        for component in overrides:
            if component.name() == "VEVENT":
                self._addOverrideEventComponent(component, limit, got_master)
            elif component.name() == "VTODO":
                self._addOverrideToDoComponent(component, limit, got_master)
            elif component.name() == "VJOURNAL":
                #TODO: VJOURNAL
                raise NotImplementedError("VJOURNAL recurrence expansion not supported yet")
            elif component.name() == "AVAILABLE":
                # AVAILABLE components are just like VEVENT components
                self._addOverrideEventComponent(component, limit, got_master)

    def addInstance(self, instance):
        """
        Add the supplied instance to the map.
        @param instance: the instance to add
        """

        self.instances[str(instance.rid)] = instance
        
        # Check for too many instances
        if len(self.instances) > max_allowed_instances:
            raise TooManyInstancesError()

    def _addMasterEventComponent(self, component, limit):
        """
        Add the specified master VEVENT Component to the instance list, expanding it
        within the supplied time range.
        @param component: the Component to expand
        @param limit: the end datetime.datetime for expansion
        """
        start = component.getStartDateUTC()
        if start is None:
            return

        end = component.getEndDateUTC()
        duration = None
        if end is None:
            if isinstance(start, datetime.datetime):
                # Timed event with zero duration
                duration = datetime.timedelta(days=0)
            else:
                # All day event default duration is one day
                duration = datetime.timedelta(days=1)
            end = start + duration
        else:
            duration = differenceDateTime(start, end)

        self._addMasterComponent(component, limit, start, end, duration)

    def _addOverrideEventComponent(self, component, limit, got_master):
        """
        Add the specified overridden VEVENT Component to the instance list, replacing 
        the one generated by the master component.
        @param component: the overridden Component.
        @param got_master: whether a master component has already been expanded.
        """
        
        #TODO: This does not take into account THISANDPRIOR - only THISANDFUTURE
        
        start = component.getStartDateUTC()
        if start is None:
            return

        end = component.getEndDateUTC()
        duration = None
        if end is None:
            if isinstance(start, datetime.datetime):
                # Timed event with zero duration
                duration = datetime.timedelta(days=0)
            else:
                # All day event default duration is one day
                duration = datetime.timedelta(days=1)
            end = start + duration
        else:
            duration = differenceDateTime(start, end)

        self._addOverrideComponent(component, limit, start, end, got_master)

    def _addMasterToDoComponent(self, component, limit):
        """
        Add the specified master VTODO Component to the instance list, expanding it
        within the supplied time range.
        @param component: the Component to expand
        @param limit: the end datetime.datetime for expansion
        """
        start = component.getStartDateUTC()
        due = component.getDueDateUTC()

        if start is None and due is None:
            return

        if start is None:
            start = due
        elif due is None:
            due = start
        duration = differenceDateTime(start, due)

        self._addMasterComponent(component, limit, start, due, duration)

    def _addOverrideToDoComponent(self, component, limit, got_master):
        """
        Add the specified overridden VTODO Component to the instance list, replacing 
        the one generated by the master component.
        @param component: the overridden Component.
        @param got_master: whether a master component has already been expanded.
        """
        
        #TODO: This does not take into account THISANDPRIOR - only THISANDFUTURE
        
        start = component.getStartDateUTC()
        due = component.getDueDateUTC()

        if start is None and due is None:
            return

        if start is None:
            start = due
        elif due is None:
            due = start

        self._addOverrideComponent(component, limit, start, due, got_master)

    def _addMasterComponent(self, component, limit, start, end, duration):
        # Always add first instance if included in range.
        if compareDateTime(start, limit) < 0:
            # dateutils does not do all-day - so convert to datetime.datetime
            start = normalizeForIndex(start)
            end = normalizeForIndex(end)
            
            # Do not add if in EXDATEs
            exdates = []
            for prop in component.properties("EXDATE"):
                exdates.extend(prop.value())
            exdates = [normalizeForIndex(exdate) for exdate in exdates]
            if start not in exdates:
                self.addInstance(Instance(component, start, end))
        else:
            self.limit = limit
        
        # Now expand recurrence
        # FIXME: Current Python implementation fails when RDATEs are PERIODs
        recur = component.getRRuleSet(True)
        if recur is not None:
            for startDate in recur:
                if compareDateTime(startDate, limit) >= 0:
                    self.limit = limit
                    break
                endDate = startDate + duration
                startDate = normalizeForIndex(startDate)
                endDate = normalizeForIndex(endDate)
                self.addInstance(Instance(component, startDate, endDate))
    
    def _addOverrideComponent(self, component, limit, start, end, got_master):

        # Get the recurrence override info
        rid = component.getRecurrenceIDUTC()
        range = component.getRange()
        
        # Now add this instance, effectively overriding the one with the matching R-ID
        start = normalizeForIndex(start)
        end = normalizeForIndex(end)
        rid = normalizeForIndex(rid)

        # Make sure start is within the limit
        if compareDateTime(start, limit) > 0 and compareDateTime(rid, limit) > 0:
            return

        # Make sure override RECURRENCE-ID is a valid instance of the master
        if got_master:
            if str(rid) not in self.instances:
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
                
                # Determine the start/end of the new instance\
                originalStart = oldinstance.rid
                start = oldinstance.start
                end = oldinstance.end
                
                if timeShift:
                    start += offsetTime
                    end = start + newDuration
                
                # Now replacing existing entry with the new one
                self.addInstance(Instance(component, start, end, originalStart, False, False))

    def _addFreeBusyComponent(self, component, limit):
        """
        Add the specified master VFREEBUSY Component to the instance list, expanding it
        within the supplied time range.
        @param component: the Component to expand
        @param limit: the end datetime.datetime for expansion
        """

        start = component.getStartDateUTC()
        if start is not None and (compareDateTime(start, limit) >= 0):
            # If the free busy is beyond the end of the range we want, ignore it
            return

        end = component.getEndDateUTC()
        if end is None and start is not None:
            raise ValueError("VFREEBUSY component must have both DTSTART and DTEND: %r" % (component, ))

        # Now look at each FREEBUSY property
        for fb in component.properties("FREEBUSY"):
            # Look at each period in the property
            assert isinstance(fb.value(), list), "FREEBUSY property does not contain a list of values: %r" % (fb,)
            for period in fb.value():
                # Ignore if period starts after limit
                if compareDateTime(period[0], limit) >= 0:
                    continue
                start = normalizeForIndex(period[0])
                end = normalizeForIndex(periodEnd(period))
                self.addInstance(Instance(component, start, end))

    def _addAvailabilityComponent(self, component, limit):
        """
        Add the specified master VAVAILABILITY Component to the instance list, expanding it
        within the supplied time range. VAVAILABILITY components are not recurring, they have an
        optional DTSTART and DTEND/DURATION defining a single time-range which may be bounded
        depending on the presence of the properties. If unbounded at one or both ends, we will
        set the time to 1/1/1900 in the past and 1/1/3000 in the future.
        @param component: the Component to expand
        @param limit: the end datetime.datetime for expansion
        """

        start = component.getStartDateUTC()
        if start is not None and (compareDateTime(start, limit) >= 0):
            # If the free busy is beyond the end of the range we want, ignore it
            return
        if start is None:
            start = datetime.datetime(1900, 1, 1, 0, 0, 0, tzinfo=utc)
        start = normalizeForIndex(start)

        end = component.getEndDateUTC()
        if end is None:
            end = datetime.datetime(3000, 1, 1, 0, 0, 0, tzinfo=utc)
        end = normalizeForIndex(end)

        self.addInstance(Instance(component, start, end))
