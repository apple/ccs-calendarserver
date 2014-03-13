#
# Copyright (c) 2013 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.record import fromTable
from twext.enterprise.dal.syntax import Select, Insert, Delete, Parameter
from twext.enterprise.locking import NamedLock
from twext.enterprise.jobqueue import WorkItem
from twext.python.log import Logger

from twisted.internet.defer import inlineCallbacks, returnValue, Deferred

from twistedcaldav.config import config
from twistedcaldav.ical import Component

from txdav.caldav.datastore.scheduling.itip import iTipGenerator, iTIPRequestStatus
from txdav.caldav.icalendarstore import ComponentUpdateState
from txdav.common.datastore.sql_tables import schema, \
    scheduleActionToSQL, scheduleActionFromSQL

import datetime
import hashlib
from pycalendar.datetime import DateTime
import traceback

__all__ = [
    "ScheduleOrganizerWork",
    "ScheduleReplyWork",
    "ScheduleReplyCancelWork",
    "ScheduleRefreshWork",
    "ScheduleAutoReplyWork",
]

log = Logger()



class ScheduleWorkMixin(object):
    """
    Base class for common schedule work item behavior.
    """

    # Track when all work is complete (needed for unit tests)
    _allDoneCallback = None
    _queued = 0

    # Schedule work is grouped based on calendar object UID
    group = property(lambda self: "ScheduleWork:%s" % (self.icalendarUid,))


    @classmethod
    def allDone(cls):
        d = Deferred()
        cls._allDoneCallback = d.callback
        cls._queued = 0
        return d


    @classmethod
    def _enqueued(cls):
        """
        Called when a new item is enqueued - using for tracking purposes.
        """
        ScheduleWorkMixin._queued += 1


    def _dequeued(self):
        """
        Called when an item is dequeued - using for tracking purposes. We call
        the callback when the last item is dequeued.
        """
        ScheduleWorkMixin._queued -= 1
        if ScheduleWorkMixin._queued == 0:
            if ScheduleWorkMixin._allDoneCallback:
                def _post():
                    ScheduleWorkMixin._allDoneCallback(None)
                    ScheduleWorkMixin._allDoneCallback = None
                self.transaction.postCommit(_post)


    def handleSchedulingResponse(self, response, calendar, is_organizer):
        """
        Update a user's calendar object resource based on the results of a queued scheduling
        message response. Note we only need to update in the case where there is an error response
        as we will already have updated the calendar object resource to make it look like scheduling
        worked prior to the work queue item being enqueued.

        @param response: the scheduling response object
        @type response: L{caldavxml.ScheduleResponse}
        @param calendar: original calendar component
        @type calendar: L{Component}
        @param is_organizer: whether or not iTIP message was sent by the organizer
        @type is_organizer: C{bool}
        """

        # Map each recipient in the response to a status code
        changed = False
        propname = calendar.mainComponent().recipientPropertyName() if is_organizer else "ORGANIZER"
        for item in response.responses:
            recipient = str(item.recipient.children[0])
            status = str(item.reqstatus)
            statusCode = status.split(";")[0]

            # Now apply to each ATTENDEE/ORGANIZER in the original data only if not 1.2
            if statusCode != iTIPRequestStatus.MESSAGE_DELIVERED_CODE:
                calendar.setParameterToValueForPropertyWithValue(
                    "SCHEDULE-STATUS",
                    statusCode,
                    propname,
                    recipient,
                )
                changed = True

        return changed



