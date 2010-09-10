# -*- test-case-name: txdav.caldav.datastore.test.test_file -*-
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
    "CalendarStoreTransaction",
    "CalendarHome",
    "Calendar",
    "CalendarObject",
]

import hashlib

from errno import ENOENT

from twisted.internet.interfaces import ITransport
from twisted.python.failure import Failure

from txdav.base.propertystore.xattr import PropertyStore

from twext.python.vcomponent import InvalidICalendarDataError
from twext.python.vcomponent import VComponent
from twext.web2.dav.element.rfc2518 import ResourceType, GETContentType
from twext.web2.dav.resource import TwistedGETContentMD5
from twext.web2.http_headers import generateContentType

from twistedcaldav import caldavxml, customxml
from twistedcaldav.caldavxml import ScheduleCalendarTransp, Opaque
from twistedcaldav.index import Index as OldIndex, IndexSchedule as OldInboxIndex
from twistedcaldav.sharing import InvitesDatabase

from txdav.caldav.icalendarstore import IAttachment
from txdav.caldav.icalendarstore import ICalendar, ICalendarObject
from txdav.caldav.icalendarstore import ICalendarHome

from txdav.caldav.datastore.util import (
    validateCalendarComponent, dropboxIDFromCalendarObject
)

from txdav.common.datastore.file import (
    CommonDataStore, CommonStoreTransaction, CommonHome, CommonHomeChild,
    CommonObjectResource
, CommonStubResource)

from txdav.common.icommondatastore import (NoSuchObjectResourceError,
    InternalDataStoreError)
from txdav.base.datastore.file import writeOperation, hidden, FileMetaDataMixin
from txdav.base.propertystore.base import PropertyName

from zope.interface import implements

CalendarStore = CommonDataStore

CalendarStoreTransaction = CommonStoreTransaction

class CalendarHome(CommonHome):
    implements(ICalendarHome)

    def __init__(self, uid, path, calendarStore, transaction, notifier):
        super(CalendarHome, self).__init__(uid, path, calendarStore, transaction, notifier)

        self._childClass = Calendar


    def calendarWithName(self, name):
        if name in ('dropbox', 'notifications', 'freebusy'):
            # "dropbox" is a file storage area, not a calendar.
            return None
        else:
            return self.childWithName(name)


    createCalendarWithName = CommonHome.createChildWithName
    removeCalendarWithName = CommonHome.removeChildWithName

    def calendars(self):
        """
        Return a generator of the child resource objects.
        """
        for child in self.children():
            if child.name() in ('dropbox', 'notification'):
                continue
            yield child

    def listCalendars(self):
        """
        Return a generator of the child resource names.
        """
        for name in self.listChildren():
            if name in ('dropbox', 'notification'):
                continue
            yield name


    def calendarObjectWithDropboxID(self, dropboxID):
        """
        Implement lookup with brute-force scanning.
        """
        for calendar in self.calendars():
            for calendarObject in calendar.calendarObjects():
                if dropboxID == calendarObject.dropboxID():
                    return calendarObject


    @property
    def _calendarStore(self):
        return self._dataStore


    def createdHome(self):
        self.createCalendarWithName("calendar")
        defaultCal = self.calendarWithName("calendar")
        props = defaultCal.properties()
        props[PropertyName(*ScheduleCalendarTransp.qname())] = ScheduleCalendarTransp(
            Opaque())
        self.createCalendarWithName("inbox")



class Calendar(CommonHomeChild):
    """
    File-based implementation of L{ICalendar}.
    """
    implements(ICalendar)

    def __init__(self, name, calendarHome, notifier, realName=None):
        """
        Initialize a calendar pointing at a path on disk.

        @param name: the subdirectory of calendarHome where this calendar
            resides.
        @type name: C{str}

        @param calendarHome: the home containing this calendar.
        @type calendarHome: L{CalendarHome}

        @param realName: If this calendar was just created, the name which it
        will eventually have on disk.
        @type realName: C{str}
        """
        super(Calendar, self).__init__(name, calendarHome, notifier,
            realName=realName)

        self._index = Index(self)
        self._invites = Invites(self)
        self._objectResourceClass = CalendarObject


    @property
    def _calendarHome(self):
        return self._home


    def resourceType(self):
        return ResourceType.calendar #@UndefinedVariable


    ownerCalendarHome = CommonHomeChild.ownerHome
    calendarObjects = CommonHomeChild.objectResources
    listCalendarObjects = CommonHomeChild.listObjectResources
    calendarObjectWithName = CommonHomeChild.objectResourceWithName
    calendarObjectWithUID = CommonHomeChild.objectResourceWithUID
    createCalendarObjectWithName = CommonHomeChild.createObjectResourceWithName
    removeCalendarObjectWithName = CommonHomeChild.removeObjectResourceWithName
    removeCalendarObjectWithUID = CommonHomeChild.removeObjectResourceWithUID
    calendarObjectsSinceToken = CommonHomeChild.objectResourcesSinceToken


    def calendarObjectsInTimeRange(self, start, end, timeZone):
        raise NotImplementedError()


    def initPropertyStore(self, props):
        # Setup peruser special properties
        props.setSpecialProperties(
            (
                PropertyName.fromElement(caldavxml.CalendarDescription),
                PropertyName.fromElement(caldavxml.CalendarTimeZone),
            ),
            (
                PropertyName.fromElement(customxml.GETCTag),
                PropertyName.fromElement(caldavxml.SupportedCalendarComponentSet),
            ),
        )



