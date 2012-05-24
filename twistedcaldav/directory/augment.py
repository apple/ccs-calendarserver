##
# Copyright (c) 2009-2012 Apple Inc. All rights reserved.
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

import copy
import grp
import os
import pwd
import time

from twisted.internet.defer import inlineCallbacks, returnValue, succeed

from twext.python.log import Logger

from twistedcaldav.config import fullServerPath, config
from twistedcaldav.database import AbstractADBAPIDatabase, ADBAPISqliteMixin,\
    ADBAPIPostgreSQLMixin
from twistedcaldav.directory import xmlaugmentsparser
from twistedcaldav.directory.xmlaugmentsparser import XMLAugmentsParser
from twistedcaldav.xmlutil import newElementTreeWithRoot, addSubElement,\
    writeXML, readXML
from twistedcaldav.directory.util import normalizeUUID


log = Logger()

allowedAutoScheduleModes = frozenset((
    "default",
    "none",
    "accept-always",
    "decline-always",
    "accept-if-free",
    "decline-if-busy",
    "automatic",
))

class AugmentRecord(object):
    """
    Augmented directory record information
    """

    def __init__(
        self,
        uid,
        enabled=False,
        serverID="",
        partitionID="",
        enabledForCalendaring=False,
        autoSchedule=False,
        autoScheduleMode="default",
        enabledForAddressBooks=False,
        enabledForLogin=True,
    ):
        self.uid = uid
        self.enabled = enabled
        self.serverID = serverID
        self.partitionID = partitionID
        self.enabledForCalendaring = enabledForCalendaring
        self.enabledForAddressBooks = enabledForAddressBooks
        self.enabledForLogin = enabledForLogin
        self.autoSchedule = autoSchedule
        self.autoScheduleMode = autoScheduleMode if autoScheduleMode in allowedAutoScheduleModes else "default"
        self.clonedFromDefault = False

recordTypesMap = {
    "users" : "User",
    "groups" : "Group",
    "locations" : "Location",
    "resources" : "Resource",
}

class AugmentDB(object):
    """
    Abstract base class for an augment record database.
    """
    
    def __init__(self):
        
        self.cachedRecords = {}


    @inlineCallbacks
    def normalizeUUIDs(self):
        """
        Normalize (uppercase) all augment UIDs which are parseable as UUIDs.

        @return: a L{Deferred} that fires when all records have been
            normalized.
        """
        remove = []
        add = []
        for uid in (yield self.getAllUIDs()):
            nuid = normalizeUUID(uid)
            if uid != nuid:
                old = yield self._lookupAugmentRecord(uid)
                new = copy.deepcopy(old)
                new.uid = uid.upper()
                remove.append(old)
                add.append(new)
        yield self.removeAugmentRecords(remove)
        yield self.addAugmentRecords(add)


    @inlineCallbacks
    def getAugmentRecord(self, uid, recordType):
        """
        Get an AugmentRecord for the specified UID or the default.

        @param uid: directory UID to lookup
        @type uid: C{str}
        
        @return: L{Deferred}
        """
        
        recordType = recordTypesMap[recordType]

        result = (yield self._lookupAugmentRecord(uid))
        if result is not None:
            returnValue(result)

        # Try wildcard/default matches next
        for lookup in (
            "%s-%s*" % (recordType, uid[0:2]),
            "%s-%s*" % (recordType, uid[0]),
            "%s*" % (uid[0:2],),
            "%s*" % (uid[0],),
            "%s-Default" % (recordType,),
            "Default",
        ):
            result = (yield self._cachedAugmentRecord(lookup))
            if result is not None:
                result = copy.deepcopy(result)
                result.uid = uid
                result.clonedFromDefault = True
                returnValue(result)

        # No default was specified in the db, so generate one
        result = AugmentRecord(
            "Default",
            enabled=True,
            enabledForCalendaring=True,
            enabledForAddressBooks=True,
            enabledForLogin=True,
        )
        self.cachedRecords["Default"] = result
        result = copy.deepcopy(result)
        result.uid = uid
        result.clonedFromDefault = True
        returnValue(result)

    @inlineCallbacks
    def getAllUIDs(self):
        """
        Get all AugmentRecord UIDs.

        @return: L{Deferred}
        """
        
        raise NotImplementedError("Child class must define this.")

    def _lookupAugmentRecord(self, uid):
        """
        Get an AugmentRecord for the specified UID.

        @param uid: directory UID to lookup
        @type uid: C{str}
        
        @return: L{Deferred}
        """
        
        raise NotImplementedError("Child class must define this.")

    @inlineCallbacks
    def _cachedAugmentRecord(self, uid):
        """
        Get an AugmentRecord for the specified UID from the cache.

        @param uid: directory UID to lookup
        @type uid: C{str}
        
        @return: L{Deferred}
        """
        
        if not uid in self.cachedRecords:
            result = (yield self._lookupAugmentRecord(uid))
            self.cachedRecords[uid] = result
        returnValue(self.cachedRecords[uid])

    def addAugmentRecords(self, records):
        """
        Add an AugmentRecord to the DB.

        @param record: augment records to add
        @type record: C{list} of L{AugmentRecord}
        
        @return: L{Deferred}
        """

        raise NotImplementedError("Child class must define this.")

    def removeAugmentRecords(self, uids):
        """
        Remove AugmentRecords with the specified UIDs.

        @param uid: directory UIDs to remove
        @type uid: C{list} of C{str}
        
        @return: L{Deferred}
        """

        raise NotImplementedError("Child class must define this.")

    def refresh(self):
        """
        Refresh any cached data.
        
        @return: L{Deferred}
        """

        self.cachedRecords.clear()
        return succeed(None)
    
    def clean(self):
        """
        Remove all records.
        
        @return: L{Deferred}
        """

        raise NotImplementedError("Child class must define this.")


