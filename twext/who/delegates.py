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
    Args are records
    """
    if delegate.recordType == RecordType.group:
        # find the groupID
        results = (yield txn.groupByGUID(delegate.guid))
        while not results:
            # need to add the group to the groups table so we have a groupID

            # TODO: is there a better pattern for this?
            yield txn.addGroup(delegate.guid, delegate.fullNames[0], "")
            results = (yield txn.groupByGUID(delegate.guid))

        groupID = results[0][0]
        yield txn.addDelegate(delegator.guid, groupID,
            1 if readWrite else 0, True)
    else:
        yield txn.addDelegate(delegator.guid, delegate.guid,
            1 if readWrite else 0, False)

def removeDelegate(txn, delegator, delegate, readWrite):
    """
    Args are records
    """
    return txn.removeDelegate(delegator.guid, delegate.guid,
        1 if readWrite else 0, delegate.recordType==RecordType.group)

@inlineCallbacks
def delegatesOf(txn, delegator, readWrite):
    """
    Args are records
    """
    records = []
    directory = delegator.service
    results = (yield txn.delegates(delegator.guid, 1 if readWrite else 0))
    for row in results:
        if row[0] != delegator.guid:
            record = (yield directory.recordWithGUID(row[0]))
            if record is not None:
                records.append(record)
    returnValue(records)

@inlineCallbacks
def delegateFor(txn, delegate, readWrite):
    """
    Args are records
    """
    records = []
    directory = delegate.service
    results = (yield txn.delegators(delegate.guid, 1 if readWrite else 0))
    for row in results:
        if row[0] != delegate.guid:
            record = (yield directory.recordWithGUID(row[0]))
            if record is not None:
                records.append(record)
    returnValue(records)
