##
# Copyright (c) 2009-2014 Apple Inc. All rights reserved.
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

from twistedcaldav.datafilters.filter import CalendarFilter
from twistedcaldav.ical import Component, Property, PERUSER_COMPONENT, \
    PERUSER_UID, PERINSTANCE_COMPONENT

__all__ = [
    "PerUserDataFilter",
]

"""
Object model for calendar data is as follows:

VCALENDAR
  VTIMEZONE*
  VEVENT* / VTODO* / VJOURNAL*
  BEGIN:X-CALENDARSERVER-PERUSER*
    X-CALENDARSERVER-PERUSER-UID
    UID
    BEGIN:X-CALENDARSERVER-PERINSTANCE
      RECURRENCE-ID?
      TRANSP?
      VALARM*

So we will store per user data inside the top-level component (alongside VEVENT, VTODO etc). That new component will
contain properties to identify the user and the UID of the VEVENT, VTODO it affects. It will contain sub-components
for each instance overridden by the per-user data. These per-user overridden components may not correspond to an
actual overridden component. In that situation the server has to re-construct the per-user data appropriately:

e.g.,

1. VEVENT contains an overridden instance, but X-CALENDARSERVER-PERUSER does not - server uses the must instance
X-CALENDARSERVER-PERUSER data (if any) for the overridden instance.

2. VEVENT does not contain an overridden instance, but X-CALENDARSERVER-PERUSER does - server synthesizes an
overridden instance to match the X-CALENDARSERVER-PERUSER one.

3. VEVENT contains overridden instance and X-CALENDARSERVER-PERUSER does - server merges X-CALENDARSERVER-PERUSER
data into overridden instance.

"""