class AugmentXMLDB(AugmentDB):
    """
    XMLFile based augment database implementation.
    """

    def __init__(self, xmlFiles, statSeconds=15):

        super(AugmentXMLDB, self).__init__()
        self.xmlFiles = [fullServerPath(config.DataRoot, path) for path in xmlFiles]
        self.xmlFileStats = { }
        for path in self.xmlFiles:
            self.xmlFileStats[path] = (0, 0) # mtime, size

        self.statSeconds = statSeconds # Don't stat more often than this value
        self.lastCached = 0
        self.db = {}

        try:
            self.db = self._parseXML()
        except RuntimeError:
            log.error("Failed to parse XML augments file - fatal error on startup")
            raise

        self.lastCached = time.time()
        self.normalizeUUIDs()


    def getAllUIDs(self):
        """
        Get all AugmentRecord UIDs.

        @return: L{Deferred}
        """
        return succeed(self.db.keys())


    def _lookupAugmentRecord(self, uid):
        """
        Get an AugmentRecord for the specified UID.

        @param uid: directory UID to lookup
        @type uid: C{str}
        
        @return: L{Deferred}
        """
        
        # May need to re-cache
        if time.time() - self.lastCached > self.statSeconds:
            self.refresh()
            
        return succeed(self.db.get(uid))

    def addAugmentRecords(self, records):
        """
        Add an AugmentRecord to the DB.

        @param records: augment records to add
        @type records: C{list} of L{AugmentRecord}
        @param update: C{True} if changing an existing record
        @type update: C{bool}
        
        @return: L{Deferred}
        """

        # Look at each record and determine whether it is new or a modify
        new_records = list()
        existing_records = list() 
        for record in records:
            (existing_records if record.uid in self.db else new_records).append(record)

        if existing_records:
            # Now look at each file and modify the UIDs
            for xmlFile in self.xmlFiles:
                self._doModifyInFile(xmlFile, existing_records)

        if new_records:
            # Add to first file in list
            self._doAddToFile(self.xmlFiles[0], new_records)

        # This is required to invalidate self.db
        self.lastCached = 0

        return succeed(None)

    def _doAddToFile(self, xmlfile, records):

        if not os.path.exists(xmlfile):

            # File doesn't yet exist.  Create it with items in self.db, and
            # set file permissions.

            _ignore_etree, augments_node = newElementTreeWithRoot(xmlaugmentsparser.ELEMENT_AUGMENTS)
            for record in self.db.itervalues():
                self._addRecordToXMLDB(record, augments_node)


            writeXML(xmlfile, augments_node)

            # Set permissions
            uid = -1
            if config.UserName:
                try:
                    uid = pwd.getpwnam(config.UserName).pw_uid
                except KeyError:
                    log.error("User not found: %s" % (config.UserName,))
            gid = -1
            if config.GroupName:
                try:
                    gid = grp.getgrnam(config.GroupName).gr_gid
                except KeyError:
                    log.error("Group not found: %s" % (config.GroupName,))
            if uid != -1 and gid != -1:
                os.chown(xmlfile, uid, gid)


        _ignore_etree, augments_node = readXML(xmlfile)

        # Create new record
        for record in records:
            self._addRecordToXMLDB(record, augments_node)
        
        # Modify xmlfile
        writeXML(xmlfile, augments_node)
        
    def _doModifyInFile(self, xmlfile, records):
    
        if not os.path.exists(xmlfile):
            return

        _ignore_etree, augments_node = readXML(xmlfile)
    
        # Map uid->record for fast lookup
        recordMap = dict([(record.uid, record) for record in records])

        # Make sure UID is present
        changed = False
        for record_node in augments_node.getchildren():
            
            if record_node.tag != xmlaugmentsparser.ELEMENT_RECORD:
                continue
    
            uid = record_node.find(xmlaugmentsparser.ELEMENT_UID).text
            if uid in recordMap:
                # Modify record
                record = recordMap[uid]
                self._updateRecordInXMLDB(record, record_node)
                changed = True

        # Modify xmlfile
        if changed:
            writeXML(xmlfile, augments_node)

    def removeAugmentRecords(self, uids):
        """
        Remove AugmentRecords with the specified UIDs.

        @param uid: directory UID to lookup
        @type uid: C{list} of C{str}
        
        @return: L{Deferred}
        """

        # Remove from cache first
        removed = set()
        for uid in uids:
            if uid in self.db:
                del self.db[uid]
                removed.add(uid)

        # Now look at each file and remove the UIDs
        for xmlFile in self.xmlFiles:
            self._doRemoveFromFile(xmlFile, removed)

        return succeed(None)

    def _doRemoveFromFile(self, xmlfile, uids):
    
        _ignore_etree, augments_node = readXML(xmlfile)
    
        # Remove all UIDs present
        changed = False
        for child in tuple(augments_node.getchildren()):
            
            if child.tag != xmlaugmentsparser.ELEMENT_RECORD:
                continue

            if child.find(xmlaugmentsparser.ELEMENT_UID).text in uids:
                augments_node.remove(child)
                changed = True
        
        # Modify xmlfile
        if changed:
            writeXML(xmlfile, augments_node)
        
        
    def _addRecordToXMLDB(self, record, parentNode):
        record_node = addSubElement(parentNode, xmlaugmentsparser.ELEMENT_RECORD)
        self._updateRecordInXMLDB(record, record_node)

    def _updateRecordInXMLDB(self, record, recordNode):
        del recordNode.getchildren()[:]
        addSubElement(recordNode, xmlaugmentsparser.ELEMENT_UID, record.uid)
        addSubElement(recordNode, xmlaugmentsparser.ELEMENT_ENABLE, "true" if record.enabled else "false")
        if record.serverID:
            addSubElement(recordNode, xmlaugmentsparser.ELEMENT_SERVERID, record.serverID)
        if record.partitionID:
            addSubElement(recordNode, xmlaugmentsparser.ELEMENT_PARTITIONID, record.partitionID)
        addSubElement(recordNode, xmlaugmentsparser.ELEMENT_ENABLECALENDAR, "true" if record.enabledForCalendaring else "false")
        addSubElement(recordNode, xmlaugmentsparser.ELEMENT_ENABLEADDRESSBOOK, "true" if record.enabledForAddressBooks else "false")
        addSubElement(recordNode, xmlaugmentsparser.ELEMENT_ENABLELOGIN, "true" if record.enabledForLogin else "false")
        addSubElement(recordNode, xmlaugmentsparser.ELEMENT_AUTOSCHEDULE, "true" if record.autoSchedule else "false")
        if record.autoScheduleMode:
            addSubElement(recordNode, xmlaugmentsparser.ELEMENT_AUTOSCHEDULE_MODE, record.autoScheduleMode)

    def refresh(self):
        """
        Refresh any cached data.
        """
        super(AugmentXMLDB, self).refresh()
        try:
            results = self._parseXML()
            # Only update the cache if _parseXML( ) returns anything
            if results:
                self.db = results
        except RuntimeError:
            log.error("Failed to parse XML augments file during cache refresh - ignoring")
        self.lastCached = time.time()

        return succeed(None)

    def clean(self):
        """
        Remove all records.
        """

        self.removeAugmentRecords(self.db.keys())
        return succeed(None)

    def _shouldReparse(self, xmlFiles):
        """
        Check to see whether any of the given files have been modified since
        we last parsed them.
        """
        for xmlFile in xmlFiles:
            if os.path.exists(xmlFile):
                oldModTime, oldSize = self.xmlFileStats.get(xmlFile, (0, 0))
                newModTime = os.path.getmtime(xmlFile)
                newSize = os.path.getsize(xmlFile)
                if (oldModTime != newModTime) or (oldSize != newSize):
                    return True
        return False

    def _parseXML(self):
        """
        Parse self.xmlFiles into AugmentRecords.

        If none of the xmlFiles exist, create a default record.
        """

        results = {}

        # If all augments files are missing, return a default record
        for xmlFile in self.xmlFiles:
            if os.path.exists(xmlFile):
                break
        else:
            results["Default"] = AugmentRecord(
                "Default",
                enabled=True,
                enabledForCalendaring=True,
                enabledForAddressBooks=True,
                enabledForLogin=True,
            )

        # Compare previously seen modification time and size of each
        # xml file.  If all are unchanged, skip.
        if self._shouldReparse(self.xmlFiles):
            for xmlFile in self.xmlFiles:
                if os.path.exists(xmlFile):
                    # Creating a parser does the parse
                    XMLAugmentsParser(xmlFile, results)
                    newModTime = os.path.getmtime(xmlFile)
                    newSize = os.path.getsize(xmlFile)
                    self.xmlFileStats[xmlFile] = (newModTime, newSize)

        return results

