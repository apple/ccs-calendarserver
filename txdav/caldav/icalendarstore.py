# -*- test-case-name: txdav.caldav.datastore -*-
##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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
from twisted.python.constants import NamedConstant, Names

"""
Calendar store interfaces
"""

from txdav.common.icommondatastore import ICommonTransaction, \
    IShareableCollection, CommonStoreError
from txdav.idav import IDataStoreObject, IDataStore

from twisted.internet.interfaces import ITransport
from txdav.idav import INotifier

__all__ = [
    # Interfaces
    "ICalendarTransaction",
    "ICalendarStore",
    "ICalendarHome",
    "ICalendar",
    "ICalendarObject",
    "IAttachmentStorageTransport",
    "IAttachment",

    # Exceptions
   #"InvalidCalendarComponentError",
    "InvalidCalendarAccessError",
    "TooManyAttendeesError",
    "ResourceDeletedError",
    "ValidOrganizerError",
    "AttendeeAllowedError",
    "ShareeAllowedError",
    "InvalidPerUserDataMerge",
    "InvalidDefaultCalendar",
    "InvalidAttachmentOperation",
    "AttachmentStoreFailed",
    "AttachmentStoreValidManagedID",
    "AttachmentRemoveFailed",
    "AttachmentMigrationFailed",
    "AttachmentDropboxNotAllowed",
    "QuotaExceeded",
    "TimeRangeLowerLimit",
    "TimeRangeUpperLimit",
    "QueryMaxResources",
]



#
# Interfaces
#

class ICalendarTransaction(ICommonTransaction):
    """
    Transaction functionality required to be implemented by calendar stores.
    """

    def calendarHomeWithUID(uid, create=False): #@NoSelf
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

    def withEachCalendarHomeDo(action, batchSize=None): #@NoSelf
        """
        Execute a given action with each calendar home present in this store,
        in serial, committing after each batch of homes of a given size.

        @note: This does not execute an action with each directory principal
            for which there might be a calendar home; it works only on calendar
            homes which have already been provisioned.  To execute an action on
            every possible calendar user, you will need to inspect the
            directory API instead.

        @note: The list of calendar homes is loaded incrementally, so this will
            not necessarily present a consistent snapshot of the entire
            database at a particular moment.  (If this behavior is desired,
            pass a C{batchSize} greater than the number of homes in the
            database.)

        @param action: a 2-argument callable, taking an L{ICalendarTransaction}
            and an L{ICalendarHome}, and returning a L{Deferred} that fires
            with C{None} when complete.  Note that C{action} should not commit
            or abort the given L{ICalendarTransaction}.  If C{action} completes
            normally, then it will be called again with the next
            L{ICalendarHome}.  If it raises an exception or returns a
            L{Deferred} that fails, processing will stop and the L{Deferred}
            returned from C{withEachCalendarHomeDo} will fail with that same
            L{Failure}.
        @type action: L{callable}

        @param batchSize: The maximum count of calendar homes to include in a
            single transaction.
        @type batchSize: L{int}

        @return: a L{Deferred} which fires with L{None} when all homes have
            completed processing, or fails with the traceback.
        """



