# -*- test-case-name: twext.enterprise.dal.test.test_record -*-
##
# Copyright (c) 2015 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.record import SerializableRecord, fromTable
from twext.enterprise.dal.syntax import SavepointAction, Select
from twext.python.log import Logger
from twisted.internet.defer import inlineCallbacks, returnValue
from txdav.common.datastore.sql_tables import schema
from txdav.common.icommondatastore import AllRetriesFailed, NotFoundError
from txdav.who.delegates import Delegates
import datetime
import hashlib

log = Logger()

"""
Classes and methods that relate to directory objects in the SQL store. e.g.,
delegates, groups etc
"""

class GroupsRecord(SerializableRecord, fromTable(schema.GROUPS)):
    """
    @DynamicAttrs
    L{Record} for L{schema.GROUPS}.
    """

    @classmethod
    def groupsForMember(cls, txn, memberUID):

        return GroupsRecord.query(
            txn,
            GroupsRecord.groupID.In(
                GroupMembershipRecord.queryExpr(
                    GroupMembershipRecord.memberUID == memberUID.encode("utf-8"),
                    attributes=(GroupMembershipRecord.groupID,),
                )
            ),
        )



class GroupMembershipRecord(SerializableRecord, fromTable(schema.GROUP_MEMBERSHIP)):
    """
    @DynamicAttrs
    L{Record} for L{schema.GROUP_MEMBERSHIP}.
    """
    pass



class DelegateRecord(SerializableRecord, fromTable(schema.DELEGATES)):
    """
    @DynamicAttrs
    L{Record} for L{schema.DELEGATES}.
    """
    pass



class DelegateGroupsRecord(SerializableRecord, fromTable(schema.DELEGATE_GROUPS)):
    """
    @DynamicAttrs
    L{Record} for L{schema.DELEGATE_GROUPS}.
    """

    @classmethod
    def allGroupDelegates(cls, txn):
        """
        Get the directly-delegated-to groups.
        """

        return GroupsRecord.query(
            txn,
            GroupsRecord.groupID.In(
                DelegateGroupsRecord.queryExpr(
                    None,
                    attributes=(DelegateGroupsRecord.groupID,),
                )
            ),
        )


    @classmethod
    def delegateGroups(cls, txn, delegator, readWrite):
        """
        Get the directly-delegated-to groups.
        """

        return GroupsRecord.query(
            txn,
            GroupsRecord.groupID.In(
                DelegateGroupsRecord.queryExpr(
                    (DelegateGroupsRecord.delegator == delegator.encode("utf-8")).And(
                        DelegateGroupsRecord.readWrite == (1 if readWrite else 0)
                    ),
                    attributes=(DelegateGroupsRecord.groupID,),
                )
            ),
        )


    @classmethod
    def indirectDelegators(cls, txn, delegate, readWrite):
        """
        Get delegators who have delegated to groups the delegate is a member of.
        """

        return cls.query(
            txn,
            cls.groupID.In(
                GroupMembershipRecord.queryExpr(
                    GroupMembershipRecord.memberUID == delegate.encode("utf-8"),
                    attributes=(GroupMembershipRecord.groupID,),
                )
            ).And(cls.readWrite == (1 if readWrite else 0)),
        )


    @classmethod
    def indirectDelegates(cls, txn, delegator, readWrite):
        """
        Get delegates who are in groups which have been delegated to.
        """

        return GroupMembershipRecord.query(
            txn,
            GroupMembershipRecord.groupID.In(
                DelegateGroupsRecord.queryExpr(
                    (DelegateGroupsRecord.delegator == delegator.encode("utf-8")).And(
                        DelegateGroupsRecord.readWrite == (1 if readWrite else 0)
                    ),
                    attributes=(DelegateGroupsRecord.groupID,),
                )
            ),
        )


    @classmethod
    @inlineCallbacks
    def delegatorGroups(cls, txn, delegator):
        """
        Get delegator/group pairs for the specified delegator.
        """

        # Do a join to get what we need
        rows = yield Select(
            list(DelegateGroupsRecord.table) + list(GroupsRecord.table),
            From=DelegateGroupsRecord.table.join(GroupsRecord.table, DelegateGroupsRecord.groupID == GroupsRecord.groupID),
            Where=(DelegateGroupsRecord.delegator == delegator.encode("utf-8"))
        ).on(txn)

        results = []
        delegatorNames = [DelegateGroupsRecord.__colmap__[column] for column in list(DelegateGroupsRecord.table)]
        groupsNames = [GroupsRecord.__colmap__[column] for column in list(GroupsRecord.table)]
        split_point = len(delegatorNames)
        for row in rows:
            delegatorRow = row[:split_point]
            delegatorRecord = DelegateGroupsRecord()
            delegatorRecord._attributesFromRow(zip(delegatorNames, delegatorRow))
            delegatorRecord.transaction = txn
            groupsRow = row[split_point:]
            groupsRecord = GroupsRecord()
            groupsRecord._attributesFromRow(zip(groupsNames, groupsRow))
            groupsRecord.transaction = txn
            results.append((delegatorRecord, groupsRecord,))

        returnValue(results)



