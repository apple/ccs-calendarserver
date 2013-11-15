# -*- test-case-name: twext.who.test.test_groups -*-
##
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

"""
Group membership caching
"""

from twext.enterprise.dal.record import fromTable
from twext.enterprise.dal.syntax import Delete, Select
from twext.enterprise.queue import WorkItem, PeerConnectionPool
from twext.who.delegates import allGroupDelegates
from twext.who.idirectory import RecordType
from twisted.internet.defer import inlineCallbacks, returnValue
from twistedcaldav.ical import ignoredComponents
from txdav.common.datastore.sql_tables import schema
import datetime
import hashlib

from twext.python.log import Logger
log = Logger()


class GroupCacherPollingWork(WorkItem,
    fromTable(schema.GROUP_CACHER_POLLING_WORK)):

    group = "group_cacher_polling"

    @inlineCallbacks
    def doWork(self):

        # Delete all other work items
        yield Delete(From=self.table, Where=None).on(self.transaction)

        groupCacher = getattr(self.transaction, "_groupCacher", None)
        if groupCacher is not None:

            # Schedule next update
            notBefore = (datetime.datetime.utcnow() +
                datetime.timedelta(seconds=groupCacher.updateSeconds))
            log.debug("Scheduling next group cacher update: %s" % (notBefore,))
            yield self.transaction.enqueue(GroupCacherPollingWork,
                notBefore=notBefore)

            try:
                groupCacher.update(self.transaction)
            except Exception, e:
                log.error("Failed to update group membership cache (%s)" % (e,))

        else:
            notBefore = (datetime.datetime.utcnow() +
                datetime.timedelta(seconds=10))
            log.debug("Rescheduling group cacher update: %s" % (notBefore,))
            yield self.transaction.enqueue(GroupCacherPollingWork,
                notBefore=notBefore)



@inlineCallbacks
def scheduleNextGroupCachingUpdate(store, seconds):
    txn = store.newTransaction()
    notBefore = datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
    log.debug("Scheduling next group cacher update: %s" % (notBefore,))
    wp = (yield txn.enqueue(GroupCacherPollingWork, notBefore=notBefore))
    yield txn.commit()
    returnValue(wp)



def schedulePolledGroupCachingUpdate(store):
    """
    Schedules a group caching update work item in "the past" so PeerConnectionPool's
    overdue-item logic picks it up quickly.
    """
    seconds = -PeerConnectionPool.queueProcessTimeout
    return scheduleNextGroupCachingUpdate(store, seconds)



class GroupRefreshWork(WorkItem, fromTable(schema.GROUP_REFRESH_WORK)):

    group = property(lambda self: self.groupGUID)

    @inlineCallbacks
    def doWork(self):

        # Delete all other work items for this group
        yield Delete(From=self.table, Where=(self.table.GROUP_GUID == self.groupGUID)).on(self.transaction)

        groupCacher = getattr(self.transaction, "_groupCacher", None)
        if groupCacher is not None:

            try:
                groupCacher.refreshGroup(self.transaction, self.groupGUID)
            except Exception, e:
                log.error("Failed to refresh group {group} {err}",
                    group=self.groupGUID, err=e)

        else:
            notBefore = (datetime.datetime.utcnow() +
                datetime.timedelta(seconds=10))
            log.debug("Rescheduling group refresh for {group}: {when}",
                group=self.groupGUID, when=notBefore)
            yield self.transaction.enqueue(GroupRefreshWork,
                groupGUID=self.groupGUID, notBefore=notBefore)



