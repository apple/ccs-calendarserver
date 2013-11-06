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

import datetime
import hashlib
from twext.enterprise.dal.record import fromTable
from twext.enterprise.queue import WorkItem, PeerConnectionPool
from txdav.common.datastore.sql_tables import schema
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twext.enterprise.dal.syntax import Delete
from twext.who.idirectory import RecordType

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

        # Delete all other work items
        yield Delete(From=self.table, Where=None).on(self.transaction)

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
    pass


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
        # Pull in external proxy assignments and stick in proxy db
        # Figure out which groups matter
        groupGUIDs = yield self.groupsToRefresh()
        # For each of those groups, create a per-group refresh work item
        for groupGUID in groupGUIDs:
            notBefore = (datetime.datetime.utcnow() +
                datetime.timedelta(seconds=1))
            yield txn.enqueue(GroupRefreshWork,
                groupGUID=groupGUID, notBefore=notBefore)

        pass


    @inlineCallbacks
    def refreshGroup(self, txn, groupGUID):
        # Does the work of a per-group refresh work item
        # Faults in the flattened membership of a group, as GUIDs
        # and updates the GROUP_MEMBERSHIP table
        record = (yield self.directory.recordWithGUID(groupGUID))
        membershipHashContent = hashlib.md5()
        members = (yield _expandedMembers(record))
        members = list(members)
        members.sort(cmp=lambda x,y: cmp(x.guid, y.guid))
        for member in members:
            membershipHashContent.update(member.guid)
        membershipHash = membershipHashContent.hexdigest()
        results = (yield txn.groupByGUID(groupGUID))
        if not results:
            # Group is not yet in the DB
            cachedName = ""
            cachedMembershipHash = ""
            addGroup = True
        else:
            groupID, cachedName, cachedMembershipHash = results[0]
            addGroup = False

        if cachedMembershipHash != membershipHash:
            membershipChanged = True
            self.log.debug("Group '{group}' changed", group=record.fullNames[0])
        else:
            membershipChanged = False

        if addGroup:
            yield txn.addGroup(groupGUID, record.fullNames[0], membershipHash)
        else:
            yield txn.updateGroup(groupGUID, record.fullNames[0],
                membershipHash)

        results = (yield txn.groupByGUID(groupGUID))
        if len(results) == 1:
            groupID, name, cachedMembershipHash = results[0]
        else:
            self.log.error("Multiple group entries for {guid}", guid=groupGUID)

        if membershipChanged:
            newMemberGUIDs = set()
            for member in members:
                newMemberGUIDs.add(member.guid)
            yield self.synchronizeMembers(txn, groupID, newMemberGUIDs)

        yield self.scheduleEventReconciliations(txn, groupID)


    @inlineCallbacks
    def synchronizeMembers(self, txn, groupID, newMemberGUIDs):
        numRemoved = numAdded = 0
        cachedMemberGUIDs = set()
        results = (yield txn.membersOfGroup(groupID))
        for row in results:
            cachedMemberGUIDs.add(row[0])

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
        results = (yield txn.membersOfGroup(groupID))
        for row in results:
            record = (yield self.directory.recordWithGUID(row[0]))
            if record is not None:
                members.add(record)
        returnValue(members)




    # @inlineCallbacks
    def scheduleEventReconciliations(self, txn, groupID):
        """
        Find all events who have this groupID as an attendee and create
        work items for them.
        """
        return succeed(None)



    @inlineCallbacks
    def groupsToRefresh(self):
        delegatedGUIDs = set((yield self.proxyDB.getAllMembers()))
        self.log.info("There are %d proxies" % (len(delegatedGUIDs),))
        self.log.info("Retrieving group hierarchy from directory")

        # "groups" maps a group to its members; the keys and values consist
        # of whatever directory attribute is used to refer to members.  The
        # attribute value comes from record.cachedGroupsAlias().
        # "aliases" maps the record.cachedGroupsAlias() value for a group
        # back to the group's guid.
        groups, aliases = (yield self.getGroups(guids=delegatedGUIDs))
        groupGUIDs = set(aliases.keys())
        self.log.info("%d groups retrieved from the directory" %
            (len(groupGUIDs),))

        delegatedGUIDs = delegatedGUIDs.intersection(groupGUIDs)
        self.log.info("%d groups are proxies" % (len(delegatedGUIDs),))
        returnValue(delegatedGUIDs)
