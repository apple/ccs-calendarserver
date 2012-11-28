# -*- test-case-name: twistedcaldav.directory.test.test_cachedirectory -*-
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

"""
Caching directory service implementation.
"""

__all__ = [
    "CachingDirectoryService",
    "CachingDirectoryRecord",
    "DictRecordTypeCache",
]


import time

import base64

from twext.python.log import LoggingMixIn
from twext.python.memcacheclient import ClientFactory, MemcacheError

from twistedcaldav.config import config
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord, DirectoryError, UnknownRecordTypeError
from twistedcaldav.scheduling.cuaddress import normalizeCUAddr
from twistedcaldav.directory.util import normalizeUUID


class RecordTypeCache(object):
    """
    Abstract class for a record type cache. We will likely have dict and memcache implementations of this.
    """
    
    def __init__(self, directoryService, recordType):
        
        self.directoryService = directoryService
        self.recordType = recordType

    def addRecord(self, record, indexType, indexKey, useMemcache=True,
        neverExpire=False):
        raise NotImplementedError()
    
    def removeRecord(self, record):
        raise NotImplementedError()
        
    def findRecord(self, indexType, indexKey):
        raise NotImplementedError()
        
class DictRecordTypeCache(RecordTypeCache, LoggingMixIn):
    """
    Cache implementation using a dict, and uses memcached to share records
    with other instances.
    """
    
    def __init__(self, directoryService, recordType):
        
        super(DictRecordTypeCache, self).__init__(directoryService, recordType)
        self.records = set()
        self.recordsIndexedBy = {
            CachingDirectoryService.INDEX_TYPE_GUID     : {},
            CachingDirectoryService.INDEX_TYPE_SHORTNAME: {},
            CachingDirectoryService.INDEX_TYPE_CUA    : {},
            CachingDirectoryService.INDEX_TYPE_AUTHID   : {},
        }
        self.directoryService = directoryService
        self.lastPurgedTime = time.time()

    def addRecord(self, record, indexType, indexKey, useMemcache=True,
        neverExpire=False):

        useMemcache = useMemcache and config.Memcached.Pools.Default.ClientEnabled
        if neverExpire:
            record.neverExpire()

        self.records.add(record)

        # Also index/cache on guid
        indexTypes = [(indexType, indexKey)]
        if indexType != CachingDirectoryService.INDEX_TYPE_GUID:
            indexTypes.append((CachingDirectoryService.INDEX_TYPE_GUID,
                record.guid))

        for indexType, indexKey in indexTypes:
            self.recordsIndexedBy[indexType][indexKey] = record
            if useMemcache:
                key = self.directoryService.generateMemcacheKey(indexType, indexKey,
                    record.recordType)
                self.log_debug("Memcache: storing %s" % (key,))
                try:
                    self.directoryService.memcacheSet(key, record)
                except DirectoryMemcacheError:
                    self.log_error("Memcache: failed to store %s" % (key,))
                    pass


    def removeRecord(self, record):
        if record in self.records:
            self.records.remove(record)
            self.log_debug("Removed record %s" % (record.guid,))
            for indexType in self.directoryService.indexTypes():
                try:
                    indexData = getattr(record, CachingDirectoryService.indexTypeToRecordAttribute[indexType])
                except AttributeError:
                    continue
                if isinstance(indexData, basestring):
                    indexData = [indexData]
                for item in indexData:
                    try:
                        del self.recordsIndexedBy[indexType][item]
                    except KeyError:
                        pass
        
    def findRecord(self, indexType, indexKey):
        self.purgeExpiredRecords()
        return self.recordsIndexedBy[indexType].get(indexKey)


    def purgeExpiredRecords(self):
        """
        Scan the cached records and remove any that have expired.
        Does nothing if we've scanned within the past cacheTimeout seconds.
        """
        if time.time() - self.lastPurgedTime > self.directoryService.cacheTimeout:
            for record in list(self.records):
                if record.isExpired():
                    self.removeRecord(record)
            self.lastPurgedTime = time.time()

            