class ICalendarHome(INotifier, IDataStoreObject):
    """
    An L{ICalendarHome} is a collection of calendars which belongs to a
    specific principal and contains the calendars which that principal has
    direct access to.  This includes both calendars owned by the principal as
    well as calendars that have been shared with and accepts by the principal.
    """

    def uid(): #@NoSelf
        """
        Retrieve the unique identifier for this calendar home.

        @return: a string.
        """

    def calendars(): #@NoSelf
        """
        Retrieve calendars contained in this calendar home.

        @return: an iterable of L{ICalendar}s.
        """

    # FIXME: This is the same interface as calendars().
    def loadCalendars(): #@NoSelf
        """
        Pre-load all calendars Depth:1.

        @return: an iterable of L{ICalendar}s.
        """

    def calendarWithName(name): #@NoSelf
        """
        Retrieve the calendar with the given C{name} contained in this
        calendar home.

        @param name: a string.
        @return: an L{ICalendar} or C{None} if no such calendar
            exists.
        """

    def calendarObjectWithDropboxID(dropboxID): #@NoSelf
        """
        Retrieve an L{ICalendarObject} by looking up its attachment collection
        ID.

        @param dropboxID: The name of the collection in a dropbox corresponding
            to a collection in the user's dropbox.

        @type dropboxID: C{str}

        @return: the calendar object identified by the given dropbox.

        @rtype: L{ICalendarObject}
        """

    def createCalendarWithName(name): #@NoSelf
        """
        Create a calendar with the given C{name} in this calendar
        home.

        @param name: a string.
        @raise CalendarAlreadyExistsError: if a calendar with the
            given C{name} already exists.
        """

    def removeCalendarWithName(name): #@NoSelf
        """
        Remove the calendar with the given C{name} from this calendar
        home.  If this calendar home owns the calendar, also remove
        the calendar from all calendar homes.

        @param name: a string.
        @raise NoSuchCalendarObjectError: if no such calendar exists.

        @return: an L{IPropertyStore}.
        """

    def getAllDropboxIDs(): #@NoSelf
        """
        Retrieve all of the dropbox IDs of events in this home for calendar
        objects which either allow attendee write access to their dropboxes,
        have attachments to read, or both.

        @return: a L{Deferred} which fires with a C{list} of all dropbox IDs (as
            unicode strings)
        """

    def quotaAllowedBytes(): #@NoSelf
        """
        The number of bytes of data that the user is allowed to store in this
        calendar home.  If quota is not enforced for this calendar home, this
        will return C{None}.

        Currently this is only enforced against attachment data.

        @rtype: C{int} or C{NoneType}
        """

    def quotaUsedBytes(): #@NoSelf
        """
        The number of bytes counted towards the user's quota.

        Currently this is only tracked against attachment data.

        @rtype: C{int}
        """

    # FIXME: This should not be part of the interface.  The
    # implementation should deal with this behind the scenes.
    def adjustQuotaUsedBytes(delta): #@NoSelf
        """
        Increase or decrease the number of bytes that count towards the user's
        quota.

        @param delta: The number of bytes to adjust the quota by.

        @type delta: C{int}

        @raise QuotaExceeded: when the quota is exceeded.
        """

    def objectResourceWithID(rid): #@NoSelf
        """
        Return the calendar object resource with the specified ID, assumed to be a child of
        a calendar collection within this home.

        @param rid: resource id of object to find
        @type rid: C{int}

        @return: L{ICalendar} or C{None} if not found
        """



