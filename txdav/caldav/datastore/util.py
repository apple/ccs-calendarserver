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
from twext.python.log import LoggingMixIn
from twisted.application.service import Service
from txdav.common.datastore.file import CommonDataStore as FileStore
from txdav.common.datastore.sql import CommonDataStore as SqlStore

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

        # Only the owner's properties are migrated, since previous releases of
        # calendar server didn't have per-user properties.
        outCalendar.calendarObjectWithName(
            calendarObject.name()).properties().update(
                calendarObject.properties())
        # XXX attachments


def migrateHome(inHome, outHome, getComponent=lambda x: x.component()):
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
    # No migration for notifications, since they weren't present in earlier
    # released versions of CalendarServer.


# TODO: implement addressbooks, import from txdav.common.datastore.file
TOPPATHS = ['calendars']

class UpgradeToDatabaseService(Service, LoggingMixIn, object):
    """
    Upgrade resources from a filesystem store to a database store.
    """


    @classmethod
    def wrapService(cls, path, service, connectionFactory, sqlAttachmentsPath):
        """
        Create an L{UpgradeToDatabaseService} if there are still file-based
        calendar or addressbook homes remaining in the given path.

        Maintenance note: we may want to pass a SQL store in directly rather
        than the combination of connection factory and attachments path, since
        there always must be a SQL store, but the path should remain a path
        because there may not I{be} a file-backed store present and we should
        not create it as a result of checking for it.

        @param path: a path pointing at the document root.
        @type path: L{CachingFilePath}

        @param service: the service to wrap.  This service should be started
            when the upgrade is complete.  (This is accomplished by returning
            it directly when no upgrade needs to be done, and by adding it to
            the service hierarchy when the upgrade completes; assuming that the
            service parent of the resulting service will be set to a
            L{MultiService} or similar.)

        @type service: L{IService}

        @return: a service
        @rtype: L{IService}
        """
        for homeType in TOPPATHS:
            if path.child(homeType).exists():
                self = cls(
                    FileStore(path, None, True, True),
                    SqlStore(connectionFactory, None, sqlAttachmentsPath,
                             True, True),
                    service
                )
                return self
        return service


    def __init__(self, fileStore, sqlStore, service):
        """
        Initialize the service.
        """
        self.wrappedService = service
        self.fileStore = fileStore
        self.sqlStore = sqlStore


    def startService(self):
        self.log_warn("Beginning filesystem -> database upgrade.")
        for fileTxn, fileHome in self.fileStore.eachCalendarHome():
            uid = fileHome.uid()
            self.log_warn("Migrating UID %r" % (uid,))
            sqlTxn = self.sqlStore.newTransaction()
            sqlHome = sqlTxn.calendarHomeWithUID(uid, create=True)
            migrateHome(fileHome, sqlHome)
            fileTxn.commit()
            sqlTxn.commit()
            # FIXME: need a public remove...HomeWithUID() for de-provisioning
            fileHome._path.remove()
        for homeType in TOPPATHS:
            homesPath = self.fileStore._path.child(homeType)
            if homesPath.isdir():
                homesPath.remove()
        self.log_warn(
            "Filesystem upgrade complete, launching database service."
        )
        self.wrappedService.setServiceParent(self.parent)