class AugmentADAPI(AugmentDB, AbstractADBAPIDatabase):
    """
    DBAPI based augment database implementation.
    """

    schema_version = "2"
    schema_type    = "AugmentDB"
    
    def __init__(self, dbID, dbapiName, dbapiArgs, **kwargs):
        
        AugmentDB.__init__(self)
        AbstractADBAPIDatabase.__init__(self, dbID, dbapiName, dbapiArgs, True, **kwargs)
        
    @inlineCallbacks
    def getAllUIDs(self):
        """
        Get all AugmentRecord UIDs.

        @return: L{Deferred}
        """
        
        # Query for the record information
        results = (yield self.queryList("select UID from AUGMENTS", ()))
        returnValue(results)

    @inlineCallbacks
    def _lookupAugmentRecord(self, uid):
        """
        Get an AugmentRecord for the specified UID.

        @param uid: directory UID to lookup
        @type uid: C{str}

        @return: L{Deferred}
        """
        
        # Query for the record information
        results = (yield self.query("select UID, ENABLED, SERVERID, PARTITIONID, CALENDARING, ADDRESSBOOKS, AUTOSCHEDULE, AUTOSCHEDULEMODE, LOGINENABLED from AUGMENTS where UID = :1", (uid,)))
        if not results:
            returnValue(None)
        else:
            uid, enabled, serverid, partitionid, enabledForCalendaring, enabledForAddressBooks, autoSchedule, autoScheduleMode, enabledForLogin = results[0]
            
            record = AugmentRecord(
                uid = uid,
                enabled = enabled == "T",
                serverID = serverid,
                partitionID = partitionid,
                enabledForCalendaring = enabledForCalendaring == "T",
                enabledForAddressBooks = enabledForAddressBooks == "T",
                enabledForLogin = enabledForLogin == "T",
                autoSchedule = autoSchedule == "T",
                autoScheduleMode = autoScheduleMode,
            )
            
            returnValue(record)

    @inlineCallbacks
    def addAugmentRecords(self, records):

        for record in records:
            
            results = (yield self.query("select UID from AUGMENTS where UID = :1", (record.uid,)))
            update = len(results) > 0

            if update:
                yield self._modifyRecord(record)
            else:
                yield self._addRecord(record)

    @inlineCallbacks
    def removeAugmentRecords(self, uids):

        for uid in uids:
            yield self.execute("delete from AUGMENTS where UID = :1", (uid,))

    def clean(self):
        """
        Remove all records.
        """

        return self.execute("delete from AUGMENTS", ())
        
    def _db_version(self):
        """
        @return: the schema version assigned to this index.
        """
        return AugmentADAPI.schema_version
        
    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return AugmentADAPI.schema_type
    
    @inlineCallbacks
    def _db_init_data_tables(self):
        """
        Initialize the underlying database tables.
        """

        #
        # AUGMENTS table
        #
        yield self._create_table(
            "AUGMENTS",
            (
                ("UID",              "text unique"),
                ("ENABLED",          "text(1)"),
                ("SERVERID",         "text"),
                ("PARTITIONID",      "text"),
                ("CALENDARING",      "text(1)"),
                ("ADDRESSBOOKS",     "text(1)"),
                ("AUTOSCHEDULE",     "text(1)"),
                ("AUTOSCHEDULEMODE", "text"),
                ("LOGINENABLED",     "text(1)"),
            ),
            ifnotexists=True,
        )

    @inlineCallbacks
    def _db_empty_data_tables(self):
        yield self._db_execute("delete from AUGMENTS")