class GroupAttendeeReconciliationWork(WorkItem, fromTable(schema.GROUP_ATTENDEE_RECONCILIATION_WORK)):

    group = property(lambda self: "%s, %s" % (self.groupID, self.eventID))

    @inlineCallbacks
    def doWork(self):

        # Delete all other work items for this group
        yield Delete(From=self.table,
            Where=((self.table.GROUP_ID == self.self.groupID).And(
                self.table.RESOURCE_ID == self.self.eventID)
            )
        ).on(self.transaction)

        # get group individual UIDs
        groupMemember = schema.GROUP_MEMBERSHIP
        rows = yield Select(
                [groupMemember.MEMBER_GUID, ],
                From=groupMemember,
                Where=groupMemember.GROUP_ID == self.groupID,
        ).on(self.transaction)
        individualGUIDs = [row[0] for row in rows]

        # get calendar Object
        calObject = schema.CALENDAR_OBJECT
        rows = yield Select(
                [calObject.CALENDAR_RESOURCE_ID, ],
                From=calObject,
                Where=calObject.RESOURCE_ID == self.eventID,
        ).on(self.transaction)

        calendarID = row[0][0]
        calendarHome = (yield self.Calendar._ownerHomeWithResourceID.on(
            self.transaction, resourceID=calendarID)
        )[0][0]

        calendar = yield calendarHome.childWithID(calendarID)
        calendarObject = yield calendar.objectResourceWithID(self.eventID)
        changed = False

        individualUUIDs = set(["urn:uuid:" + individualGUID for individualGUID in individualGUIDs])
        groupUUID = "urn:uuid:" + self.groupGUID()
        vcalendar = yield calendarObject.component()
        for component in vcalendar.subcomponents():
            if component.name() in ignoredComponents:
                continue

            oldAttendeeProps = component.getAttendees()
            oldAttendeeUUIDs = set([attendeeProp.value() for attendeeProp in oldAttendeeProps])

            # add new member attendees
            for individualUUID in individualUUIDs - oldAttendeeUUIDs:
                individualGUID = individualUUID[len("urn:uuid:"):]
                directoryRecord = self.transaction.directoryService().recordWithUID(individualGUID)
                newAttendeeProp = directoryRecord.attendee(params={"MEMBER": groupUUID})
                component.addProperty(newAttendeeProp)
                changed = True

            # remove attendee or update MEMBER attribute for non-primary attendees in this group,
            for attendeeProp in oldAttendeeProps:
                if attendeeProp.hasParameter("MEMBER"):
                    parameterValues = attendeeProp.parameterValues("MEMBER")
                    if groupUUID in parameterValues:
                        if attendeeProp.value() not in individualUUIDs:
                            attendeeProp.removeParameterValue("MEMBER", groupUUID)
                            if not attendeeProp.parameterValues("MEMBER"):
                                component.removeProperty(attendeeProp)
                            changed = True
                    else:
                        if attendeeProp.value() in individualUUIDs:
                            attendeeProp.setParameter("MEMBER", parameterValues + [groupUUID, ])
                            changed = True

        # replace old with new
        if changed:
            # TODO:  call calendarObject._setComponentInternal( vcalendar, mode ) instead?
            yield calendarObject.setComponent(vcalendar)



@inlineCallbacks
def _expandedMembers(record, members=None, records=None):
    """
    Return the expanded set of member records.  Intermediate groups are not returned
    in the results, but their members are.
    """
    if members is None:
        members = set()
    if records is None:
        records = set()

    if record not in records:
        records.add(record)
        for member in (yield record.members()):
            if member not in records:
                if member.recordType != RecordType.group:
                    members.add(member)
                yield _expandedMembers(member, members, records)

    returnValue(members)



