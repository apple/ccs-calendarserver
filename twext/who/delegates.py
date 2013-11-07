# -*- test-case-name: twext.who.test.test_delegates -*-
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

from twisted.internet.defer import inlineCallbacks, returnValue
from twext.who.idirectory import RecordType

from twext.python.log import Logger
log = Logger()


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
    if delegate.recordType == RecordType.group:
        # find the groupID
        groupID, name, membershipHash = (yield txn.groupByGUID(delegate.guid))
        yield txn.addDelegateGroup(delegator.guid, groupID, readWrite)
    else:
        yield txn.addDelegate(delegator.guid, delegate.guid, readWrite)
        

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
    if delegate.recordType == RecordType.group:
        # find the groupID
        groupID, name, membershipHash = (yield txn.groupByGUID(delegate.guid))
        yield txn.removeDelegateGroup(delegator.guid, groupID, readWrite)
    else:
        yield txn.removeDelegate(delegator.guid, delegate.guid,
            readWrite)


@inlineCallbacks
def delegatesOf(txn, delegator, readWrite):
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
    records = []
    directory = delegator.service
    delegateGUIDs = (yield txn.delegates(delegator.guid, readWrite))
    for guid in delegateGUIDs:
        if guid != delegator.guid:
            record = (yield directory.recordWithGUID(guid))
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
    records = []
    directory = delegate.service
    delegatorGUIDs = (yield txn.delegators(delegate.guid, readWrite))
    for guid in delegatorGUIDs:
        if guid != delegate.guid:
            record = (yield directory.recordWithGUID(guid))
            if record is not None:
                records.append(record)
    returnValue(records)


def allGroupDelegates(txn):
    """
    @return: the GUIDs of all groups which are currently delegated to
    @rtype: a Deferred which fires with a set() of GUID strings
    """
    return txn.allGroupDelegates()
