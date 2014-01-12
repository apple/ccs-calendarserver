##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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
Database for storing extra resource information, such as auto-schedule
"""

__all__ = [
    "ResourceInfoDatabase",
]

import os

from twisted.internet.defer import inlineCallbacks, returnValue

from twext.python.log import Logger

from twistedcaldav.memcacher import Memcacher
from twistedcaldav.sql import AbstractSQLDatabase, db_prefix

class ResourceInfoDatabase(AbstractSQLDatabase):
    """
    A database to maintain resource (and location) information

    SCHEMA:

    Group Database:

    ROW: GUID, AUTOSCHEDULE
    """
    log = Logger()

    dbType = "RESOURCEINFO"
    dbFilename = "resourceinfo.sqlite"
    dbOldFilename = db_prefix + "resourceinfo"
    dbFormatVersion = "1"

    class ResourceInfoDBMemcacher(Memcacher):

        def setAutoSchedule(self, guid, autoSchedule):
            return self.set("resourceinfo:%s" % (str(guid),), "1" if autoSchedule else "0")

        @inlineCallbacks
        def getAutoSchedule(self, guid):
            result = (yield self.get("resourceinfo:%s" % (str(guid),)))
            if result is not None:
                autoSchedule = result == "1"
            else:
                autoSchedule = None
            returnValue(autoSchedule)

    def __init__(self, path):
        path = os.path.join(path, ResourceInfoDatabase.dbFilename)
        super(ResourceInfoDatabase, self).__init__(path, True)

        self._memcacher = ResourceInfoDatabase.ResourceInfoDBMemcacher("resourceInfoDB")

    @inlineCallbacks
    def setAutoSchedule(self, guid, autoSchedule):
        """
        Set a resource/location's auto-Schedule boolean.

        @param guid: the UID of the group principal to add.
        @param autoSchedule: boolean
        """
        self.setAutoScheduleInDatabase(guid, autoSchedule)

        # Update cache
        (yield self._memcacher.setAutoSchedule(guid, autoSchedule))

    def setAutoScheduleInDatabase(self, guid, autoSchedule):
        """
        A blocking call to set a resource/location's auto-Schedule boolean
        value in the database.

        @param guid: the UID of the group principal to add.
        @param autoSchedule: boolean
        """
        # Remove what is there, then add it back.
        self._delete_from_db(guid)
        self._add_to_db(guid, autoSchedule)
        self._db_commit()

    @inlineCallbacks
    def getAutoSchedule(self, guid):
        """
        Return the auto-Schedule state for the resource/location specified by guid
        """

        # Pull from cache
        autoSchedule = (yield self._memcacher.getAutoSchedule(guid))
        if autoSchedule is None:
            # Not in memcache, check local db
            autoSchedule = self._db_value_for_sql("select AUTOSCHEDULE from RESOURCEINFO where GUID = :1", guid)
            if autoSchedule is not None:
                autoSchedule = autoSchedule == 1
                (yield self._memcacher.setAutoSchedule(guid, autoSchedule))
        returnValue(autoSchedule)

    def _add_to_db(self, guid, autoSchedule):
        """
        Insert the specified entry into the database.

        @param guid: the guid of the resource/location
        @param autoSchedule: a boolean
        """
        self._db_execute(
            """
            insert into RESOURCEINFO (GUID, AUTOSCHEDULE)
            values (:1, :2)
            """, guid, 1 if autoSchedule else 0
        )

    def _delete_from_db(self, guid):
        """
        Deletes the specified entry from the database.

        @param guid: the guid of the resource/location to delete
        """
        self._db_execute("delete from RESOURCEINFO where GUID = :1", guid)

    def _db_version(self):
        """
        @return: the schema version assigned to this index.
        """
        return ResourceInfoDatabase.dbFormatVersion

    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return ResourceInfoDatabase.dbType

    def _db_init_data_tables(self, q):
        """
        Initialise the underlying database tables.
        @param q:           a database cursor to use.
        """

        #
        # RESOURCEINFO table
        #
        q.execute(
            """
            create table RESOURCEINFO (
                GUID            text,
                AUTOSCHEDULE    integer
            )
            """
        )
        q.execute(
            """
            create index RESOURCEGUIDS on RESOURCEINFO (GUID)
            """
        )