class GroupCacher(object):
    log = Logger()

    def __init__(self, proxyDB, directory, store, updateSeconds,
        useExternalProxies=False, externalProxiesSource=None):
        self.proxyDB = proxyDB
        self.directory = directory
        self.store = store
        self.updateSeconds = updateSeconds
        self.useExternalProxies = useExternalProxies
        if useExternalProxies and externalProxiesSource is None:
            externalProxiesSource = self.directory.getExternalProxyAssignments
        self.externalProxiesSource = externalProxiesSource


    @inlineCallbacks
    def update(self, txn):
        # Pull in external delegate assignments and stick in delegate db
        # TODO

        # Figure out which groups matter
        groupGUIDs = yield self.groupsToRefresh()
        # For each of those groups, create a per-group refresh work item
        for groupGUID in groupGUIDs:
            notBefore = (datetime.datetime.utcnow() +
                datetime.timedelta(seconds=1))
            yield txn.enqueue(GroupRefreshWork,
                groupGUID=groupGUID, notBefore=notBefore)


    @inlineCallbacks
    def refreshGroup(self, txn, groupGUID):
        # Does the work of a per-group refresh work item
        # Faults in the flattened membership of a group, as GUIDs
        # and updates the GROUP_MEMBERSHIP table
        record = (yield self.directory.recordWithGUID(groupGUID))
        membershipHashContent = hashlib.md5()
        members = (yield _expandedMembers(record))
        members = list(members)
        members.sort(cmp=lambda x, y: cmp(x.guid, y.guid))
        for member in members:
            membershipHashContent.update(str(member.guid))
        membershipHash = membershipHashContent.hexdigest()
        groupID, cachedName, cachedMembershipHash = (yield #@UnusedVariable
            txn.groupByGUID(groupGUID))

        if cachedMembershipHash != membershipHash:
            membershipChanged = True
            self.log.debug("Group '{group}' changed", group=record.fullNames[0])
        else:
            membershipChanged = False

        yield txn.updateGroup(groupGUID, record.fullNames[0], membershipHash)

        if membershipChanged:
            newMemberGUIDs = set()
            for member in members:
                newMemberGUIDs.add(member.guid)
            yield self.synchronizeMembers(txn, groupID, newMemberGUIDs)

        yield self.scheduleEventReconciliations(txn, groupID, groupGUID)


    @inlineCallbacks
    def synchronizeMembers(self, txn, groupID, newMemberGUIDs):
        numRemoved = numAdded = 0
        cachedMemberGUIDs = (yield txn.membersOfGroup(groupID))

        for memberGUID in cachedMemberGUIDs:
            if memberGUID not in newMemberGUIDs:
                numRemoved += 1
                yield txn.removeMemberFromGroup(memberGUID, groupID)

        for memberGUID in newMemberGUIDs:
            if memberGUID not in cachedMemberGUIDs:
                numAdded += 1
                yield txn.addMemberToGroup(memberGUID, groupID)

        returnValue((numAdded, numRemoved))


    @inlineCallbacks
    def cachedMembers(self, txn, groupID):
        members = set()
        memberGUIDs = (yield txn.membersOfGroup(groupID))
        for guid in memberGUIDs:
            record = (yield self.directory.recordWithGUID(guid))
            if record is not None:
                members.add(record)
        returnValue(members)


    # @inlineCallbacks
    def scheduleEventReconciliations(self, txn, groupID, groupGUID):
        """
        Find all events who have this groupID as an attendee and create
        work items for them.
        """
        groupAttendee = schema.GROUP_ATTENDEE
        rows = yield Select(
                [groupAttendee.RESOURCE_ID, ],
                From=groupAttendee,
                Where=groupAttendee.GROUP_ID == groupID,
        ).on(txn)
        eventIDs = [row[0] for row in rows]

        for eventID in eventIDs:

            notBefore = (datetime.datetime.utcnow() +
                datetime.timedelta(seconds=10))
            log.debug("scheduling group reconciliation for ({eventID}, {groupID}, {groupGUID}): {when}",
                eventID=eventID,
                groupID=groupID,
                groupGUID=groupGUID,
                when=notBefore)

            yield txn.enqueue(GroupAttendeeReconciliationWork,
                eventID=eventID,
                groupID=groupID,
                groupGUID=groupGUID,
                notBefore=notBefore
            )


    @inlineCallbacks
    def groupsToRefresh(self, txn):
        delegatedGUIDs = set((yield allGroupDelegates(txn)))
        self.log.info("There are %d group delegates" % (len(delegatedGUIDs),))

        # TODO: Retrieve the set of attendee group guids
        attendeeGroupGUIDs = set()

        returnValue(delegatedGUIDs.union(attendeeGroupGUIDs))
