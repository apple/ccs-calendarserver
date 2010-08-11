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
from twistedcaldav.customxml import GETCTag
from uuid import uuid4
from txdav.propertystore.base import PropertyName


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



class SyncTokenHelper(object):
    """
    Implement a basic _updateSyncToken in terms of an object with a property
    store.  This is a mixin for use by data store implementations.
    """

    def _updateSyncToken(self, reset=False):
        # FIXME: add locking a-la CalDAVResource.bumpSyncToken
        # FIXME: tests for desired concurrency properties
        ctag = PropertyName.fromString(GETCTag.sname())
        props = self.properties()
        token = props.get(ctag)
        if token is None or reset:
            tokenuuid = uuid4()
            revision = 1
        else:
            # FIXME: no direct tests for update
            token = str(token)
            tokenuuid, revision = token.split("#", 1)
            revision = int(revision) + 1
        token = "%s#%d" % (tokenuuid, revision)
        props[ctag] = GETCTag(token)
        # FIXME: no direct tests for commit
        return revision



