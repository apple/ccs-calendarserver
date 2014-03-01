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
from twext.enterprise.jobqueue import WorkItem, PeerConnectionPool
from txdav.who.delegates import allGroupDelegates
from twext.who.idirectory import RecordType
from twisted.internet.defer import inlineCallbacks, returnValue
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

        oldGroupCacher = getattr(self.transaction, "_groupCacher", None)
        newGroupCacher = getattr(self.transaction, "_newGroupCacher", None)
        if oldGroupCacher is not None or newGroupCacher is not None:

            # Schedule next update

            # TODO: Be sure to move updateSeconds to the new cacher
            # implementation
            notBefore = (
                datetime.datetime.utcnow() +
                datetime.timedelta(seconds=oldGroupCacher.updateSeconds)
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
                newGroupCacher.update(self.transaction)
            except Exception, e:
                log.error(
                    "Failed to update new group membership cache ({error})",
                    error=e
                )

            # Old implmementation
            try:
                oldGroupCacher.updateCache()
            except Exception, e:
                log.error(
                    "Failed to update old group membership cache ({error})",
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
    txn = store.newTransaction()
    notBefore = (
        datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
    )
    log.debug(
        "Scheduling next group cacher update: {when}", when=notBefore
    )
    wp = (yield txn.enqueue(GroupCacherPollingWork, notBefore=notBefore))
    yield txn.commit()
    returnValue(wp)



def schedulePolledGroupCachingUpdate(store):
    """
    Schedules a group caching update work item in "the past" so
    PeerConnectionPool's overdue-item logic picks it up quickly.
    """
    seconds = -PeerConnectionPool.queueProcessTimeout
    return scheduleNextGroupCachingUpdate(store, seconds)



class GroupRefreshWork(WorkItem, fromTable(schema.GROUP_REFRESH_WORK)):

    group = property(lambda self: self.groupGUID)

    @inlineCallbacks
    def doWork(self):

        # Delete all other work items for this group
        yield Delete(
            From=self.table, Where=(self.table.GROUP_GUID == self.groupGUID)
        ).on(self.transaction)

        groupCacher = getattr(self.transaction, "_groupCacher", None)
        if groupCacher is not None:

            try:
                groupCacher.refreshGroup(self.transaction, self.groupGUID)
            except Exception, e:
                log.error(
                    "Failed to refresh group {group} {err}",
                    group=self.groupGUID, err=e
                )

        else:
            notBefore = (
                datetime.datetime.utcnow() +
                datetime.timedelta(seconds=10)
            )
            log.debug(
                "Rescheduling group refresh for {group}: {when}",
                group=self.groupGUID, when=notBefore
            )
            yield self.transaction.enqueue(
                GroupRefreshWork,
                groupGUID=self.groupGUID, notBefore=notBefore
            )



class GroupAttendeeReconciliationWork(
    WorkItem, fromTable(schema.GROUP_ATTENDEE_RECONCILIATION_WORK)
):

    group = property(
        lambda self: "{0}, {1}".format(self.groupID, self.eventID)
    )

    @inlineCallbacks
    def doWork(self):

        # Delete all other work items for this group
        yield Delete(
            From=self.table,
            Where=((self.table.GROUP_ID == self.self.groupID).And(
                self.table.RESOURCE_ID == self.self.eventID)
            )
        ).on(self.transaction)

    # TODO: Pull this over from groupcacher branch



@inlineCallbacks
def expandedMembers(record, members=None, records=None):
    """
    Return the expanded set of member records.  Intermediate groups are not
    returned in the results, but their members are.
    """
    if members is None:
        members = set()
    if records is None:
        records = set()

    if record not in records:
        records.add(record)
        for member in (yield record.members()):
            if member not in records:
                #TODO:  HACK for old-style XML. FIX
                if (
                    member.recordType != RecordType.group and
                    str(member.recordType) != "groups"
                ):
                    members.add(member)
                yield expandedMembers(member, members, records)

    returnValue(members)



def diffAssignments(old, new):
    """
    Compare two proxy assignment lists and return their differences in the form
    of two lists -- one for added/updated assignments, and one for removed
    assignments.

    @param old: dictionary of delegator: (readGroupGUID, writeGroupGUID)
    @type old: C{dict}

    @param new: dictionary of delegator: (readGroupGUID, writeGroupGUID)
    @type new: C{dict}

    @return: Tuple of two lists; the first list contains tuples of (delegator,
        (readGroupGUID, writeGroupGUID)), and represents all the new or updated
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
        useExternalProxies=False, externalProxiesSource=None
    ):
        self.directory = directory
        self.useExternalProxies = useExternalProxies
        if useExternalProxies and externalProxiesSource is None:
            externalProxiesSource = self.directory.getExternalProxyAssignments
        self.externalProxiesSource = externalProxiesSource


    @inlineCallbacks
    def update(self, txn):
        # TODO
        # Pull in external delegate assignments and stick in delegate db
        # if self.useExternalProxies:
        #     externalAssignments = (yield self.externalProxiesSource())
        # yield self.applyExternalAssignments(txn, externalAssignments)

        # Figure out which groups matter
        groupGUIDs = yield self.groupsToRefresh(txn)
        self.log.debug(
            "Number of groups to refresh: {num}", num=len(groupGUIDs)
        )
        # For each of those groups, create a per-group refresh work item
        for groupGUID in groupGUIDs:
            notBefore = (
                datetime.datetime.utcnow() +
                datetime.timedelta(seconds=1)
            )
            yield txn.enqueue(
                GroupRefreshWork, groupGUID=groupGUID, notBefore=notBefore
            )


    @inlineCallbacks
    def applyExternalAssignments(self, txn, newAssignments):

        oldAssignments = (yield txn.externalDelegates())

        # external assignments is of the form:
        # { delegatorGUID: (readDelegateGroupGUID, writeDelegateGroupGUID),
        # }

        changed, removed = diffAssignments(oldAssignments, newAssignments)
        if changed:
            for (
                delegatorGUID, (readDelegateGUID, writeDelegateGUID)
            ) in changed:
                readDelegateGroupID = writeDelegateGroupID = None
                if readDelegateGUID:
                    readDelegateGroupID, _ignore_name, hash = (
                        yield txn.groupByGUID(readDelegateGUID)
                    )
                if writeDelegateGUID:
                    writeDelegateGroupID, _ignore_name, hash = (
                        yield txn.groupByGUID(writeDelegateGUID)
                    )
                yield txn.assignExternalDelegates(
                    delegatorGUID, readDelegateGroupID, writeDelegateGroupID,
                    readDelegateGUID, writeDelegateGUID
                )
        if removed:
            for delegatorGUID in removed:
                yield txn.assignExternalDelegates(
                    delegatorGUID, None, None, None, None
                )


    @inlineCallbacks
    def refreshGroup(self, txn, groupGUID):
        # Does the work of a per-group refresh work item
        # Faults in the flattened membership of a group, as GUIDs
        # and updates the GROUP_MEMBERSHIP table
        record = (yield self.directory.recordWithGUID(groupGUID))
        membershipHashContent = hashlib.md5()
        members = (yield expandedMembers(record))
        members = list(members)
        members.sort(cmp=lambda x, y: cmp(x.guid, y.guid))
        for member in members:
            membershipHashContent.update(str(member.guid))
        membershipHash = membershipHashContent.hexdigest()
        groupID, _ignore_cachedName, cachedMembershipHash = (
            yield txn.groupByGUID(groupGUID)
        )

        if cachedMembershipHash != membershipHash:
            membershipChanged = True
            self.log.debug(
                "Group '{group}' changed", group=record.fullNames[0]
            )
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
        """
        The members of the given group as recorded in the db
        """
        members = set()
        memberGUIDs = (yield txn.membersOfGroup(groupID))
        for guid in memberGUIDs:
            record = (yield self.directory.recordWithGUID(guid))
            if record is not None:
                members.add(record)
        returnValue(members)


    def cachedGroupsFor(self, txn, guid):
        """
        The IDs of the groups the guid is a member of
        """
        return txn.groupsFor(guid)


    @inlineCallbacks
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

            notBefore = (
                datetime.datetime.utcnow() +
                datetime.timedelta(seconds=10)
            )
            log.debug(
                "scheduling group reconciliation for "
                "({eventID}, {groupID}, {groupGUID}): {when}",
                eventID=eventID,
                groupID=groupID,
                groupGUID=groupGUID,
                when=notBefore)

            yield txn.enqueue(
                GroupAttendeeReconciliationWork,
                eventID=eventID,
                groupID=groupID,
                groupGUID=groupGUID,
                notBefore=notBefore
            )


    @inlineCallbacks
    def groupsToRefresh(self, txn):
        delegatedGUIDs = set((yield allGroupDelegates(txn)))
        self.log.info(
            "There are {count} group delegates", count=len(delegatedGUIDs)
        )

        attendeeGroupGUIDs = set()

        # get all groups from events
        groupAttendee = schema.GROUP_ATTENDEE
        rows = yield Select(
            [groupAttendee.GROUP_ID, ],
            From=groupAttendee,
        ).on(txn)
        groupIDs = set([row[0] for row in rows])

        # get groupGUIDs
        if groupIDs:
            gr = schema.GROUPS
            rows = yield Select(
                [gr.GROUP_GUID, ],
                From=gr,
                Where=gr.GROUP_ID.In(groupIDs)
            ).on(txn)
            attendeeGroupGUIDs = set([row[0] for row in rows])

        returnValue(delegatedGUIDs.union(attendeeGroupGUIDs))