class CalendarObject(CommonObjectResource):
    """
    @ivar _path: The path of the .ics file on disk

    @type _path: L{FilePath}
    """
    implements(ICalendarObject)

    def __init__(self, name, calendar):
        super(CalendarObject, self).__init__(name, calendar)
        self._attachments = {}


    @property
    def _calendar(self):
        return self._parentCollection


    def calendar(self):
        return self._calendar


    @writeOperation
    def setComponent(self, component, inserting=False):
        validateCalendarComponent(self, self._calendar, component, inserting)

        self._calendar.retrieveOldIndex().addResource(
            self.name(), component
        )

        self._component = component
        # FIXME: needs to clear text cache

        def do():
            # Mark all properties as dirty, so they can be added back
            # to the newly updated file.
            self.properties().update(self.properties())

            backup = None
            if self._path.exists():
                backup = hidden(self._path.temporarySibling())
                self._path.moveTo(backup)
            fh = self._path.open("w")
            try:
                # FIXME: concurrency problem; if this write is interrupted
                # halfway through, the underlying file will be corrupt.
                fh.write(str(component))
            finally:
                fh.close()

            # Now re-write the original properties on the updated file
            self.properties().flush()

            def undo():
                if backup:
                    backup.moveTo(self._path)
                else:
                    self._path.remove()
            return undo
        self._transaction.addOperation(do, "set calendar component %r" % (self.name(),))

        self._calendar.notifyChanged()


    def component(self):
        if self._component is not None:
            return self._component
        text = self.text()

        try:
            component = VComponent.fromString(text)
        except InvalidICalendarDataError, e:
            raise InternalDataStoreError(
                "File corruption detected (%s) in file: %s"
                % (e, self._path.path)
            )
        return component


    def text(self):
        if self._component is not None:
            return str(self._component)
        try:
            fh = self._path.open()
        except IOError, e:
            if e[0] == ENOENT:
                raise NoSuchObjectResourceError(self)
            else:
                raise

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
                % (self._path.path,)
            )
        return text

    iCalendarText = text

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


    def createAttachmentWithName(self, name, contentType):
        """
        Implement L{ICalendarObject.removeAttachmentWithName}.
        """
        # Make a (FIXME: temp, remember rollbacks) file in dropbox-land
        attachment = Attachment(self, name)
        self._attachments[name] = attachment
        return attachment.store(contentType)


    def removeAttachmentWithName(self, name):
        """
        Implement L{ICalendarObject.removeAttachmentWithName}.
        """
        # FIXME: rollback, tests for rollback
        self._dropboxPath().child(name).remove()
        if name in self._attachments:
            del self._attachments[name]


    def attachmentWithName(self, name):
        # Attachments can be local or remote, but right now we only care about
        # local.  So we're going to base this on the listing of files in the
        # dropbox and not on the calendar data.  However, we COULD examine the
        # 'attach' properties.

        if name in self._attachments:
            return self._attachments[name]
        # FIXME: cache consistently (put it in self._attachments)
        if self._dropboxPath().child(name).exists():
            return Attachment(self, name)
        else:
            # FIXME: test for non-existent attachment.
            return None


    def attendeesCanManageAttachments(self):
        return self.component().hasPropertyInAnyComponent("X-APPLE-DROPBOX")


    def dropboxID(self):
        return dropboxIDFromCalendarObject(self)


    def _dropboxPath(self):
        dropboxPath = self._parentCollection._home._path.child(
            "dropbox"
        ).child(self.dropboxID())
        if not dropboxPath.isdir():
            dropboxPath.makedirs()
        return dropboxPath


    def attachments(self):
        # See comment on attachmentWithName.
        return [Attachment(self, name)
                for name in self._dropboxPath().listdir()]

    def initPropertyStore(self, props):
        # Setup peruser special properties
        props.setSpecialProperties(
            (
            ),
            (
                PropertyName.fromElement(customxml.TwistedCalendarAccessProperty),
                PropertyName.fromElement(customxml.TwistedSchedulingObjectResource),
                PropertyName.fromElement(caldavxml.ScheduleTag),
                PropertyName.fromElement(customxml.TwistedScheduleMatchETags),
                PropertyName.fromElement(customxml.TwistedCalendarHasPrivateCommentsProperty),
                PropertyName.fromElement(caldavxml.Originator),
                PropertyName.fromElement(caldavxml.Recipient),
                PropertyName.fromElement(customxml.ScheduleChanges),
            ),
        )