class ICalendar(INotifier, IShareableCollection, IDataStoreObject):
    """
    Calendar

    A calendar is a container for calendar objects (events, to-dos,
    etc.).  A calendar belongs to a specific principal but may be
    shared with other principals, granting them read-only or
    read/write access.
    """

    # FIXME: This should be setName(), and we should add name(),
    # assuming this shouldn't be API on the hom instead.
    def rename(name): #@NoSelf
        """
        Change the name of this calendar.
        """

    def displayName(): #@NoSelf
        """
        Get the display name of this calendar.

        @return: a unicode string.
        """

    def setDisplayName(name): #@NoSelf
        """
        Set the display name of this calendar.

        @param name: a C{unicode}.
        """

    def ownerCalendarHome(): #@NoSelf
        """
        Retrieve the calendar home for the owner of this calendar.  Calendars
        may be shared from one (the owner's) calendar home to other (the
        sharee's) calendar homes.

        FIXME: implementations of this method currently do not behave as
        documented; a sharee's home, rather than the owner's home, may be
        returned in some cases.  Current usages should likely be changed to use
        viewerCalendarHome() instead.

        @return: an L{ICalendarHome}.
        """

    def calendarObjects(): #@NoSelf
        """
        Retrieve the calendar objects contained in this calendar.

        @return: an iterable of L{ICalendarObject}s.
        """

    def calendarObjectWithName(name): #@NoSelf
        """
        Retrieve the calendar object with the given C{name} contained
        in this calendar.

        @param name: a string.
        @return: an L{ICalendarObject} or C{None} if no such calendar
            object exists.
        """

    def calendarObjectWithUID(uid): #@NoSelf
        """
        Retrieve the calendar object with the given C{uid} contained
        in this calendar.

        @param uid: a string.

        @return: a L{Deferred} firing an L{ICalendarObject} or C{None} if no
            such calendar object exists.
        """

    def createCalendarObjectWithName(name, component): #@NoSelf
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

    def syncToken(): #@NoSelf
        """
        Retrieve the current sync token for this calendar.

        @return: a string containing a sync token.
        """

    def calendarObjectsInTimeRange(start, end, timeZone): #@NoSelf
        """
        Retrieve all calendar objects in this calendar which have
        instances that occur within the time range that begins at
        C{start} and ends at C{end}.

        @param start: a L{DateTime}.
        @param end: a L{DateTime}.
        @param timeZone: a L{Timezone}.
        @return: an iterable of L{ICalendarObject}s.
        """

    def calendarObjectsSinceToken(token): #@NoSelf
        """
        Retrieve all calendar objects in this calendar that have
        changed since the given C{token} was last valid.

        @param token: a sync token.
        @return: a 3-tuple containing an iterable of
            L{ICalendarObject}s that have changed, an iterable of uids
            that have been removed, and the current sync token.
        """

    def resourceNamesSinceToken(revision): #@NoSelf
        """
        Low-level query to gather names for calendarObjectsSinceToken.
        """

    def sharingInvites(): #@NoSelf
        """
        Retrieve the list of all L{SharingInvitation} for this L{CommonHomeChild}, irrespective of mode.

        @return: L{SharingInvitation} objects
        @rtype: a L{Deferred} which fires with a L{list} of L{SharingInvitation}s.
        """

    # FIXME: This module should define it's own constants and this
    # method should return those.  Pulling constants from the SQL
    # implementation is not good.
    def shareMode(): #@NoSelf
        """
        The sharing mode of this calendar; one of the C{BIND_*} constants in
        this module.

        @see: L{ICalendar.viewerCalendarHome}
        """
        # TODO: implement this for the file store.

    # FIXME: This should be calendarHome(), assuming we want to allow
    # back-references.
    def viewerCalendarHome(): #@NoSelf
        """
        Retrieve the calendar home for the viewer of this calendar.  In other
        words, the calendar home that this L{ICalendar} was retrieved through.

        For example: if Alice shares her calendar with Bob,
        C{txn.calendarHomeWithUID("alice") ...
        .calendarWithName("calendar").viewerCalendarHome()} will return Alice's
        home, whereas C{txn.calendarHomeWithUID("bob") ...
        .childWithName("alice's calendar").viewerCalendarHome()} will
        return Bob's calendar home.

        @return: (synchronously) the calendar home of the user into which this
            L{ICalendar} is bound.
        @rtype: L{ICalendarHome}
        """
        # TODO: implement this for the file store.



