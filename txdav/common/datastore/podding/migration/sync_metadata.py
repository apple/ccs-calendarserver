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

from twext.enterprise.dal.record import Record, fromTable
from twext.enterprise.dal.syntax import Parameter, Delete
from twisted.internet.defer import inlineCallbacks
from txdav.common.datastore.sql_tables import schema

"""
Module that manages store-level metadata objects used during the migration process.
"""

class CalendarMigrationRecord(Record, fromTable(schema.CALENDAR_MIGRATION)):
    """
    @DynamicAttrs
    L{Record} for L{schema.CALENDAR_MIGRATION}.
    """

    @classmethod
    @inlineCallbacks
    def deleteremotes(cls, txn, homeid, remotes):
        return Delete(
            From=cls.table,
            Where=(cls.calendarHomeResourceID == homeid).And(
                cls.remoteResourceID.In(Parameter("remotes", len(remotes)))
            ),
        ).on(txn, remotes=remotes)



class CalendarObjectMigrationRecord(Record, fromTable(schema.CALENDAR_OBJECT_MIGRATION)):
    """
    @DynamicAttrs
    L{Record} for L{schema.CALENDAR_OBJECT_MIGRATION}.
    """
    pass



class AttachmentMigrationRecord(Record, fromTable(schema.ATTACHMENT_MIGRATION)):
    """
    @DynamicAttrs
    L{Record} for L{schema.ATTACHMENT_MIGRATION}.
    """
    pass
