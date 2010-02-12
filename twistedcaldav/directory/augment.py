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
import time

from twisted.internet.defer import inlineCallbacks, returnValue, succeed

from twext.log import Logger

from twistedcaldav.database import AbstractADBAPIDatabase, ADBAPISqliteMixin,\
    ADBAPIPostgreSQLMixin
from twistedcaldav.directory.xmlaugmentsparser import XMLAugmentsParser
import os
from twistedcaldav.directory import xmlaugmentsparser
from twistedcaldav.xmlutil import newElementTreeWithRoot, addSubElement,\
    writeXML


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

class AugmentDB(object):
    """
    Abstract base class for an augment record database.
    """
    
    def __init__(self):
        pass
    
    @inlineCallbacks
    def getAugmentRecord(self, uid):
        """
        Get an AugmentRecord for the specified UID or the default.

        @param uid: directory UID to lookup
        @type uid: C{str}
        
        @return: L{Deferred}
        """
        
        result = (yield self._lookupAugmentRecord(uid))
        if result is None:
            if not hasattr(self, "_defaultRecord"):
                self._defaultRecord = (yield self._lookupAugmentRecord("Default"))
            if self._defaultRecord is not None:
                result = copy.deepcopy(self._defaultRecord)
                result.uid = uid
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

    def refresh(self):
        """
        Refresh any cached data.
        """
        pass
        
AugmentService = AugmentDB()   # Global augment service


class AugmentXMLDB(AugmentDB):
    """
    XMLFile based augment database implementation.
    """
    
    def __init__(self, xmlFiles, cacheTimeout=30):
        
        self.xmlFiles = xmlFiles
        self.cacheTimeout = cacheTimeout * 60 # Value is mins we want secs
        self.lastCached = 0
        self.db = {}
        
        # Preflight existence of files
        missing = list()
        for xmlFile in self.xmlFiles:
            if not os.path.exists(xmlFile):
                missing.append(xmlFile)
                
        # For each missing one create an empty xml file
        if missing:
            # If all files are missing, then create one augment file that defaults
            # to all records being enabled
            doDefault = (len(missing) == len(self.xmlFiles))
            for missedFile in missing:
                
                _ignore_etree, root = newElementTreeWithRoot(xmlaugmentsparser.ELEMENT_AUGMENTS)
                if doDefault:
                    record = addSubElement(root, xmlaugmentsparser.ELEMENT_RECORD)
                    addSubElement(record, xmlaugmentsparser.ELEMENT_UID, "Default")
                    addSubElement(record, xmlaugmentsparser.ELEMENT_ENABLE, "true")
                    addSubElement(record, xmlaugmentsparser.ELEMENT_ENABLECALENDAR, "true")
                    doDefault = False
                writeXML(missedFile, root)
            
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

    def refresh(self):
        """
        Refresh any cached data.
        """
        try:
            self.db = self._parseXML()
        except RuntimeError:
            log.error("Failed to parse XML augments file during cache refresh - ignoring")
        self.lastCached = time.time()

    def _parseXML(self):
        
        # Do each file
        results = {}
        for xmlFile in self.xmlFiles:
            
            # Creating a parser does the parse
            XMLAugmentsParser(xmlFile, results)
        
        return results

class AugmentADAPI(AugmentDB, AbstractADBAPIDatabase):
    """
    DBAPI based augment database implementation.
    """

    schema_version = "1"
    schema_type    = "AugmentDB"
    
    def __init__(self, dbID, dbapiName, dbapiArgs, **kwargs):
        
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
        results = (yield self.query("select UID, ENABLED, PARTITIONID, CALENDARING, AUTOSCHEDULE from AUGMENTS where UID = :1", (uid,)))
        if not results:
            returnValue(None)
        else:
            uid, enabled, partitionid, enabdledForCalendaring, autoSchedule = results[0]
            
            record = AugmentRecord(
                uid = uid,
                enabled = enabled == "T",
                hostedAt = (yield self._getPartition(partitionid)),
                enabledForCalendaring = enabdledForCalendaring == "T",
                autoSchedule = autoSchedule == "T",
            )
            
            returnValue(record)

    @inlineCallbacks
    def addAugmentRecord(self, record, update=False):

        partitionid = (yield self._getPartitionID(record.hostedAt))
        
        if update:
            yield self.execute(
                """update AUGMENTS set
                (UID, ENABLED, PARTITIONID, CALENDARING, AUTOSCHEDULE) =
                (:1, :2, :3, :4, :5) where UID = :6""",
                (
                    record.uid,
                    "T" if record.enabled else "F",
                    partitionid,
                    "T" if record.enabledForCalendaring else "F",
                    "T" if record.autoSchedule else "F",
                    record.uid,
                )
            )
        else:
            yield self.execute(
                """insert into AUGMENTS
                (UID, ENABLED, PARTITIONID, CALENDARING, AUTOSCHEDULE)
                values (:1, :2, :3, :4, :5)""",
                (
                    record.uid,
                    "T" if record.enabled else "F",
                    partitionid,
                    "T" if record.enabledForCalendaring else "F",
                    "T" if record.autoSchedule else "F",
                )
            )

    def removeAugmentRecord(self, uid):

        return self.query("delete from AUGMENTS where UID = :1", (uid,))

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
        # TESTTYPE table
        #
        yield self._create_table("AUGMENTS", (
            ("UID",          "text unique"),
            ("ENABLED",      "text(1)"),
            ("PARTITIONID",  "text"),
            ("CALENDARING",  "text(1)"),
            ("AUTOSCHEDULE", "text(1)"),
        ))

        yield self._create_table("PARTITIONS", (
            ("PARTITIONID",   "serial"),
            ("HOSTEDAT",      "text"),
        ))

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
        AugmentADAPI.__init__(self, "Augments", "sqlite3", (dbpath,))

class AugmentPostgreSQLDB(ADBAPIPostgreSQLMixin, AugmentADAPI):
    """
    PostgreSQL based augment database implementation.
    """

    def __init__(self, host, database, user=None, password=None):
        
        ADBAPIPostgreSQLMixin.__init__(self)
        AugmentADAPI.__init__(self, "Augments", "pgdb", (), host=host, database=database, user=user, password=password,)