class ScheduleOrganizerWork(WorkItem, fromTable(schema.SCHEDULE_ORGANIZER_WORK), ScheduleWorkMixin):
    """
    The associated work item table is SCHEDULE_ORGANIZER_WORK.

    This work item is used to send a iTIP request and cancel messages when an organizer changes
    their calendar object resource.
    """

    @classmethod
    @inlineCallbacks
    def schedule(cls, txn, uid, action, home, resource, calendar_old, calendar_new, organizer, attendee_count, smart_merge):
        """
        The actual arguments depend on the action:

        1) If action is "create", resource is None, calendar_old is None, calendar_new is the new data
        2) If action is "modify", resource is existing resource, calendar_old is the old calendar_old data, and
            calendar_new is the new data
        3) If action is "remove", resource is the existing resource, calendar_old is the old calendar_old data,
            and calendar_new is None

        Right now we will also create the iTIP message based on the diff of calendar_old and calendar_new rather than
        looking at the current state of the orgnaizer's resource (which may have changed since this work item was
        filed). That means that we are basically NOT doing any coalescing of changes - instead every change results
        in its own iTIP message (pretty much as it would without the queue). Ultimately we need to support coalescing
        for performance benefit, but the logic involved in doing that is tricky (e.g., certain properties like
        SCHEDULE-FORCE-SEND are not preserved in the saved data, yet need to be accounted for because they change the
        nature of the iTIP processing).
        """
        # Always queue up new work - coalescing happens when work is executed
        notBefore = datetime.datetime.utcnow() + datetime.timedelta(seconds=config.Scheduling.Options.WorkQueues.RequestDelaySeconds)
        proposal = (yield txn.enqueue(
            cls,
            notBefore=notBefore,
            icalendarUid=uid,
            scheduleAction=scheduleActionToSQL[action],
            homeResourceID=home.id(),
            resourceID=resource.id() if resource else None,
            icalendarTextOld=calendar_old.getTextWithTimezones(includeTimezones=not config.EnableTimezonesByReference) if calendar_old else None,
            icalendarTextNew=calendar_new.getTextWithTimezones(includeTimezones=not config.EnableTimezonesByReference) if calendar_new else None,
            attendeeCount=attendee_count,
            smartMerge=smart_merge
        ))
        cls._enqueued()
        yield proposal.whenProposed()
        log.debug("ScheduleOrganizerWork - enqueued for ID: {id}, UID: {uid}, organizer: {org}", id=proposal.workItem.workID, uid=uid, org=organizer)


    @classmethod
    @inlineCallbacks
    def hasWork(cls, txn):
        srw = schema.SCHEDULE_ORGANIZER_WORK
        rows = (yield Select(
            (srw.WORK_ID,),
            From=srw,
        ).on(txn))
        returnValue(len(rows) > 0)


    @inlineCallbacks
    def doWork(self):

        try:
            home = (yield self.transaction.calendarHomeWithResourceID(self.homeResourceID))
            resource = (yield home.objectResourceWithID(self.resourceID))
            organizerPrincipal = yield home.directoryService().recordWithUID(home.uid().decode("utf-8"))
            organizer = organizerPrincipal.canonicalCalendarUserAddress()
            calendar_old = Component.fromString(self.icalendarTextOld) if self.icalendarTextOld else None
            calendar_new = Component.fromString(self.icalendarTextNew) if self.icalendarTextNew else None

            log.debug("ScheduleOrganizerWork - running for ID: {id}, UID: {uid}, organizer: {org}", id=self.workID, uid=self.icalendarUid, org=organizer)

            # We need to get the UID lock for implicit processing.
            yield NamedLock.acquire(self.transaction, "ImplicitUIDLock:%s" % (hashlib.md5(self.icalendarUid).hexdigest(),))

            from txdav.caldav.datastore.scheduling.implicit import ImplicitScheduler
            scheduler = ImplicitScheduler()
            yield scheduler.queuedOrganizerProcessing(
                self.transaction,
                scheduleActionFromSQL[self.scheduleAction],
                home,
                resource,
                self.icalendarUid,
                calendar_old,
                calendar_new,
                self.smartMerge
            )

            # Handle responses - update the actual resource in the store. Note that for a create the resource did not previously
            # exist and is stored as None for the work item, but the scheduler will attempt to find the new resources and use
            # that. We need to grab the scheduler's resource for further processing.
            resource = scheduler.resource
            if resource is not None:
                changed = False
                calendar = (yield resource.componentForUser())
                for response in scheduler.queuedResponses:
                    changed |= yield self.handleSchedulingResponse(response, calendar, True)

                if changed:
                    yield resource._setComponentInternal(calendar, internal_state=ComponentUpdateState.ORGANIZER_ITIP_UPDATE)

            self._dequeued()

        except Exception, e:
            log.debug("ScheduleOrganizerWork - exception ID: {id}, UID: '{uid}', {err}", id=self.workID, uid=self.icalendarUid, err=str(e))
            log.debug(traceback.format_exc())
            raise
        except:
            log.debug("ScheduleOrganizerWork - bare exception ID: {id}, UID: '{uid}'", id=self.workID, uid=self.icalendarUid)
            log.debug(traceback.format_exc())
            raise

        log.debug("ScheduleOrganizerWork - done for ID: {id}, UID: {uid}, organizer: {org}", id=self.workID, uid=self.icalendarUid, org=organizer)



