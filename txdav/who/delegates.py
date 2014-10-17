# -*- test-case-name: txdav.who.test.test_delegates -*-
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
Delegate assignments
"""

from twisted.python.constants import Names, NamedConstant
from twisted.internet.defer import inlineCallbacks, returnValue, succeed, \
    DeferredList

from twistedcaldav.config import config

from twext.python.log import Logger
from twext.who.idirectory import (
    RecordType as BaseRecordType, FieldName, NotAllowedError
)
from twext.who.directory import (
    DirectoryService as BaseDirectoryService,
    DirectoryRecord as BaseDirectoryRecord
)
from twext.who.expression import MatchExpression, MatchType

log = Logger()



class RecordType(Names):
    """
    Constants for read-only delegates and read-write delegate groups
    """

    readDelegateGroup = NamedConstant()
    readDelegateGroup.description = u"read-delegate-group"

    writeDelegateGroup = NamedConstant()
    writeDelegateGroup.description = u"write-delegate-group"

    readDelegatorGroup = NamedConstant()
    readDelegatorGroup.description = u"read-delegator-group"

    writeDelegatorGroup = NamedConstant()
    writeDelegatorGroup.description = u"write-delegator-group"



class DirectoryRecord(BaseDirectoryRecord):

    @inlineCallbacks
    def members(self, expanded=False):
        """
        If this is a readDelegateGroup or writeDelegateGroup, the members
        will consist of the records who are delegates *of* this record.
        If this is a readDelegatorGroup or writeDelegatorGroup,
        the members will consist of the records who have delegated *to*
        this record.
        """
        parentUID, _ignore_proxyType = self.uid.split(u"#")
        parentRecord = yield self.service._masterDirectory.recordWithUID(parentUID)

        @inlineCallbacks
        def _members(txn):
            if self.recordType in (
                RecordType.readDelegateGroup, RecordType.writeDelegateGroup
            ):  # Members are delegates of this record
                readWrite = (self.recordType is RecordType.writeDelegateGroup)
                delegateUIDs = yield _delegatesOfUIDs(txn, parentRecord, readWrite, expanded=expanded)

            else:  # Members have delegated to this record
                readWrite = (self.recordType is RecordType.writeDelegatorGroup)
                delegateUIDs = yield _delegatedToUIDs(txn, parentRecord, readWrite)
            returnValue(delegateUIDs)

        delegateUIDs = yield self.service._store.inTransaction(
            "DirectoryRecord.members", _members
        )

        records = []
        for uid in delegateUIDs:
            if uid != parentUID:
                record = yield self.service._masterDirectory.recordWithUID(uid)
                if record is not None:
                    records.append(record)

        returnValue(records)


    @inlineCallbacks
    def setMembers(self, memberRecords):
        """
        Replace the members of this group with the new members.

        @param memberRecords: The new members of the group
        @type memberRecords: iterable of L{iDirectoryRecord}s
        """
        if self.recordType not in (
            RecordType.readDelegateGroup, RecordType.writeDelegateGroup
        ):
            raise NotAllowedError("Setting members not supported")

        parentUID, _ignore_proxyType = self.uid.split(u"#")
        readWrite = (self.recordType is RecordType.writeDelegateGroup)

        log.info(
            "Setting delegate assignments for {u} ({rw}) to {m}",
            u=parentUID, rw=("write" if readWrite else "read"),
            m=[r.uid for r in memberRecords]
        )

        delegator = (
            yield self.service._masterDirectory.recordWithUID(parentUID)
        )

        def _setMembers(txn):
            return setDelegates(txn, delegator, memberRecords, readWrite)

        yield self.service._store.inTransaction(
            "DirectoryRecord.setMembers", _setMembers
        )



def recordTypeToProxyType(recordType):
    return {
        RecordType.readDelegateGroup: "calendar-proxy-read",
        RecordType.writeDelegateGroup: "calendar-proxy-write",
        RecordType.readDelegatorGroup: "calendar-proxy-read-for",
        RecordType.writeDelegatorGroup: "calendar-proxy-write-for",
    }.get(recordType, None)



def proxyTypeToRecordType(proxyType):
    return {
        "calendar-proxy-read": RecordType.readDelegateGroup,
        "calendar-proxy-write": RecordType.writeDelegateGroup,
        "calendar-proxy-read-for": RecordType.readDelegatorGroup,
        "calendar-proxy-write-for": RecordType.writeDelegatorGroup,
    }.get(proxyType, None)



class DirectoryService(BaseDirectoryService):
    """
    Delegate directory service
    """

    recordType = RecordType


    def __init__(self, realmName, store):
        BaseDirectoryService.__init__(self, realmName)
        self._store = store
        self._masterDirectory = None


    def setMasterDirectory(self, masterDirectory):
        self._masterDirectory = masterDirectory


    def recordWithShortName(self, recordType, shortName, timeoutSeconds=None):
        uid = shortName + "#" + recordTypeToProxyType(recordType)

        record = DirectoryRecord(self, {
            FieldName.uid: uid,
            FieldName.recordType: recordType,
            FieldName.shortNames: (uid,),
        })
        return succeed(record)


    def recordWithUID(self, uid, timeoutSeconds=None):
        if "#" not in uid:  # Not a delegate group uid
            return succeed(None)
        uid, proxyType = uid.split("#")
        recordType = proxyTypeToRecordType(proxyType)
        if recordType is None:
            return succeed(None)
        return self.recordWithShortName(
            recordType, uid, timeoutSeconds=timeoutSeconds
        )


    @inlineCallbacks
    def recordsFromExpression(
        self, expression, recordTypes=None, records=None,
        limitResults=None, timeoutSeconds=None
    ):
        """
        It's only ever appropriate to look up delegate group record by
        shortName or uid.  When wrapped by an aggregate directory, looking up
        by shortName will already go directly to recordWithShortName.  However
        when looking up by UID, it won't.  Inspect the expression to see if
        it's one we can handle.
        """
        if isinstance(expression, MatchExpression):
            if(
                (expression.fieldName is FieldName.uid) and
                (expression.matchType is MatchType.equals) and
                ("#" in expression.fieldValue)
            ):
                record = yield self.recordWithUID(
                    expression.fieldValue, timeoutSeconds=timeoutSeconds
                )
                if record is not None:
                    returnValue((record,))

        returnValue(())



@inlineCallbacks
def setDelegates(txn, delegator, delegates, readWrite):
    """
    Sets the full set of delegates for a delegator.

    We need to take multiple pods into account by re-directing this request
    to the cross-pod conduit if the delegator is not local to this pod.

    @param delegator: the delegator's directory record
    @type delegator: L{IDirectoryRecord}
    @param delegates: the delegates directory records
    @type delegates: L{list}} of L{IDirectoryRecord}
    @param readWrite: if True, read and write access is granted; read-only
        access otherwise
    """
    if delegator.thisServer():
        yield txn.removeDelegates(delegator.uid, readWrite)
        yield txn.removeDelegateGroups(delegator.uid, readWrite)

        for delegate in delegates:
            yield addDelegate(txn, delegator, delegate, readWrite)
    else:
        yield _podSetDelegates(txn, delegator, delegates, readWrite)



@inlineCallbacks
def addDelegate(txn, delegator, delegate, readWrite):
    """
    Adds "delegate" as a delegate of "delegator".  The type of access is
    specified by the "readWrite" parameter.

    @param delegator: the delegator's directory record
    @type delegator: L{IDirectoryRecord}
    @param delegate: the delegate's directory record
    @type delegate: L{IDirectoryRecord}
    @param readWrite: if True, read and write access is granted; read-only
        access otherwise
    """
    if delegate.recordType == BaseRecordType.group:
        # find the groupID
        (
            groupID, _ignore_name, _ignore_membershipHash, _ignore_modified,
            _ignore_extant
        ) = yield txn.groupByUID(
            delegate.uid
        )
        yield txn.addDelegateGroup(delegator.uid, groupID, readWrite)
    else:
        yield txn.addDelegate(delegator.uid, delegate.uid, readWrite)



@inlineCallbacks
def removeDelegate(txn, delegator, delegate, readWrite):
    """
    Removes "delegate" as a delegate of "delegator".  The type of access is
    specified by the "readWrite" parameter.

    @param delegator: the delegator's directory record
    @type delegator: L{IDirectoryRecord}
    @param delegate: the delegate's directory record
    @type delegate: L{IDirectoryRecord}
    @param readWrite: if True, read and write access is revoked; read-only
        access otherwise
    """
    if delegate.recordType == BaseRecordType.group:
        # find the groupID
        (
            groupID, _ignore_name, _ignore_membershipHash, _ignore_modified,
            _ignore_extant
        ) = yield txn.groupByUID(
            delegate.uid
        )
        yield txn.removeDelegateGroup(delegator.uid, groupID, readWrite)
    else:
        yield txn.removeDelegate(delegator.uid, delegate.uid, readWrite)



@inlineCallbacks
def delegatesOf(txn, delegator, readWrite, expanded=False):
    """
    Return the records of the delegates of "delegator".  The type of access
    is specified by the "readWrite" parameter.

    @param delegator: the delegator's directory record
    @type delegator: L{IDirectoryRecord}
    @param readWrite: if True, read and write access delegates are returned;
        read-only access otherwise
    @return: the set of directory records
    @rtype: a Deferred which fires a set of L{IDirectoryRecord}
    """
    delegateUIDs = yield _delegatesOfUIDs(txn, delegator, readWrite, expanded)

    records = []
    directory = delegator.service
    for uid in delegateUIDs:
        if uid != delegator.uid:
            record = (yield directory.recordWithUID(uid))
            if record is not None:
                records.append(record)
    returnValue(records)



@inlineCallbacks
def delegatedTo(txn, delegate, readWrite):
    """
    Return the records of those who have delegated to "delegate".  The type of
    access is specified by the "readWrite" parameter.

    @param delegate: the delegate's directory record
    @type delegate: L{IDirectoryRecord}
    @param readWrite: if True, read and write access delegators are returned;
        read-only access otherwise
    @return: the set of directory records
    @rtype: a Deferred which fires a set of L{IDirectoryRecord}
    """
    delegatorUIDs = yield _delegatedToUIDs(txn, delegate, readWrite)

    records = []
    directory = delegate.service
    for uid in delegatorUIDs:
        if uid != delegate.uid:
            record = (yield directory.recordWithUID(uid))
            if record is not None:
                records.append(record)
    returnValue(records)



@inlineCallbacks
def _delegatesOfUIDs(txn, delegator, readWrite, expanded=False):
    """
    Return the UIDs of the delegates of "delegator".  The type of access
    is specified by the "readWrite" parameter.

    We need to take multiple pods into account by re-directing this request
    to the cross-pod conduit if the delegator is not local to this pod.

    @param delegator: the delegator's directory record
    @type delegator: L{IDirectoryRecord}
    @param readWrite: if True, read and write access delegates are returned;
        read-only access otherwise
    @return: the set of directory record uids
    @rtype: a Deferred which fires a set of L{str}
    """

    log.debug("_delegatesOfUIDs for: {} and read-write = {} and expanded = {}".format(delegator.uid, readWrite, expanded,))
    if delegator.thisServer():
        delegateUIDs = yield txn.delegates(delegator.uid, readWrite, expanded=expanded)
    else:
        delegateUIDs = yield _podDelegates(txn, delegator, readWrite, expanded=expanded)
    returnValue(delegateUIDs)



@inlineCallbacks
def _delegatedToUIDs(txn, delegate, readWrite, onlyThisServer=False):
    """
    Return the UIDs of those who have delegated to "delegate".  The type of
    access is specified by the "readWrite" parameter.

    We need to take multiple pods into account by re-directing this request
    to the cross-pod conduit if the delegate is not local to this pod.

    @param delegate: the delegate's directory record
    @type delegate: L{IDirectoryRecord}
    @param readWrite: if True, read and write access delegators are returned;
        read-only access otherwise
    @param onlyThisServer: used when doing the query as part of a cross-pod request since that
        should only returns results for this server
    @type onlyThisServer: L{bool}
    @return: the set of directory record uids
    @rtype: a Deferred which fires a set of L{str}
    """


    log.debug("_delegatedToUIDs for: {} and read-write = {}".format(delegate.uid, readWrite,))
    delegatorUIDs = (yield txn.delegators(delegate.uid, readWrite))
    if not onlyThisServer and config.Servers.Enabled:
        delegatorUIDs.update((yield _podDelegators(txn, delegate, readWrite)))
    returnValue(delegatorUIDs)



def _podSetDelegates(txn, delegator, delegates, readWrite):
    """
    Sets the full set of delegates for a delegator.

    We need to take multiple pods into account by re-directing this request
    to the cross-pod conduit if the delegator is not local to this pod.

    @param delegator: the delegator's directory record
    @type delegator: L{IDirectoryRecord}
    @param delegates: the delegates directory records
    @type delegates: L{list}} of L{IDirectoryRecord}
    @param readWrite: if True, read and write access is granted; read-only
        access otherwise
    """
    return txn.store().conduit.send_set_delegates(txn, delegator, delegates, readWrite)



def _podDelegates(txn, delegator, readWrite, expanded=False):
    """
    Do a cross-pod request to get the delegates for this delegator.

    @param delegator: the delegator's directory record
    @type delegator: L{IDirectoryRecord}
    @param readWrite: if True, read and write access delegates are returned;
        read-only access otherwise
    @return: the set of directory record uids
    @rtype: a Deferred which fires a set of L{str}
    """

    log.debug("_podDelegates for: {} and read-write = {} and expanded = {}".format(delegator.uid, readWrite, expanded,))
    return txn.store().conduit.send_get_delegates(txn, delegator, readWrite, expanded)



@inlineCallbacks
def _podDelegators(txn, delegate, readWrite):
    """
    Do a cross-pod request to get the delegators for this delegate. We need to iterate over all
    other pod servers to get results from each one.

    @param delegate: the delegate's directory record
    @type delegate: L{IDirectoryRecord}
    @param readWrite: if True, read and write access delegates are returned;
        read-only access otherwise
    @return: the set of directory record uids
    @rtype: a Deferred which fires a set of L{str}
    """

    log.debug("_podDelegators for: {} and read-write = {}".format(delegate.uid, readWrite,))
    results = yield DeferredList([
        txn.store().conduit.send_get_delegators(txn, server, delegate, readWrite) for
        server in txn.directoryService().serversDB.allServersExceptThis()
    ], consumeErrors=True)
    delegators = set()
    for result in results:
        if result and result[0]:
            delegators.update(result[1])
    returnValue(delegators)