class ExternalDelegateGroupsRecord(SerializableRecord, fromTable(schema.EXTERNAL_DELEGATE_GROUPS)):
    """
    @DynamicAttrs
    L{Record} for L{schema.EXTERNAL_DELEGATE_GROUPS}.
    """
    pass



class GroupsAPIMixin(object):
    """
    A mixin for L{CommonStoreTransaction} that covers the groups API.
    """

    @inlineCallbacks
    def addGroup(self, groupUID, name, membershipHash):
        """
        @type groupUID: C{unicode}
        @type name: C{unicode}
        @type membershipHash: C{str}
        """
        record = yield self.directoryService().recordWithUID(groupUID)
        if record is None:
            returnValue(None)

        group = yield GroupsRecord.create(
            self,
            name=name.encode("utf-8"),
            groupUID=groupUID.encode("utf-8"),
            membershipHash=membershipHash,
        )

        yield self.refreshGroup(group, record)
        returnValue(group)


    def updateGroup(self, groupUID, name, membershipHash, extant=True):
        """
        @type groupUID: C{unicode}
        @type name: C{unicode}
        @type membershipHash: C{str}
        @type extant: C{boolean}
        """
        timestamp = datetime.datetime.utcnow()
        group = yield self.groupByUID(groupUID, create=False)
        if group is not None:
            yield group.update(
                name=name.encode("utf-8"),
                membershipHash=membershipHash,
                extant=(1 if extant else 0),
                modified=timestamp,
            )


    @inlineCallbacks
    def groupByUID(self, groupUID, create=True):
        """
        Return or create a record for the group UID.

        @type groupUID: C{unicode}

        @return: Deferred firing with tuple of group ID C{str}, group name
            C{unicode}, membership hash C{str}, modified timestamp, and
            extant C{boolean}
        """
        results = yield GroupsRecord.query(
            self,
            GroupsRecord.groupUID == groupUID.encode("utf-8")
        )
        if results:
            returnValue(results[0])
        elif create:
            savepoint = SavepointAction("groupByUID")
            yield savepoint.acquire(self)
            try:
                group = yield self.addGroup(groupUID, u"", "")
                if group is None:
                    # The record does not actually exist within the directory
                    yield savepoint.release(self)
                    returnValue(None)

            except Exception:
                yield savepoint.rollback(self)
                results = yield GroupsRecord.query(
                    self,
                    GroupsRecord.groupUID == groupUID.encode("utf-8")
                )
                returnValue(results[0] if results else None)
            else:
                yield savepoint.release(self)
                returnValue(group)
        else:
            returnValue(None)


    @inlineCallbacks
    def groupByID(self, groupID):
        """
        Given a group ID, return the group UID, or raise NotFoundError

        @type groupID: C{str}
        @return: Deferred firing with a tuple of group UID C{unicode},
            group name C{unicode}, membership hash C{str}, and extant C{boolean}
        """
        results = yield GroupsRecord.query(
            self,
            GroupsRecord.groupID == groupID,
        )
        if results:
            returnValue(results[0])
        else:
            raise NotFoundError