class ScheduleReplyWorkMixin(ScheduleWorkMixin):


    def makeScheduler(self, home):
        """
        Convenience method which we can override in unit tests to make testing easier.
        """
        from txdav.caldav.datastore.scheduling.caldav.scheduler import CalDAVScheduler
        return CalDAVScheduler(self.transaction, home.uid())


    @inlineCallbacks
    def sendToOrganizer(self, home, action, itipmsg, originator, recipient):

        # Send scheduling message

        # This is a local CALDAV scheduling operation.
        scheduler = self.makeScheduler(home)

        # Do the PUT processing
        log.info("Implicit %s - attendee: '%s' to organizer: '%s', UID: '%s'" % (action, originator, recipient, itipmsg.resourceUID(),))
        response = (yield scheduler.doSchedulingViaPUT(originator, (recipient,), itipmsg, internal_request=True))
        returnValue(response)



class ScheduleReplyWork(WorkItem, fromTable(schema.SCHEDULE_REPLY_WORK), ScheduleReplyWorkMixin):
    """
    The associated work item table is SCHEDULE_REPLY_WORK.

    This work item is used to send an iTIP reply message when an attendee changes
    their partstat in the calendar object resource.
    """

    @classmethod
    @inlineCallbacks
    def reply(cls, txn, home, resource, changedRids, attendee):
        # Always queue up new work - coalescing happens when work is executed
        notBefore = datetime.datetime.utcnow() + datetime.timedelta(seconds=config.Scheduling.Options.WorkQueues.ReplyDelaySeconds)
        proposal = (yield txn.enqueue(
            cls,
            notBefore=notBefore,
            icalendarUid=resource.uid(),
            homeResourceID=home.id(),
            resourceID=resource.id(),

            # Serialize None as ""
            changedRids=",".join(map(lambda x: "" if x is None else str(x), changedRids)) if changedRids else None,
        ))
        cls._enqueued()
        yield proposal.whenProposed()
        log.debug("ScheduleReplyWork - enqueued for ID: {id}, UID: {uid}, attendee: {att}", id=proposal.workItem.workID, uid=resource.uid(), att=attendee)


    @classmethod
    @inlineCallbacks
    def hasWork(cls, txn):
        srw = schema.SCHEDULE_REPLY_WORK
        rows = (yield Select(
            (srw.WORK_ID,),
            From=srw,
        ).on(txn))
        returnValue(len(rows) > 0)


    @inlineCallbacks
    def doWork(self):

        try:
            home = (yield self.transaction.calendarHomeWithResourceID(self.homeResourceID))
            resource = (yield home.objectResourceWithID(self.resourceID))
            attendeePrincipal = yield home.directoryService().recordWithUID(home.uid().decode("utf-8"))
            attendee = attendeePrincipal.canonicalCalendarUserAddress()
            calendar = (yield resource.componentForUser())
            organizer = calendar.validOrganizerForScheduling()

            # Deserialize "" as None
            changedRids = map(lambda x: DateTime.parseText(x) if x else None, self.changedRids.split(",")) if self.changedRids else None

            log.debug("ScheduleReplyWork - running for ID: {id}, UID: {uid}, attendee: {att}", id=self.workID, uid=calendar.resourceUID(), att=attendee)

            # We need to get the UID lock for implicit processing.
            yield NamedLock.acquire(self.transaction, "ImplicitUIDLock:%s" % (hashlib.md5(calendar.resourceUID()).hexdigest(),))

            itipmsg = iTipGenerator.generateAttendeeReply(calendar, attendee, changedRids=changedRids)

            # Send scheduling message and process response
            response = (yield self.sendToOrganizer(home, "REPLY", itipmsg, attendee, organizer))
            changed = yield self.handleSchedulingResponse(response, calendar, False)

            if changed:
                yield resource._setComponentInternal(calendar, internal_state=ComponentUpdateState.ATTENDEE_ITIP_UPDATE)

            self._dequeued()

        except Exception, e:
            # FIXME: calendar may not be set here!
            log.debug("ScheduleReplyWork - exception ID: {id}, UID: '{uid}', {err}", id=self.workID, uid=calendar.resourceUID(), err=str(e))
            raise
        except:
            log.debug("ScheduleReplyWork - bare exception ID: {id}, UID: '{uid}'", id=self.workID, uid=calendar.resourceUID())
            raise

        log.debug("ScheduleReplyWork - done for ID: {id}, UID: {uid}, attendee: {att}", id=self.workID, uid=calendar.resourceUID(), att=attendee)



