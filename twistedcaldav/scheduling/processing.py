#
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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

from twisted.python.log import err as log_traceback
from twext.python.log import Logger

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twext.web2.dav.method.report import NumberOfMatchesWithinLimits
from twext.web2.dav.util import joinURL
from twext.web2.http import HTTPError
from twistedcaldav import customxml, caldavxml
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.config import config
from twistedcaldav.ical import Property
from twistedcaldav.instance import InvalidOverriddenInstanceError
from twistedcaldav.method import report_common
from twistedcaldav.scheduling.cuaddress import normalizeCUAddr
from twistedcaldav.scheduling.itip import iTipProcessing, iTIPRequestStatus
from twistedcaldav.scheduling.utils import getCalendarObjectForPrincipals
from twistedcaldav.memcachelock import MemcacheLock, MemcacheLockTimeoutError
from twistedcaldav.memcacher import Memcacher
from pycalendar.duration import PyCalendarDuration
from pycalendar.datetime import PyCalendarDateTime
from pycalendar.timezone import PyCalendarTimezone
import uuid

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
    def doImplicitProcessing(self, request, message, originator, recipient):
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

        self.request = request
        self.message = message
        self.originator = originator
        self.recipient = recipient
        
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
                log_traceback()
                log.error("ImplicitProcessing - originator '%s' to recipient '%s' with UID: '%s' - exception raised will try to fix: %s" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid, e))
                result = (yield self.doImplicitAttendeeEventFix(e))
                if result:
                    log.error("ImplicitProcessing - originator '%s' to recipient '%s' with UID: '%s' - restored organizer's copy" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                    try:
                        result = (yield self.doImplicitAttendee())
                    except Exception, e:
                        log_traceback()
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
        self.recipient_calendar_collection = None
        self.recipient_calendar_collection_uri = None
        self.recipient_calendar_name = None
        calendar_resource, resource_name, calendar_collection, calendar_collection_uri = (yield getCalendarObjectForPrincipals(self.request, self.recipient.principal, self.uid))
        if calendar_resource:
            self.recipient_calendar = (yield calendar_resource.iCalendarForUser(self.request))
            self.recipient_calendar_collection = calendar_collection
            self.recipient_calendar_collection_uri = calendar_collection_uri
            self.recipient_calendar_name = resource_name
    
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
 
            # Update the organizer's copy of the event
            log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:REPLY, UID: '%s' - updating event" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
            self.organizer_calendar_resource = (yield self.writeCalendarResource(self.recipient_calendar_collection_uri, self.recipient_calendar_collection, self.recipient_calendar_name, self.recipient_calendar))
            
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
                    changes.append(customxml.ChangedProperty(customxml.ChangedParameter(name="PARTSTAT"), name="ATTENDEE" ))
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
            if partstatChanged and not getattr(self.request, "noAttendeeRefresh", False):
                yield self.queueAttendeeUpdate((attendeeReplying,))

            result = (True, False, True, changes,)

        else:
            # Ignore scheduling message
            result = (True, True, False, None,)

        returnValue(result)

    @inlineCallbacks
    def queueAttendeeUpdate(self, exclude_attendees):
        """
        Queue up an update to attendees and use a memcache lock to ensure we don't update too frequently.
        
        @param exclude_attendees: list of attendees who should not be refreshed (e.g., the one that triggeed the refresh)
        @type exclude_attendees: C{list}
        """
        
        # When doing auto-processing of replies, only refresh attendees when the last auto-accept is done.
        # Note that when we do this we also need to refresh the attendee that is generating the reply because they
        # are no longer up to date with changes of other auto-accept attendees.
        if hasattr(self.request, "auto_reply_processing_count") and self.request.auto_reply_processing_count > 1:
            self.request.auto_reply_suppressed = True
            returnValue(None)
        if hasattr(self.request, "auto_reply_suppressed"):
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
    
                # Always need to refresh every attendee
                exclude_attendees = ()
                
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
                    reactor.callLater(config.Scheduling.Options.AttendeeRefreshBatchDelaySeconds, self._doBatchRefresh)
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
        from twistedcaldav.scheduling.implicit import ImplicitScheduler
        scheduler = ImplicitScheduler()
        yield scheduler.refreshAllAttendeesExceptSome(
            self.request,
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

        # We need to get the UID lock for implicit processing whilst we send the auto-reply
        # as the Organizer processing will attempt to write out data to other attendees to
        # refresh them. To prevent a race we need a lock.
        uidlock = MemcacheLock(
            "ImplicitUIDLock",
            self.uid,
            timeout=config.Scheduling.Options.UIDLockTimeoutSeconds,
            expire_time=config.Scheduling.Options.UIDLockExpirySeconds,
        )

        try:
            yield uidlock.acquire()
        except MemcacheLockTimeoutError:
            # Just try again to get the lock
            reactor.callLater(2.0, self._doDelayedRefresh, attendeesToProcess)
        else:

            # inNewTransaction wipes out the remembered resource<-> URL mappings in the
            # request object but we need to be able to map the actual reply resource to its
            # URL when doing auto-processing, so we have to sneak that mapping back in here.
            txn = yield self.organizer_calendar_resource.inNewTransaction(self.request, label="Delayed attendee refresh")

            try:
                organizer_resource = (yield self.request.locateResource(self.organizer_calendar_resource._url))
                if organizer_resource.exists():
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
        finally:
            yield uidlock.clean()

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
                    reactor.callLater(config.Scheduling.Options.AttendeeRefreshBatchIntervalSeconds, self._doBatchRefresh)
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
    def doImplicitAttendeeRequest(self):

        # If there is no existing copy, then look for default calendar and copy it here
        if self.new_resource:
            
            # Check for default calendar
            default = (yield self.recipient.inbox.defaultCalendar(self.request, self.message.mainType()))
            if default is None:
                log.error("No default calendar for recipient: '%s'." % (self.recipient.cuaddr,))
                raise ImplicitProcessorException(iTIPRequestStatus.NO_USER_SUPPORT)

            log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:REQUEST, UID: '%s' - new processed" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
            new_calendar = iTipProcessing.processNewRequest(self.message, self.recipient.cuaddr)
            name =  str(uuid.uuid4()) + ".ics"
            
            # Handle auto-reply behavior
            if self.recipient.principal.canAutoSchedule():
                send_reply, store_inbox, partstat = (yield self.checkAttendeeAutoReply(new_calendar, self.recipient.principal.getAutoScheduleMode()))
                
                # Only store inbox item when reply is not sent or always for users
                store_inbox = store_inbox or self.recipient.principal.getCUType() == "INDIVIDUAL"
            else:
                send_reply = False
                store_inbox = True

            new_resource = (yield self.writeCalendarResource(default.url(), default, name, new_calendar))
            
            if send_reply:
                # Track outstanding auto-reply processing
                if not hasattr(self.request, "auto_reply_processing_count"):
                    self.request.auto_reply_processing_count = 1
                else:
                    self.request.auto_reply_processing_count += 1
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
                if self.recipient.principal.canAutoSchedule():
                    send_reply, store_inbox, partstat = (yield self.checkAttendeeAutoReply(new_calendar, self.recipient.principal.getAutoScheduleMode()))
                    
                    # Only store inbox item when reply is not sent or always for users
                    store_inbox = store_inbox or self.recipient.principal.getCUType() == "INDIVIDUAL"
                else:
                    send_reply = False
                    store_inbox = True

                # Update the attendee's copy of the event
                log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:REQUEST, UID: '%s' - updating event" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                new_resource = (yield self.writeCalendarResource(self.recipient_calendar_collection_uri, self.recipient_calendar_collection, self.recipient_calendar_name, new_calendar))
                
                if send_reply:
                    # Track outstanding auto-reply processing
                    if not hasattr(self.request, "auto_reply_processing_count"):
                        self.request.auto_reply_processing_count = 1
                    else:
                        self.request.auto_reply_processing_count += 1
                    reactor.callLater(2.0, self.sendAttendeeAutoReply, *(new_calendar, new_resource, partstat))

                # Build the schedule-changes XML element
                update_details = []
                for rid, props_changed in sorted(rids.iteritems(), key=lambda x:x[0]):
                    recurrence = []
                    if rid == "":
                        recurrence.append(customxml.Master())
                    else:
                        recurrence.append(customxml.RecurrenceID.fromString(rid))
                    changes = []
                    for propName, paramNames in sorted(props_changed.iteritems(), key=lambda x:x[0]):
                        params = tuple([customxml.ChangedParameter(name=param) for param in paramNames])
                        changes.append(customxml.ChangedProperty(*params, **{"name":propName}))
                    recurrence.append(customxml.Changes(*changes))
                    update_details += (customxml.Recurrence(*recurrence),)

                changes = customxml.ScheduleChanges(
                    customxml.DTStamp(),
                    customxml.Action(
                        customxml.Update(*update_details),
                    ),
                )
                
                # Refresh from another Attendee should not have Inbox item
                if hasattr(self.request, "doing_attendee_refresh"):
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
            autoprocessed = self.recipient.principal.getAutoSchedule() and self.recipient.principal.getCUType() != "INDIVIDUAL"
            store_inbox = not autoprocessed or self.recipient.principal.getCUType() == "INDIVIDUAL"

            # Check to see if this is a cancel of the entire event
            processed_message, delete_original, rids = iTipProcessing.processCancel(self.message, self.recipient_calendar, autoprocessing=autoprocessed)
            if processed_message:
                if delete_original:
                    
                    # Delete the attendee's copy of the event
                    log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:CANCEL, UID: '%s' - deleting entire event" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                    yield self.deleteCalendarResource(self.recipient_calendar_collection_uri, self.recipient_calendar_collection, self.recipient_calendar_name)

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
                    yield self.writeCalendarResource(self.recipient_calendar_collection_uri, self.recipient_calendar_collection, self.recipient_calendar_name, self.recipient_calendar)

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

        @param calendar: calendar data to examine
        @type calendar: L{Component}

        @return: L{Component} for the new calendar data to write
        """
        
        # We need to get the UID lock for implicit processing whilst we send the auto-reply
        # as the Organizer processing will attempt to write out data to other attendees to
        # refresh them. To prevent a race we need a lock.
        lock = MemcacheLock(
            "ImplicitUIDLock",
            calendar.resourceUID(),
            timeout=config.Scheduling.Options.UIDLockTimeoutSeconds,
            expire_time=config.Scheduling.Options.UIDLockExpirySeconds,
        )

        # Note that this lock also protects the request, as this request is
        # being re-used by potentially multiple transactions and should not be
        # used concurrency (the locateResource cache needs to be cleared each
        # time, by inNewTransaction). -glyph
        try:
            yield lock.acquire()
        except MemcacheLockTimeoutError:
            # Just try again to get the lock
            reactor.callLater(2.0, self.sendAttendeeAutoReply, *(calendar, resource, partstat))
        else:
            # inNewTransaction wipes out the remembered resource<-> URL mappings in the
            # request object but we need to be able to map the actual reply resource to its
            # URL when doing auto-processing, so we have to sneak that mapping back in here.
            txn = yield resource.inNewTransaction(self.request, label="Send Attendee auto-reply")

            try:
                self.request._rememberResource(resource, resource._url)
                # Send out a reply
                log.debug("ImplicitProcessing - recipient '%s' processing UID: '%s' - auto-reply: %s" % (self.recipient.cuaddr, self.uid, partstat))
                from twistedcaldav.scheduling.implicit import ImplicitScheduler
                scheduler = ImplicitScheduler()
                yield scheduler.sendAttendeeReply(self.request, resource, calendar, self.recipient)
            except Exception, e:
                log.debug("ImplicitProcessing - auto-reply exception UID: '%s', %s" % (self.uid, str(e)))
                yield txn.abort()
            except:
                log.debug("ImplicitProcessing - auto-reply bare exception UID: '%s'" % (self.uid,))
                yield txn.abort()
            else:
                yield txn.commit()
        finally:
            # This correctly gets called only after commit or abort is done
            yield lock.clean()

            # Track outstanding auto-reply processing
            if hasattr(self.request, "auto_reply_processing_count"):
                self.request.auto_reply_processing_count -= 1

    @inlineCallbacks
    def checkAttendeeAutoReply(self, calendar, automode):
        """
        Check whether a reply to the given iTIP message is needed. We will not process a reply
        A reply will either be positive (accepted invitation) or negative (denied invitation).
        In addition we will modify calendar to reflect
        any new state (e.g. set PARTSTAT to ACCEPTED or DECLINED).
        
        BTW The incoming iTIP message may contain multiple components so we need to iterate over all those.
        At the moment we will treat a failure on one instance as a DECLINE of the entire set.

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

        # The accept-always and decline-always modes do not need any freebusy checks
        if automode in ("accept-always", "decline-always",):
            all_accepted = automode == "accept-always"
            all_declined = automode == "decline-always"
        
        # Other modes need freebusy check
        else:
            # First expand current one to get instances (only go 1 year into the future)
            default_future_expansion_duration = PyCalendarDuration(days=356*1)
            expand_max = PyCalendarDateTime.getToday() + default_future_expansion_duration
            instances = calendar.expandTimeRanges(expand_max, ignoreInvalidInstances=True)
            instance_states = dict([(instance, True) for instance in instances.instances.itervalues()])
            
            # Extract UID from primary component as we want to ignore this one if we match it
            # in any calendars.
            comp = calendar.mainComponent(allow_multiple=True)
            uid = comp.propertyValue("UID")
        
            # Now compare each instance time-range with the index and see if there is an overlap
            calendars = (yield self._getCalendarsToMatch())
        
            for calURL in calendars:
                testcal = (yield self.request.locateResource(calURL))
    
                # Get the timezone property from the collection, and store in the query filter
                # for use during the query itself.
                has_prop = (yield testcal.hasProperty((caldav_namespace, "calendar-timezone"), self.request))
                if has_prop:
                    tz = (yield testcal.readProperty((caldav_namespace, "calendar-timezone"), self.request))
                    tzinfo = tz.calendar().gettimezone()
                else:
                    tzinfo = PyCalendarTimezone(utc=True)
    
                # Now do search for overlapping time-range
                for instance in instances.instances.itervalues():
                    if instance_states[instance]:
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
    
                            yield report_common.generateFreeBusyInfo(self.request, testcal, fbinfo, tr, 0, uid, servertoserver=True)
                            
                            # If any fbinfo entries exist we have an overlap
                            if len(fbinfo[0]) or len(fbinfo[1]) or len(fbinfo[2]):
                                instance_states[instance] = False
                        except NumberOfMatchesWithinLimits:
                            instance_states[instance] = False
                            log.info("Exceeded number of matches whilst trying to find free-time.")
                
                # If everything is declined we can exit now
                if not any(instance_states.itervalues()):
                    break
            
            # TODO: here we should do per-instance ACCEPT/DECLINE behavior
            # For now we will assume overall ACCEPT/DECLINE
    
            # Collect all the accepted and declined states
            all_accepted = all(instance_states.itervalues())
            all_declined = not any(instance_states.itervalues())

        # Do the simple case of all accepted or decline separately
        cuas = self.recipient.principal.calendarUserAddresses()
        if all_accepted or all_declined:
            # Extract the ATTENDEE property matching current recipient from the calendar data
            attendeeProps = calendar.getAttendeeProperties(cuas)
            if not attendeeProps:
                returnValue((False, True, "",))
        
            if automode == "accept-always":
                freePartstat = busyPartstat = "ACCEPTED"
            elif automode == "decline-always":
                freePartstat = busyPartstat = "DECLINED"
            else:
                freePartstat = "ACCEPTED" if automode in ("accept-if-free", "automatic",) else "NEEDS-ACTION"
                busyPartstat = "DECLINED" if automode in ("decline-if-busy", "automatic",) else "NEEDS-ACTION"
            freeStateOpaque = freePartstat == "ACCEPTED"

            partstat = freePartstat if all_accepted else busyPartstat
            calendar.replacePropertyInAllComponents(Property("TRANSP", "OPAQUE" if all_accepted and freeStateOpaque else "TRANSPARENT"))
    
            made_changes = self.changeAttendeePartstat(attendeeProps, partstat)
            store_inbox = partstat == "NEEDS-ACTION"
        
        else:
            # Hard case: some accepted some declined
            # What we will do is mark any master instance as accepted, then mark each existing
            # overridden instance as accepted or declined, and generate new overridden instances for
            # any other declines.
            
            made_changes = False
            store_inbox = False
            partstat = "MIXED RESPONSE"
            
            freePartstat = "ACCEPTED" if automode in ("accept-if-free", "automatic",) else "NEEDS-ACTION"
            busyPartstat = "DECLINED" if automode in ("decline-if-busy", "automatic",) else "NEEDS-ACTION"
            freeStateOpaque = freePartstat == "ACCEPTED"

            # Default state is whichever of free or busy has most instances
            defaultStateFree = len(filter(lambda x:x, instance_states.values())) >= len(instance_states.keys()) / 2

            # See if there is a master component first
            hadMasterRsvp = False
            master = calendar.masterComponent()
            if master:
                attendee = master.getAttendeeProperty(cuas)
                if attendee:
                    hadMasterRsvp = attendee.parameterValue("RSVP", "FALSE") == "TRUE"
                    new_partstat = freePartstat if defaultStateFree else busyPartstat
                    if new_partstat == "NEEDS-ACTION":
                        store_inbox = True
                    made_changes |= self.changeAttendeePartstat(attendee, new_partstat)
                    master.replaceProperty(Property("TRANSP", "OPAQUE" if defaultStateFree and freeStateOpaque else "TRANSPARENT"))

            # Look at expanded instances and change partstat accordingly
            for instance, free in sorted(instance_states.iteritems(), key=lambda x: x[0].rid):
                
                overridden = calendar.overriddenComponent(instance.rid)
                if not overridden and free == defaultStateFree:
                    # Nothing to do as state matches the master
                    continue 
                
                if overridden:
                    # Change ATTENDEE property to match new state
                    attendee = overridden.getAttendeeProperty(cuas)
                    if attendee:
                        new_partstat = freePartstat if free else busyPartstat
                        if new_partstat == "NEEDS-ACTION":
                            store_inbox = True
                        made_changes |= self.changeAttendeePartstat(attendee, new_partstat)
                        overridden.replaceProperty(Property("TRANSP", "OPAQUE" if free and freeStateOpaque else "TRANSPARENT"))
                else:
                    # Derive a new overridden component and change partstat. We also need to make sure we restore any RSVP
                    # value that may have been overwritten by any change to the master itself. 
                    derived = calendar.deriveInstance(instance.rid)
                    if derived:
                        attendee = derived.getAttendeeProperty(cuas)
                        if attendee:
                            new_partstat = freePartstat if free else busyPartstat
                            if new_partstat == "NEEDS-ACTION":
                                store_inbox = True
                            self.changeAttendeePartstat(attendee, new_partstat, hadMasterRsvp)
                            derived.replaceProperty(Property("TRANSP", "OPAQUE" if free and freeStateOpaque else "TRANSPARENT"))
                            calendar.addComponent(derived)
                            made_changes = True
            
        # Fake a SCHEDULE-STATUS on the ORGANIZER property
        if made_changes:
            calendar.setParameterToValueForPropertyWithValue("SCHEDULE-STATUS", iTIPRequestStatus.MESSAGE_DELIVERED_CODE, "ORGANIZER", None)
        
        returnValue((made_changes, store_inbox, partstat,))

    def _getCalendarsToMatch(self):
        # Determine the set of calendar URIs for a principal need to be searched.
        
        # Find the current recipients calendar-free-busy-set
        return self.recipient.principal.calendarFreeBusyURIs(self.request)

    @inlineCallbacks
    def writeCalendarResource(self, collURL, collection, name, calendar):
        """
        Write out the calendar resource (iTIP) message to the specified calendar, either over-writing the named
        resource or by creating a new one.
        
        @param collURL: the C{str} containing the URL of the calendar collection.
        @param collection: the L{CalDAVResource} for the calendar collection to store the resource in.
        @param name: the C{str} for the resource name to write into, or {None} to write a new resource.
        @param calendar: the L{Component} calendar to write.
        @return: L{Deferred} -> L{CalDAVResource}
        """
        
        # Create a new name if one was not provided
        if name is None:
            name =  str(uuid.uuid4()) + ".ics"
    
        # Get a resource for the new item
        newchildURL = joinURL(collURL, name)
        newchild = yield self.request.locateResource(newchildURL)
        newchild._url = newchildURL
        
        # Now write it to the resource
        from twistedcaldav.method.put_common import StoreCalendarObjectResource
        yield StoreCalendarObjectResource(
                     request=self.request,
                     destination = newchild,
                     destination_uri = newchildURL,
                     destinationparent = collection,
                     destinationcal = True,
                     calendar = calendar,
                     isiTIP = False,
                     allowImplicitSchedule = False,
                     internal_request = True,
                     processing_organizer = self.isOrganizerReceivingMessage(),
                 ).run()
    
        returnValue(newchild)


    @inlineCallbacks
    def deleteCalendarResource(self, collURL, collection, name):
        """
        Delete the calendar resource in the specified calendar.
        
        @param collURL: the URL of the calendar collection.
        @type name: C{str}
        @param collection: the calendar collection to delete the resource from.
        @type collection: L{CalDAVResource}
        @param name: the resource name to write into, or {None} to write a new resource.
        @type name: C{str}
        """
        delchild = yield collection.getChild(name)
        childURL = joinURL(collURL, name)
        self.request._rememberResource(delchild, childURL)
        yield delchild.storeRemove(self.request, False, childURL)


    def changeAttendeePartstat(self, attendees, partstat, hadRSVP=False):
        """
        Change the PARTSTAT on any ATTENDEE properties passed in.

        @param attendees: a single ATTENDEE property or a list of them
        @type attendees: L{Property}, C{list} or C{tuple}
        @param partstat: new PARTSTAT to set
        @type partstat: C{str}
        @param hadRSVP: indicates whether RSVP should be added when changing to NEEDS-ACTION
        @type hadRSVP: C{bool}
        
        @return: C{True} if any change was made, C{False} otherwise
        """

        if isinstance(attendees, Property):
            attendees = (attendees,)

        madeChanges = False
        for attendee in attendees:
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
        calendar_resource, _ignore_name, _ignore_collection, _ignore_uri = (yield getCalendarObjectForPrincipals(self.request, self.originator.principal, self.uid))
        if not calendar_resource:
            raise ImplicitProcessorException("5.1;Service unavailable")
        originator_calendar = (yield calendar_resource.iCalendarForUser(self.request))

        # Get attendee's view of that
        originator_calendar.attendeesView((self.recipient.cuaddr,))

        # Locate the attendee's copy of the event if it exists.
        recipient_resource, recipient_resource_name, recipient_collection, recipient_collection_uri = (yield getCalendarObjectForPrincipals(self.request, self.recipient.principal, self.uid))
        
        # We only need to fix data that already exists
        if recipient_resource:
            if originator_calendar.mainType() != None:
                yield self.writeCalendarResource(recipient_collection_uri, recipient_collection, recipient_resource_name, originator_calendar)
            else:
                yield self.deleteCalendarResource(recipient_collection_uri, recipient_collection, recipient_resource_name)
        
        returnValue(True)
