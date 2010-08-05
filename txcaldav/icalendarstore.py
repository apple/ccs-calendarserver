# -*- test-case-name: txcaldav.calendarstore -*-
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
Calendar store interfaces
"""

from txdav.common.icommondatastore import ICommonTransaction
from txdav.idav import IDataStoreResource

from zope.interface import Interface
from txdav.idav import INotifier


__all__ = [
    # Classes
    "ICalendarTransaction",
    "ICalendarHome",
    "ICalendar",
    "ICalendarObject",
]


# The following imports are used by the L{} links below, but shouldn't actually
# be imported.as they're not really needed.

# from datetime import datetime, date, tzinfo

# from twext.python.vcomponent import VComponent

# from txdav.idav import IPropertyStore
# from txdav.idav import ITransaction

class ICalendarTransaction(ICommonTransaction):
    """
    Transaction functionality required to be implemented by calendar stores.
    """

    def calendarHomeWithUID(uid, create=False):
        """
        Retrieve the calendar home for the principal with the given C{uid}.

        If C{create} is C{True}, create the calendar home if it doesn't
        already exist.

        @return: an L{ICalendarHome} or C{None} if no such calendar
            home exists.
        """


#
# Interfaces
#

class ICalendarHome(INotifier, IDataStoreResource):
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


class ICalendar(INotifier, IDataStoreResource):
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
        @return: an L{ICalendarObject} or C{None} if no such calendar
            object exists.
        """

    def createCalendarObjectWithName(name, component):
        """
        Create a calendar component with the given C{name} in this
        calendar from the given C{component}.

        @param name: a string.
        @param component: a C{VCALENDAR} L{Component}
        @raise CalendarObjectNameAlreadyExistsError: if a calendar
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

        @param start: a L{datetime} or L{date}.
        @param end: a L{datetime} or L{date}.
        @param timeZone: a L{tzinfo}.
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


class ICalendarObject(IDataStoreResource):
    """
    Calendar object

    A calendar object describes an event, to-do, or other iCalendar
    object.
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

        @return: a C{VCALENDAR} L{VComponent}.
        """

    def iCalendarText():
        """
        Retrieve the iCalendar text data for this calendar object.

        @return: a string containing iCalendar data for a single
            calendar object.
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


    def createAttachmentWithName(name, contentType):
        """
        Add an attachment to this calendar object.

        @param name: An identifier, unique to this L{ICalendarObject}, which
            names the attachment for future retrieval.

        @type name: C{str}

        @param contentType: a slash-separated content type.

        @type contentType: C{str}

        @return: the same type as L{IAttachment.store} returns.
        """


    def attachmentWithName(name):
        """
        Retrieve an attachment from this calendar object.

        @param name: An identifier, unique to this L{ICalendarObject}, which
            names the attachment for future retrieval.

        @type name: C{str}
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



class IAttachment(IDataStoreResource):
    """
    Information associated with an attachment to a calendar object.
    """

    def store(contentType):
        """
        @param contentType: The content type of the data which will be stored.
        @type contentType: C{str}

        @return: An L{ITransport}/L{IConsumer} provider that will store the
            bytes passed to its 'write' method.

            The caller of C{store} must call C{loseConnection} on its result to
            indicate that the attachment upload was successfully completed.  If
            the transaction associated with this upload is committed or aborted
            before C{loseConnection} is called, the upload will be presumed to
            have failed, and no attachment data will be stored.
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