class ScheduleReplyCancelWork(WorkItem, fromTable(schema.SCHEDULE_REPLY_CANCEL_WORK), ScheduleReplyWorkMixin):
    """
    The associated work item table is SCHEDULE_REPLY_CANCEL_WORK.

    This work item is used to send an iTIP reply message when an attendee deletes
    their copy of the calendar object resource. For this to work we need to store a copy
    of the original resource data.
    """

    # Schedule work is grouped based on calendar object UID
    group = property(lambda self: "ScheduleWork:%s" % (self.icalendarUid,))


    @classmethod
    @inlineCallbacks
    def replyCancel(cls, txn, home, calendar, attendee):
        # Always queue up new work - coalescing happens when work is executed
        notBefore = datetime.datetime.utcnow() + datetime.timedelta(seconds=config.Scheduling.Options.WorkQueues.ReplyDelaySeconds)
        proposal = (yield txn.enqueue(
            cls,
            notBefore=notBefore,
            icalendarUid=calendar.resourceUID(),
            homeResourceID=home.id(),
            icalendarText=calendar.getTextWithTimezones(includeTimezones=not config.EnableTimezonesByReference),
        ))
        cls._enqueued()
        yield proposal.whenProposed()
        log.debug("ScheduleReplyCancelWork - enqueued for ID: {id}, UID: {uid}, attendee: {att}", id=proposal.workItem.workID, uid=calendar.resourceUID(), att=attendee)


    @inlineCallbacks
    def doWork(self):

        try:
            home = (yield self.transaction.calendarHomeWithResourceID(self.homeResourceID))
            attendeePrincipal = yield home.directoryService().recordWithUID(home.uid().decode("utf-8"))
            attendee = attendeePrincipal.canonicalCalendarUserAddress()
            calendar = Component.fromString(self.icalendarText)
            organizer = calendar.validOrganizerForScheduling()

            log.debug("ScheduleReplyCancelWork - running for ID: {id}, UID: {uid}, attendee: {att}", id=self.workID, uid=calendar.resourceUID(), att=attendee)

            # We need to get the UID lock for implicit processing.
            yield NamedLock.acquire(self.transaction, "ImplicitUIDLock:%s" % (hashlib.md5(calendar.resourceUID()).hexdigest(),))

            itipmsg = iTipGenerator.generateAttendeeReply(calendar, attendee, force_decline=True)

            # Send scheduling message - no need to process response as original resource is gone
            yield self.sendToOrganizer(home, "CANCEL", itipmsg, attendee, organizer)

            self._dequeued()

        except Exception, e:
            log.debug("ScheduleReplyCancelWork - exception ID: {id}, UID: '{uid}', {err}", id=self.workID, uid=calendar.resourceUID(), err=str(e))
            raise
        except:
            log.debug("ScheduleReplyCancelWork - bare exception ID: {id}, UID: '{uid}'", id=self.workID, uid=calendar.resourceUID())
            raise

        log.debug("ScheduleReplyCancelWork - done for ID: {id}, UID: {uid}, attendee: {att}", id=self.workID, uid=calendar.resourceUID(), att=attendee)



