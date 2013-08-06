#
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

from pycalendar.datetime import PyCalendarDateTime
from pycalendar.duration import PyCalendarDuration
from pycalendar.timezone import PyCalendarTimezone

from twext.python.log import Logger
from twext.web2.dav.method.report import NumberOfMatchesWithinLimits
from twext.web2.http import HTTPError

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from twistedcaldav import customxml, caldavxml
from twistedcaldav.config import config
from twistedcaldav.ical import Property
from twistedcaldav.instance import InvalidOverriddenInstanceError
from twistedcaldav.memcachelock import MemcacheLock, MemcacheLockTimeoutError
from twistedcaldav.memcacher import Memcacher

from txdav.caldav.datastore.scheduling.cuaddress import normalizeCUAddr
from txdav.caldav.datastore.scheduling.itip import iTipProcessing, iTIPRequestStatus
from txdav.caldav.datastore.scheduling.utils import getCalendarObjectForRecord

import collections
import hashlib
import uuid
from txdav.caldav.icalendarstore import ComponentUpdateState, \
    ComponentRemoveState
from twext.enterprise.locking import NamedLock
from txdav.caldav.datastore.scheduling.freebusy import generateFreeBusyInfo

"""
CalDAV implicit processing.

This module handles the processing of scheduling messages being delivered to a calendar user's inbox.
It determines who is scheduling (organizer or attendee) and applies the scheduling message changes
to the recipient's calendar data as well as depositing the scheduling message in the inbox. For users
who have an auto-accept option on, it will also handle the automatic response. Also, refreshes of other
attendees (when one attendee replies) are triggered from here.
"""

__all__ = [
    "ImplicitProcessor",
    "ImplicitProcessorException",
]

log = Logger()

class ImplicitProcessorException(Exception):

    def __init__(self, msg):
        self.msg = msg