class ICalendarObject(IDataStoreObject):
    """
    Calendar object

    A calendar object describes an event, to-do, or other iCalendar
    object.
    """

    def calendar(): #@NoSelf
        """
        @return: The calendar which this calendar object is a part of.
        @rtype: L{ICalendar}
        """

    def uid(): #@NoSelf
        """
        Retrieve the UID for this calendar object.

        @return: a string containing a UID.
        """

    def component(): #@NoSelf
        """
        Retrieve the calendar component for this calendar object.

        @raise ConcurrentModification: if this L{ICalendarObject} has been
            deleted and committed by another transaction between its creation
            and the first call to this method.

        @return: a C{VCALENDAR} L{VComponent}.
        """

    def setComponent(component): #@NoSelf
        """
        Rewrite this calendar object to match the given C{component}.
        C{component} must have the same UID and be of the same
        component type as this calendar object.

        @param component: a C{VCALENDAR} L{VComponent}.
        @raise InvalidCalendarComponentError: if the given
            C{component} is not a valid C{VCALENDAR} L{VComponent} for
            a calendar object.
        """

    def componentType(): #@NoSelf
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

    # FIXME: Ideally should return a URI object
    def organizer(): #@NoSelf
        """
        Retrieve the organizer's calendar user address for this
        calendar object.

        @return: a URI string.
        """

    #
    # New managed attachment APIs that supersede dropbox
    #

    def addAttachment(pathpattern, rids, content_type, filename, stream): #@NoSelf
        """
        Add a managed attachment to the calendar data.

        @param pathpattern: URI template for the attachment property value.
        @type pathpattern: C{str}
        @param rids: set of RECURRENCE-ID values (not adjusted for UTC or TZID offset) to add the
            new attachment to. The server must create necessary overrides if none already exist.
        @type rids: C{iterable}
        @param content_type: content-type information for the attachment data.
        @type content_type: L{MimeType}
        @param filename: display file name to use for the attachment.
        @type filename: C{str}
        @param stream: stream from which attachment data can be retrieved.
        @type stream: L{IStream}

        @raise: if anything goes wrong...
        """

    def updateAttachment(pathpattern, managed_id, content_type, filename, stream): #@NoSelf
        """
        Update an existing managed attachment in the calendar data.

        @param pathpattern: URI template for the attachment property value.
        @type pathpattern: C{str}
        @param managed_id: the identifier of the attachment to update.
        @type managed_id: C{str}
        @param content_type: content-type information for the attachment data.
        @type content_type: L{MimeType}
        @param filename: display file name to use for the attachment.
        @type filename: C{str}
        @param stream: stream from which attachment data can be retrieved.
        @type stream: L{IStream}

        @raise: if anything goes wrong...
        """

    def removeAttachment(rids, managed_id): #@NoSelf
        """
        Remove an existing managed attachment from the calendar data.

        @param rids: set of RECURRENCE-ID values (not adjusted for UTC or TZID offset) to remove the
            attachment from. The server must create necessary overrides if none already exist.
        @type rids: C{iterable}
        @param managed_id: the identifier of the attachment to remove.
        @type managed_id: C{str}

        @raise: if anything goes wrong...
        """
    #
    # The following APIs are for the older Dropbox protocol, which is now deprecated in favor of
    # managed attachments
    #

    def dropboxID(): #@NoSelf
        """
        An identifier, unique to the calendar home, that specifies a location
        where attachments are to be stored for this object.

        @return: the value of the last segment of the C{X-APPLE-DROPBOX}
            property.

        @rtype: C{string}
        """

    def createAttachmentWithName(name): #@NoSelf
        """
        Add an attachment to this calendar object.

        @param name: An identifier, unique to this L{ICalendarObject}, which
            names the attachment for future retrieval.

        @type name: C{str}

        @return: the L{IAttachment}.
        """

    def attachmentWithName(name): #@NoSelf
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

    def attachments(): #@NoSelf
        """
        List all attachments on this calendar object.

        @return: an iterable of L{IAttachment}s
        """

    def removeAttachmentWithName(name): #@NoSelf
        """
        Delete an attachment with the given name.

        @param name: The basename of the attachment (i.e. the last segment of
            its URI) as given to L{attachmentWithName}.
        @type name: C{str}
        """

    def attendeesCanManageAttachments(): #@NoSelf
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

    def loseConnection(): #@NoSelf
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

    def store(contentType): #@NoSelf
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

    def retrieve(protocol): #@NoSelf
        """
        Retrieve the content of this attachment into a protocol instance.

        @param protocol: A protocol which will receive the contents of the
            attachment to its C{dataReceived} method, and then a notification
            that the stream is complete to its C{connectionLost} method.
        @type protocol: L{IProtocol}
        """



#
# Exceptions
#

# FIXME: Clean these up:
# * Exception names should end in "Error"
# * Inherrit from common base class
# * Possible structure inherritance a bit
# * InvalidCalendarComponentError is AWOL

class InvalidComponentTypeError(CommonStoreError):
    """
    Invalid object resource component type for collection.
    """



class InvalidCalendarAccessError(CommonStoreError):
    """
    Invalid access mode in calendar data.
    """



class TooManyAttendeesError(CommonStoreError):
    """
    Too many attendees in calendar data.
    """



class ResourceDeletedError(CommonStoreError):
    """
    The resource was determined to be redundant and was deleted by the server.
    """



class ValidOrganizerError(CommonStoreError):
    """
    Specified organizer is not valid.
    """



class AttendeeAllowedError(CommonStoreError):
    """
    Attendee is not allowed to make an implicit scheduling change.
    """



class ShareeAllowedError(CommonStoreError):
    """
    Sharee is not allowed to make an implicit scheduling change.
    """



class DuplicatePrivateCommentsError(CommonStoreError):
    """
    Calendar data cannot contain duplicate private comment properties.
    """



class InvalidPerUserDataMerge(CommonStoreError):
    """
    Per-user data merge failed.
    """



class InvalidDefaultCalendar(CommonStoreError):
    """
    Setting a default calendar failed.
    """



