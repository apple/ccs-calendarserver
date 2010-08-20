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
from twistedcaldav.vcard import Component as VCard
from twistedcaldav.vcard import InvalidVCardDataError

from txdav.common.icommondatastore import InvalidObjectResourceError,\
    NoSuchObjectResourceError


def validateCalendarComponent(calendarObject, calendar, component):
    """
    Validate a calendar component for a particular calendar.

    @param calendarObject: The calendar object whose component will be replaced.
    @type calendarObject: L{ICalendarObject}

    @param calendar: The calendar which the L{ICalendarObject} is present in.
    @type calendar: L{ICalendar}

    @param component: The VComponent to be validated.
    @type component: L{VComponent}
    """

    if not isinstance(component, VComponent):
        raise TypeError(type(component))

    try:
        if component.resourceUID() != calendarObject.uid():
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
    attachProperty = calendarObject.component().getFirstPropertyInAnyComponent("ATTACH")
    if attachProperty is not None:
        # Make sure the value type is URI
        valueType = attachProperty.params().get("VALUE", ("TEXT",))
        if valueType[0] == "URI": 
            # FIXME: more aggressive checking to see if this URI is really the
            # 'right' URI.  Maybe needs to happen in the front end.
            attachPath = attachProperty.value().split("/")[-2]
            return attachPath
    
    return calendarObject.uid() + ".dropbox"


def validateAddressBookComponent(addressbookObject, vcard, component):
    """
    Validate an addressbook component for a particular addressbook.

    @param addressbookObject: The addressbook object whose component will be replaced.
    @type addressbookObject: L{IAddressBookObject}

    @param addressbook: The addressbook which the L{IAddressBookObject} is present in.
    @type addressbook: L{IAddressBook}

    @param component: The VComponent to be validated.
    @type component: L{VComponent}
    """

    if not isinstance(component, VCard):
        raise TypeError(type(component))

    try:
        if component.resourceUID() != addressbookObject.uid():
            raise InvalidObjectResourceError(
                "UID may not change (%s != %s)" % (
                    component.resourceUID(), addressbookObject.uid()
                 )
            )
    except NoSuchObjectResourceError:
        pass

    try:
        component.validForCardDAV()
    except InvalidVCardDataError, e:
        raise InvalidObjectResourceError(e)



class CalendarSyncTokenHelper(object):
    """
    This is a mixin for use by data store implementations.
    """

    def syncToken(self):
        revision = self._txn.execSQL(
            "select REVISION from CALENDAR where RESOURCE_ID = %s",
            [self._resourceID])[0][0]
        return "%s#%s" % (self._resourceID, revision,)

    def _updateSyncToken(self):
        
        self._txn.execSQL("""
            update CALENDAR
            set (REVISION)
            = (nextval('CALENDAR_OBJECT_REVISION_SEQ'))
            where RESOURCE_ID = %s
            """,
            [self._resourceID]
        )

    def _insertRevision(self, name):
        self._changeRevision("insert", name)

    def _updateRevision(self, name):
        self._changeRevision("update", name)

    def _deleteRevision(self, name):
        self._changeRevision("delete", name)

    def _changeRevision(self, action, name):
        
        nextrevision = self._txn.execSQL("""
            select nextval('CALENDAR_OBJECT_REVISION_SEQ')
            """
        )

        if action == "delete":
            self._txn.execSQL("""
                update CALENDAR_OBJECT_REVISIONS
                set (REVISION, DELETED) = (%s, TRUE)
                where CALENDAR_RESOURCE_ID = %s and RESOURCE_NAME = %s
                """,
                [nextrevision, self._resourceID, name]
            )
            self._txn.execSQL("""    
                update CALENDAR
                set (REVISION) = (%s)
                where RESOURCE_ID = %s
                """,
                [nextrevision, self._resourceID]
            )
        elif action == "update":
            self._txn.execSQL("""
                update CALENDAR_OBJECT_REVISIONS
                set (REVISION) = (%s)
                where CALENDAR_RESOURCE_ID = %s and RESOURCE_NAME = %s
                """,
                [nextrevision, self._resourceID, name]
            )
            self._txn.execSQL("""    
                update CALENDAR
                set (REVISION) = (%s)
                where RESOURCE_ID = %s
                """,
                [nextrevision, self._resourceID]
            )
        elif action == "insert":
            self._txn.execSQL("""
                delete from CALENDAR_OBJECT_REVISIONS
                where CALENDAR_RESOURCE_ID = %s and RESOURCE_NAME = %s
                """,
                [self._resourceID, name,]
            )
            self._txn.execSQL("""
                insert into CALENDAR_OBJECT_REVISIONS
                (CALENDAR_RESOURCE_ID, RESOURCE_NAME, REVISION, DELETED)
                values (%s, %s, %s, FALSE)
                """,
                [self._resourceID, name, nextrevision]
            )
            self._txn.execSQL("""    
                update CALENDAR
                set (REVISION) = (%s)
                where RESOURCE_ID = %s
                """,
                [nextrevision, self._resourceID]
            )