class ScheduleRefreshWork(WorkItem, fromTable(schema.SCHEDULE_REFRESH_WORK), ScheduleWorkMixin):
    """
    The associated work item table is SCHEDULE_REFRESH_WORK.

    This work item is used to trigger an iTIP refresh of attendees. This happens when one attendee
    replies to an invite, and we want to have the others attendees see that change - eventually. We
    are going to use the SCHEDULE_REFRESH_ATTENDEES table to track the list of attendees needing
    a refresh for each calendar object resource (identified by the organizer's resource-id for that
    calendar object). We want to do refreshes in batches with a configurable time between each batch.

    The tricky part here is handling race conditions, where two or more attendee replies happen at the
    same time, or happen whilst a previously queued refresh has started batch processing. Here is how
    we will handle that:

    1) Each time a refresh is needed we will add all attendees to the SCHEDULE_REFRESH_ATTENDEES table.
    This will happen even if those attendees are currently listed in that table. We ensure the table is
    not unique wrt to attendees - this means that two simultaneous refreshes can happily insert the
    same set of attendees without running into unique constraints and thus without having to use
    savepoints to cope with that. This will mean duplicate attendees listed in the table, but we take
    care of that when executing the work item, as per the next point. We also always schedule a new work
    item for the refresh - even if others are present. The work items are coalesced when executed, with
    the actual refresh only running at the time of the latest enqueued item. That ensures there is always
    a pause between a change that causes a refresh and then next actual refresh batch being done, giving
    some breathing space in case rapid changes are happening to the iCalendar data.

    2) When a work item is triggered we get the set of unique attendees needing a refresh from the
    SCHEDULE_REFRESH_ATTENDEES table. We split out a batch of those to actually refresh - with the
    others being left in the table as-is. We then remove the batch of attendees from the
    SCHEDULE_REFRESH_ATTENDEES table - this will remove duplicates. The refresh is then done and a
    new work item scheduled to do the next batch. We only stop rescheduling work items when nothing
    is found during the initial query. Note that if any refresh is done we will always reschedule work
    even if we know none remain. That should handle the case where a new refresh occurs whilst
    processing the last batch from a previous refresh.

    Hopefully the above methodology will deal with concurrency issues, preventing any excessive locking
    or failed inserts etc.
    """

    @classmethod
    @inlineCallbacks
    def refreshAttendees(cls, txn, organizer_resource, organizer_calendar, attendees):
        # See if there is already a pending refresh and merge current attendees into that list,
        # otherwise just mark all attendees as pending
        sra = schema.SCHEDULE_REFRESH_ATTENDEES
        pendingAttendees = (yield Select(
            [sra.ATTENDEE, ],
            From=sra,
            Where=sra.RESOURCE_ID == organizer_resource.id(),
        ).on(txn))
        pendingAttendees = [row[0] for row in pendingAttendees]
        attendeesToRefresh = set(attendees) - set(pendingAttendees)
        for attendee in attendeesToRefresh:
            yield Insert(
                {
                    sra.RESOURCE_ID: organizer_resource.id(),
                    sra.ATTENDEE: attendee,
                }
            ).on(txn)

        # Always queue up new work - coalescing happens when work is executed
        notBefore = datetime.datetime.utcnow() + datetime.timedelta(seconds=config.Scheduling.Options.WorkQueues.AttendeeRefreshBatchDelaySeconds)
        proposal = (yield txn.enqueue(
            cls,
            icalendarUid=organizer_resource.uid(),
            homeResourceID=organizer_resource._home.id(),
            resourceID=organizer_resource.id(),
            attendeeCount=len(attendees),
            notBefore=notBefore,
        ))
        cls._enqueued()
        yield proposal.whenProposed()
        log.debug("ScheduleRefreshWork - enqueued for ID: {id}, UID: {uid}, attendees: {att}", id=proposal.workItem.workID, uid=organizer_resource.uid(), att=",".join(attendeesToRefresh))


    @inlineCallbacks
    def doWork(self):

        # Look for other work items for this resource and ignore this one if other later ones exist
        srw = schema.SCHEDULE_REFRESH_WORK
        rows = (yield Select(
            (srw.WORK_ID,),
            From=srw,
            Where=(srw.HOME_RESOURCE_ID == self.homeResourceID).And(
                   srw.RESOURCE_ID == self.resourceID),
        ).on(self.transaction))
        if rows:
            log.debug("Schedule refresh for resource-id: {rid} - ignored", rid=self.resourceID)
            returnValue(None)

        log.debug("ScheduleRefreshWork - running for ID: {id}, UID: {uid}", id=self.workID, uid=self.icalendarUid)

        # Get the unique list of pending attendees and split into batch to process
        # TODO: do a DELETE ... and rownum <= N returning attendee - but have to fix Oracle to
        # handle multi-row returning. Would be better than entire select + delete of each one,
        # but need to make sure to use UNIQUE as there may be duplicate attendees.
        sra = schema.SCHEDULE_REFRESH_ATTENDEES
        pendingAttendees = (yield Select(
            [sra.ATTENDEE, ],
            From=sra,
            Where=sra.RESOURCE_ID == self.resourceID,
        ).on(self.transaction))
        pendingAttendees = list(set([row[0] for row in pendingAttendees]))

        # Nothing left so done
        if len(pendingAttendees) == 0:
            returnValue(None)

        attendeesToProcess = pendingAttendees[:config.Scheduling.Options.AttendeeRefreshBatch]
        pendingAttendees = pendingAttendees[config.Scheduling.Options.AttendeeRefreshBatch:]

        yield Delete(
            From=sra,
            Where=(sra.RESOURCE_ID == self.resourceID).And(sra.ATTENDEE.In(Parameter("attendeesToProcess", len(attendeesToProcess))))
        ).on(self.transaction, attendeesToProcess=attendeesToProcess)

        # Reschedule work item if pending attendees remain.
        if len(pendingAttendees) != 0:
            notBefore = datetime.datetime.utcnow() + datetime.timedelta(seconds=config.Scheduling.Options.WorkQueues.AttendeeRefreshBatchIntervalSeconds)
            yield self.transaction.enqueue(
                self.__class__,
                icalendarUid=self.icalendarUid,
                homeResourceID=self.homeResourceID,
                resourceID=self.resourceID,
                attendeeCount=len(pendingAttendees),
                notBefore=notBefore
            )

            self._enqueued()

        # Do refresh
        yield self._doDelayedRefresh(attendeesToProcess)

        self._dequeued()

        log.debug("ScheduleRefreshWork - done for ID: {id}, UID: {uid}", id=self.workID, uid=self.icalendarUid)


    @inlineCallbacks
    def _doDelayedRefresh(self, attendeesToProcess):
        """
        Do an attendee refresh that has been delayed until after processing of the request that called it. That
        requires that we create a new transaction to work with.

        @param attendeesToProcess: list of attendees to refresh.
        @type attendeesToProcess: C{list}
        """

        organizer_home = (yield self.transaction.calendarHomeWithResourceID(self.homeResourceID))
        organizer_resource = (yield organizer_home.objectResourceWithID(self.resourceID))
        if organizer_resource is not None:
            try:
                # We need to get the UID lock for implicit processing whilst we send the auto-reply
                # as the Organizer processing will attempt to write out data to other attendees to
                # refresh them. To prevent a race we need a lock.
                yield NamedLock.acquire(self.transaction, "ImplicitUIDLock:%s" % (hashlib.md5(organizer_resource.uid()).hexdigest(),))

                yield self._doRefresh(organizer_resource, attendeesToProcess)
            except Exception, e:
                log.debug("ImplicitProcessing - refresh exception UID: '{uid}', {exc}", uid=organizer_resource.uid(), exc=str(e))
                raise
            except:
                log.debug("ImplicitProcessing - refresh bare exception UID: '{uid}'", uid=organizer_resource.uid())
                raise
        else:
            log.debug("ImplicitProcessing - skipping refresh of missing ID: '{rid}'", rid=self.resourceID)


    @inlineCallbacks
    def _doRefresh(self, organizer_resource, only_attendees):
        """
        Do a refresh of attendees.

        @param organizer_resource: the resource for the organizer's calendar data
        @type organizer_resource: L{DAVResource}
        @param only_attendees: list of attendees to refresh (C{None} - refresh all)
        @type only_attendees: C{tuple}
        """
        log.debug("ImplicitProcessing - refreshing UID: '{uid}', Attendees: {att}", uid=organizer_resource.uid(), att=", ".join(only_attendees) if only_attendees else "all")
        from txdav.caldav.datastore.scheduling.implicit import ImplicitScheduler
        scheduler = ImplicitScheduler()
        yield scheduler.refreshAllAttendeesExceptSome(
            self.transaction,
            organizer_resource,
            only_attendees=only_attendees,
        )



