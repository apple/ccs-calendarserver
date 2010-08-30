##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
Utility logic common to multiple backend implementations.
"""

from twext.python.vcomponent import InvalidICalendarDataError
from twext.python.vcomponent import VComponent

from txdav.common.icommondatastore import InvalidObjectResourceError, \
    NoSuchObjectResourceError


def validateCalendarComponent(calendarObject, calendar, component, inserting):
    """
    Validate a calendar component for a particular calendar.

    @param calendarObject: The calendar object whose component will be
        replaced.
    @type calendarObject: L{ICalendarObject}

    @param calendar: The calendar which the L{ICalendarObject} is present in.
    @type calendar: L{ICalendar}

    @param component: The VComponent to be validated.
    @type component: L{VComponent}
    """

    if not isinstance(component, VComponent):
        raise TypeError(type(component))

    try:
        if not inserting and component.resourceUID() != calendarObject.uid():
            raise InvalidObjectResourceError(
                "UID may not change (%s != %s)" % (
                    component.resourceUID(), calendarObject.uid()
                 )
            )
    except NoSuchObjectResourceError:
        pass

    try:
        # FIXME: This is a bad way to do this test, there should be a
        # Calendar-level API for it.
        if calendar.name() == 'inbox':
            component.validateComponentsForCalDAV(True)
        else:
            component.validateForCalDAV()
    except InvalidICalendarDataError, e:
        raise InvalidObjectResourceError(e)


def dropboxIDFromCalendarObject(calendarObject):
    """
    Helper to implement L{ICalendarObject.dropboxID}.

    @param calendarObject: The calendar object to retrieve a dropbox ID for.
    @type calendarObject: L{ICalendarObject}
    """
    dropboxProperty = calendarObject.component(
        ).getFirstPropertyInAnyComponent("X-APPLE-DROPBOX")
    if dropboxProperty is not None:
        componentDropboxID = dropboxProperty.value().split("/")[-1]
        return componentDropboxID
    attachProperty = calendarObject.component().getFirstPropertyInAnyComponent(
        "ATTACH"
    )
    if attachProperty is not None:
        # Make sure the value type is URI
        valueType = attachProperty.params().get("VALUE", ("TEXT",))
        if valueType[0] == "URI":
            # FIXME: more aggressive checking to see if this URI is really the
            # 'right' URI.  Maybe needs to happen in the front end.
            attachPath = attachProperty.value().split("/")[-2]
            return attachPath

    return calendarObject.uid() + ".dropbox"


def _migrateCalendar(inCalendar, outCalendar, getComponent):
    """
    Copy all calendar objects and properties in the given input calendar to the
    given output calendar.

    @param inCalendar: the L{ICalendar} to retrieve calendar objects from.
    @param outCalendar: the L{ICalendar} to store calendar objects to.
    @param getComponent: a 1-argument callable; see L{migrateHome}.
    """
    outCalendar.properties().update(inCalendar.properties())
    for calendarObject in inCalendar.calendarObjects():
        outCalendar.createCalendarObjectWithName(
            calendarObject.name(),
            calendarObject.component()) # XXX WRONG SHOULD CALL getComponent
        outCalendar.calendarObjectWithName(
            calendarObject.name()).properties().update(
                calendarObject.properties())
        # XXX attachments


def migrateHome(inHome, outHome, getComponent):
    """
    Copy all calendars and properties in the given input calendar to the given
    output calendar.

    @param inHome: the L{ICalendarHome} to retrieve calendars and properties
        from.

    @param outHome: the L{ICalendarHome} to store calendars and properties
        into.

    @param getComponent: a 1-argument callable that takes an L{ICalendarObject}
        (from a calendar in C{inHome}) and returns a L{VComponent} (to store in
        a calendar in outHome).
    """
    outHome.removeCalendarWithName("calendar")
    outHome.removeCalendarWithName("inbox")
    outHome.properties().update(inHome.properties())
    for calendar in inHome.calendars():
        name = calendar.name()
        outHome.createCalendarWithName(name)
        outCalendar = outHome.calendarWithName(name)
        _migrateCalendar(calendar, outCalendar, getComponent)
