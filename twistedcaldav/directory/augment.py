##
# Copyright (c) 2009-2010 Apple Inc. All rights reserved.
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


log = Logger()

class AugmentRecord(object):
    """
    Augmented directory record information
    """

    def __init__(
        self,
        uid,
        enabled=False,
        hostedAt="",
        enabledForCalendaring=False,
        autoSchedule=False,
        enabledForAddressBooks=False,
    ):
        self.uid = uid
        self.enabled = enabled
        self.hostedAt = hostedAt
        self.enabledForCalendaring = enabledForCalendaring
        self.enabledForAddressBooks = enabledForAddressBooks
        self.autoSchedule = autoSchedule
        self.clonedFromDefault = False

class AugmentDB(object):
    """
    Abstract base class for an augment record database.
    """
    
    def __init__(self):
        
        self.cachedRecords = {}
    
    @inlineCallbacks
    def getAugmentRecord(self, uid):
        """
        Get an AugmentRecord for the specified UID or the default.

        @param uid: directory UID to lookup
        @type uid: C{str}
        
        @return: L{Deferred}
        """
        
        result = (yield self._lookupAugmentRecord(uid))
        if result is not None:
            returnValue(result)

        # Try wildcard/default matches next
        for lookup in ("%s*" % (uid[0:2],), "%s*" % (uid[0],), "Default"):
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
        
AugmentService = AugmentDB()   # Global augment service


class AugmentXMLDB(AugmentDB):
    """
    XMLFile based augment database implementation.
    """

    def __init__(self, xmlFiles, cacheTimeout=30):

        super(AugmentXMLDB, self).__init__()
        self.xmlFiles = [fullServerPath(config.DataRoot, path) for path in xmlFiles]
        self.cacheTimeout = cacheTimeout * 60 # Value is mins we want secs
        self.lastCached = 0
        self.db = {}

        try:
            self.db = self._parseXML()
        except RuntimeError:
            log.error("Failed to parse XML augments file - fatal error on startup")
            raise

        self.lastCached = time.time()


    @inlineCallbacks
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
        if self.lastCached + self.cacheTimeout <= time.time():
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
                record_node = addSubElement(augments_node, xmlaugmentsparser.ELEMENT_RECORD)
                addSubElement(record_node, xmlaugmentsparser.ELEMENT_UID, record.uid)
                addSubElement(record_node, xmlaugmentsparser.ELEMENT_ENABLE, "true" if record.enabled else "false")
                addSubElement(record_node, xmlaugmentsparser.ELEMENT_HOSTEDAT, record.hostedAt)
                addSubElement(record_node, xmlaugmentsparser.ELEMENT_ENABLECALENDAR, "true" if record.enabledForCalendaring else "false")
                addSubElement(record_node, xmlaugmentsparser.ELEMENT_ENABLEADDRESSBOOK, "true" if record.enabledForAddressBooks else "false")
                addSubElement(record_node, xmlaugmentsparser.ELEMENT_AUTOSCHEDULE, "true" if record.autoSchedule else "false")


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
            record_node = addSubElement(augments_node, xmlaugmentsparser.ELEMENT_RECORD)
            addSubElement(record_node, xmlaugmentsparser.ELEMENT_UID, record.uid)
            addSubElement(record_node, xmlaugmentsparser.ELEMENT_ENABLE, "true" if record.enabled else "false")
            addSubElement(record_node, xmlaugmentsparser.ELEMENT_HOSTEDAT, record.hostedAt)
            addSubElement(record_node, xmlaugmentsparser.ELEMENT_ENABLECALENDAR, "true" if record.enabledForCalendaring else "false")
            addSubElement(record_node, xmlaugmentsparser.ELEMENT_ENABLEADDRESSBOOK, "true" if record.enabledForAddressBooks else "false")
            addSubElement(record_node, xmlaugmentsparser.ELEMENT_AUTOSCHEDULE, "true" if record.autoSchedule else "false")
        
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
                del record_node.getchildren()[:]
                addSubElement(record_node, xmlaugmentsparser.ELEMENT_UID, record.uid)
                addSubElement(record_node, xmlaugmentsparser.ELEMENT_ENABLE, "true" if record.enabled else "false")
                addSubElement(record_node, xmlaugmentsparser.ELEMENT_HOSTEDAT, record.hostedAt)
                addSubElement(record_node, xmlaugmentsparser.ELEMENT_ENABLECALENDAR, "true" if record.enabledForCalendaring else "false")
                addSubElement(record_node, xmlaugmentsparser.ELEMENT_ENABLEADDRESSBOOK, "true" if record.enabledForAddressBooks else "false")
                addSubElement(record_node, xmlaugmentsparser.ELEMENT_AUTOSCHEDULE, "true" if record.autoSchedule else "false")
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
        
    def refresh(self):
        """
        Refresh any cached data.
        """
        super(AugmentXMLDB, self).refresh()
        try:
            self.db = self._parseXML()
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

    def _parseXML(self):
        """
        Parse self.xmlFiles into AugmentRecords.

        If none of the xmlFiles exist, create a default record.
        """

        # Do each file
        results = {}

        allMissing = True
        for xmlFile in self.xmlFiles:
            if os.path.exists(xmlFile):
                # Creating a parser does the parse
                XMLAugmentsParser(xmlFile, results)
                allMissing = False

        if allMissing:
            results["Default"] = AugmentRecord(
                "Default",
                enabled=True,
                enabledForCalendaring=True,
                enabledForAddressBooks=True,
            )
        
        return results

