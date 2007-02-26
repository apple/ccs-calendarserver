##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
SQL (sqlite) based user/group/resource directory service implementation.
"""

"""
SCHEMA:

User Database:

ROW: RECORD_TYPE, SHORT_NAME (unique), PASSWORD, NAME

Group Database:

ROW: SHORT_NAME, MEMBER_SHORT_NAME

CUAddress database:

ROW: ADDRESS (unqiue), SHORT_NAME

"""

__all__ = [
    "SQLDirectoryService",
]

from twisted.cred.credentials import UsernamePassword
from twisted.python.filepath import FilePath

from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.directory.xmlaccountsparser import XMLAccountsParser
from twistedcaldav.sql import AbstractSQLDatabase

import os

class SQLDirectoryManager(AbstractSQLDatabase):
    """
    House keeping operations on the SQL DB, including loading from XML file,
    and record dumping. This can be used as a standalong DB management tool.
    """
    dbType = "DIRECTORYSERVICE"
    dbFilename = ".db.accounts"
    dbFormatVersion = "2"

    def __init__(self, path):
        path = os.path.join(path, SQLDirectoryManager.dbFilename)
        super(SQLDirectoryManager, self).__init__(path, SQLDirectoryManager.dbFormatVersion)

    def loadFromXML(self, xmlFile):
        parser = XMLAccountsParser(xmlFile)

        # Totally wipe existing DB and start from scratch
        if os.path.exists(self.dbpath):
            os.remove(self.dbpath)

        self._db_execute("insert into SERVICE (REALM) values (:1)", parser.realm)

        # Now add records to db
        for item in parser.items.values():
            for entry in item.itervalues():
                self._add_to_db(entry)
        self._db_commit()

    def getRealm(self):
        for realm in self._db_execute("select REALM from SERVICE"):
            return realm[0].decode("utf-8")
        else:
            return ""

    def listRecords(self, recordType):
        # Get each account record
        for shortName, guid, password, name in self._db_execute(
            """
            select SHORT_NAME, GUID, PASSWORD, NAME
              from ACCOUNTS
             where RECORD_TYPE = :1
            """, recordType
        ):
            # See if we have members
            members = self.members(shortName)

            # See if we are a member of any groups
            groups = self.groups(shortName)

            # Get calendar user addresses
            calendarUserAddresses = self.calendarUserAddresses(shortName)

            yield shortName, guid, password, name, members, groups, calendarUserAddresses

    def getRecord(self, recordType, shortName):
        # Get individual account record
        for shortName, guid, password, name in self._db_execute(
            """
            select SHORT_NAME, GUID, PASSWORD, NAME
              from ACCOUNTS
             where RECORD_TYPE = :1
               and SHORT_NAME  = :2
            """, recordType, shortName
        ):
            break
        else:
            return None

        # See if we have members
        members = self.members(shortName)

        # See if we are a member of any groups
        groups = self.groups(shortName)

        # Get calendar user addresses
        calendarUserAddresses = self.calendarUserAddresses(shortName)

        return shortName, guid, password, name, members, groups, calendarUserAddresses

    def members(self, shortName):
        members = set()
        for member in self._db_execute(
            """
            select MEMBER_RECORD_TYPE, MEMBER_SHORT_NAME
              from GROUPS
             where SHORT_NAME = :1
            """, shortName
        ):
            members.add(tuple(member))
        return members

    def groups(self, shortName):
        groups = set()
        for (name,) in self._db_execute(
            """
            select SHORT_NAME
              from GROUPS
             where MEMBER_SHORT_NAME = :1
            """, shortName
        ):
            groups.add(name)
        return groups

    def calendarUserAddresses(self, shortName):
        calendarUserAddresses = set()
        for (address,) in self._db_execute(
            """
            select ADDRESS
              from ADDRESSES
             where SHORT_NAME = :1
            """, shortName
        ):
            calendarUserAddresses.add(address)
        return calendarUserAddresses

    def _add_to_db(self, record):
        # Do regular account entry
        recordType = record.recordType
        shortName = record.shortName
        guid = record.guid
        password = record.password
        name = record.name

        self._db_execute(
            """
            insert into ACCOUNTS (RECORD_TYPE, SHORT_NAME, GUID, PASSWORD, NAME)
            values (:1, :2, :3, :4, :5)
            """, recordType, shortName, guid, password, name
        )

        # Check for members
        for memberRecordType, memberShortName in record.members:
            self._db_execute(
                """
                insert into GROUPS (SHORT_NAME, MEMBER_RECORD_TYPE, MEMBER_SHORT_NAME)
                values (:1, :2, :3)
                """, shortName, memberRecordType, memberShortName
            )

        # CUAddress
        for cuaddr in record.calendarUserAddresses:
            self._db_execute(
                """
                insert into ADDRESSES (ADDRESS, SHORT_NAME)
                values (:1, :2)
                """, cuaddr, shortName
            )

    def _delete_from_db(self, shortName):
        """
        Deletes the specified entry from all dbs.
        @param name: the name of the resource to delete.
        @param shortName: the short name of the resource to delete.
        """
        self._db_execute("delete from ACCOUNTS  where SHORT_NAME        = :1", shortName)
        self._db_execute("delete from GROUPS    where SHORT_NAME        = :1", shortName)
        self._db_execute("delete from GROUPS    where MEMBER_SHORT_NAME = :1", shortName)
        self._db_execute("delete from ADDRESSES where SHORT_NAME        = :1", shortName)

    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return SQLDirectoryManager.dbType

    def _db_init_data_tables(self, q):
        """
        Initialise the underlying database tables.
        @param q:           a database cursor to use.
        """
        #
        # SERVICE table
        #
        q.execute("create table SERVICE (REALM text)")

        #
        # ACCOUNTS table
        #
        q.execute(
            """
            create table ACCOUNTS (
                RECORD_TYPE  text,
                SHORT_NAME   text,
                GUID         text,
                PASSWORD     text,
                NAME         text
            )
            """
        )

        #
        # GROUPS table
        #
        q.execute(
            """
            create table GROUPS (
                SHORT_NAME          text,
                MEMBER_RECORD_TYPE  text,
                MEMBER_SHORT_NAME   text
            )
            """
        )

        #
        # ADDRESSES table
        #
        q.execute(
            """
            create table ADDRESSES (
                ADDRESS     text unique,
                SHORT_NAME  text
            )
            """
        )

class SQLDirectoryService(DirectoryService):
    """
    XML based implementation of L{IDirectoryService}.
    """
    baseGUID = "8256E464-35E0-4DBB-A99C-F0E30C231675"
    realmName = None

    def __repr__(self):
        return "<%s %r: %r>" % (self.__class__.__name__, self.realmName, self.manager.dbpath)

    def __init__(self, dbParentPath, xmlFile=None):
        super(SQLDirectoryService, self).__init__()

        if type(dbParentPath) is str:
            dbParentPath = FilePath(dbParentPath)

        self.xmlFile = xmlFile

        self.manager = SQLDirectoryManager(dbParentPath.path)

    def startService(self):
        if self.xmlFile:
            self.manager.loadFromXML(self.xmlFile)
        self.realmName = self.manager.getRealm()

    def recordTypes(self):
        recordTypes = (
            DirectoryService.recordType_users,
            DirectoryService.recordType_groups,
            DirectoryService.recordType_locations,
            DirectoryService.recordType_resources,
        )
        return recordTypes

    def listRecords(self, recordType):
        for result in self.manager.listRecords(recordType):
            yield SQLDirectoryRecord(
                service               = self,
                recordType            = recordType,
                shortName             = result[0],
                guid                  = result[1],
                password              = result[2],
                name                  = result[3],
                members               = result[4],
                groups                = result[5],
                calendarUserAddresses = result[6],
            )

    def recordWithShortName(self, recordType, shortName):
        result = self.manager.getRecord(recordType, shortName)
        if result:
            return SQLDirectoryRecord(
                service               = self,
                recordType            = recordType,
                shortName             = result[0],
                guid                  = result[1],
                password              = result[2],
                name                  = result[3],
                members               = result[4],
                groups                = result[5],
                calendarUserAddresses = result[6],
            )

        return None

class SQLDirectoryRecord(DirectoryRecord):
    """
    XML based implementation implementation of L{IDirectoryRecord}.
    """
    def __init__(self, service, recordType, shortName, guid, password, name, members, groups, calendarUserAddresses):
        super(SQLDirectoryRecord, self).__init__(
            service               = service,
            recordType            = recordType,
            guid                  = guid,
            shortName             = shortName,
            fullName              = name,
            calendarUserAddresses = calendarUserAddresses,
        )

        self.password = password
        self._members = members
        self._groups  = groups

    def members(self):
        for recordType, shortName in self._members:
            yield self.service.recordWithShortName(recordType, shortName)

    def groups(self):
        for shortName in self._groups:
            yield self.service.recordWithShortName(DirectoryService.recordType_groups, shortName)

    def verifyCredentials(self, credentials):
        if isinstance(credentials, UsernamePassword):
            return credentials.password == self.password

        return super(SQLDirectoryRecord, self).verifyCredentials(credentials)

if __name__ == '__main__':
    mgr = SQLDirectoryManager("./")
    mgr.loadFromXML("test/accounts.xml")
