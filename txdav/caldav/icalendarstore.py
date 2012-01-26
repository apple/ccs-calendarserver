# -*- test-case-name: txdav.caldav.datastore -*-
##
# Copyright (c) 2010-2011 Apple Inc. All rights reserved.
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
Calendar store interfaces
"""

from txdav.common.icommondatastore import ICommonTransaction, \
    IShareableCollection
from txdav.idav import IDataStoreObject, IDataStore

from twisted.internet.interfaces import ITransport
from txdav.idav import INotifier


__all__ = [
    # Interfaces
    "ICalendarTransaction",
    "ICalendarHome",
    "ICalendar",
    "ICalendarObject",

    # Exceptions
    "QuotaExceeded",
]



class QuotaExceeded(Exception):
    """
    The quota for a particular user has been exceeded.
    """



class ICalendarTransaction(ICommonTransaction):
    """
    Transaction functionality required to be implemented by calendar stores.
    """

    def calendarHomeWithUID(uid, create=False):
        """
        Retrieve the calendar home for the principal with the given C{uid}.

        If C{create} is C{True}, create the calendar home if it doesn't
        already exist.

        @return: a L{Deferred} which fires with L{ICalendarHome} or C{None} if
            no such calendar home exists.
        """



class ICalendarStore(IDataStore):
    """
    API root for calendar data storage.
    """

    def eachCalendarHome(self):
        """
        Enumerate all calendar homes in this store, with each one in an
        accompanying transaction.

        @return: an iterator of 2-tuples of C{(transaction, calendar home)}
            where C{transaction} is an L{ITransaction} provider and C{calendar
            home} is an L{ICalendarHome} provider.
        """


#
# Interfaces
#

class ICalendarHome(INotifier, IDataStoreObject):
    """
    An L{ICalendarHome} is a collection of calendars which belongs to a
    specific principal and contains the calendars which that principal has
    direct access to.  This includes both calendars owned by the principal as
    well as calendars that have been shared with and accepts by the principal.
    """

    def uid():
        """
        Retrieve the unique identifier for this calendar home.

        @return: a string.
        """

    def calendars():
        """
        Retrieve calendars contained in this calendar home.

        @return: an iterable of L{ICalendar}s.
        """

    def loadCalendars():
        """
        Pre-load all calendars Depth:1.

        @return: an iterable of L{ICalendar}s.
        """

    def calendarWithName(name):
        """
        Retrieve the calendar with the given C{name} contained in this
        calendar home.

        @param name: a string.
        @return: an L{ICalendar} or C{None} if no such calendar
            exists.
        """


    def calendarObjectWithDropboxID(dropboxID):
        """
        Retrieve an L{ICalendarObject} by looking up its attachment collection
        ID.

        @param dropboxID: The name of the collection in a dropbox corresponding
            to a collection in the user's dropbox.

        @type dropboxID: C{str}

        @return: the calendar object identified by the given dropbox.

        @rtype: L{ICalendarObject}
        """


    def createCalendarWithName(name):
        """
        Create a calendar with the given C{name} in this calendar
        home.

        @param name: a string.
        @raise CalendarAlreadyExistsError: if a calendar with the
            given C{name} already exists.
        """

    def removeCalendarWithName(name):
        """
        Remove the calendar with the given C{name} from this calendar
        home.  If this calendar home owns the calendar, also remove
        the calendar from all calendar homes.

        @param name: a string.
        @raise NoSuchCalendarObjectError: if no such calendar exists.

        @return: an L{IPropertyStore}.
        """


    def getAllDropboxIDs():
        """
        Retrieve all of the dropbox IDs of events in this home for calendar
        objects which either allow attendee write access to their dropboxes,
        have attachments to read, or both.

        @return: a L{Deferred} which fires with a C{list} of all dropbox IDs (as
            unicode strings)
        """


    def quotaAllowedBytes():
        """
        The number of bytes of data that the user is allowed to store in this
        calendar home.  If quota is not enforced for this calendar home, this
        will return C{None}.

        Currently this is only enforced against attachment data.

        @rtype: C{int} or C{NoneType}
        """


    def quotaUsedBytes():
        """
        The number of bytes counted towards the user's quota.

        Currently this is only tracked against attachment data.

        @rtype: C{int}
        """


    def adjustQuotaUsedBytes(delta):
        """
        Increase or decrease the number of bytes that count towards the user's
        quota.

        @param delta: The number of bytes to adjust the quota by.

        @type delta: C{int}

        @raise QuotaExceeded: when the quota is exceeded.
        """



class ICalendar(INotifier, IShareableCollection, IDataStoreObject):
    """
    Calendar

    A calendar is a container for calendar objects (events, to-dos,
    etc.).  A calendar belongs to a specific principal but may be
    shared with other principals, granting them read-only or
    read/write access.
    """

    def rename(name):
        """
        Change the name of this calendar.
        """

    def ownerCalendarHome():
        """
        Retrieve the calendar home for the owner of this calendar.
        Calendars may be shared from one (the owner's) calendar home
        to other (the sharee's) calendar homes.

        @return: an L{ICalendarHome}.
        """

    def calendarObjects():
        """
        Retrieve the calendar objects contained in this calendar.

        @return: an iterable of L{ICalendarObject}s.
        """

    def calendarObjectWithName(name):
        """
        Retrieve the calendar object with the given C{name} contained
        in this calendar.

        @param name: a string.
        @return: an L{ICalendarObject} or C{None} if no such calendar
            object exists.
        """

    def calendarObjectWithUID(uid):
        """
        Retrieve the calendar object with the given C{uid} contained
        in this calendar.

        @param uid: a string.

        @return: a L{Deferred} firing an L{ICalendarObject} or C{None} if no
            such calendar object exists.
        """

    def createCalendarObjectWithName(name, component):
        """
        Create a calendar component with the given C{name} in this
        calendar from the given C{component}.

        @param name: a string.
        @param component: a C{VCALENDAR} L{Component}
        @raise ObjectResourceNameAlreadyExistsError: if a calendar
            object with the given C{name} already exists.
        @raise CalendarObjectUIDAlreadyExistsError: if a calendar
            object with the same UID as the given C{component} already
            exists.
        @raise InvalidCalendarComponentError: if the given
            C{component} is not a valid C{VCALENDAR} L{VComponent} for
            a calendar object.
        """

    def removeCalendarObjectWithName(name):
        """
        Remove the calendar object with the given C{name} from this
        calendar.

        @param name: a string.
        @raise NoSuchCalendarObjectError: if no such calendar object
            exists.
        """

    def removeCalendarObjectWithUID(uid):
        """
        Remove the calendar object with the given C{uid} from this
        calendar.

        @param uid: a string.
        @raise NoSuchCalendarObjectError: if the calendar object does
            not exist.
        """

    def syncToken():
        """
        Retrieve the current sync token for this calendar.

        @return: a string containing a sync token.
        """

    def calendarObjectsInTimeRange(start, end, timeZone):
        """
        Retrieve all calendar objects in this calendar which have
        instances that occur within the time range that begins at
        C{start} and ends at C{end}.

        @param start: a L{PyCalendarDateTime}.
        @param end: a L{PyCalendarDateTime}.
        @param timeZone: a L{PyCalendarTimezone}.
        @return: an iterable of L{ICalendarObject}s.
        """

    def calendarObjectsSinceToken(token):
        """
        Retrieve all calendar objects in this calendar that have
        changed since the given C{token} was last valid.

        @param token: a sync token.
        @return: a 3-tuple containing an iterable of
            L{ICalendarObject}s that have changed, an iterable of uids
            that have been removed, and the current sync token.
        """


    def resourceNamesSinceToken(revision):
        """
        Low-level query to gather names for calendarObjectsSinceToken.
        """



class ICalendarObject(IDataStoreObject):
    """
    Calendar object

    A calendar object describes an event, to-do, or other iCalendar
    object.
    """

    def calendar():
        """
        @return: The calendar which this calendar object is a part of.
        @rtype: L{ICalendar}
        """

    def setComponent(component):
        """
        Rewrite this calendar object to match the given C{component}.
        C{component} must have the same UID and be of the same
        component type as this calendar object.

        @param component: a C{VCALENDAR} L{VComponent}.
        @raise InvalidCalendarComponentError: if the given
            C{component} is not a valid C{VCALENDAR} L{VComponent} for
            a calendar object.
        """

    def component():
        """
        Retrieve the calendar component for this calendar object.

        @raise ConcurrentModification: if this L{ICalendarObject} has been
            deleted and committed by another transaction between its creation
            and the first call to this method.

        @return: a C{VCALENDAR} L{VComponent}.
        """

    def uid():
        """
        Retrieve the UID for this calendar object.

        @return: a string containing a UID.
        """

    def componentType():
        """
        Retrieve the iCalendar component type for the main component
        in this calendar object.

        @raise InvalidICalendarDataError: if this L{ICalendarObject} has invalid
            calendar data.  This should only ever happen when reading in data
            that hasn't passed through setComponent( ) or
            createCalendarObjectXXX( ) such as data imported from an older store
            or an external system.

        @return: a string containing the component type.
        """

    def organizer():
        # FIXME: Ideally should return a URI object
        """
        Retrieve the organizer's calendar user address for this
        calendar object.

        @return: a URI string.
        """

    def dropboxID():
        """
        An identifier, unique to the calendar home, that specifies a location
        where attachments are to be stored for this object.

        @return: the value of the last segment of the C{X-APPLE-DROPBOX}
            property.

        @rtype: C{string}
        """


    def createAttachmentWithName(name):
        """
        Add an attachment to this calendar object.

        @param name: An identifier, unique to this L{ICalendarObject}, which
            names the attachment for future retrieval.

        @type name: C{str}

        @return: the L{IAttachment}.
        """


    def attachmentWithName(name):
        """
        Asynchronously retrieve an attachment with the given name from this
        calendar object.

        @param name: An identifier, unique to this L{ICalendarObject}, which
            names the attachment for future retrieval.

        @type name: C{str}

        @return: a L{Deferred} which fires with an L{IAttachment} with the given
            name, or L{None} if no such attachment exists.

        @rtype: L{Deferred}
        """
        # FIXME: MIME-type?


    def attachments():
        """
        List all attachments on this calendar object.

        @return: an iterable of L{IAttachment}s
        """


    def removeAttachmentWithName(name):
        """
        Delete an attachment with the given name.

        @param name: The basename of the attachment (i.e. the last segment of
            its URI) as given to L{attachmentWithName}.
        @type name: C{str}
        """


    def attendeesCanManageAttachments():
        """
        Are attendees allowed to manage attachments?

        @return: C{True} if they can, C{False} if they can't.
        """



class IAttachmentStorageTransport(ITransport):
    """
    An L{IAttachmentStorageTransport} is a transport which stores the bytes
    written to in a calendar attachment.

    The user of an L{IAttachmentStorageTransport} must call C{loseConnection} on
    its result to indicate that the attachment upload was successfully
    completed.  If the transaction associated with this upload is committed or
    aborted before C{loseConnection} is called, the upload will be presumed to
    have failed, and no attachment data will be stored.
    """

    # Note: should also require IConsumer

    def loseConnection():
        """
        The attachment has completed being uploaded successfully.

        Unlike L{ITransport.loseConnection}, which returns C{None}, providers of
        L{IAttachmentStorageTransport} must return a L{Deferred} from
        C{loseConnection}, which may fire with a few different types of error;
        for example, it may fail with a L{QuotaExceeded}.

        If the upload fails for some reason, the transaction should be
        terminated with L{ICalendarTransaction.abort} and this method should
        never be called.
        """



class IAttachment(IDataStoreObject):
    """
    Information associated with an attachment to a calendar object.
    """

    def store(contentType):
        """
        Store an attachment (of the given MIME content/type).

        @param contentType: The content type of the data which will be stored.

        @type contentType: L{twext.web2.http_headers.MimeType}

        @return: A transport which stores the contents written to it.

        @rtype: L{IAttachmentStorageTransport}
        """
        # If you do a big write()/loseConnection(), how do you tell when the
        # data has actually been written?  you don't: commit() ought to return
        # a deferred anyway, and any un-flushed attachment data needs to be
        # dealt with by that too.


    def retrieve(protocol):
        """
        Retrieve the content of this attachment into a protocol instance.

        @param protocol: A protocol which will receive the contents of the
            attachment to its C{dataReceived} method, and then a notification
            that the stream is complete to its C{connectionLost} method.
        @type protocol: L{IProtocol}
        """


