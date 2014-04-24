# -*- test-case-name: txdav.who.test.test_groups -*-
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
from twext.enterprise.jobqueue import WorkItem, PeerConnectionPool
from twisted.internet.defer import inlineCallbacks, returnValue
from txdav.caldav.datastore.sql import CalendarStoreFeatures
from txdav.common.datastore.sql_tables import schema
import datetime
import hashlib

from twext.python.log import Logger
log = Logger()


class GroupCacherPollingWork(
    WorkItem,
    fromTable(schema.GROUP_CACHER_POLLING_WORK)
):

    group = "group_cacher_polling"

    @inlineCallbacks
    def doWork(self):

        # Delete all other work items
        yield Delete(From=self.table, Where=None).on(self.transaction)

        groupCacher = getattr(self.transaction, "_groupCacher", None)
        if groupCacher is not None:

            # Schedule next update

            notBefore = (
                datetime.datetime.utcnow() +
                datetime.timedelta(seconds=groupCacher.updateSeconds)
            )
            log.debug(
                "Scheduling next group cacher update: {when}", when=notBefore
            )
            yield self.transaction.enqueue(
                GroupCacherPollingWork,
                notBefore=notBefore
            )

            # New implmementation
            try:
                yield groupCacher.update(self.transaction)
            except Exception, e:
                log.error(
                    "Failed to update new group membership cache ({error})",
                    error=e
                )

        else:
            notBefore = (
                datetime.datetime.utcnow() +
                datetime.timedelta(seconds=10)
            )
            log.debug(
                "Rescheduling group cacher update: {when}", when=notBefore
            )
            yield self.transaction.enqueue(
                GroupCacherPollingWork,
                notBefore=notBefore
            )



@inlineCallbacks
def scheduleNextGroupCachingUpdate(store, seconds):

    notBefore = (
        datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
    )

    log.debug(
        "Scheduling next group cacher update: {when}", when=notBefore
    )

    def _enqueue(txn):
        return txn.enqueue(GroupCacherPollingWork, notBefore=notBefore)

    wp = yield store.inTransaction("scheduleNextGroupCachingUpdate", _enqueue)

    returnValue(wp)



def schedulePolledGroupCachingUpdate(store):
    """
    Schedules a group caching update work item in "the past" so
    PeerConnectionPool's overdue-item logic picks it up quickly.
    """
    seconds = -PeerConnectionPool.queueProcessTimeout
    return scheduleNextGroupCachingUpdate(store, seconds)



class GroupRefreshWork(WorkItem, fromTable(schema.GROUP_REFRESH_WORK)):

    group = property(lambda self: self.groupUid)

    @inlineCallbacks
    def doWork(self):
        # Delete all other work items for this group
        yield Delete(
            From=self.table, Where=(self.table.GROUP_UID == self.groupUid)
        ).on(self.transaction)

        groupCacher = getattr(self.transaction, "_groupCacher", None)
        if groupCacher is not None:

            try:
                yield groupCacher.refreshGroup(
                    self.transaction, self.groupUid.decode("utf-8")
                )
            except Exception, e:
                log.error(
                    "Failed to refresh group {group} {err}",
                    group=self.groupUid, err=e
                )

        else:
            notBefore = (
                datetime.datetime.utcnow() +
                datetime.timedelta(seconds=10)
            )
            log.debug(
                "Rescheduling group refresh for {group}: {when}",
                group=self.groupUid, when=notBefore
            )
            yield self.transaction.enqueue(
                GroupRefreshWork,
                groupUID=self.groupUid, notBefore=notBefore
            )



class GroupAttendeeReconciliationWork(
    WorkItem, fromTable(schema.GROUP_ATTENDEE_RECONCILE_WORK)
):

    group = property(
        lambda self: "{0}, {1}".format(self.groupID, self.resourceID)
    )

    @inlineCallbacks
    def doWork(self):

        # Delete all other work items for this event
        yield Delete(
            From=self.table,
            Where=self.table.RESOURCE_ID == self.resourceID,
        ).on(self.transaction)

        # get db object
        calendarObject = (yield CalendarStoreFeatures(self.transaction._store).calendarObjectWithID(self.transaction, self.resourceID))
        component = yield calendarObject.componentForUser()

        # Change a copy of the original, as we need the original cached on the resource
        # so we can do a diff to test implicit scheduling changes
        component = component.duplicate()

        # sync group attendees
        if (yield calendarObject.reconcileGroupAttendees(component)):
            yield calendarObject.setComponent(component)