class AugmentADAPI(AugmentDB, AbstractADBAPIDatabase):
    """
    DBAPI based augment database implementation.
    """

    schema_version = "1"
    schema_type    = "AugmentDB"
    
    def __init__(self, dbID, dbapiName, dbapiArgs, **kwargs):
        
        AugmentDB.__init__(self)
        self.cachedPartitions = {}
        self.cachedHostedAt = {}
        
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
        results = (yield self.query("select UID, ENABLED, PARTITIONID, CALENDARING, ADDRESSBOOKS, AUTOSCHEDULE from AUGMENTS where UID = :1", (uid,)))
        if not results:
            returnValue(None)
        else:
            uid, enabled, partitionid, enabledForCalendaring, enabledForAddressBooks, autoSchedule = results[0]
            
            record = AugmentRecord(
                uid = uid,
                enabled = enabled == "T",
                hostedAt = (yield self._getPartition(partitionid)),
                enabledForCalendaring = enabledForCalendaring == "T",
                enabledForAddressBooks = enabledForAddressBooks == "T",
                autoSchedule = autoSchedule == "T",
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
        
    @inlineCallbacks
    def _getPartitionID(self, hostedat, createIfMissing=True):
        
        # We will use a cache for these as we do not expect changes whilst running
        try:
            returnValue(self.cachedHostedAt[hostedat])
        except KeyError:
            pass

        partitionid = (yield self.queryOne("select PARTITIONID from PARTITIONS where HOSTEDAT = :1", (hostedat,)))
        if partitionid == None:
            yield self.execute("insert into PARTITIONS (HOSTEDAT) values (:1)", (hostedat,))
            partitionid = (yield self.queryOne("select PARTITIONID from PARTITIONS where HOSTEDAT = :1", (hostedat,)))
        self.cachedHostedAt[hostedat] = partitionid
        returnValue(partitionid)

    @inlineCallbacks
    def _getPartition(self, partitionid):
        
        # We will use a cache for these as we do not expect changes whilst running
        try:
            returnValue(self.cachedPartitions[partitionid])
        except KeyError:
            pass

        partition = (yield self.queryOne("select HOSTEDAT from PARTITIONS where PARTITIONID = :1", (partitionid,)))
        self.cachedPartitions[partitionid] = partition
        returnValue(partition)

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
                ("UID",          "text unique"),
                ("ENABLED",      "text(1)"),
                ("PARTITIONID",  "text"),
                ("CALENDARING",  "text(1)"),
                ("ADDRESSBOOKS", "text(1)"),
                ("AUTOSCHEDULE", "text(1)"),
            ),
            ifnotexists=True,
        )

        yield self._create_table(
            "PARTITIONS",
            (
                ("PARTITIONID",   "serial"),
                ("HOSTEDAT",      "text"),
            ),
            ifnotexists=True,
        )

    @inlineCallbacks
    def _db_empty_data_tables(self):
        yield self._db_execute("delete from AUGMENTS")
        yield self._db_execute("delete from PARTITIONS")

class AugmentSqliteDB(ADBAPISqliteMixin, AugmentADAPI):
    """
    Sqlite based augment database implementation.
    """

    def __init__(self, dbpath):
        
        ADBAPISqliteMixin.__init__(self)
        AugmentADAPI.__init__(self, "Augments", "sqlite3", (fullServerPath(config.DataRoot, dbpath),))

    @inlineCallbacks
    def _addRecord(self, record):
        partitionid = (yield self._getPartitionID(record.hostedAt))
        yield self.execute(
            """insert or replace into AUGMENTS
            (UID, ENABLED, PARTITIONID, CALENDARING, ADDRESSBOOKS, AUTOSCHEDULE)
            values (:1, :2, :3, :4, :5, :6)""",
            (
                record.uid,
                "T" if record.enabled else "F",
                partitionid,
                "T" if record.enabledForCalendaring else "F",
                "T" if record.enabledForAddressBooks else "F",
                "T" if record.autoSchedule else "F",
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
        partitionid = (yield self._getPartitionID(record.hostedAt))
        yield self.execute(
            """insert into AUGMENTS
            (UID, ENABLED, PARTITIONID, CALENDARING, ADDRESSBOOKS, AUTOSCHEDULE)
            values (:1, :2, :3, :4, :5, :6)""",
            (
                record.uid,
                "T" if record.enabled else "F",
                partitionid,
                "T" if record.enabledForCalendaring else "F",
                "T" if record.enabledForAddressBooks else "F",
                "T" if record.autoSchedule else "F",
            )
        )

    @inlineCallbacks
    def _modifyRecord(self, record):
        partitionid = (yield self._getPartitionID(record.hostedAt))
        yield self.execute(
            """update AUGMENTS set
            (UID, ENABLED, PARTITIONID, CALENDARING, ADDRESSBOOKS, AUTOSCHEDULE) =
            (:1, :2, :3, :4, :5, :6) where UID = :7""",
            (
                record.uid,
                "T" if record.enabled else "F",
                partitionid,
                "T" if record.enabledForCalendaring else "F",
                "T" if record.enabledForAddressBooks else "F",
                "T" if record.autoSchedule else "F",
                record.uid,
            )
        )