contentTypeKey = PropertyName.fromElement(GETContentType)
md5key = PropertyName.fromElement(TwistedGETContentMD5)

class AttachmentStorageTransport(object):

    implements(ITransport)

    def __init__(self, attachment, contentType):
        """
        Initialize this L{AttachmentStorageTransport} and open its file for
        writing.

        @param attachment: The attachment whose data is being filled out.
        @type attachment: L{Attachment}
        """
        self._attachment = attachment
        self._contentType = contentType
        self._file = self._attachment._path.open("w")


    def write(self, data):
        # FIXME: multiple chunks
        self._file.write(data)


    def loseConnection(self):
        # FIXME: do anything
        self._file.close()

        md5 = hashlib.md5(self._attachment._path.getContent()).hexdigest()
        props = self._attachment.properties()
        props[contentTypeKey] = GETContentType(generateContentType(self._contentType))
        props[md5key] = TwistedGETContentMD5.fromString(md5)
        props.flush()



class Attachment(FileMetaDataMixin):
    """
    An L{Attachment} is a container for the data associated with a I{locally-
    stored} calendar attachment.  That is to say, there will only be
    L{Attachment} objects present on the I{organizer's} copy of and event, and
    only for C{ATTACH} properties where this server is storing the resource.
    (For example, the organizer may specify an C{ATTACH} property that
    references an URI on a remote server.)
    """

    implements(IAttachment)

    def __init__(self, calendarObject, name):
        self._calendarObject = calendarObject
        self._name = name


    def name(self):
        return self._name


    def properties(self):
        uid = self._calendarObject._parentCollection._home.uid()
        return PropertyStore(uid, lambda :self._path)


    def store(self, contentType):
        return AttachmentStorageTransport(self, contentType)

    def retrieve(self, protocol):
        # FIXME: makeConnection
        # FIXME: actually stream
        # FIMXE: connectionLost
        protocol.dataReceived(self._path.getContent())
        # FIXME: ConnectionDone, not NotImplementedError
        protocol.connectionLost(Failure(NotImplementedError()))

    @property
    def _path(self):
        dropboxPath = self._calendarObject._dropboxPath()
        return dropboxPath.child(self.name())



class CalendarStubResource(CommonStubResource):
    """
    Just enough resource to keep the calendar's sql DB classes going.
    """

    def isCalendarCollection(self):
        return True


    def getChild(self, name):
        calendarObject = self.resource.calendarObjectWithName(name)
        if calendarObject:
            class ChildResource(object):
                def __init__(self, calendarObject):
                    self.calendarObject = calendarObject

                def iCalendar(self):
                    return self.calendarObject.component()

            return ChildResource(calendarObject)
        else:
            return None



class Index(object):
    #
    # OK, here's where we get ugly.
    # The index code needs to be rewritten also, but in the meantime...
    #
    def __init__(self, calendar):
        self.calendar = calendar
        stubResource = CalendarStubResource(calendar)
        if self.calendar.name() == 'inbox':
            indexClass = OldInboxIndex
        else:
            indexClass = OldIndex
        self._oldIndex = indexClass(stubResource)


    def calendarObjects(self):
        calendar = self.calendar
        for name, uid, componentType in self._oldIndex.bruteForceSearch():
            calendarObject = calendar.calendarObjectWithName(name)

            # Precache what we found in the index
            calendarObject._uid = uid
            calendarObject._componentType = componentType

            yield calendarObject


class Invites(object):
    #
    # OK, here's where we get ugly.
    # The index code needs to be rewritten also, but in the meantime...
    #
    def __init__(self, calendar):
        self.calendar = calendar
        stubResource = CalendarStubResource(calendar)
        self._oldInvites = InvitesDatabase(stubResource)