class AugmentSqliteDB(ADBAPISqliteMixin, AugmentADAPI):
    """
    Sqlite based augment database implementation.
    """

    def __init__(self, dbpath):
        
        ADBAPISqliteMixin.__init__(self)
        AugmentADAPI.__init__(self, "Augments", "sqlite3", (fullServerPath(config.DataRoot, dbpath),))

    @inlineCallbacks
    def _addRecord(self, record):
        yield self.execute(
            """insert or replace into AUGMENTS
            (UID, ENABLED, SERVERID, PARTITIONID, CALENDARING, ADDRESSBOOKS, AUTOSCHEDULE, AUTOSCHEDULEMODE, LOGINENABLED)
            values (:1, :2, :3, :4, :5, :6, :7, :8, :9)""",
            (
                record.uid,
                "T" if record.enabled else "F",
                record.serverID,
                record.partitionID,
                "T" if record.enabledForCalendaring else "F",
                "T" if record.enabledForAddressBooks else "F",
                "T" if record.autoSchedule else "F",
                record.autoScheduleMode if record.autoScheduleMode else "",
                "T" if record.enabledForLogin else "F",
            )
        )

    def _modifyRecord(self, record):
        return self._addRecord(record)

class AugmentPostgreSQLDB(ADBAPIPostgreSQLMixin, AugmentADAPI):
    """
    PostgreSQL based augment database implementation.
    """

    def __init__(self, host, database, user=None, password=None):
        
        ADBAPIPostgreSQLMixin.__init__(self)
        AugmentADAPI.__init__(self, "Augments", "pgdb", (), host=host, database=database, user=user, password=password,)

    @inlineCallbacks
    def _addRecord(self, record):
        yield self.execute(
            """insert into AUGMENTS
            (UID, ENABLED, SERVERID, PARTITIONID, CALENDARING, ADDRESSBOOKS, AUTOSCHEDULE, AUTOSCHEDULEMODE, LOGINENABLED)
            values (:1, :2, :3, :4, :5, :6, :7, :8, :9)""",
            (
                record.uid,
                "T" if record.enabled else "F",
                record.serverID,
                record.partitionID,
                "T" if record.enabledForCalendaring else "F",
                "T" if record.enabledForAddressBooks else "F",
                "T" if record.autoSchedule else "F",
                record.autoScheduleMode if record.autoScheduleMode else "",
                "T" if record.enabledForLogin else "F",
            )
        )

    @inlineCallbacks
    def _modifyRecord(self, record):
        yield self.execute(
            """update AUGMENTS set
            (UID, ENABLED, SERVERID, PARTITIONID, CALENDARING, ADDRESSBOOKS, AUTOSCHEDULE, AUTOSCHEDULEMODE, LOGINENABLED) =
            (:1, :2, :3, :4, :5, :6, :7, :8, :9) where UID = :10""",
            (
                record.uid,
                "T" if record.enabled else "F",
                record.serverID,
                record.partitionID,
                "T" if record.enabledForCalendaring else "F",
                "T" if record.enabledForAddressBooks else "F",
                "T" if record.autoSchedule else "F",
                record.autoScheduleMode if record.autoScheduleMode else "",
                "T" if record.enabledForLogin else "F",
                record.uid,
            )
        )
