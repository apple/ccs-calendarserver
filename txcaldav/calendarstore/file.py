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
File calendar store.
"""

__all__ = [
    "CalendarStore",
    "CalendarHome",
    "Calendar",
    "CalendarObject",
]

import errno

from zope.interface import implements

from twisted.python.filepath import FilePath

from twext.log import LoggingMixIn
from twext.python.icalendar import Component as iComponent
from twext.python.icalendar import InvalidICalendarDataError

from txdav.propertystore.xattr import PropertyStore

from txcaldav.icalendarstore import ICalendarHome, ICalendar, ICalendarObject
from txcaldav.icalendarstore import CalendarNameNotAllowedError
from txcaldav.icalendarstore import CalendarObjectNameNotAllowedError
from txcaldav.icalendarstore import CalendarAlreadyExistsError
from txcaldav.icalendarstore import CalendarObjectNameAlreadyExistsError
from txcaldav.icalendarstore import NotFoundError
from txcaldav.icalendarstore import NoSuchCalendarError
from txcaldav.icalendarstore import NoSuchCalendarObjectError
from txcaldav.icalendarstore import InvalidCalendarComponentError
from txcaldav.icalendarstore import InternalDataStoreError

from twistedcaldav.index import Index


class CalendarStore(LoggingMixIn):
    # FIXME: Do we need an interface?

    calendarHomeClass = property(lambda _: CalendarHome)

    def __init__(self, path):
        """
        @param path: a L{FilePath}
        """
        assert isinstance(path, FilePath)

        self.path = path

        if not path.isdir():
            # FIXME: If we add a CalendarStore interface, this should
            # be CalendarStoreNotFoundError.
            raise NotFoundError("No such calendar store")

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.path.path)

    def calendarHomeWithUID(self, uid):
        if uid.startswith("."):
            return None

        childPath = self.path.child(uid)

        if childPath.isdir():
            return CalendarHome(childPath, self)
        else:
            return None


class CalendarHome(LoggingMixIn):
    implements(ICalendarHome)

    calendarClass = property(lambda _: Calendar)

    def __init__(self, path, calendarStore):
        self.path = path
        self.calendarStore = calendarStore

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.path)

    def uid(self):
        return self.path.basename()

    def calendars(self):
        return (
            self.calendarWithName(name)
            for name in self.path.listdir()
            if not name.startswith(".")
        )

    def calendarWithName(self, name):
        if name.startswith("."):
            return None

        childPath = self.path.child(name)
        if childPath.isdir():
            return Calendar(childPath, self)
        else:
            return None

    def createCalendarWithName(self, name):
        if name.startswith("."):
            raise CalendarNameNotAllowedError(name)

        childPath = self.path.child(name)

        try:
            childPath.createDirectory()
        except (IOError, OSError), e:
            if e.errno == errno.EEXIST:
                raise CalendarAlreadyExistsError(name)
            raise

    def removeCalendarWithName(self, name):
        if name.startswith("."):
            raise NoSuchCalendarError(name)

        childPath = self.path.child(name)
        try:
            childPath.remove()
        except (IOError, OSError), e:
            if e.errno == errno.ENOENT:
                raise NoSuchCalendarError(name)
            raise

    def properties(self):
        if not hasattr(self, "_properties"):
            self._properties = PropertyStore(self.path)
        return self._properties


class Calendar(LoggingMixIn):
    implements(ICalendar)

    calendarObjectClass = property(lambda _: CalendarObject)

    def __init__(self, path, calendarHome):
        self.path = path
        self.calendarHome = calendarHome

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.path.path)

    def name(self):
        return self.path.basename()

    def ownerCalendarHome(self):
        return self.calendarHome

    def calendarObjects(self):
        return (
            self.calendarObjectWithName(name)
            for name in self.path.listdir()
            if not name.startswith(".")
        )

    def calendarObjectWithName(self, name):
        childPath = self.path.child(name)
        if childPath.isfile():
            return CalendarObject(childPath, self)
        else:
            return None

    def calendarObjectWithUID(self, uid):
        raise NotImplementedError()

    def createCalendarObjectWithName(self, name, component):
        if name.startswith("."):
            raise CalendarObjectNameNotAllowedError(name)

        childPath = self.path.child(name)
        if childPath.exists():
            raise CalendarObjectNameAlreadyExistsError(name)

        calendarObject = CalendarObject(childPath, self)
        calendarObject.setComponent(component)

    def removeCalendarObjectWithName(self, name):
        if name.startswith("."):
            raise NoSuchCalendarObjectError(name)

        childPath = self.path.child(name)
        if childPath.isfile():
            childPath.remove()
        else:
            raise NoSuchCalendarObjectError(name)

    def removeCalendarObjectWithUID(self, uid):
        raise NotImplementedError()

    def syncToken(self):
        raise NotImplementedError()

    def calendarObjectsInTimeRange(self, start, end, timeZone):
        raise NotImplementedError()

    def calendarObjectsSinceToken(self, token):
        raise NotImplementedError()

    def properties(self):
        if not hasattr(self, "_properties"):
            self._properties = PropertyStore(self.path)
        return self._properties


class CalendarObject(LoggingMixIn):
    implements(ICalendarObject)

    def __init__(self, path, calendar):
        self.path = path
        self.calendar = calendar

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.path.path)

    def name(self):
        return self.path.basename()

    def setComponent(self, component):
        if not isinstance(component, iComponent):
            raise TypeError(iComponent)

        try:
            component.validateForCalDAV()
        except InvalidICalendarDataError, e:
            raise InvalidCalendarComponentError(e)

        self._component = component
        if hasattr(self, "_text"):
            del self._text

        fh = self.path.open("w")
        try:
            fh.write(str(component))
        finally:
            fh.close()

    def component(self):
        if not hasattr(self, "_component"):
            text = self.iCalendarText()

            try:
                component = iComponent.fromString(text)
            except InvalidICalendarDataError, e:
                raise InternalDataStoreError(
                    "File corruption detected (%s) in file: %s"
                    % (e, self.path.path)
                )

            del self._text
            self._component = component

        return self._component

    def iCalendarText(self):
        #
        # Note I'm making an assumption here that caching both is
        # redundant, so we're caching the text if it's asked for and
        # we don't have the component cached, then tossing it and
        # relying on the component if we have that cached. -wsv
        #
        if not hasattr(self, "_text"):
            if hasattr(self, "_component"):
                return str(self._component)

            try:
                fh = self.path.open()
            except IOError, e:
                if e[0] == errno.ENOENT:
                    raise NoSuchCalendarObjectError(self)

            try:
                text = fh.read()
            finally:
                fh.close()

            if not (
                text.startswith("BEGIN:VCALENDAR\r\n") or
                text.endswith("\r\nEND:VCALENDAR\r\n")
            ):
                raise InternalDataStoreError(
                    "File corruption detected (improper start) in file: %s"
                    % (self.path.path,)
                )

            self._text = text

        return self._text

    def uid(self):
        if not hasattr(self, "_uid"):
            self._uid = self.component().resourceUID()
        return self._uid

    def componentType(self):
        if not hasattr(self, "_componentType"):
            self._componentType = self.component().mainType()
        return self._componentType

    def organizer(self):
        return self.component().getOrganizer()

    def properties(self):
        if not hasattr(self, "_properties"):
            self._properties = PropertyStore(self.path)
        return self._properties