class ImplicitProcessor(object):

    def __init__(self):
        pass


    @inlineCallbacks
    def doImplicitProcessing(self, txn, message, originator, recipient, noAttendeeRefresh=False):
        """
        Do implicit processing of a scheduling message, and possibly also auto-process it
        if the recipient has auto-accept on.

        @param message:
        @type message:
        @param originator:
        @type originator:
        @param recipient:
        @type recipient:

        @return: a C{tuple} of (C{bool}, C{bool}) indicating whether the message was processed, and if it was whether
            auto-processing has taken place.
        """

        self.txn = txn
        self.message = message
        self.originator = originator
        self.recipient = recipient
        self.noAttendeeRefresh = noAttendeeRefresh

        # TODO: for now going to assume that the originator is local - i.e. the scheduling message sent
        # represents the actual organizer's view.

        # First see whether this is the organizer or attendee sending the message
        self.extractCalendarData()

        if self.isOrganizerReceivingMessage():
            result = (yield self.doImplicitOrganizer())
        elif self.isAttendeeReceivingMessage():
            try:
                result = (yield self.doImplicitAttendee())
            except ImplicitProcessorException:
                # These we always pass up
                raise
            except Exception, e:
                # We attempt to recover from this. That involves trying to re-write the attendee data
                # to match that of the organizer assuming we have the organizer's full data available, then
                # we try the processing operation again.
                log.failure("{processor}.doImplicitAttendee()", processor=self)
                log.error("ImplicitProcessing - originator '%s' to recipient '%s' with UID: '%s' - exception raised will try to fix: %s" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid, e))
                result = (yield self.doImplicitAttendeeEventFix(e))
                if result:
                    log.error("ImplicitProcessing - originator '%s' to recipient '%s' with UID: '%s' - restored organizer's copy" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                    try:
                        result = (yield self.doImplicitAttendee())
                    except Exception, e:
                        log.failure("{processor}.doImplicitAttendee()", processor=self)
                        log.error("ImplicitProcessing - originator '%s' to recipient '%s' with UID: '%s' - exception raised after fix: %s" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid, e))
                        raise ImplicitProcessorException("5.1;Service unavailable")
                else:
                    log.error("ImplicitProcessing - originator '%s' to recipient '%s' with UID: '%s' - could not fix" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                    raise ImplicitProcessorException("5.1;Service unavailable")
        else:
            log.error("METHOD:%s not supported for implicit scheduling." % (self.method,))
            raise ImplicitProcessorException("3.14;Unsupported capability")

        returnValue(result)


    def extractCalendarData(self):

        # Some other useful things
        self.method = self.message.propertyValue("METHOD")
        self.uid = self.message.resourceUID()


    def isOrganizerReceivingMessage(self):
        return self.method in ("REPLY", "REFRESH")


    def isAttendeeReceivingMessage(self):
        return self.method in ("REQUEST", "ADD", "CANCEL")


    @inlineCallbacks
    def getRecipientsCopy(self):
        """
        Get the Recipient's copy of the event being processed.
        """

        self.recipient_calendar = None
        self.recipient_calendar_resource = None
        calendar_resource = (yield getCalendarObjectForRecord(self.txn, self.recipient.principal, self.uid))
        if calendar_resource:
            self.recipient_calendar = (yield calendar_resource.componentForUser(self.recipient.principal.uid))
            self.recipient_calendar_resource = calendar_resource


    @inlineCallbacks
    def doImplicitOrganizer(self):

        # Locate the organizer's copy of the event.
        yield self.getRecipientsCopy()
        if self.recipient_calendar is None:
            log.debug("ImplicitProcessing - originator '%s' to recipient '%s' ignoring UID: '%s' - organizer has no copy" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
            returnValue((True, True, False, None,))

        # Handle new items differently than existing ones.
        if self.method == "REPLY":
            result = (yield self.doImplicitOrganizerUpdate())
        elif self.method == "REFRESH":
            # With implicit we ignore refreshes.
            # TODO: for iMIP etc we do need to handle them
            result = (True, True, False, None,)

        returnValue(result)


    @inlineCallbacks
    def doImplicitOrganizerUpdate(self):

        # Check to see if this is a valid reply
        result, processed = iTipProcessing.processReply(self.message, self.recipient_calendar)
        if result:

            # Let the store know that no time-range info has changed
            self.recipient_calendar.noInstanceIndexing = True

            # Update the organizer's copy of the event
            log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:REPLY, UID: '%s' - updating event" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
            self.organizer_calendar_resource = (yield self.writeCalendarResource(None, self.recipient_calendar_resource, self.recipient_calendar))
            self.organizer_uid = self.organizer_calendar_resource.parentCollection().ownerHome().uid()
            self.organizer_calendar_resource_id = self.organizer_calendar_resource.id()

            organizer = self.recipient_calendar.getOrganizer()

            # Build the schedule-changes XML element
            attendeeReplying, rids = processed
            partstatChanged = False
            reply_details = (customxml.Attendee.fromString(attendeeReplying),)

            for rid, partstatChanged, privateCommentChanged in sorted(rids):
                recurrence = []
                if rid == "":
                    recurrence.append(customxml.Master())
                else:
                    recurrence.append(customxml.RecurrenceID.fromString(rid))
                changes = []
                if partstatChanged:
                    changes.append(customxml.ChangedProperty(customxml.ChangedParameter(name="PARTSTAT"), name="ATTENDEE"))
                    partstatChanged = True
                if privateCommentChanged:
                    changes.append(customxml.ChangedProperty(name="X-CALENDARSERVER-PRIVATE-COMMENT"))
                recurrence.append(customxml.Changes(*changes))
                reply_details += (customxml.Recurrence(*recurrence),)

            changes = customxml.ScheduleChanges(
                customxml.DTStamp(),
                customxml.Action(
                    customxml.Reply(*reply_details),
                ),
            )

            # Only update other attendees when the partstat was changed by the reply,
            # and only if the request does not indicate we should skip attendee refresh
            # (e.g. inbox item processing during migration from non-implicit server)
            if partstatChanged and not self.noAttendeeRefresh:
                # Check limit of attendees
                if config.Scheduling.Options.AttendeeRefreshCountLimit == 0 or len(self.recipient_calendar.getAllUniqueAttendees()) <= config.Scheduling.Options.AttendeeRefreshCountLimit:
                    yield self.queueAttendeeUpdate((attendeeReplying, organizer,))

            result = (True, False, True, changes,)

        else:
            # Ignore scheduling message
            result = (True, True, False, None,)

        returnValue(result)


    @inlineCallbacks
    def queueAttendeeUpdate(self, exclude_attendees):
        """
        Queue up an update to attendees and use a memcache lock to ensure we don't update too frequently.

        @param exclude_attendees: list of attendees who should not be refreshed (e.g., the one that triggered the refresh)
        @type exclude_attendees: C{list}
        """

        # When doing auto-processing of replies, only refresh attendees when the last auto-accept is done.
        # Note that when we do this we also need to refresh the attendee that is generating the reply because they
        # are no longer up to date with changes of other auto-accept attendees. See docstr for sendAttendeeAutoReply
        # below for more details of what is going on here.
        if getattr(self.txn, "auto_reply_processing_count", 0) > 1:
            log.debug("ImplicitProcessing - refreshing UID: '%s', Suppressed: %s" % (self.uid, self.txn.auto_reply_processing_count,))
            self.txn.auto_reply_suppressed = True
            returnValue(None)
        if getattr(self.txn, "auto_reply_suppressed", False):
            log.debug("ImplicitProcessing - refreshing UID: '%s', Suppression lifted" % (self.uid,))
            exclude_attendees = ()

        self.uid = self.recipient_calendar.resourceUID()

        # Check for batched refreshes
        if config.Scheduling.Options.AttendeeRefreshBatch:

            # Need to lock whilst manipulating the batch list
            lock = MemcacheLock(
                "BatchRefreshUIDLock",
                self.uid,
                timeout=config.Scheduling.Options.UIDLockTimeoutSeconds,
                expire_time=config.Scheduling.Options.UIDLockExpirySeconds,
            )
            try:
                yield lock.acquire()
            except MemcacheLockTimeoutError:
                # If we could not lock then just fail the refresh - not sure what else to do
                returnValue(None)

            try:
                # Get all attendees to refresh
                allAttendees = sorted(list(self.recipient_calendar.getAllUniqueAttendees()))
                allAttendees = filter(lambda x: x not in exclude_attendees, allAttendees)

                if allAttendees:
                    # See if there is already a pending refresh and merge current attendees into that list,
                    # otherwise just mark all attendees as pending
                    cache = Memcacher("BatchRefreshAttendees", pickle=True)
                    pendingAttendees = yield cache.get(self.uid)
                    firstTime = False
                    if pendingAttendees:
                        for attendee in allAttendees:
                            if attendee not in pendingAttendees:
                                pendingAttendees.append(attendee)
                    else:
                        firstTime = True
                        pendingAttendees = allAttendees
                    yield cache.set(self.uid, pendingAttendees)

                    # Now start the first batch off
                    if firstTime:
                        self._enqueueBatchRefresh()
            finally:
                yield lock.clean()

        else:
            yield self._doRefresh(self.organizer_calendar_resource, exclude_attendees)


    @inlineCallbacks
    def _doRefresh(self, organizer_resource, exclude_attendees=(), only_attendees=None):
        """
        Do a refresh of attendees.

        @param organizer_resource: the resource for the organizer's calendar data
        @type organizer_resource: L{DAVResource}
        @param exclude_attendees: list of attendees to not refresh
        @type exclude_attendees: C{tuple}
        @param only_attendees: list of attendees to refresh (C{None} - refresh all)
        @type only_attendees: C{tuple}
        """
        log.debug("ImplicitProcessing - refreshing UID: '%s', Attendees: %s" % (self.uid, ", ".join(only_attendees) if only_attendees else "all"))
        from txdav.caldav.datastore.scheduling.implicit import ImplicitScheduler
        scheduler = ImplicitScheduler()
        yield scheduler.refreshAllAttendeesExceptSome(
            self.txn,
            organizer_resource,
            exclude_attendees,
            only_attendees=only_attendees,
        )


    @inlineCallbacks
    def _doDelayedRefresh(self, attendeesToProcess):
        """
        Do an attendee refresh that has been delayed until after processing of the request that called it. That
        requires that we create a new transaction to work with.

        @param attendeesToProcess: list of attendees to refresh.
        @type attendeesToProcess: C{list}
        """

        # The original transaction is still around but likely committed at this point, so we need a brand new
        # transaction to do this work.
        txn = yield self.txn.store().newTransaction("Delayed attendee refresh for UID: %s" % (self.uid,))

        try:
            # We need to get the UID lock for implicit processing whilst we send the auto-reply
            # as the Organizer processing will attempt to write out data to other attendees to
            # refresh them. To prevent a race we need a lock.
            yield NamedLock.acquire(txn, "ImplicitUIDLock:%s" % (hashlib.md5(self.uid).hexdigest(),))

            organizer_home = (yield txn.calendarHomeForUID(self.organizer_uid))
            organizer_resource = (yield organizer_home.objectResourceWithID(self.organizer_calendar_resource_id))
            if organizer_resource is not None:
                yield self._doRefresh(organizer_resource, only_attendees=attendeesToProcess)
            else:
                log.debug("ImplicitProcessing - skipping refresh of missing UID: '%s'" % (self.uid,))
        except Exception, e:
            log.debug("ImplicitProcessing - refresh exception UID: '%s', %s" % (self.uid, str(e)))
            yield txn.abort()
        except:
            log.debug("ImplicitProcessing - refresh bare exception UID: '%s'" % (self.uid,))
            yield txn.abort()
        else:
            yield txn.commit()


    def _enqueueBatchRefresh(self):
        """
        Mostly here to help unit test by being able to stub this out.
        """
        reactor.callLater(config.Scheduling.Options.AttendeeRefreshBatchDelaySeconds, self._doBatchRefresh)


    @inlineCallbacks
    def _doBatchRefresh(self):
        """
        Do refresh of attendees in batches until the batch list is empty.
        """

        # Need to lock whilst manipulating the batch list
        log.debug("ImplicitProcessing - batch refresh for UID: '%s'" % (self.uid,))
        lock = MemcacheLock(
            "BatchRefreshUIDLock",
            self.uid,
            timeout=config.Scheduling.Options.UIDLockTimeoutSeconds,
            expire_time=config.Scheduling.Options.UIDLockExpirySeconds,
        )
        try:
            yield lock.acquire()
        except MemcacheLockTimeoutError:
            # If we could not lock then just fail the refresh - not sure what else to do
            returnValue(None)

        try:
            # Get the batch list
            cache = Memcacher("BatchRefreshAttendees", pickle=True)
            pendingAttendees = yield cache.get(self.uid)
            if pendingAttendees:

                # Get the next batch of attendees to process and update the cache value or remove it if
                # no more processing is needed
                attendeesToProcess = pendingAttendees[:config.Scheduling.Options.AttendeeRefreshBatch]
                pendingAttendees = pendingAttendees[config.Scheduling.Options.AttendeeRefreshBatch:]
                if pendingAttendees:
                    yield cache.set(self.uid, pendingAttendees)
                else:
                    yield cache.delete(self.uid)

                # Make sure we release this here to avoid potential deadlock when grabbing the ImplicitUIDLock in the next call
                yield lock.release()

                # Now do the batch refresh
                yield self._doDelayedRefresh(attendeesToProcess)

                # Queue the next refresh if needed
                if pendingAttendees:
                    self._enqueueBatchRefresh()
            else:
                yield cache.delete(self.uid)
                yield lock.release()
        finally:
            yield lock.clean()


    @inlineCallbacks
    def doImplicitAttendee(self):

        # Locate the attendee's copy of the event if it exists.
        yield self.getRecipientsCopy()
        self.new_resource = self.recipient_calendar is None

        # Handle new items differently than existing ones.
        if self.new_resource and self.method == "CANCEL":
            result = (True, True, False, None)
        else:
            result = (yield self.doImplicitAttendeeUpdate())

        returnValue(result)


    @inlineCallbacks
    def doImplicitAttendeeUpdate(self):

        # Do security check: ORGANZIER in iTIP MUST match existing resource value
        if self.recipient_calendar:
            existing_organizer = self.recipient_calendar.getOrganizer()
            existing_organizer = normalizeCUAddr(existing_organizer) if existing_organizer else ""
            new_organizer = normalizeCUAddr(self.message.getOrganizer())
            new_organizer = normalizeCUAddr(new_organizer) if new_organizer else ""
            if existing_organizer != new_organizer:
                log.debug("ImplicitProcessing - originator '%s' to recipient '%s' ignoring UID: '%s' - organizer has no copy" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                raise ImplicitProcessorException("5.3;Organizer change not allowed")

        # Handle splitting of data early so we can preserve per-attendee data
        if self.message.hasProperty("X-CALENDARSERVER-SPLIT-OLDER-UID"):
            if config.Scheduling.Options.Splitting.Enabled:
                # Tell the existing resource to split
                log.debug("ImplicitProcessing - originator '%s' to recipient '%s' splitting UID: '%s'" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                split = (yield self.doImplicitAttendeeSplit())
                if split:
                    returnValue((True, False, False, None,))
            else:
                self.message.removeProperty("X-CALENDARSERVER-SPLIT-OLDER-UID")
                self.message.removeProperty("X-CALENDARSERVER-SPLIT-RID")

        elif self.message.hasProperty("X-CALENDARSERVER-SPLIT-NEWER-UID"):
            if config.Scheduling.Options.Splitting.Enabled:
                log.debug("ImplicitProcessing - originator '%s' to recipient '%s' ignoring UID: '%s' - split already done" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                returnValue((True, False, False, None,))
            else:
                self.message.removeProperty("X-CALENDARSERVER-SPLIT-OLDER-UID")
                self.message.removeProperty("X-CALENDARSERVER-SPLIT-RID")

        # Different based on method
        if self.method == "REQUEST":
            result = (yield self.doImplicitAttendeeRequest())
        elif self.method == "CANCEL":
            result = (yield self.doImplicitAttendeeCancel())
        elif self.method == "ADD":
            # TODO: implement ADD
            result = (False, False, False, None)
        else:
            # NB We should never get here as we will have rejected unsupported METHODs earlier.
            result = (True, True, False, None,)

        returnValue(result)


    @inlineCallbacks
    def doImplicitAttendeeSplit(self):
        """
        Handle splitting of the existing calendar data.
        """
        olderUID = self.message.propertyValue("X-CALENDARSERVER-SPLIT-OLDER-UID")
        split_rid = self.message.propertyValue("X-CALENDARSERVER-SPLIT-RID")
        if olderUID is None or split_rid is None:
            returnValue(False)

        # Split the resource
        yield self.recipient_calendar_resource.splitForAttendee(rid=split_rid, olderUID=olderUID)

        returnValue(True)


    @inlineCallbacks
    def doImplicitAttendeeRequest(self):
        """
        @return: C{tuple} of (processed, auto-processed, store inbox item, changes)
        """

        # If there is no existing copy, then look for default calendar and copy it here
        if self.new_resource:

            # Check if the incoming data has the recipient declined in all instances. In that case we will not create
            # a new resource as chances are the recipient previously deleted the resource and we want to keep it deleted.
            attendees = self.message.getAttendeeProperties((self.recipient.cuaddr,))
            if all([attendee.parameterValue("PARTSTAT", "NEEDS-ACTION") == "DECLINED" for attendee in attendees]):
                log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:REQUEST, UID: '%s' - ignoring all declined" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                returnValue((True, False, False, None,))

            # Check for default calendar
            default = (yield self.recipient.inbox.viewerHome().defaultCalendar(self.message.mainType()))
            if default is None:
                log.error("No default calendar for recipient: '%s'." % (self.recipient.cuaddr,))
                raise ImplicitProcessorException(iTIPRequestStatus.NO_USER_SUPPORT)

            log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:REQUEST, UID: '%s' - new processed" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
            new_calendar = iTipProcessing.processNewRequest(self.message, self.recipient.cuaddr, creating=True)

            # Handle auto-reply behavior
            organizer = normalizeCUAddr(self.message.getOrganizer())
            if self.recipient.principal.canAutoSchedule(organizer=organizer):
                # auto schedule mode can depend on who the organizer is
                mode = self.recipient.principal.getAutoScheduleMode(organizer=organizer)
                send_reply, store_inbox, partstat = (yield self.checkAttendeeAutoReply(new_calendar, mode))

                # Only store inbox item when reply is not sent or always for users
                store_inbox = store_inbox or self.recipient.principal.getCUType() == "INDIVIDUAL"
            else:
                send_reply = False
                store_inbox = True

            new_resource = (yield self.writeCalendarResource(default, None, new_calendar))

            if send_reply:
                # Track outstanding auto-reply processing
                self.txn.auto_reply_processing_count = getattr(self.txn, "auto_reply_processing_count", 0) + 1
                log.debug("ImplicitProcessing - recipient '%s' processing UID: '%s' - auto-reply queued: %s" % (self.recipient.cuaddr, self.uid, self.txn.auto_reply_processing_count,))
                reactor.callLater(2.0, self.sendAttendeeAutoReply, *(new_calendar, new_resource, partstat))

            # Build the schedule-changes XML element
            changes = customxml.ScheduleChanges(
                customxml.DTStamp(),
                customxml.Action(
                    customxml.Create(),
                ),
            )
            result = (True, send_reply, store_inbox, changes,)
        else:
            # Processing update to existing event
            new_calendar, rids = iTipProcessing.processRequest(self.message, self.recipient_calendar, self.recipient.cuaddr)
            if new_calendar:

                # Handle auto-reply behavior
                organizer = normalizeCUAddr(self.message.getOrganizer())
                if self.recipient.principal.canAutoSchedule(organizer=organizer) and not hasattr(self.txn, "doing_attendee_refresh"):
                    # auto schedule mode can depend on who the organizer is
                    mode = self.recipient.principal.getAutoScheduleMode(organizer=organizer)
                    send_reply, store_inbox, partstat = (yield self.checkAttendeeAutoReply(new_calendar, mode))

                    # Only store inbox item when reply is not sent or always for users
                    store_inbox = store_inbox or self.recipient.principal.getCUType() == "INDIVIDUAL"
                else:
                    send_reply = False
                    store_inbox = True

                # Let the store know that no time-range info has changed for a refresh (assuming that
                # no auto-accept changes were made)
                if hasattr(self.txn, "doing_attendee_refresh"):
                    new_calendar.noInstanceIndexing = not send_reply

                # Update the attendee's copy of the event
                log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:REQUEST, UID: '%s' - updating event" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                new_resource = (yield self.writeCalendarResource(None, self.recipient_calendar_resource, new_calendar))

                if send_reply:
                    # Track outstanding auto-reply processing
                    self.txn.auto_reply_processing_count = getattr(self.txn, "auto_reply_processing_count", 0) + 1
                    log.debug("ImplicitProcessing - recipient '%s' processing UID: '%s' - auto-reply queued: %s" % (self.recipient.cuaddr, self.uid, self.txn.auto_reply_processing_count,))
                    reactor.callLater(2.0, self.sendAttendeeAutoReply, *(new_calendar, new_resource, partstat))

                # Build the schedule-changes XML element
                update_details = []
                for rid, props_changed in sorted(rids.iteritems(), key=lambda x: x[0]):
                    recurrence = []
                    if rid == "":
                        recurrence.append(customxml.Master())
                    else:
                        recurrence.append(customxml.RecurrenceID.fromString(rid))
                    changes = []
                    for propName, paramNames in sorted(props_changed.iteritems(), key=lambda x: x[0]):
                        params = tuple([customxml.ChangedParameter(name=param) for param in paramNames])
                        changes.append(customxml.ChangedProperty(*params, **{"name": propName}))
                    recurrence.append(customxml.Changes(*changes))
                    update_details += (customxml.Recurrence(*recurrence),)

                changes = customxml.ScheduleChanges(
                    customxml.DTStamp(),
                    customxml.Action(
                        customxml.Update(*update_details),
                    ),
                )

                # Refresh from another Attendee should not have Inbox item
                if hasattr(self.txn, "doing_attendee_refresh"):
                    store_inbox = False

                result = (True, send_reply, store_inbox, changes,)

            else:
                # Request needs to be ignored
                log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:REQUEST, UID: '%s' - ignoring" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                result = (True, True, False, None,)

        returnValue(result)


    @inlineCallbacks
    def doImplicitAttendeeCancel(self):

        # If there is no existing copy, then ignore
        if self.recipient_calendar is None:
            log.debug("ImplicitProcessing - originator '%s' to recipient '%s' ignoring METHOD:CANCEL, UID: '%s' - attendee has no copy" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
            result = (True, True, None)
        else:
            # Need to check for auto-respond attendees. These need to suppress the inbox message
            # if the cancel is processed. However, if the principal is a user we always force the
            # inbox item on them even if auto-schedule is true so that they get a notification
            # of the cancel.
            organizer = normalizeCUAddr(self.message.getOrganizer())
            autoprocessed = self.recipient.principal.canAutoSchedule(organizer=organizer)
            store_inbox = not autoprocessed or self.recipient.principal.getCUType() == "INDIVIDUAL"

            # Check to see if this is a cancel of the entire event
            processed_message, delete_original, rids = iTipProcessing.processCancel(self.message, self.recipient_calendar, autoprocessing=autoprocessed)
            if processed_message:
                if delete_original:

                    # Delete the attendee's copy of the event
                    log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:CANCEL, UID: '%s' - deleting entire event" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                    yield self.deleteCalendarResource(self.recipient_calendar_resource)

                    # Build the schedule-changes XML element
                    changes = customxml.ScheduleChanges(
                        customxml.DTStamp(),
                        customxml.Action(
                            customxml.Cancel(),
                        ),
                    )
                    result = (True, autoprocessed, store_inbox, changes,)

                else:

                    # Update the attendee's copy of the event
                    log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:CANCEL, UID: '%s' - updating event" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                    yield self.writeCalendarResource(None, self.recipient_calendar_resource, self.recipient_calendar)

                    # Build the schedule-changes XML element
                    if rids:
                        action = customxml.Cancel(
                            *[customxml.Recurrence(customxml.RecurrenceID.fromString(rid)) for rid in sorted(rids)]
                        )
                    else:
                        action = customxml.Cancel()
                    changes = customxml.ScheduleChanges(
                        customxml.DTStamp(),
                        customxml.Action(action),
                    )
                    result = (True, autoprocessed, store_inbox, changes)
            else:
                log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:CANCEL, UID: '%s' - ignoring" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                result = (True, True, False, None)

        returnValue(result)


    @inlineCallbacks
    def sendAttendeeAutoReply(self, calendar, resource, partstat):
        """
        Auto-process the calendar option to generate automatic accept/decline status and
        send a reply if needed.

        There is some tricky behavior here: when multiple auto-accept attendees are present in a
        calendar object, we want to suppress the processing of other attendee refreshes until all
        auto-accepts have replied, to avoid a flood of refreshes. We do that by tracking the pending
        auto-replies via a "auto_reply_processing_count" attribute on the original txn objection (even
        though that has been committed). We also use a "auto_reply_suppressed" attribute on that txn
        to indicate when suppression has occurred, to ensure that when the refresh is finally sent, we
        send it to everyone to make sure all are in sync. In order for the actual refreshes to be
        suppressed we have to "transfer" those two attributes from the original txn to the new one
        used to send the reply. Then we transfer "auto_reply_suppressed" back when done, and decrement
        "auto_reply_processing_count" (all done under a UID lock to prevent race conditions).

        @param calendar: calendar data to examine
        @type calendar: L{Component}

        @return: L{Component} for the new calendar data to write
        """

        # The original transaction is still around but likely committed at this point, so we need a brand new
        # transaction to do this work.
        txn = yield self.txn.store().newTransaction("Attendee (%s) auto-reply for UID: %s" % (self.recipient.cuaddr, self.uid,))

        aborted = False
        try:
            # We need to get the UID lock for implicit processing whilst we send the auto-reply
            # as the Organizer processing will attempt to write out data to other attendees to
            # refresh them. To prevent a race we need a lock.
            yield NamedLock.acquire(txn, "ImplicitUIDLock:%s" % (hashlib.md5(calendar.resourceUID()).hexdigest(),))

            # Must be done after acquiring the lock to avoid a race-condition
            txn.auto_reply_processing_count = getattr(self.txn, "auto_reply_processing_count", 0)
            txn.auto_reply_suppressed = getattr(self.txn, "auto_reply_suppressed", False)

            # Send out a reply
            log.debug("ImplicitProcessing - recipient '%s' processing UID: '%s' - auto-reply: %s" % (self.recipient.cuaddr, self.uid, partstat))
            from txdav.caldav.datastore.scheduling.implicit import ImplicitScheduler
            scheduler = ImplicitScheduler()
            yield scheduler.sendAttendeeReply(txn, resource, calendar, self.recipient)
        except Exception, e:
            log.debug("ImplicitProcessing - auto-reply exception UID: '%s', %s" % (self.uid, str(e)))
            aborted = True
        except:
            log.debug("ImplicitProcessing - auto-reply bare exception UID: '%s'" % (self.uid,))
            aborted = True

        # Track outstanding auto-reply processing - must be done before commit/abort which releases the lock
        self.txn.auto_reply_processing_count = getattr(self.txn, "auto_reply_processing_count", 0) - 1
        self.txn.auto_reply_suppressed = txn.auto_reply_suppressed

        if aborted:
            yield txn.abort()
        else:
            yield txn.commit()


    @inlineCallbacks
    def checkAttendeeAutoReply(self, calendar, automode):
        """
        Check whether a reply to the given iTIP message is needed and if so make the
        appropriate changes to the calendar data. Changes are only made for the case
        where the PARTSTAT of the attendee is NEEDS-ACTION - i.e., any existing state
        is left unchanged. This allows, e.g., proxies to decline events that would
        otherwise have been auto-accepted and those stay declined as non-schedule-change
        updates are received.

        @param calendar: the iTIP message to process
        @type calendar: L{Component}
        @param automode: the auto-schedule mode for the recipient
        @type automode: C{str}

        @return: C{tuple} of C{bool}, C{bool}, C{str} indicating whether changes were made, whether the inbox item
            should be added, and the new PARTSTAT.
        """

        # First ignore the none mode
        if automode == "none":
            returnValue((False, True, "",))
        elif not automode or automode == "default":
            automode = config.Scheduling.Options.AutoSchedule.DefaultMode

        log.debug("ImplicitProcessing - recipient '%s' processing UID: '%s' - checking for auto-reply with mode: %s" % (self.recipient.cuaddr, self.uid, automode,))

        cuas = self.recipient.principal.calendarUserAddresses

        # First expand current one to get instances (only go 1 year into the future)
        default_future_expansion_duration = PyCalendarDuration(days=config.Scheduling.Options.AutoSchedule.FutureFreeBusyDays)
        expand_max = PyCalendarDateTime.getToday() + default_future_expansion_duration
        instances = calendar.expandTimeRanges(expand_max, ignoreInvalidInstances=True)

        # We are going to ignore auto-accept processing for anything more than a day old (actually use -2 days
        # to add some slop to account for possible timezone offsets)
        min_date = PyCalendarDateTime.getToday()
        min_date.offsetDay(-2)
        allOld = True

        # Cache the current attendee partstat on the instance object for later use, and
        # also mark whether the instance time slot would be free
        for instance in instances.instances.itervalues():
            attendee = instance.component.getAttendeeProperty(cuas)
            instance.partstat = attendee.parameterValue("PARTSTAT", "NEEDS-ACTION") if attendee else None
            instance.free = True
            instance.active = (instance.end > min_date)
            if instance.active:
                allOld = False

        # If every instance is in the past we punt right here so we don't waste time on freebusy lookups etc.
        # There will be no auto-accept and no inbox item stored (so as not to waste storage on items that will
        # never be processed).
        if allOld:
            returnValue((False, False, "",))

        # Extract UID from primary component as we want to ignore this one if we match it
        # in any calendars.
        uid = calendar.resourceUID()

        # Now compare each instance time-range with the index and see if there is an overlap
        fbset = (yield self.recipient.inbox.ownerHome().loadCalendars())
        fbset = [fbcalendar for fbcalendar in fbset if fbcalendar.isUsedForFreeBusy()]

        for testcal in fbset:

            # Get the timezone property from the collection, and store in the query filter
            # for use during the query itself.
            tz = testcal.getTimezone()
            tzinfo = tz.gettimezone() if tz is not None else PyCalendarTimezone(utc=True)

            # Now do search for overlapping time-range and set instance.free based
            # on whether there is an overlap or not
            for instance in instances.instances.itervalues():
                if instance.partstat == "NEEDS-ACTION" and instance.free and instance.active:
                    try:
                        # First list is BUSY, second BUSY-TENTATIVE, third BUSY-UNAVAILABLE
                        fbinfo = ([], [], [])

                        def makeTimedUTC(dt):
                            dt = dt.duplicate()
                            if dt.isDateOnly():
                                dt.setDateOnly(False)
                                dt.setHHMMSS(0, 0, 0)
                            if dt.floating():
                                dt.setTimezone(tzinfo)
                                dt.adjustToUTC()
                            return dt

                        tr = caldavxml.TimeRange(
                            start=str(makeTimedUTC(instance.start)),
                            end=str(makeTimedUTC(instance.end)),
                        )

                        yield generateFreeBusyInfo(testcal, fbinfo, tr, 0, uid, servertoserver=True)

                        # If any fbinfo entries exist we have an overlap
                        if len(fbinfo[0]) or len(fbinfo[1]) or len(fbinfo[2]):
                            instance.free = False
                    except NumberOfMatchesWithinLimits:
                        instance.free[instance] = False
                        log.info("Exceeded number of matches whilst trying to find free-time.")

            # If everything is declined we can exit now
            if not any([instance.free for instance in instances.instances.itervalues()]):
                break

        # Now adjust the instance.partstat currently set to "NEEDS-ACTION" to the
        # value determined by auto-accept logic based on instance.free state. However,
        # ignore any instance in the past - leave them as NEEDS-ACTION.
        partstat_counts = collections.defaultdict(int)
        for instance in instances.instances.itervalues():
            if instance.partstat == "NEEDS-ACTION" and instance.active:
                if automode == "accept-always":
                    freePartstat = busyPartstat = "ACCEPTED"
                elif automode == "decline-always":
                    freePartstat = busyPartstat = "DECLINED"
                else:
                    freePartstat = "ACCEPTED" if automode in ("accept-if-free", "automatic",) else "NEEDS-ACTION"
                    busyPartstat = "DECLINED" if automode in ("decline-if-busy", "automatic",) else "NEEDS-ACTION"
                instance.partstat = freePartstat if instance.free else busyPartstat
            partstat_counts[instance.partstat] += 1

        if len(partstat_counts) == 0:
            # Nothing to do
            returnValue((False, False, "",))

        elif len(partstat_counts) == 1:
            # Do the simple case of all PARTSTATs the same separately
            # Extract the ATTENDEE property matching current recipient from the calendar data
            attendeeProps = calendar.getAttendeeProperties(cuas)
            if not attendeeProps:
                returnValue((False, False, "",))

            made_changes = False
            partstat = partstat_counts.keys()[0]
            for component in calendar.subcomponents():
                made_changes |= self.resetAttendeePartstat(component, cuas, partstat)
            store_inbox = partstat == "NEEDS-ACTION"

        else:
            # Hard case: some accepted, some declined, some needs-action
            # What we will do is mark any master instance as accepted, then mark each existing
            # overridden instance as accepted or declined, and generate new overridden instances for
            # any other declines.

            made_changes = False
            store_inbox = False
            partstat = "MIXED RESPONSE"

            # Default state is whichever of free or busy has most instances
            defaultPartStat = max(sorted(partstat_counts.items()), key=lambda x: x[1])[0]

            # See if there is a master component first
            hadMasterRsvp = False
            master = calendar.masterComponent()
            if master:
                attendee = master.getAttendeeProperty(cuas)
                if attendee:
                    hadMasterRsvp = attendee.parameterValue("RSVP", "FALSE") == "TRUE"
                    if defaultPartStat == "NEEDS-ACTION":
                        store_inbox = True
                    made_changes |= self.resetAttendeePartstat(master, cuas, defaultPartStat)

            # Look at expanded instances and change partstat accordingly
            for instance in sorted(instances.instances.values(), key=lambda x: x.rid):

                overridden = calendar.overriddenComponent(instance.rid)
                if not overridden and instance.partstat == defaultPartStat:
                    # Nothing to do as state matches the master
                    continue

                if overridden:
                    # Change ATTENDEE property to match new state
                    if instance.partstat == "NEEDS-ACTION" and instance.active:
                        store_inbox = True
                    made_changes |= self.resetAttendeePartstat(overridden, cuas, instance.partstat)
                else:
                    # Derive a new overridden component and change partstat. We also need to make sure we restore any RSVP
                    # value that may have been overwritten by any change to the master itself.
                    derived = calendar.deriveInstance(instance.rid)
                    if derived is not None:
                        attendee = derived.getAttendeeProperty(cuas)
                        if attendee:
                            if instance.partstat == "NEEDS-ACTION" and instance.active:
                                store_inbox = True
                            self.resetAttendeePartstat(derived, cuas, instance.partstat, hadMasterRsvp)
                            made_changes = True
                            calendar.addComponent(derived)

        # Fake a SCHEDULE-STATUS on the ORGANIZER property
        if made_changes:
            calendar.setParameterToValueForPropertyWithValue("SCHEDULE-STATUS", iTIPRequestStatus.MESSAGE_DELIVERED_CODE, "ORGANIZER", None)

        returnValue((made_changes, store_inbox, partstat,))


    @inlineCallbacks
    def writeCalendarResource(self, collection, resource, calendar):
        """
        Write out the calendar resource (iTIP) message to the specified calendar, either over-writing the named
        resource or by creating a new one.

        @param collection: the calendar collection to store the resource in.
        @type: L{Calendar}
        @param resource: the resource object to write to, or C{None} to write a new resource.
        @type: L{CalendarObject}
        @param calendar: the calendar data to write.
        @type: L{Component}

        @return: the object resource written to (either the one passed in or a new one)
        @rtype: L{CalendarObject}
        """

        # Create a new name if one was not provided
        internal_state = ComponentUpdateState.ORGANIZER_ITIP_UPDATE if self.isOrganizerReceivingMessage() else ComponentUpdateState.ATTENDEE_ITIP_UPDATE
        if resource is None:
            name = "%s-%s.ics" % (hashlib.md5(calendar.resourceUID()).hexdigest(), str(uuid.uuid4())[:8],)
            newchild = (yield collection._createCalendarObjectWithNameInternal(name, calendar, internal_state))
        else:
            yield resource._setComponentInternal(calendar, internal_state=internal_state)
            newchild = resource

        returnValue(newchild)


    @inlineCallbacks
    def deleteCalendarResource(self, resource):
        """
        Delete the calendar resource in the specified calendar.

        @param collURL: the URL of the calendar collection.
        @type name: C{str}
        @param collection: the calendar collection to delete the resource from.
        @type collection: L{CalDAVResource}
        @param name: the resource name to write into, or {None} to write a new resource.
        @type name: C{str}
        """

        yield resource._removeInternal(internal_state=ComponentRemoveState.INTERNAL)


    def resetAttendeePartstat(self, component, cuas, partstat, hadRSVP=False):
        """
        Change the PARTSTAT on any ATTENDEE properties that match the list of calendar user
        addresses on the component passed in. Also adjust the TRANSP property to match the
        new PARTSTAT value.

        @param component: an iCalendar component to modify
        @type attendees: L{Component}
        @param cuas: a list of calendar user addresses to match
        @type attendees: C{list} or C{tuple}
        @param partstat: new PARTSTAT to set
        @type partstat: C{str}
        @param hadRSVP: indicates whether RSVP should be added when changing to NEEDS-ACTION
        @type hadRSVP: C{bool}

        @return: C{True} if any change was made, C{False} otherwise
        """

        madeChanges = False
        attendee = component.getAttendeeProperty(cuas)
        if attendee:
            if attendee.parameterValue("PARTSTAT", "NEEDS-ACTION") != partstat:
                attendee.setParameter("PARTSTAT", partstat)
                madeChanges = True

            # Always remove RSVP when a state other than NEEDS-ACTION is set - this
            # is only an attendee change so madeChanges does not need to be changed
            try:
                if attendee.parameterValue("PARTSTAT", "NEEDS-ACTION") != "NEEDS-ACTION":
                    attendee.removeParameter("RSVP")
                elif hadRSVP:
                    attendee.setParameter("RSVP", "TRUE")
            except KeyError:
                pass

            # Adjust TRANSP to OPAQUE if PARTSTAT is ACCEPTED, otherwise TRANSPARENT
            component.replaceProperty(Property("TRANSP", "OPAQUE" if partstat == "ACCEPTED" else "TRANSPARENT"))

        return madeChanges


    @inlineCallbacks
    def doImplicitAttendeeEventFix(self, ex):

        # Only certain types of exception should be handled - ones related to calendar data errors.
        # All others should result in the scheduling response coming back as a 5.x code

        if type(ex) not in (InvalidOverriddenInstanceError, HTTPError):
            raise ImplicitProcessorException("5.1;Service unavailable")

        # Check to see whether the originator is hosted on this server
        if not self.originator.principal:
            raise ImplicitProcessorException("5.1;Service unavailable")

        # Locate the originator's copy of the event
        calendar_resource = (yield getCalendarObjectForRecord(self.txn, self.originator.principal, self.uid))
        if calendar_resource is None:
            raise ImplicitProcessorException("5.1;Service unavailable")
        originator_calendar = (yield calendar_resource.componentForUser(self.originator.principal.uid))

        # Get attendee's view of that
        originator_calendar.attendeesView((self.recipient.cuaddr,))

        # Locate the attendee's copy of the event if it exists.
        recipient_resource = (yield getCalendarObjectForRecord(self.txn, self.recipient.principal, self.uid))

        # We only need to fix data that already exists
        if recipient_resource is not None:
            if originator_calendar.mainType() != None:
                yield self.writeCalendarResource(recipient_resource, originator_calendar)
            else:
                yield self.deleteCalendarResource(recipient_resource)

        returnValue(True)