class PerUserDataFilter(CalendarFilter):
    """
    Filter per-user data
    """

    # Regular properties that need to be treated as per-user
    PERUSER_PROPERTIES = ("TRANSP",)

    # Regular components that need to be treated as per-user
    PERUSER_SUBCOMPONENTS = ("VALARM",)

    # X- properties that are ignored - by default all X- properties are treated as per-user except for the
    # ones listed here
    IGNORE_X_PROPERTIES = [Component.HIDDEN_INSTANCE_PROPERTY]

    def __init__(self, uid):
        """

        @param uid: unique identifier of the user for whom the data is being filtered
        @type uid: C{str}
        """

        self.uid = uid


    def filter(self, ical):
        """
        Filter the supplied iCalendar object using the request information.
        Assume that the object is a CalDAV calendar resource.

        @param ical: iCalendar object - this will be modified and returned
        @type ical: L{Component} or C{str}

        @return: L{Component} for the filtered calendar data
        """

        # Make sure input is valid
        ical = self.validCalendar(ical)

        # Look for matching per-user sub-component, removing all the others
        peruser_component = None
        for component in tuple(ical.subcomponents()):
            if component.name() == PERUSER_COMPONENT:

                # Check user id - remove if not matches
                if component.propertyValue(PERUSER_UID) != self.uid:
                    ical.removeComponent(component)
                elif peruser_component is None:
                    peruser_component = component
                    ical.removeComponent(component)
                else:
                    raise AssertionError("Can't have two X-CALENDARSERVER-PERUSER components for the same user")

        # Now transfer any components over
        if peruser_component:
            self._mergeBack(ical, peruser_component)

        return ical


    def merge(self, icalnew, icalold):
        """
        Merge the new data with the old taking per-user information into account.

        @param icalnew: new calendar data
        @type icalnew: L{Component} or C{str}
        @param icalold: existing calendar data
        @type icalold: L{Component} or C{str}

        @return: L{Component} for the merged calendar data
        """

        # Make sure input is valid
        icalnew = self.validCalendar(icalnew)

        # There cannot be any X-CALENDARSERVER-PERUSER components in the new data
        for component in tuple(icalnew.subcomponents()):
            if component.name() == PERUSER_COMPONENT:
                raise ValueError("Cannot merge calendar data with X-CALENDARSERVER-PERUSER components in it")

        # First split the new data into common and per-user pieces
        self._splitPerUserData(icalnew)
        if icalold is None:
            return icalnew

        # Make sure input is valid
        icalold = self.validCalendar(icalold)

        self._mergeRepresentations(icalnew, icalold)
        return icalnew


    def _mergeBack(self, ical, peruser):
        """
        Merge the per-user data back into the main calendar data.

        @param ical: main calendar data to merge into
        @type ical: L{Component}
        @param peruser: the per-user data to merge in
        @type peruser: L{Component}
        """

        # Iterate over each instance in the per-user data and build mapping
        peruser_recurrence_map = {}
        for subcomponent in peruser.subcomponents():
            if subcomponent.name() != PERINSTANCE_COMPONENT:
                raise AssertionError("Wrong sub-component '%s' in a X-CALENDARSERVER-PERUSER component" % (subcomponent.name(),))
            peruser_recurrence_map[subcomponent.getRecurrenceIDUTC()] = subcomponent

        ical_recurrence_set = set(ical.getComponentInstances())
        peruser_recurrence_set = set(peruser_recurrence_map.keys())

        # Set operations to find union and differences
        union_set = ical_recurrence_set.intersection(peruser_recurrence_set)
        ical_only_set = ical_recurrence_set.difference(peruser_recurrence_set)
        peruser_only_set = peruser_recurrence_set.difference(ical_recurrence_set)

        # For ones in per-user data but no main data, we synthesize an instance and copy over per-user data
        # NB We have to do this before we do any merge that may change the master
        if ical.masterComponent() is not None:
            for rid in peruser_only_set:
                ical_component = ical.deriveInstance(rid)
                if ical_component is None:
                    continue
                peruser_component = peruser_recurrence_map[rid]
                self._mergeBackComponent(ical_component, peruser_component)
                ical.addComponent(ical_component)
        elif peruser_only_set:
            # We used to error out here, but instead we should silently ignore this error and keep going
            pass

        # Process the unions by merging in per-user data
        for rid in union_set:
            ical_component = ical.overriddenComponent(rid)
            peruser_component = peruser_recurrence_map[rid]
            self._mergeBackComponent(ical_component, peruser_component)

        # For ones in main data but no per-user data, we try and copy over the master per-user data
        if ical_only_set:
            peruser_master = peruser_recurrence_map.get(None)
            if peruser_master:
                for rid in ical_only_set:
                    ical_component = ical.overriddenComponent(rid)
                    self._mergeBackComponent(ical_component, peruser_master)


    def _mergeBackComponent(self, ical, peruser):
        """
        Copy all properties and sub-components from per-user data into the main component
        @param ical:
        @type ical:
        @param peruser:
        @type peruser:
        """

        # Each sub-component
        for subcomponent in peruser.subcomponents():
            ical.addComponent(subcomponent)

        # Each property except RECURRENCE-ID
        for property in peruser.properties():
            if property.name() == "RECURRENCE-ID":
                continue
            ical.addProperty(property)


    def _splitPerUserData(self, ical):
        """
        Split the per-user data out of the "normal" iCalendar components into separate per-user
        components. Along the way keep the iCalendar representation in a "minimal" state by eliminating
        any components that are the same as the master derived component.

        @param ical: calendar data to process
        @type ical: L{Component}
        """

        def init_peruser_component():
            peruser = Component(PERUSER_COMPONENT)
            peruser.addProperty(Property("UID", ical.resourceUID()))
            peruser.addProperty(Property(PERUSER_UID, self.uid))
            return peruser

        components = tuple(ical.subcomponents())
        peruser_component = init_peruser_component() if self.uid else None
        perinstance_components = {}

        for component in components:
            if component.name() == "VTIMEZONE":
                continue
            rid = component.propertyValue("RECURRENCE-ID")
            rid = rid.duplicate() if rid is not None else None

            perinstance_component = Component(PERINSTANCE_COMPONENT) if self.uid else None
            perinstance_id_different = False

            # Transfer per-user properties from main component to per-instance component
            for property in tuple(component.properties()):
                if property.name() in PerUserDataFilter.PERUSER_PROPERTIES or property.name().startswith("X-") and property.name() not in PerUserDataFilter.IGNORE_X_PROPERTIES:
                    if self.uid:
                        perinstance_component.addProperty(property)
                    component.removeProperty(property)
                    perinstance_id_different = True

            # Transfer per-user components from main component to per-instance component
            for subcomponent in tuple(component.subcomponents()):
                if subcomponent.name() in PerUserDataFilter.PERUSER_SUBCOMPONENTS or subcomponent.name().startswith("X-"):
                    if self.uid:
                        perinstance_component.addComponent(subcomponent)
                    component.removeComponent(subcomponent)
                    perinstance_id_different = True

            if perinstance_id_different and perinstance_component:
                perinstance_components[rid] = perinstance_component

        if self.uid:
            # Add unique per-instance components into the per-user component
            peruser_component_different = False
            master_perinstance = perinstance_components.get(None)
            if master_perinstance:
                peruser_component.addComponent(master_perinstance)
                peruser_component_different = True
            for rid, perinstance in perinstance_components.iteritems():
                if rid is None:
                    continue
                if master_perinstance is None or perinstance != master_perinstance:
                    perinstance.addProperty(Property("RECURRENCE-ID", rid))
                    peruser_component.addComponent(perinstance)
                    peruser_component_different = True

            if peruser_component_different:
                ical.addComponent(peruser_component)

            self._compactInstances(ical)


    def _compactInstances(self, ical):
        """
        Remove recurrences instances that are the same as their master-derived counterparts. This gives the most
        compact representation of the calendar data.

        @param ical: calendar data to process
        @type ical: L{Component}
        """

        # Must have a master component in order to do this
        master = ical.masterComponent()
        if master is None:
            return

        masterDerived = ical.masterDerived()

        for subcomponent in tuple(ical.subcomponents()):
            if subcomponent.name() == "VTIMEZONE" or subcomponent.name().startswith("X-"):
                continue
            rid = subcomponent.getRecurrenceIDUTC()
            if rid is None:
                continue
            derived = ical.deriveInstance(rid, newcomp=masterDerived)
            if derived is not None and derived == subcomponent:
                ical.removeComponent(subcomponent)


    def _mergeRepresentations(self, icalnew, icalold):

        # Test for simple case first
        if icalnew.isRecurring() and icalold.isRecurring():
            # Test each instance from old data to see whether it is still valid in the new one
            self._complexMerge(icalnew, icalold)
        else:
            self._simpleMerge(icalnew, icalold)


    def _simpleMerge(self, icalnew, icalold):

        # Take all per-user components from old and add to new, except for our user
        new_recur = icalnew.isRecurring()
        old_recur = icalold.isRecurring()
        new_recur_has_no_master = new_recur and (icalnew.masterComponent() is None)
        for component in icalold.subcomponents():
            if component.name() == PERUSER_COMPONENT:
                if component.propertyValue(PERUSER_UID) != self.uid and not new_recur_has_no_master:
                    newcomponent = component.duplicate()

                    # Only transfer the master components from the old data to the new when the old
                    # was recurring and the new is not recurring
                    if not new_recur and old_recur:
                        for subcomponent in tuple(newcomponent.subcomponents()):
                            if subcomponent.getRecurrenceIDUTC() is not None:
                                newcomponent.removeComponent(subcomponent)

                    if len(tuple(newcomponent.subcomponents())):
                        icalnew.addComponent(newcomponent)


    def _complexMerge(self, icalnew, icalold):

        # Take all per-user components from old and add to new, except for our user
        for component in icalold.subcomponents():
            if component.name() == PERUSER_COMPONENT:
                if component.propertyValue(PERUSER_UID) != self.uid:
                    newcomponent = component.duplicate()

                    # See which of the instances are still valid
                    old_rids = dict([(subcomponent.getRecurrenceIDUTC(), subcomponent,) for subcomponent in newcomponent.subcomponents()])
                    valid_rids = icalnew.validInstances(old_rids.keys())
                    for old_rid, subcomponent in old_rids.iteritems():
                        if old_rid not in valid_rids:
                            newcomponent.removeComponent(subcomponent)

                    if len(tuple(newcomponent.subcomponents())):
                        icalnew.addComponent(newcomponent)
