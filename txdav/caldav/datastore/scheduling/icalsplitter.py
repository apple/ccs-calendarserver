##
# Copyright (c) 2013-2014 Apple Inc. All rights reserved.
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

from pycalendar.datetime import DateTime

from twistedcaldav.ical import Property


class iCalSplitter(object):
    """
    Class that manages the "splitting" of large iCalendar objects into two pieces so that we can keep the overall
    size of individual calendar objects to a reasonable limit. This should only be used on Organizer events.
    """

    def __init__(self, threshold, past):
        """
        @param threshold: the size in bytes that will trigger a split
        @type threshold: C{int}
        @param past: number of days in the past where the split will occur
        @type past: C{int}

        """
        self.threshold = threshold
        self.past = DateTime.getNowUTC()
        self.past.setHHMMSS(0, 0, 0)
        self.past.offsetDay(-past)
        self.now = DateTime.getNowUTC()
        self.now.setHHMMSS(0, 0, 0)
        self.now.offsetDay(-1)


    def willSplit(self, ical):
        """
        Determine if the specified iCalendar object needs to be split. Our policy is
        we can only split recurring events with past instances and future instances.

        @param ical: the iCalendar object to examine
        @type ical: L{Component}

        @return: C{True} if a split is require, C{False} otherwise
        @rtype: C{bool}
        """

        # Must be recurring
        if not ical.isRecurring():
            return False

        # Look for past/future (cacheExpandedTimeRanges will go one year in the future by default)
        now = self.now.duplicate()
        now.offsetDay(1)
        instances = ical.cacheExpandedTimeRanges(now)
        instances = sorted(instances.instances.values(), key=lambda x: x.start)
        if instances[0].start >= self.past or instances[-1].start < self.now or len(instances) <= 1:
            return False

        # Make sure there are some overridden components in the past - as splitting only makes sense when
        # overrides are present
        past_count = 0
        for instance in instances:
            if instance.start >= self.past:
                break
            elif instance.component.hasProperty("RECURRENCE-ID"):
                past_count += 1

        # Only split when there is more than one past override to split off
        if past_count < 2:
            return False

        # Now see if overall size exceeds our threshold
        return len(str(ical)) > self.threshold


    def whereSplit(self, ical):
        """
        Determine where a split is going to happen - i.e., the RECURRENCE-ID.

        @param ical: the iCalendar object to test
        @type ical: L{Component}

        @return: recurrence-id of the split
        @rtype: L{DateTime}
        """

        # Find the instance RECURRENCE-ID where a split is going to happen
        now = self.now.duplicate()
        now.offsetDay(1)
        instances = ical.cacheExpandedTimeRanges(now)
        instances = sorted(instances.instances.values(), key=lambda x: x.start)
        rid = instances[0].rid
        for instance in instances:
            rid = instance.rid
            if instance.start >= self.past:
                break
        else:
            # We can get here when splitting and event for overrides only in the past,
            # which happens when splitting an Attendee's copy of an Organizer event
            # where the Organizer event has L{willSplit} == C{True}
            rid = self.past

        return rid


    def split(self, ical, rid=None, olderUID=None):
        """
        Split the specified iCalendar object. This assumes that L{willSplit} has already
        been called and returned C{True}. Splitting is done by carving out old instances
        into a new L{Component} and adjusting the specified component for the on-going
        set. A RELATED-TO property is added to link old to new.

        @param ical: the iCalendar object to split
        @type ical: L{Component}

        @param rid: recurrence-id where the split should occur, or C{None} to determine it here
        @type rid: L{DateTime} or C{None}

        @param olderUID: UID to use for the split off component, or C{None} to generate one here
        @type olderUID: C{str} or C{None}

        @return: iCalendar objects for the old and new "carved out" instances
        @rtype: C{tuple} of two L{Component}'s
        """

        # Find the instance RECURRENCE-ID where a split is going to happen
        rid = self.whereSplit(ical) if rid is None else rid

        # Create the old one with a new UID value (or the one passed in)
        icalOld = ical.duplicate()
        oldUID = icalOld.newUID(newUID=olderUID)
        icalOld.onlyPastInstances(rid)

        # Adjust the current one
        icalNew = ical.duplicate()
        icalNew.onlyFutureInstances(rid)

        # Relate them - add RELATED-TO;RELTYPE=RECURRENCE-SET if not already present
        if not icalOld.hasPropertyWithParameterMatch("RELATED-TO", "RELTYPE", "X-CALENDARSERVER-RECURRENCE-SET"):
            property = Property("RELATED-TO", oldUID, params={"RELTYPE": "X-CALENDARSERVER-RECURRENCE-SET"})
            icalOld.addPropertyToAllComponents(property)
            icalNew.addPropertyToAllComponents(property)

        return (icalOld, icalNew,)