class InvalidAttachmentOperation(Exception):
    """
    Unable to store an attachment because some aspect of the request is invalid.
    """



class AttachmentStoreFailed(Exception):
    """
    Unable to store an attachment.
    """



class AttachmentStoreValidManagedID(Exception):
    """
    Specified attachment managed-id is not valid.
    """

    def __str__(self):
        return "Invalid Managed-ID parameter in calendar data"



class AttachmentRemoveFailed(Exception):
    """
    Unable to remove an attachment.
    """



class AttachmentMigrationFailed(Exception):
    """
    Unable to migrate an attachment.
    """



class AttachmentDropboxNotAllowed(Exception):
    """
    Dropbox attachments no longer allowed.
    """



class QuotaExceeded(Exception):
    """
    The quota for a particular user has been exceeded.
    """



class TimeRangeLowerLimit(Exception):
    """
    A request for time-range information too far in the past cannot be satisfied.
    """

    def __init__(self, lowerLimit):
        self.limit = lowerLimit



class TimeRangeUpperLimit(Exception):
    """
    A request for time-range information too far in the future cannot be satisfied.
    """

    def __init__(self, upperLimit):
        self.limit = upperLimit



class QueryMaxResources(CommonStoreError):
    """
    A query-based request for resources returned more resources than the server is willing to deal with in one go.
    """

    def __init__(self, limit, actual):
        super(QueryMaxResources, self).__init__("Query result count limit (%s) exceeded: %s" % (limit, actual,))



#
# FIXME: These may belong elsewhere.
#

class ComponentUpdateState(Names):
    """
    These are constants that define what type of component store operation is being done. This is used
    in the .setComponent() api to determine what type of processing needs to occur.

    NORMAL -                this is an application layer (user) generated store that should do all
                            validation and implicit scheduling operations.

    INBOX  -                the store is updating an inbox item as the result of an iTIP message.

    ORGANIZER_ITIP_UPDATE - the store is an update to an organizer's data caused by processing an incoming
                            iTIP message. Some validation and implicit scheduling is not done. Schedule-Tag
                            is not changed.

    ATTENDEE_ITIP_UPDATE  - the store is an update to an attendee's data caused by processing an incoming
                            iTIP message. Some validation and implicit scheduling is not done. Schedule-Tag
                            is changed.

    ATTACHMENT_UPDATE     - change to a managed attachment that is re-writing calendar data.

    SPLIT_OWNER           - owner calendar data is being split. Implicit is done with non-hosted attendees.

    SPLIT_ATTENDEE        - attendee calendar data is being split. No implicit done, but some extra processing
                            is done (more than RAW).

    RAW                   - store the supplied data as-is without any processing or validation. This is used
                            for unit testing purposes only.
    """

    NORMAL = NamedConstant()
    INBOX = NamedConstant()
    ORGANIZER_ITIP_UPDATE = NamedConstant()
    ATTENDEE_ITIP_UPDATE = NamedConstant()
    ATTACHMENT_UPDATE = NamedConstant()
    SPLIT_OWNER = NamedConstant()
    SPLIT_ATTENDEE = NamedConstant()
    RAW = NamedConstant()

    NORMAL.description = "normal"
    INBOX.description = "inbox"
    ORGANIZER_ITIP_UPDATE.description = "organizer-update"
    ATTENDEE_ITIP_UPDATE.description = "attendee-update"
    ATTACHMENT_UPDATE.description = "attachment-update"
    SPLIT_OWNER.description = "split-owner"
    SPLIT_ATTENDEE.description = "split-attendee"
    RAW.description = "raw"



class ComponentRemoveState(Names):
    """
    These are constants that define what type of component remove operation is being done. This is used
    in the .remove() api to determine what type of processing needs to occur.

    NORMAL -                this is an application layer (user) generated remove that should do all
                            implicit scheduling operations.

    NORMAL_NO_IMPLICIT -    this is an application layer (user) generated remove that deliberately turns
                            off implicit scheduling operations.

    INTERNAL -              remove the resource without implicit scheduling.
    """

    NORMAL = NamedConstant()
    NORMAL_NO_IMPLICIT = NamedConstant()
    INTERNAL = NamedConstant()

    NORMAL.description = "normal"
    NORMAL_NO_IMPLICIT.description = "normal-no-implicit"
    INTERNAL.description = "internal"
