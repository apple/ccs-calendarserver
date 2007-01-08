##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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

ROW: RECORD_TYPE, SHORT_NAME (unique), PASSWORD, NAME, CAN_PROXY

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
        for (shortName, password, name) in self._db_execute(
            """
            select SHORT_NAME, PASSWORD, NAME from ACCOUNTS
            where RECORD_TYPE = :1
            """, recordType
        ):
            members = set()
            groups = set()
            calendarUserAddresses = set()
    
            # See if we have members
            for member in self._db_execute(
                """
                select MEMBER_RECORD_TYPE, MEMBER_SHORT_NAME from GROUPS
                where SHORT_NAME = :1
                """, shortName
            ):
                members.add(tuple(member))
                
            # See if we are a member of a group
            for (name,) in self._db_execute(
                """
                select SHORT_NAME from GROUPS
                where MEMBER_SHORT_NAME = :1
                """, shortName
            ):
                groups.add(name)
                
            # Get calendar user addresses
            for (address,) in self._db_execute(
                """
                select ADDRESS from ADDRESSES
                where SHORT_NAME = :1
                """, shortName
            ):
                calendarUserAddresses.add(address)
                
            yield shortName, password, name, members, groups, calendarUserAddresses

    def getRecord(self, recordType, shortName):
        # Get individual account record
        for shortName, password, name in self._db_execute(
            """
            select SHORT_NAME, PASSWORD, NAME from ACCOUNTS
            where RECORD_TYPE = :1
              and SHORT_NAME  = :2
            """, recordType, shortName
        ):
            break
        else:
            return None
        
        # See if we have members
        members = set()
        for row in self._db_execute("select MEMBER_RECORD_TYPE, MEMBER_SHORT_NAME from GROUPS where SHORT_NAME = :1", shortName):
            members.add((row[0], row[1]))
            
        # See if we are a member of a group
        groups = set()
        for row in self._db_execute("select SHORT_NAME from GROUPS where MEMBER_SHORT_NAME = :1", shortName):
            groups.add(row[0])
            
        # Get calendar user addresses
        calendarUserAddresses = set()
        for row in self._db_execute("select ADDRESS from ADDRESSES where SHORT_NAME = :1", shortName):
            calendarUserAddresses.add(row[0])
            
        return shortName, password, name, members, groups, calendarUserAddresses
            
    def _add_to_db(self, record):
        # Do regular account entry
        recordType = record.recordType
        shortName = record.shortName
        password = record.password
        name = record.name
        canproxy = ('F', 'T')[record.canproxy]

        self._db_execute(
            """
            insert into ACCOUNTS (RECORD_TYPE, SHORT_NAME, PASSWORD, NAME, CAN_PROXY)
            values (:1, :2, :3, :4, :5)
            """, recordType, shortName, password, name, canproxy
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
                PASSWORD     text,
                NAME         text,
                CAN_PROXY    text(1)
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
            
        self.manager = SQLDirectoryManager(dbParentPath.path)
        if xmlFile:
            self.manager.loadFromXML(xmlFile)
        self.realmName = self.manager.getRealm()

    def recordTypes(self):
        recordTypes = ("user", "group", "location", "resource")
        return recordTypes

    def listRecords(self, recordType):
        for result in self.manager.listRecords(recordType):
            yield SQLDirectoryRecord(
                service               = self,
                recordType            = recordType,
                shortName             = result[0],
                password              = result[1],
                name                  = result[2],
                members               = result[3],
                groups                = result[4],
                calendarUserAddresses = result[5],
            )

    def recordWithShortName(self, recordType, shortName):
        result = self.manager.getRecord(recordType, shortName)
        if result:
            return SQLDirectoryRecord(
                service               = self,
                recordType            = recordType,
                shortName             = result[0],
                password              = result[1],
                name                  = result[2],
                members               = result[3],
                groups                = result[4],
                calendarUserAddresses = result[5],
            )

        return None

class SQLDirectoryRecord(DirectoryRecord):
    """
    XML based implementation implementation of L{IDirectoryRecord}.
    """
    def __init__(self, service, recordType, shortName, password, name, members, groups, calendarUserAddresses):
        super(SQLDirectoryRecord, self).__init__(
            service               = service,
            recordType            = recordType,
            guid                  = None,
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
            yield self.service.recordWithShortName("group", shortName)

    def verifyCredentials(self, credentials):
        if isinstance(credentials, UsernamePassword):
            return credentials.password == self.password

        return super(SQLDirectoryRecord, self).verifyCredentials(credentials)

if __name__ == '__main__':
    mgr = SQLDirectoryManager("./")
    mgr.loadFromXML("test/accounts.xml")