class GroupCacherAPIMixin(object):
    """
    A mixin for L{CommonStoreTransaction} that covers the group cacher API.
    """

    def addMemberToGroup(self, memberUID, groupID):
        return GroupMembershipRecord.create(self, groupID=groupID, memberUID=memberUID.encode("utf-8"))


    def removeMemberFromGroup(self, memberUID, groupID):
        return GroupMembershipRecord.deletesimple(
            self, groupID=groupID, memberUID=memberUID.encode("utf-8")
        )


    @inlineCallbacks
    def groupMemberUIDs(self, groupID):
        """
        Returns the cached set of UIDs for members of the given groupID.
        Sub-groups are not returned in the results but their members are,
        because the group membership has already been expanded/flattened
        before storing in the db.

        @param groupID: the group ID
        @type groupID: C{int}
        @return: the set of member UIDs
        @rtype: a Deferred which fires with a set() of C{str} UIDs
        """

        members = yield GroupMembershipRecord.query(self, GroupMembershipRecord.groupID == groupID)
        returnValue(set([record.memberUID.decode("utf-8") for record in members]))


    @inlineCallbacks
    def refreshGroup(self, group, record):
        """
        @param group: the group record
        @type group: L{GroupsRecord}
        @param record: the directory record
        @type record: C{iDirectoryRecord}

        @return: Deferred firing with membershipChanged C{boolean}

        """

        if record is not None:
            memberUIDs = yield record.expandedMemberUIDs()
            name = record.displayName
            extant = True
        else:
            memberUIDs = frozenset()
            name = group.name
            extant = False

        membershipHashContent = hashlib.md5()
        for memberUID in sorted(memberUIDs):
            membershipHashContent.update(str(memberUID))
        membershipHash = membershipHashContent.hexdigest()

        if group.membershipHash != membershipHash:
            membershipChanged = True
            log.debug(
                "Group '{group}' changed", group=name
            )
        else:
            membershipChanged = False

        if membershipChanged or extant != group.extant:
            # also updates group mod date
            yield group.update(
                name=name,
                membershipHash=membershipHash,
                extant=(1 if extant else 0),
            )

        if membershipChanged:
            addedUIDs, removedUIDs = yield self.synchronizeMembers(group.groupID, set(memberUIDs))
        else:
            addedUIDs = removedUIDs = None

        returnValue((membershipChanged, addedUIDs, removedUIDs,))


    @inlineCallbacks
    def synchronizeMembers(self, groupID, newMemberUIDs):
        """
        Update the group membership table in the database to match the new membership list. This
        method will diff the existing set with the new set and apply the changes. It also calls out
        to a groupChanged() method with the set of added and removed members so that other modules
        that depend on groups can monitor the changes.

        @param groupID: group id of group to update
        @type groupID: L{str}
        @param newMemberUIDs: set of new member UIDs in the group
        @type newMemberUIDs: L{set} of L{str}
        """
        cachedMemberUIDs = yield self.groupMemberUIDs(groupID)

        removed = cachedMemberUIDs - newMemberUIDs
        for memberUID in removed:
            yield self.removeMemberFromGroup(memberUID, groupID)

        added = newMemberUIDs - cachedMemberUIDs
        for memberUID in added:
            yield self.addMemberToGroup(memberUID, groupID)

        yield self.groupChanged(groupID, added, removed)

        returnValue((added, removed,))


    @inlineCallbacks
    def groupChanged(self, groupID, addedUIDs, removedUIDs):
        """
        Called when membership of a group changes.

        @param groupID: group id of group that changed
        @type groupID: L{str}
        @param addedUIDs: set of new member UIDs added to the group
        @type addedUIDs: L{set} of L{str}
        @param removedUIDs: set of old member UIDs removed from the group
        @type removedUIDs: L{set} of L{str}
        """
        yield Delegates.groupChanged(self, groupID, addedUIDs, removedUIDs)


    @inlineCallbacks
    def groupMembers(self, groupID):
        """
        The members of the given group as recorded in the db
        """
        members = set()
        memberUIDs = (yield self.groupMemberUIDs(groupID))
        for uid in memberUIDs:
            record = (yield self.directoryService().recordWithUID(uid))
            if record is not None:
                members.add(record)
        returnValue(members)


    @inlineCallbacks
    def groupUIDsFor(self, uid):
        """
        Returns the cached set of UIDs for the groups this given uid is
        a member of.

        @param uid: the uid
        @type uid: C{unicode}
        @return: the set of group IDs
        @rtype: a Deferred which fires with a set() of C{int} group IDs
        """
        groups = yield GroupsRecord.groupsForMember(self, uid)
        returnValue(set([group.groupUID.decode("utf-8") for group in groups]))