class CachingDirectoryService(DirectoryService):
    """
    Caching Directory implementation of L{IDirectoryService}.
    
    This is class must be overridden to provide a concrete implementation.
    """

    INDEX_TYPE_GUID      = "guid"
    INDEX_TYPE_SHORTNAME = "shortname"
    INDEX_TYPE_CUA       = "cua"
    INDEX_TYPE_AUTHID    = "authid"

    indexTypeToRecordAttribute = {
        "guid"     : "guid",
        "shortname": "shortNames",
        "cua"      : "calendarUserAddresses",
        "authid"   : "authIDs",
    }

    def __init__(
        self,
        cacheTimeout=1,
        negativeCaching=False,
        cacheClass=DictRecordTypeCache,
    ):
        """
        @param cacheTimeout: C{int} number of minutes before cache is invalidated.
        """
        
        self.cacheTimeout = cacheTimeout * 60
        self.negativeCaching = negativeCaching

        self.cacheClass = cacheClass
        self._initCaches()

        super(CachingDirectoryService, self).__init__()

    def _getMemcacheClient(self, refresh=False):
        if refresh or not hasattr(self, "memcacheClient"):
            self.memcacheClient = ClientFactory.getClient(['%s:%s' %
                (config.Memcached.Pools.Default.BindAddress, config.Memcached.Pools.Default.Port)],
                debug=0, pickleProtocol=2)
        return self.memcacheClient

    def memcacheSet(self, key, record):

        hideService = isinstance(record, DirectoryRecord)

        try:
            if hideService:
                record.service = None # so we don't pickle service

            key = base64.b64encode(key)
            if not self._getMemcacheClient().set(key, record, time=self.cacheTimeout):
                self.log_error("Could not write to memcache, retrying")
                if not self._getMemcacheClient(refresh=True).set(
                    key, record,
                    time=self.cacheTimeout
                ):
                    self.log_error("Could not write to memcache again, giving up")
                    del self.memcacheClient
                    raise DirectoryMemcacheError("Failed to write to memcache")
        finally:
            if hideService:
                record.service = self

    def memcacheGet(self, key):

        key = base64.b64encode(key)
        try:
            record = self._getMemcacheClient().get(key)
            if record is not None and isinstance(record, DirectoryRecord):
                record.service = self
        except MemcacheError:
            self.log_error("Could not read from memcache, retrying")
            try:
                record = self._getMemcacheClient(refresh=True).get(key)
                if record is not None and isinstance(record, DirectoryRecord):
                    record.service = self
            except MemcacheError:
                self.log_error("Could not read from memcache again, giving up")
                del self.memcacheClient
                raise DirectoryMemcacheError("Failed to read from memcache")
        return record

    def generateMemcacheKey(self, indexType, indexKey, recordType):
        """
        Return a key that can be used to store/retrieve a record in memcache.
        if short-name is the indexType the recordType be encoded into the key.

        @param indexType: one of the indexTypes( ) values
        @type indexType: C{str}
        @param indexKey: the value being indexed
        @type indexKey: C{str}
        @param recordType: the type of record being cached
        @type recordType: C{str}
        @return: a memcache key comprised of the passed-in values and the directory
            service's baseGUID
        @rtype: C{str}
        """
        keyVersion = 2
        if indexType == CachingDirectoryService.INDEX_TYPE_SHORTNAME:
            return "dir|v%d|%s|%s|%s|%s" % (keyVersion,self.baseGUID, recordType,
                indexType, indexKey)
        else:
            return "dir|v%d|%s|%s|%s" % (keyVersion, self.baseGUID, indexType,
                indexKey)

    def _initCaches(self):
        self._recordCaches = dict([
            (recordType, self.cacheClass(self, recordType))
            for recordType in self.recordTypes()
        ])
            
        self._disabledKeys = dict([(indexType, dict()) for indexType in self.indexTypes()])

    def indexTypes(self):
        
        return (
            CachingDirectoryService.INDEX_TYPE_GUID,
            CachingDirectoryService.INDEX_TYPE_SHORTNAME,
            CachingDirectoryService.INDEX_TYPE_CUA,
            CachingDirectoryService.INDEX_TYPE_AUTHID,
        )

    def recordCacheForType(self, recordType):
        try:
            return self._recordCaches[recordType]
        except KeyError:
            raise UnknownRecordTypeError(recordType)

    def listRecords(self, recordType):
        return self.recordCacheForType(recordType).records

    def recordWithShortName(self, recordType, shortName):
        return self._lookupRecord((recordType,), CachingDirectoryService.INDEX_TYPE_SHORTNAME, shortName)

    def recordWithCalendarUserAddress(self, address):
        address = normalizeCUAddr(address)
        record = None
        if address.startswith("urn:uuid:"):
            guid = address[9:]
            record = self.recordWithGUID(guid)
        elif address.startswith("mailto:"):
            record = self._lookupRecord(None, CachingDirectoryService.INDEX_TYPE_CUA, address)

        return record if record and record.enabledForCalendaring else None

    def recordWithAuthID(self, authID):
        return self._lookupRecord(None, CachingDirectoryService.INDEX_TYPE_AUTHID, authID)

    def recordWithGUID(self, guid):
        guid = normalizeUUID(guid)
        return self._lookupRecord(None, CachingDirectoryService.INDEX_TYPE_GUID, guid)

    recordWithUID = recordWithGUID

    def _lookupRecord(self, recordTypes, indexType, indexKey):

        if recordTypes is None:
            recordTypes = self.recordTypes()
        else:
            # Only use recordTypes this service supports:
            supportedRecordTypes = self.recordTypes()
            recordTypes = [t for t in recordTypes if t in supportedRecordTypes]
            if not recordTypes:
                return None

        def lookup():
            for recordType in recordTypes:
                record = self.recordCacheForType(recordType).findRecord(indexType, indexKey)

                if record:
                    if record.isExpired():
                        self.recordCacheForType(recordType).removeRecord(record)
                        return None
                    else:
                        return record
            else:
                return None

        record = lookup()
        if record:
            return record

        if self.negativeCaching:

            # Check negative cache (take cache entry timeout into account)
            try:
                disabledTime = self._disabledKeys[indexType][indexKey]
                if time.time() - disabledTime < self.cacheTimeout:
                    return None
            except KeyError:
                pass

        # Check memcache
        if config.Memcached.Pools.Default.ClientEnabled:

            # The only time the recordType arg matters is when indexType is
            # short-name, and in that case recordTypes will contain exactly
            # one recordType, so using recordTypes[0] here is always safe:
            key = self.generateMemcacheKey(indexType, indexKey, recordTypes[0])

            self.log_debug("Memcache: checking %s" % (key,))

            try:
                record = self.memcacheGet(key)
            except DirectoryMemcacheError:
                self.log_error("Memcache: failed to get %s" % (key,))
                record = None

            if record is None:
                self.log_debug("Memcache: miss %s" % (key,))
            else:
                self.log_debug("Memcache: hit %s" % (key,))
                self.recordCacheForType(record.recordType).addRecord(record, indexType, indexKey, useMemcache=False)
                return record

            if self.negativeCaching:

                # Check negative memcache
                try:
                    val = self.memcacheGet("-%s" % (key,))
                except DirectoryMemcacheError:
                    self.log_error("Memcache: failed to get -%s" % (key,))
                    val = None
                if val == 1:
                    self.log_debug("Memcache: negative %s" % (key,))
                    self._disabledKeys[indexType][indexKey] = time.time()
                    return None

        # Try query
        self.log_debug("Faulting record for attribute '%s' with value '%s'" % (indexType, indexKey,))
        self.queryDirectory(recordTypes, indexType, indexKey)
        
        # Now try again from cache
        record = lookup()
        if record:
            self.log_debug("Found record for attribute '%s' with value '%s'" % (indexType, indexKey,))
            return record

        if self.negativeCaching:

            # Add to negative cache with timestamp
            self.log_debug("Failed to fault record for attribute '%s' with value '%s'" % (indexType, indexKey,))
            self._disabledKeys[indexType][indexKey] = time.time()

            if config.Memcached.Pools.Default.ClientEnabled:
                self.log_debug("Memcache: storing (negative) %s" % (key,))
                try:
                    self.memcacheSet("-%s" % (key,), 1)
                except DirectoryMemcacheError:
                    self.log_error("Memcache: failed to set -%s" % (key,))
                    pass


        return None

    def queryDirectory(self, recordTypes, indexType, indexKey):
        raise NotImplementedError()

class CachingDirectoryRecord(DirectoryRecord):

    def __init__(
        self, service, recordType, guid,
        shortNames=(), authIDs=set(),
        fullName=None, firstName=None, lastName=None, emailAddresses=set(),
        uid=None, **kwargs
    ):
        super(CachingDirectoryRecord, self).__init__(
            service,
            recordType,
            guid,
            shortNames            = shortNames,
            authIDs               = authIDs,
            fullName              = fullName,
            firstName             = firstName,
            lastName              = lastName,
            emailAddresses        = emailAddresses,
            uid                   = uid,
            **kwargs
        )
        
        self.cachedTime = time.time()

    def neverExpire(self):
        self.cachedTime = 0

    def isExpired(self):
        """
        Returns True if this record was created more than cacheTimeout
        seconds ago
        """
        if (
            self.cachedTime != 0 and
            time.time() - self.cachedTime > self.service.cacheTimeout
        ):
            return True
        else:
            return False


class DirectoryMemcacheError(DirectoryError):
    """
    Error communicating with memcached.
    """