class ScheduleAutoReplyWork(WorkItem, fromTable(schema.SCHEDULE_AUTO_REPLY_WORK), ScheduleWorkMixin):
    """
    The associated work item table is SCHEDULE_AUTO_REPLY_WORK.

    This work item is used to send auto-reply iTIP messages after the calendar data for the
    auto-accept user has been written to the user calendar.
    """

    @classmethod
    @inlineCallbacks
    def autoReply(cls, txn, resource, partstat):
        # Always queue up new work - coalescing happens when work is executed
        notBefore = datetime.datetime.utcnow() + datetime.timedelta(seconds=config.Scheduling.Options.WorkQueues.AutoReplyDelaySeconds)
        proposal = (yield txn.enqueue(
            cls,
            icalendarUid=resource.uid(),
            homeResourceID=resource._home.id(),
            resourceID=resource.id(),
            partstat=partstat,
            notBefore=notBefore,
        ))
        cls._enqueued()
        yield proposal.whenProposed()
        log.debug("ScheduleAutoReplyWork - enqueued for ID: {id}, UID: {uid}", id=proposal.workItem.workID, uid=resource.uid())


    @inlineCallbacks
    def doWork(self):

        log.debug("ScheduleAutoReplyWork - running for ID: {id}, UID: {uid}", id=self.workID, uid=self.icalendarUid)

        # Delete all other work items with the same pushID
        yield Delete(From=self.table,
            Where=self.table.RESOURCE_ID == self.resourceID
        ).on(self.transaction)

        # Do reply
        yield self._sendAttendeeAutoReply()

        self._dequeued()

        log.debug("ScheduleAutoReplyWork - done for ID: {id}, UID: {uid}", id=self.workID, uid=self.icalendarUid)


    @inlineCallbacks
    def _sendAttendeeAutoReply(self):
        """
        Auto-process the calendar option to generate automatic accept/decline status and
        send a reply if needed.

        We used to have logic to suppress attendee refreshes until after all auto-replies have
        been processed. We can't do that with the work queue (easily) so we are going to ignore
        that for now. It may not be a big deal given that the refreshes are themselves done in the
        queue and we only do the refresh when the last queued work item is processed.

        @param resource: calendar resource to process
        @type resource: L{CalendarObject}
        @param partstat: new partstat value
        @type partstat: C{str}
        """

        home = (yield self.transaction.calendarHomeWithResourceID(self.homeResourceID))
        resource = (yield home.objectResourceWithID(self.resourceID))
        if resource is not None:
            try:
                # We need to get the UID lock for implicit processing whilst we send the auto-reply
                # as the Organizer processing will attempt to write out data to other attendees to
                # refresh them. To prevent a race we need a lock.
                yield NamedLock.acquire(self.transaction, "ImplicitUIDLock:%s" % (hashlib.md5(resource.uid()).hexdigest(),))

                # Send out a reply
                log.debug("ImplicitProcessing - recipient '%s' processing UID: '%s' - auto-reply: %s" % (home.uid(), resource.uid(), self.partstat))
                from txdav.caldav.datastore.scheduling.implicit import ImplicitScheduler
                scheduler = ImplicitScheduler()
                yield scheduler.sendAttendeeReply(self.transaction, resource)
            except Exception, e:
                log.debug("ImplicitProcessing - auto-reply exception UID: '%s', %s" % (resource.uid(), str(e)))
                raise
            except:
                log.debug("ImplicitProcessing - auto-reply bare exception UID: '%s'" % (resource.uid(),))
                raise
        else:
            log.debug("ImplicitProcessing - skipping auto-reply of missing ID: '{rid}'", rid=self.resourceID)