def diffAssignments(old, new):
    """
    Compare two proxy assignment lists and return their differences in the form
    of two lists -- one for added/updated assignments, and one for removed
    assignments.

    @param old: dictionary of delegator: (readGroupUID, writeGroupUID)
    @type old: C{dict}

    @param new: dictionary of delegator: (readGroupUID, writeGroupUID)
    @type new: C{dict}

    @return: Tuple of two lists; the first list contains tuples of (delegator,
        (readGroupUID, writeGroupUID)), and represents all the new or updated
        assignments.  The second list contains all the delegators which used to
        have a delegate but don't anymore.
    """
    changed = []
    removed = []
    for key in old.iterkeys():
        if key not in new:
            removed.append(key)
        else:
            if old[key] != new[key]:
                changed.append((key, new[key]))
    for key in new.iterkeys():
        if key not in old:
            changed.append((key, new[key]))
    return changed, removed



class GroupCacher(object):
    log = Logger()


    def __init__(
        self, directory,
        updateSeconds=600,
        useExternalProxies=False,
        externalProxiesSource=None
    ):
        self.directory = directory
        self.useExternalProxies = useExternalProxies
        if useExternalProxies and externalProxiesSource is None:
            externalProxiesSource = self.directory.getExternalProxyAssignments
        self.externalProxiesSource = externalProxiesSource
        self.updateSeconds = updateSeconds


    @inlineCallbacks
    def update(self, txn):
        # TODO
        # Pull in external delegate assignments and stick in delegate db
        # if self.useExternalProxies:
        #     externalAssignments = (yield self.externalProxiesSource())
        # yield self.applyExternalAssignments(txn, externalAssignments)

        # Figure out which groups matter
        groupUIDs = yield self.groupsToRefresh(txn)
        self.log.debug(
            "Number of groups to refresh: {num}", num=len(groupUIDs)
        )
        # For each of those groups, create a per-group refresh work item
        for groupUID in groupUIDs:
            notBefore = (
                datetime.datetime.utcnow() +
                datetime.timedelta(seconds=1)
            )
            self.log.debug("Enqueuing group refresh for {u}", u=groupUID)
            yield txn.enqueue(
                GroupRefreshWork, groupUid=groupUID, notBefore=notBefore
            )
            self.log.debug("Enqueued group refresh for {u}", u=groupUID)


    @inlineCallbacks
    def applyExternalAssignments(self, txn, newAssignments):

        oldAssignments = (yield txn.externalDelegates())

        # external assignments is of the form:
        # { delegatorUID: (readDelegateGroupUID, writeDelegateGroupUID),
        # }

        changed, removed = diffAssignments(oldAssignments, newAssignments)
        if changed:
            for (
                delegatorUID, (readDelegateUID, writeDelegateUID)
            ) in changed:
                readDelegateGroupID = writeDelegateGroupID = None
                if readDelegateUID:
                    readDelegateGroupID, _ignore_name, hash, _ignore_modified = (
                        yield txn.groupByUID(readDelegateUID)
                    )
                if writeDelegateUID:
                    writeDelegateGroupID, _ignore_name, hash, _ignore_modified = (
                        yield txn.groupByUID(writeDelegateUID)
                    )
                yield txn.assignExternalDelegates(
                    delegatorUID, readDelegateGroupID, writeDelegateGroupID,
                    readDelegateUID, writeDelegateUID
                )
        if removed:
            for delegatorUID in removed:
                yield txn.assignExternalDelegates(
                    delegatorUID, None, None, None, None
                )


    @inlineCallbacks
    def refreshGroup(self, txn, groupUID):
        """
            Does the work of a per-group refresh work item
            Faults in the flattened membership of a group, as UIDs
            and updates the GROUP_MEMBERSHIP table
            WorkProposal is returned for tests
        """
        self.log.debug("Faulting in group: {g}", g=groupUID)
        record = (yield self.directory.recordWithUID(groupUID))
        if record is None:
            # the group has disappeared from the directory
            self.log.info("Group is missing: {g}", g=groupUID)
        else:
            self.log.debug("Got group record: {u}", u=record.uid)

        groupID, cachedName, cachedMembershipHash, _ignore_modified = (
            yield txn.groupByUID(
                groupUID,
                create=(record is not None)
            )
        )
        wps = tuple()
        if groupID:
            if record is not None:
                members = yield record.expandedMembers()
                name = record.fullNames[0]
            else:
                members = frozenset()
                name = cachedName

            membershipHashContent = hashlib.md5()
            members = list(members)
            members.sort(cmp=lambda x, y: cmp(x.uid, y.uid))
            for member in members:
                membershipHashContent.update(str(member.uid))
            membershipHash = membershipHashContent.hexdigest()

            if cachedMembershipHash != membershipHash:
                membershipChanged = True
                self.log.debug(
                    "Group '{group}' changed", group=name
                )
            else:
                membershipChanged = False

            if membershipChanged or record is not None:
                # also updates group mod date
                yield txn.updateGroup(groupUID, name, membershipHash)

            if membershipChanged:
                newMemberUIDs = set()
                for member in members:
                    newMemberUIDs.add(member.uid)
                yield self.synchronizeMembers(txn, groupID, newMemberUIDs)

                wps = yield self.scheduleEventReconciliations(txn, groupID)

        returnValue(wps)


    @inlineCallbacks
    def synchronizeMembers(self, txn, groupID, newMemberUIDs):
        numRemoved = numAdded = 0
        cachedMemberUIDs = (yield txn.membersOfGroup(groupID))

        for memberUID in cachedMemberUIDs:
            if memberUID not in newMemberUIDs:
                numRemoved += 1
                yield txn.removeMemberFromGroup(memberUID, groupID)

        for memberUID in newMemberUIDs:
            if memberUID not in cachedMemberUIDs:
                numAdded += 1
                yield txn.addMemberToGroup(memberUID, groupID)

        returnValue((numAdded, numRemoved))


    @inlineCallbacks
    def cachedMembers(self, txn, groupID):
        """
        The members of the given group as recorded in the db
        """
        members = set()
        memberUIDs = (yield txn.membersOfGroup(groupID))
        for uid in memberUIDs:
            record = (yield self.directory.recordWithUID(uid))
            if record is not None:
                members.add(record)
        returnValue(members)


    def cachedGroupsFor(self, txn, uid):
        """
        The UIDs of the groups the uid is a member of
        """
        return txn.groupsFor(uid)


    @inlineCallbacks
    def scheduleEventReconciliations(self, txn, groupID):
        """
        Find all events who have this groupID as an attendee and create
        work items for them.
        returns: WorkProposal
        """
        ga = schema.GROUP_ATTENDEE
        rows = yield Select(
            [ga.RESOURCE_ID, ],
            From=ga,
            Where=ga.GROUP_ID == groupID,
        ).on(txn)

        wps = []
        for [eventID] in rows:

            notBefore = (
                datetime.datetime.utcnow() +
                datetime.timedelta(seconds=10)
            )
            log.debug(
                "scheduling group reconciliation for "
                "({resourceID}, {groupID},): {when}",
                resourceID=eventID,
                groupID=groupID,
                when=notBefore
            )

            wp = yield txn.enqueue(
                GroupAttendeeReconciliationWork,
                resourceID=eventID,
                groupID=groupID,
                notBefore=notBefore
            )
            wps.append(wp)

        returnValue(tuple(wps))


    @inlineCallbacks
    def groupsToRefresh(self, txn):
        delegatedUIDs = set((yield txn.allGroupDelegates()))
        self.log.info(
            "There are {count} group delegates", count=len(delegatedUIDs)
        )

        attendeeGroupUIDs = set()

        # get all groups from events
        groupAttendee = schema.GROUP_ATTENDEE
        rows = yield Select(
            [groupAttendee.GROUP_ID, ],
            From=groupAttendee,
        ).on(txn)
        groupIDs = set([row[0] for row in rows])

        # get groupUIDs
        if groupIDs:
            gr = schema.GROUPS
            rows = yield Select(
                [gr.GROUP_UID, ],
                From=gr,
                Where=gr.GROUP_ID.In(groupIDs)
            ).on(txn)
            attendeeGroupUIDs = set([row[0] for row in rows])

        # FIXME: is this a good place to clear out unreferenced groups?

        returnValue(delegatedUIDs.union(attendeeGroupUIDs))