class AddressbookSyncTokenHelper(object):
    """
    This is a mixin for use by data store implementations.
    """

    def syncToken(self):
        revision = self._txn.execSQL(
            "select REVISION from ADDRESSBOOK where RESOURCE_ID = %s",
            [self._resourceID])[0][0]
        return "%s#%s" % (self._resourceID, revision,)

    def _updateSyncToken(self):
        
        self._txn.execSQL("""
            update ADDRESSBOOK
            set (REVISION)
            = (nextval('ADDRESSBOOK_OBJECT_REVISION_SEQ'))
            where RESOURCE_ID = %s
            """,
            [self._resourceID]
        )

    def _insertRevision(self, name):
        self._changeRevision("insert", name)

    def _updateRevision(self, name):
        self._changeRevision("update", name)

    def _deleteRevision(self, name):
        self._changeRevision("delete", name)

    def _changeRevision(self, action, name):
        
        nextrevision = self._txn.execSQL("""
            select nextval('ADDRESSBOOK_OBJECT_REVISION_SEQ')
            """
        )

        if action == "delete":
            self._txn.execSQL("""
                update ADDRESSBOOK_OBJECT_REVISIONS
                set (REVISION, DELETED) = (%s, TRUE)
                where ADDRESSBOOK_RESOURCE_ID = %s and RESOURCE_NAME = %s
                """,
                [nextrevision, self._resourceID, name]
            )
            self._txn.execSQL("""    
                update ADDRESSBOOK
                set (REVISION) = (%s)
                where RESOURCE_ID = %s
                """,
                [nextrevision, self._resourceID]
            )
        elif action == "update":
            self._txn.execSQL("""
                update ADDRESSBOOK_OBJECT_REVISIONS
                set (REVISION) = (%s)
                where ADDRESSBOOK_RESOURCE_ID = %s and RESOURCE_NAME = %s
                """,
                [nextrevision, self._resourceID, name]
            )
            self._txn.execSQL("""    
                update ADDRESSBOOK
                set (REVISION) = (%s)
                where RESOURCE_ID = %s
                """,
                [nextrevision, self._resourceID]
            )
        elif action == "insert":
            self._txn.execSQL("""
                delete from ADDRESSBOOK_OBJECT_REVISIONS
                where ADDRESSBOOK_RESOURCE_ID = %s and RESOURCE_NAME = %s
                """,
                [self._resourceID, name,]
            )
            self._txn.execSQL("""
                insert into ADDRESSBOOK_OBJECT_REVISIONS
                (ADDRESSBOOK_RESOURCE_ID, RESOURCE_NAME, REVISION, DELETED)
                values (%s, %s, %s, FALSE)
                """,
                [self._resourceID, name, nextrevision]
            )
            self._txn.execSQL("""    
                update ADDRESSBOOK
                set (REVISION) = (%s)
                where RESOURCE_ID = %s
                """,
                [nextrevision, self._resourceID]
            )
        