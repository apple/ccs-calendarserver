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

ROW: TYPE, UID (unique), PSWD, NAME, CANPROXY

Group Database:

ROW: GRPUID, UID

CUAddress database:

ROW: CUADDR (unqiue), UID

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
    dbFormatVersion = "1"

    def _getRealmName(self):
        #
        # This is used frequently enough that it's worth caching.
        # Downside is that changing the realm name (with SQL directly) requires
        # a server restart.
        #
        if not hasattr(self, "_realmName"):
            realmName = None
            for row in self._db_execute("select REALM from SERVICE"):
                assert realmName is None
                realmName = row[0]
            self._realmName = realmName
        return self._realmName

    realmName = property(_getRealmName)

    def __init__(self, path):
        path = os.path.join(path, SQLDirectoryManager.dbFilename)
        super(SQLDirectoryManager, self).__init__(path, SQLDirectoryManager.dbFormatVersion)

    def loadFromXML(self, xmlFile):
        parser = XMLAccountsParser(xmlFile)
       
        # Totally wipe existing DB and start from scratch
        if os.path.exists(self.dbpath):
            os.remove(self.dbpath)

        self._realmName = parser.realm

        self._db_execute("insert into SERVICE (REALM) values (:1)", parser.realm)

        # Now add records to db
        for item in parser.items.values():
            for entry in item.itervalues():
                self._add_to_db(entry)
        self._db_commit()

    def listRecords(self, recordType):
        # Get each account record
        rowiter = self._db_execute("select UID, PSWD, NAME from ACCOUNTS where TYPE = :1", recordType)
        for row in rowiter:
            uid = row[0]
            password = row[1]
            name = row[2]
            members = set()
            groups = set()
            calendarUserAddresses = set()
    
            # See if we have a group
            if recordType == "group":
                rowiter = self._db_execute("select MEMBER_RECORD_TYPE, MEMBER_UID from GROUPS where GRPUID = :1", uid)
                for row in rowiter:
                    members.add((row[0], row[1]))
                
            # See if we are a member of a group
            rowiter = self._db_execute("select GRPUID from GROUPS where MEMBER_UID = :1", uid)
            for row in rowiter:
                groups.add(row[0])
                
            # Get calendar user addresses
            rowiter = self._db_execute("select CUADDR from CUADDRS where UID = :1", uid)
            for row in rowiter:
                calendarUserAddresses.add(row[0])
                
            yield uid, password, name, members, groups, calendarUserAddresses

    def getRecord(self, recordType, uid):
        # Get individual account record
        rowiter = self._db_execute("select UID, PSWD, NAME from ACCOUNTS where TYPE = :1 and UID = :2", recordType, uid)
        result = None
        for row in rowiter:
            if result:
                result = None
                break
            result = row

        if result is None:
            return None
        
        uid = result[0]
        password = result[1]
        name = result[2]
        members = set()
        groups = set()
        calendarUserAddresses = set()

        # See if we have a group
        if recordType == "group":
            rowiter = self._db_execute("select MEMBER_RECORD_TYPE, MEMBER_UID from GROUPS where GRPUID = :1", uid)
            for row in rowiter:
                members.add((row[0], row[1]))
            
        # See if we are a member of a group
        rowiter = self._db_execute("select GRPUID from GROUPS where MEMBER_UID = :1", uid)
        for row in rowiter:
            groups.add(row[0])
            
        # Get calendar user addresses
        rowiter = self._db_execute("select CUADDR from CUADDRS where UID = :1", uid)
        for row in rowiter:
            calendarUserAddresses.add(row[0])
            
        return uid, password, name, members, groups, calendarUserAddresses
            
    def _add_to_db(self, record):
        # Do regular account entry
        recordType = record.recordType
        uid = record.uid
        password = record.password
        name = record.name
        canproxy = ('F', 'T')[record.canproxy]

        self._db_execute(
            """
            insert into ACCOUNTS (TYPE, UID, PSWD, NAME, CANPROXY)
            values (:1, :2, :3, :4, :5)
            """, recordType, uid, password, name, canproxy
        )
        
        # Check for group
        if recordType == "group":
            for memberRecordType, memberShortName in record.members:
                self._db_execute(
                    """
                    insert into GROUPS (GRPUID, MEMBER_RECORD_TYPE, MEMBER_UID)
                    values (:1, :2, :3)
                    """, uid, memberRecordType, memberShortName
                )
                
        # CUAddress
        for cuaddr in record.calendarUserAddresses:
            self._db_execute(
                """
                insert into CUADDRS (CUADDR, UID)
                values (:1, :2)
                """, cuaddr, uid
            )
       
    def _delete_from_db(self, uid):
        """
        Deletes the specified entry from all dbs.
        @param name: the name of the resource to delete.
        @param uid: the uid of the resource to delete.
        """
        self._db_execute("delete from ACCOUNTS where UID = :1", uid)
        self._db_execute("delete from GROUPS where GRPUID = :1", uid)
        self._db_execute("delete from GROUPS where MEMBER_UID = :1", uid)
        self._db_execute("delete from CUADDRS where UID = :1", uid)
    
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
                TYPE           text,
                UID            text,
                PSWD           text,
                NAME           text,
                CANPROXY       text(1)
            )
            """
        )

        #
        # GROUPS table
        #
        q.execute(
            """
            create table GROUPS (
                GRPUID              text,
                MEMBER_RECORD_TYPE  text,
                MEMBER_UID          text
            )
            """
        )

        #
        # CUADDRS table
        #
        q.execute(
            """
            create table CUADDRS (
                CUADDR         text unique,
                UID            text
            )
            """
        )

class SQLDirectoryService(DirectoryService):
    """
    XML based implementation of L{IDirectoryService}.
    """
    baseGUID = "8256E464-35E0-4DBB-A99C-F0E30C231675"
    realmName = property(lambda self: self.manager.realmName)

    def __repr__(self):
        return "<%s %r: %r>" % (self.__class__.__name__, self.realmName, self.xmlFile)

    def __init__(self, dbParentPath, xmlFile = None):
        super(SQLDirectoryService, self).__init__()

        if type(dbParentPath) is str:
            dbParentPath = FilePath(dbParentPath)
            
        self.manager = SQLDirectoryManager(dbParentPath.path)
        if xmlFile:
            self.manager.loadFromXML(xmlFile)

    def recordTypes(self):
        recordTypes = ("user", "group", "resource")
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