class DelegatesAPIMixin(object):
    """
    A mixin for L{CommonStoreTransaction} that covers the delegates API.
    """

    @inlineCallbacks
    def addDelegate(self, delegator, delegate, readWrite):
        """
        Adds a row to the DELEGATES table.  The delegate should not be a
        group.  To delegate to a group, call addDelegateGroup() instead.

        @param delegator: the UID of the delegator
        @type delegator: C{unicode}
        @param delegate: the UID of the delegate
        @type delegate: C{unicode}
        @param readWrite: grant read and write access if True, otherwise
            read-only access
        @type readWrite: C{boolean}
        """

        def _addDelegate(subtxn):
            return DelegateRecord.create(
                subtxn,
                delegator=delegator.encode("utf-8"),
                delegate=delegate.encode("utf-8"),
                readWrite=1 if readWrite else 0
            )

        try:
            yield self.subtransaction(_addDelegate, retries=0, failureOK=True)
        except AllRetriesFailed:
            pass


    @inlineCallbacks
    def addDelegateGroup(self, delegator, delegateGroupID, readWrite,
                         isExternal=False):
        """
        Adds a row to the DELEGATE_GROUPS table.  The delegate should be a
        group.  To delegate to a person, call addDelegate() instead.

        @param delegator: the UID of the delegator
        @type delegator: C{unicode}
        @param delegateGroupID: the GROUP_ID of the delegate group
        @type delegateGroupID: C{int}
        @param readWrite: grant read and write access if True, otherwise
            read-only access
        @type readWrite: C{boolean}
        """

        def _addDelegateGroup(subtxn):
            return DelegateGroupsRecord.create(
                subtxn,
                delegator=delegator.encode("utf-8"),
                groupID=delegateGroupID,
                readWrite=1 if readWrite else 0,
                isExternal=1 if isExternal else 0
            )

        try:
            yield self.subtransaction(_addDelegateGroup, retries=0, failureOK=True)
        except AllRetriesFailed:
            pass


    def removeDelegate(self, delegator, delegate, readWrite):
        """
        Removes a row from the DELEGATES table.  The delegate should not be a
        group.  To remove a delegate group, call removeDelegateGroup() instead.

        @param delegator: the UID of the delegator
        @type delegator: C{unicode}
        @param delegate: the UID of the delegate
        @type delegate: C{unicode}
        @param readWrite: remove read and write access if True, otherwise
            read-only access
        @type readWrite: C{boolean}
        """
        return DelegateRecord.deletesimple(
            self,
            delegator=delegator.encode("utf-8"),
            delegate=delegate.encode("utf-8"),
            readWrite=(1 if readWrite else 0),
        )


    def removeDelegates(self, delegator, readWrite):
        """
        Removes all rows for this delegator/readWrite combination from the
        DELEGATES table.

        @param delegator: the UID of the delegator
        @type delegator: C{unicode}
        @param readWrite: remove read and write access if True, otherwise
            read-only access
        @type readWrite: C{boolean}
        """
        return DelegateRecord.deletesimple(
            self,
            delegator=delegator.encode("utf-8"),
            readWrite=(1 if readWrite else 0)
        )


    def removeDelegateGroup(self, delegator, delegateGroupID, readWrite):
        """
        Removes a row from the DELEGATE_GROUPS table.  The delegate should be a
        group.  To remove a delegate person, call removeDelegate() instead.

        @param delegator: the UID of the delegator
        @type delegator: C{unicode}
        @param delegateGroupID: the GROUP_ID of the delegate group
        @type delegateGroupID: C{int}
        @param readWrite: remove read and write access if True, otherwise
            read-only access
        @type readWrite: C{boolean}
        """
        return DelegateGroupsRecord.deletesimple(
            self,
            delegator=delegator.encode("utf-8"),
            groupID=delegateGroupID,
            readWrite=(1 if readWrite else 0),
        )


    def removeDelegateGroups(self, delegator, readWrite):
        """
        Removes all rows for this delegator/readWrite combination from the
        DELEGATE_GROUPS table.

        @param delegator: the UID of the delegator
        @type delegator: C{unicode}
        @param readWrite: remove read and write access if True, otherwise
            read-only access
        @type readWrite: C{boolean}
        """
        return DelegateGroupsRecord.deletesimple(
            self,
            delegator=delegator.encode("utf-8"),
            readWrite=(1 if readWrite else 0),
        )


    @inlineCallbacks
    def delegates(self, delegator, readWrite, expanded=False):
        """
        Returns the UIDs of all delegates for the given delegator.  If
        expanded is False, only the direct delegates (users and groups)
        are returned.  If expanded is True, the expanded membership is
        returned, not including the groups themselves.

        @param delegator: the UID of the delegator
        @type delegator: C{unicode}
        @param readWrite: the access-type to check for; read and write
            access if True, otherwise read-only access
        @type readWrite: C{boolean}
        @returns: the UIDs of the delegates (for the specified access
            type)
        @rtype: a Deferred resulting in a set
        """
        delegates = set()
        delegatorU = delegator.encode("utf-8")

        # First get the direct delegates
        results = yield DelegateRecord.query(
            self,
            (DelegateRecord.delegator == delegatorU).And(
                DelegateRecord.readWrite == (1 if readWrite else 0)
            )
        )
        delegates.update([record.delegate.decode("utf-8") for record in results])

        if expanded:
            # Get those who are in groups which have been delegated to
            results = yield DelegateGroupsRecord.indirectDelegates(
                self, delegator, readWrite
            )
            # Skip the delegator if they are in one of the groups
            delegates.update([record.memberUID.decode("utf-8") for record in results if record.memberUID != delegatorU])

        else:
            # Get the directly-delegated-to groups
            results = yield DelegateGroupsRecord.delegateGroups(
                self, delegator, readWrite,
            )
            delegates.update([record.groupUID.decode("utf-8") for record in results])

        returnValue(delegates)


    @inlineCallbacks
    def delegators(self, delegate, readWrite):
        """
        Returns the UIDs of all delegators which have granted access to
        the given delegate, either directly or indirectly via groups.

        @param delegate: the UID of the delegate
        @type delegate: C{unicode}
        @param readWrite: the access-type to check for; read and write
            access if True, otherwise read-only access
        @type readWrite: C{boolean}
        @returns: the UIDs of the delegators (for the specified access
            type)
        @rtype: a Deferred resulting in a set
        """
        delegators = set()
        delegateU = delegate.encode("utf-8")

        # First get the direct delegators
        results = yield DelegateRecord.query(
            self,
            (DelegateRecord.delegate == delegateU).And(
                DelegateRecord.readWrite == (1 if readWrite else 0)
            )
        )
        delegators.update([record.delegator.decode("utf-8") for record in results])

        # Finally get those who have delegated to groups the delegate
        # is a member of
        results = yield DelegateGroupsRecord.indirectDelegators(
            self, delegate, readWrite
        )
        # Skip the delegator if they are in one of the groups
        delegators.update([record.delegator.decode("utf-8") for record in results if record.delegator != delegateU])

        returnValue(delegators)


    @inlineCallbacks
    def delegatorsToGroup(self, delegateGroupID, readWrite):
        """
        Return the UIDs of those who have delegated to the given group with the
        given access level.

        @param delegateGroupID: the group ID of the delegate group
        @type delegateGroupID: C{int}
        @param readWrite: the access-type to check for; read and write
            access if True, otherwise read-only access
        @type readWrite: C{boolean}
        @returns: the UIDs of the delegators (for the specified access
            type)
        @rtype: a Deferred resulting in a set

        """
        results = yield DelegateGroupsRecord.query(
            self,
            (DelegateGroupsRecord.groupID == delegateGroupID).And(
                DelegateGroupsRecord.readWrite == (1 if readWrite else 0)
            )
        )
        delegators = set([record.delegator.decode("utf-8") for record in results])
        returnValue(delegators)


    @inlineCallbacks
    def allGroupDelegates(self):
        """
        Return the UIDs of all groups which have been delegated to.  Useful
        for obtaining the set of groups which need to be synchronized from
        the directory.

        @returns: the UIDs of all delegated-to groups
        @rtype: a Deferred resulting in a set
        """

        results = yield DelegateGroupsRecord.allGroupDelegates(self)
        delegates = set([record.groupUID.decode("utf-8") for record in results])

        returnValue(delegates)


    @inlineCallbacks
    def externalDelegates(self):
        """
        Returns a dictionary mapping delegate UIDs to (read-group, write-group)
        tuples, including only those assignments that originated from the
        directory.

        @returns: dictionary mapping delegator uid to (readDelegateUID,
            writeDelegateUID) tuples
        @rtype: a Deferred resulting in a dictionary
        """
        delegates = {}

        # Get the externally managed delegates (which are all groups)
        results = yield ExternalDelegateGroupsRecord.all(self)
        for record in results:
            delegates[record.delegator.encode("utf-8")] = (
                record.groupUIDRead.encode("utf-8") if record.groupUIDRead else None,
                record.groupUIDWrite.encode("utf-8") if record.groupUIDWrite else None
            )

        returnValue(delegates)


    @inlineCallbacks
    def assignExternalDelegates(
        self, delegator, readDelegateGroupID, writeDelegateGroupID,
        readDelegateUID, writeDelegateUID
    ):
        """
        Update the external delegate group table so we can quickly identify
        diffs next time, and update the delegate group table itself

        @param delegator
        @type delegator: C{UUID}
        """

        # Delete existing external assignments for the delegator
        yield DelegateGroupsRecord.deletesimple(
            self,
            delegator=str(delegator),
            isExternal=1,
        )

        # Remove from the external comparison table
        yield ExternalDelegateGroupsRecord.deletesimple(
            self,
            delegator=str(delegator),
        )

        # Store new assignments in the external comparison table
        if readDelegateUID or writeDelegateUID:
            readDelegateForDB = (
                readDelegateUID.encode("utf-8") if readDelegateUID else ""
            )
            writeDelegateForDB = (
                writeDelegateUID.encode("utf-8") if writeDelegateUID else ""
            )
            yield ExternalDelegateGroupsRecord.create(
                self,
                delegator=str(delegator),
                groupUIDRead=readDelegateForDB,
                groupUIDWrite=writeDelegateForDB,
            )

        # Apply new assignments
        if readDelegateGroupID is not None:
            yield self.addDelegateGroup(
                delegator, readDelegateGroupID, False, isExternal=True
            )
        if writeDelegateGroupID is not None:
            yield self.addDelegateGroup(
                delegator, writeDelegateGroupID, True, isExternal=True
            )


    def dumpIndividualDelegatesLocal(self, delegator):
        """
        Get the L{DelegateRecord} for all delegates associated with this delegator.
        """
        return DelegateRecord.querysimple(self, delegator=delegator.encode("utf-8"))


    @inlineCallbacks
    def dumpIndividualDelegatesExternal(self, delegator):
        """
        Get the L{DelegateRecord} for all delegates associated with this delegator.
        """
        raw_results = yield self.store().conduit.send_dump_individual_delegates(self, delegator)
        returnValue([DelegateRecord.deserialize(row) for row in raw_results])


    def dumpGroupDelegatesLocal(self, delegator):
        """
        Get the L{DelegateGroupsRecord},L{GroupsRecord} for all group delegates associated with this delegator.
        """
        return DelegateGroupsRecord.delegatorGroups(self, delegator)


    @inlineCallbacks
    def dumpGroupDelegatesExternal(self, delegator):
        """
        Get the L{DelegateGroupsRecord},L{GroupsRecord} for all delegates associated with this delegator.
        """
        raw_results = yield self.store().conduit.send_dump_group_delegates(self, delegator)
        returnValue([(DelegateGroupsRecord.deserialize(row[0]), GroupsRecord.deserialize(row[1]),) for row in raw_results])


    def dumpExternalDelegatesLocal(self, delegator):
        """
        Get the L{ExternalDelegateGroupsRecord} for all delegates associated with this delegator.
        """
        return ExternalDelegateGroupsRecord.querysimple(self, delegator=delegator.encode("utf-8"))


    @inlineCallbacks
    def dumpExternalDelegatesExternal(self, delegator):
        """
        Get the L{ExternalDelegateGroupsRecord} for all delegates associated with this delegator.
        """
        raw_results = yield self.store().conduit.send_dump_external_delegates(self, delegator)
        returnValue([ExternalDelegateGroupsRecord.deserialize(row) for row in raw_results])
