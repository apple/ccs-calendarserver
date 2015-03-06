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
from twext.enterprise.dal.syntax import Select, Parameter
from twisted.internet.defer import inlineCallbacks, returnValue
from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.sql_directory import GroupsRecord

"""
Classes and methods that relate to directory objects in the SQL store. e.g.,
delegates, groups etc
"""

class GroupAttendeeRecord(SerializableRecord, fromTable(schema.GROUP_ATTENDEE)):
    """
    @DynamicAttrs
    L{Record} for L{schema.GROUP_ATTENDEE}.
    """

    @classmethod
    @inlineCallbacks
    def groupAttendeesForObjects(cls, txn, cobjs):
        """
        Get delegator/group pairs for each of the specified calendar objects.
        """

        # Do a join to get what we need
        rows = yield Select(
            list(GroupAttendeeRecord.table) + list(GroupsRecord.table),
            From=GroupAttendeeRecord.table.join(GroupsRecord.table, GroupAttendeeRecord.groupID == GroupsRecord.groupID),
            Where=(GroupAttendeeRecord.resourceID.In(Parameter("cobjs", len(cobjs))))
        ).on(txn, cobjs=cobjs)

        results = []
        groupAttendeeNames = [GroupAttendeeRecord.__colmap__[column] for column in list(GroupAttendeeRecord.table)]
        groupsNames = [GroupsRecord.__colmap__[column] for column in list(GroupsRecord.table)]
        split_point = len(groupAttendeeNames)
        for row in rows:
            groupAttendeeRow = row[:split_point]
            groupAttendeeRecord = GroupAttendeeRecord()
            groupAttendeeRecord._attributesFromRow(zip(groupAttendeeNames, groupAttendeeRow))
            groupAttendeeRecord.transaction = txn
            groupsRow = row[split_point:]
            groupsRecord = GroupsRecord()
            groupsRecord._attributesFromRow(zip(groupsNames, groupsRow))
            groupsRecord.transaction = txn
            results.append((groupAttendeeRecord, groupsRecord,))

        returnValue(results)



class GroupShareeRecord(SerializableRecord, fromTable(schema.GROUP_SHAREE)):
    """
    @DynamicAttrs
    L{Record} for L{schema.GROUP_SHAREE}.
    """
    pass
