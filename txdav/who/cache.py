# -*- test-case-name: txdav.who.test.test_cache -*-
##
# Copyright (c) 2014-2017 Apple Inc. All rights reserved.
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
Caching Directory Service
"""

__all__ = [
    "CachingDirectoryService",
]

import base64
import time
import uuid

from zope.interface import implementer

from twistedcaldav.memcacheclient import ClientFactory, MemcacheError
from twistedcaldav.config import config

from twisted.internet.defer import inlineCallbacks, returnValue
from twext.python.log import Logger
from twext.who.directory import DirectoryService as BaseDirectoryService
from twext.who.idirectory import (
    IDirectoryService,
    FieldName as BaseFieldName,
    RecordType as BaseRecordType,
    DirectoryServiceError,)
from twext.who.util import ConstantsContainer

from txdav.common.idirectoryservice import IStoreDirectoryService
from txdav.dps.client import DirectoryService as DPSClientDirectoryService
from txdav.who.directory import (
    CalendarDirectoryServiceMixin,
)
from txdav.who.idirectory import FieldName, RecordType
from twisted.python.constants import Values, ValueConstant, NamedConstant, Names

log = Logger()


class IndexType(Values):
    """
    Constants to use for identifying indexes
    """
    uid = ValueConstant("uid")
    guid = ValueConstant("guid")
    shortName = ValueConstant("shortName")
    emailAddress = ValueConstant("emailAddress")


class DirectoryMemcacheError(DirectoryServiceError):
    """
    Error communicating with memcached.
    """


class DirectoryMemcacher(object):
    """
    Provide a cache of directory records in memcached so that worker processes
    and the DPS processes across multiple app servers can share a cache and thus
    reduce load on the directory server.
    """

    KEY_VERSION = 1

    def __init__(self, cacheTimeout, recordService, realmName, keyModifier):
        self._cacheTimeout = cacheTimeout
        self._recordService = recordService
        self._realmName = realmName
        self._keyVersion = "%d%s" % (DirectoryMemcacher.KEY_VERSION, keyModifier,)

    def _getMemcacheClient(self, refresh=False):
        """
        Get the memcache client instance to use for caching.

        @param refresh: whether or not to create a new memcache client
        @type refresh: L{bool}

        @return: the client to use
        @rtype: L{memcacheclient.Client}
        """
        if refresh or not hasattr(self, "memcacheClient"):

            if config.Memcached.Pools.Default.MemcacheSocket:
                client_addr = "unix:{}".format(config.Memcached.Pools.Default.MemcacheSocket)
            else:
                client_addr = "{}:{}".format(
                    config.Memcached.Pools.Default.BindAddress,
                    config.Memcached.Pools.Default.Port,
                )
            self.memcacheClient = ClientFactory.getClient([client_addr], debug=0, pickleProtocol=2)
        return self.memcacheClient

    def pickleRecord(self, record):
        fields = {}
        for field, value in record.fields.iteritems():
            valueType = record.service.fieldName.valueType(field)
            if valueType in (unicode, bool):
                fields[field.name] = value
            elif valueType is uuid.UUID:
                fields[field.name] = str(value)
            elif issubclass(valueType, (Names, NamedConstant)):
                fields[field.name] = value.name if value else None
        return (record.__class__, fields)

    def unpickleRecord(self, data):
        # If the wrapped directory service is the DPS client service, we need to unpickle
        # the record type as a DPS client record
        record_class, record_fields = data
        if isinstance(self._recordService, DPSClientDirectoryService):
            return self._recordService._dictToRecord(record_fields)
        else:
            # Manually unpickle the fields and use the wrapped directory service record type
            fields = {}
            for fieldName, value in record_fields.iteritems():
                try:
                    field = self._recordService.fieldName.lookupByName(fieldName)
                except ValueError:
                    # unknown field
                    pass
                else:
                    valueType = self._recordService.fieldName.valueType(field)
                    if valueType in (unicode, bool):
                        fields[field] = value
                    elif valueType is uuid.UUID:
                        fields[field] = uuid.UUID(value)
                    elif issubclass(valueType, Names):
                        if value is not None:
                            fields[field] = field.valueType.lookupByName(value)
                        else:
                            fields[field] = None
                    elif issubclass(valueType, NamedConstant):
                        if fieldName == "recordType":  # Is there a better way?
                            try:
                                fields[field] = BaseRecordType.lookupByName(value)
                            except ValueError:
                                try:
                                    fields[field] = RecordType.lookupByName(value)
                                except ValueError:
                                    log.error("Failed to lookup record type: {}".format(value))
                                    raise DirectoryMemcacheError

            return record_class(self._recordService, fields)

    def memcacheSetRecord(self, key, record):
        """
        Store a record in memcache.

        @param key: memcache key to use
        @type key: L{str}
        @param record: record to store
        @type record: L{DirectoryRecord}

        @raise: L{DirectoryMemcacheError} if failure to store in memcache
        """

        self.memcacheSet(key, self.pickleRecord(record))

    def memcacheSet(self, key, value):
        """
        Store a value in memcache.

        @param key: memcache key to use
        @type key: L{str}
        @param value: value to store
        @type value: L{str}

        @raise: L{DirectoryMemcacheError} if failure to store in memcache
        """

        key = base64.b64encode(key)
        if not self._getMemcacheClient().set(key, value, time=self._cacheTimeout):
            log.error("Could not write to memcache, retrying")
            if not self._getMemcacheClient(refresh=True).set(
                key, value,
                time=self._cacheTimeout
            ):
                log.error("Could not write to memcache again, giving up")
                del self.memcacheClient
                raise DirectoryMemcacheError("Failed to write to memcache")

    def memcacheGetRecord(self, key):
        """
        Try to get a record from memcache.

        @param key: the memcache key to use
        @type key: L{str}

        @return: any directory record found or L{None}
        @rtype: L{DirectoryRecord} or L{None}

        @raise: L{DirectoryMemcacheError} if failure to read from memcache
        """

        pickled = self.memcacheGet(key)
        return self.unpickleRecord(pickled) if pickled is not None else None

    def memcacheGet(self, key):
        """
        Try to get a record from memcache.

        @param key: the memcache key to use
        @type key: L{str}

        @return: any value found or L{None}
        @rtype: L{str} or L{None}

        @raise: L{DirectoryMemcacheError} if failure to read from memcache
        """

        key = base64.b64encode(key)
        try:
            value = self._getMemcacheClient().get(key)
        except MemcacheError:
            log.error("Could not read from memcache, retrying")
            try:
                value = self._getMemcacheClient(refresh=True).get(key)
            except MemcacheError:
                log.error("Could not read from memcache again, giving up")
                del self.memcacheClient
                raise DirectoryMemcacheError("Failed to read from memcache")
        return value

    def generateMemcacheKey(self, indexType, indexKey):
        """
        Return a key that can be used to store/retrieve a record in memcache.
        if short-name is the indexType the recordType be encoded into the key.

        @param indexType: one of the IndexType values
        @type indexType: L{str}
        @param indexKey: the value being indexed
        @type indexKey: L{str}

        @return: a memcache key comprised of the passed-in values and the directory
            service's realm
        @rtype: L{str}
        """
        if isinstance(indexKey, tuple):
            return "dir|v%s|%s|%s|%s|%s" % (
                self._keyVersion,
                self._realmName,
                indexType.value,
                indexKey[0],
                indexKey[1],
            )
        else:
            return "dir|v%s|%s|%s|%s" % (
                self._keyVersion,
                self._realmName,
                indexType.value,
                indexKey,
            )

    def flush(self):
        """
        Flush all records from memcache. Note this is only for testing and must not be
        called in a production setup because it flushes everything from memcache
        """
        self._getMemcacheClient().flush_all()


@implementer(IDirectoryService, IStoreDirectoryService)
class CachingDirectoryService(
    BaseDirectoryService, CalendarDirectoryServiceMixin
):
    """
    Caching directory service.

    This is a directory service that wraps an L{IDirectoryService} and caches
    directory records.
    """

    fieldName = ConstantsContainer((
        BaseFieldName,
        FieldName,
    ))

    def __init__(self, directory, expireSeconds=30, lookupsBetweenPurges=0, negativeCaching=True):
        BaseDirectoryService.__init__(self, directory.realmName)
        self._directory = directory

        # Patch the wrapped directory service's recordWithXXX to instead
        # use this cache

        directory._wrapped_recordWithUID = directory.recordWithUID
        directory.recordWithUID = self.recordWithUID

        directory._wrapped_recordWithGUID = directory.recordWithGUID
        directory.recordWithGUID = self.recordWithGUID

        directory._wrapped_recordWithShortName = directory.recordWithShortName
        directory.recordWithShortName = self.recordWithShortName

        directory._wrapped_recordsWithEmailAddress = directory.recordsWithEmailAddress
        directory.recordsWithEmailAddress = self.recordsWithEmailAddress

        self._expireSeconds = expireSeconds

        if lookupsBetweenPurges == 0:
            self._purgingEnabled = False
        else:
            self._purgingEnabled = True
            self._lookupsBetweenPurges = lookupsBetweenPurges

        self.negativeCaching = negativeCaching

        self.resetCache()

    def setTimingMethod(self, f):
        """
        Replace the default no-op timing method
        """
        self._addTiming = f

    def _addTiming(self, key, duration):
        """
        Timing won't get recorded by default -- you must call setTimingMethod
        with a callable that takes a key such as a method name, and a duration.
        """
        pass

    def resetCache(self):
        """
        Clear the cache
        """

        log.debug("Resetting cache")
        self._cache = {
            IndexType.uid: {},
            IndexType.guid: {},
            IndexType.shortName: {},  # key is (recordType.name, shortName)
            IndexType.emailAddress: {},
        }
        self._negativeCache = {
            IndexType.uid: {},
            IndexType.guid: {},
            IndexType.shortName: {},  # key is (recordType.name, shortName)
            IndexType.emailAddress: {},
        }
        self._hitCount = 0
        self._requestCount = 0
        if self._purgingEnabled:
            self._lookupsUntilScan = self._lookupsBetweenPurges

        # If DPS is in use we restrict the cache to the DPSClients only, otherwise we can
        # cache in each worker process
        if config.Memcached.Pools.Default.ClientEnabled and (
            not config.DirectoryProxy.Enabled or isinstance(self._directory, DPSClientDirectoryService)
        ):
            self._memcacher = DirectoryMemcacher(
                self._expireSeconds,
                self._directory,
                self._directory.realmName,
                "a" if config.DirectoryProxy.Enabled else "b"
            )
        else:
            self._memcacher = None

    def setTestTime(self, timestamp):
        """
        Only used for unit tests to override the notion of "now"

        @param timestamp: seconds
        @type timestamp: C{float}
        """
        self._test_time = timestamp

    def cacheRecord(self, record, indexTypes, addToMemcache=True):
        """
        Store a record in the cache, within the specified indexes

        @param record: the directory record
        @param indexTypes: an iterable of L{IndexType}
        """

        if hasattr(self, "_test_time"):
            timestamp = self._test_time
        else:
            timestamp = time.time()

        cached = []
        if IndexType.uid in indexTypes:
            self._cache[IndexType.uid][record.uid] = (timestamp, record)
            cached.append((IndexType.uid, record.uid,))

        if IndexType.guid in indexTypes:
            try:
                self._cache[IndexType.guid][record.guid] = (timestamp, record)
                cached.append((IndexType.guid, record.guid,))
            except AttributeError:
                pass
        if IndexType.shortName in indexTypes:
            try:
                typeName = record.recordType.name
                for name in record.shortNames:
                    self._cache[IndexType.shortName][(typeName, name)] = (timestamp, record)
                    cached.append((IndexType.shortName, (typeName, name),))
            except AttributeError:
                pass
        if IndexType.emailAddress in indexTypes:
            try:
                for emailAddress in record.emailAddresses:
                    self._cache[IndexType.emailAddress][emailAddress] = (timestamp, record)
                    cached.append((IndexType.emailAddress, emailAddress,))
            except AttributeError:
                pass

        if addToMemcache and self._memcacher is not None:
            for indexType, key in cached:
                memcachekey = self._memcacher.generateMemcacheKey(indexType, key)
                log.debug("Memcache: storing %s" % (memcachekey,))
                try:
                    self._memcacher.memcacheSetRecord(memcachekey, record)
                except DirectoryMemcacheError:
                    log.error("Memcache: failed to store %s" % (memcachekey,))
                    pass

    def negativeCacheRecord(self, indexType, key):
        """
        Store a record in the negative cache, within the specified indexes

        @param record: the directory record
        @param indexType: an L{IndexType}
        """

        if hasattr(self, "_test_time"):
            timestamp = self._test_time
        else:
            timestamp = time.time()

        self._negativeCache[indexType][key] = timestamp

        # Do memcache
        if self._memcacher is not None:

            # The only time the recordType arg matters is when indexType is
            # short-name, and in that case recordTypes will contain exactly
            # one recordType, so using recordTypes[0] here is always safe:
            memcachekey = self._memcacher.generateMemcacheKey(indexType, key)
            try:
                self._memcacher.memcacheSet("-%s" % (memcachekey,), timestamp)
            except DirectoryMemcacheError:
                log.error("Memcache: failed to store -%s" % (memcachekey,))
                pass

        log.debug(
            "Directory negative cache: {index} {key}",
            index=indexType.value,
            key=key
        )

    def purgeRecord(self, record):
        """
        Remove a record from all indices in the cache

        @param record: the directory record
        """

        if record.uid in self._cache[IndexType.uid]:
            del self._cache[IndexType.uid][record.uid]

        try:
            if record.guid in self._cache[IndexType.guid]:
                del self._cache[IndexType.guid][record.guid]
        except AttributeError:
            pass

        try:
            typeName = record.recordType.name
            for name in record.shortNames:
                key = (typeName, name)
                if key in self._cache[IndexType.shortName]:
                    del self._cache[IndexType.shortName][key]
        except AttributeError:
            pass

        try:
            for emailAddress in record.emailAddresses:
                if emailAddress in self._cache[IndexType.emailAddress]:
                    del self._cache[IndexType.emailAddress][emailAddress]
        except AttributeError:
            pass

    def purgeExpiredRecords(self):
        """
        Scans the cache for expired records and deletes them
        """
        if hasattr(self, "_test_time"):
            now = self._test_time
        else:
            now = time.time()

        for indexType in self._cache:
            for key, (cachedTime, _ignore_record) in self._cache[indexType].items():
                if now - self._expireSeconds > cachedTime:
                    del self._cache[indexType][key]

    def lookupRecord(self, indexType, key, name):
        """
        Looks for a record in the specified index, under the specified key.
        After every config.DirectoryCaching.LookupsBetweenPurges lookups are done,
        purgeExpiredRecords() is called.

        @param index: an index type
        @type indexType: L{IndexType}

        @param key: the key to look up in the specified index
        @type key: any valid type that can be used as a dictionary key

        @return: tuple of (the cached L{DirectoryRecord}, or L{None}) and a L{bool}
            indicating whether a query will be required (not required if a negative cache hit)
        @rtype: L{tuple}
        """

        if self._purgingEnabled:
            if self._lookupsUntilScan == 0:
                self._lookupsUntilScan = self._lookupsBetweenPurges
                self.purgeExpiredRecords()
            else:
                self._lookupsUntilScan -= 1

        if hasattr(self, "_test_time"):
            now = self._test_time
        else:
            now = time.time()

        self._requestCount += 1
        if key in self._cache[indexType]:

            cachedTime, record = self._cache[indexType].get(key, (0.0, None))
            if now - self._expireSeconds > cachedTime:
                log.debug(
                    "Directory cache miss (expired): {index} {key}",
                    index=indexType.value,
                    key=key
                )
                # This record has expired
                self.purgeRecord(record)
                self._addTiming("{}-expired".format(name), 0)

                # Fall through when the in-memory cache expires so that we check memcache
                # for a valid record BEFORE we try an ldap query and recache

            else:
                log.debug(
                    "Directory cache hit: {index} {key}",
                    index=indexType.value,
                    key=key
                )
                self._hitCount += 1
                self._addTiming("{}-hit".format(name), 0)
                return (record, False,)

        # Check negative cache (take cache entry timeout into account)
        if self.negativeCaching:
            try:
                disabledTime = self._negativeCache[indexType][key]
                if now - disabledTime < self._expireSeconds:
                    log.debug(
                        "Directory negative cache hit: {index} {key}",
                        index=indexType.value,
                        key=key
                    )
                    self._addTiming("{}-neg-hit".format(name), 0)
                    return (None, False,)
                else:
                    del self._negativeCache[indexType][key]
            except KeyError:
                pass

        # Check memcache
        if self._memcacher is not None:

            # The only time the recordType arg matters is when indexType is
            # short-name, and in that case recordTypes will contain exactly
            # one recordType, so using recordTypes[0] here is always safe:
            memcachekey = self._memcacher.generateMemcacheKey(indexType, key)

            log.debug("Memcache: checking %s" % (memcachekey,))

            try:
                record = self._memcacher.memcacheGetRecord(memcachekey)
            except DirectoryMemcacheError:
                log.error("Memcache: failed to get %s" % (memcachekey,))
                record = None

            if record is None:
                log.debug("Memcache: miss %s" % (memcachekey,))
            else:
                log.debug("Memcache: hit %s" % (memcachekey,))
                self.cacheRecord(record, (IndexType.uid, IndexType.guid, IndexType.shortName,), addToMemcache=False)
                return (record, False,)

            # Check negative memcache
            if self.negativeCaching:
                try:
                    val = self._memcacher.memcacheGet("-%s" % (memcachekey,))
                except DirectoryMemcacheError:
                    log.error("Memcache: failed to get -%s" % (memcachekey,))
                    val = None
                if val == 1:
                    log.debug("Memcache: negative hit %s" % (memcachekey,))
                    self._negativeCache[indexType][key] = now
                    return (None, False,)

        log.debug(
            "Directory cache miss: {index} {key}",
            index=indexType.value,
            key=key
        )

        self._addTiming("{}-miss".format(name), 0)
        return (None, True,)

    # Cached methods:

    @inlineCallbacks
    def recordWithUID(self, uid, timeoutSeconds=None):

        # First check our cache
        record, doQuery = self.lookupRecord(IndexType.uid, uid, "recordWithUID")
        if record is None and doQuery:
            record = yield self._directory._wrapped_recordWithUID(
                uid, timeoutSeconds=timeoutSeconds
            )
            if record is not None:
                # Note we do not index on email address; see below.
                self.cacheRecord(
                    record,
                    (IndexType.uid, IndexType.guid, IndexType.shortName)
                )
            else:
                self.negativeCacheRecord(IndexType.uid, uid)

        returnValue(record)

    @inlineCallbacks
    def recordWithGUID(self, guid, timeoutSeconds=None):

        # First check our cache
        record, doQuery = self.lookupRecord(IndexType.guid, guid, "recordWithGUID")
        if record is None and doQuery:
            record = yield self._directory._wrapped_recordWithGUID(
                guid, timeoutSeconds=timeoutSeconds
            )
            if record is not None:
                # Note we do not index on email address; see below.
                self.cacheRecord(
                    record,
                    (IndexType.uid, IndexType.guid, IndexType.shortName)
                )
            else:
                self.negativeCacheRecord(IndexType.guid, guid)

        returnValue(record)

    @inlineCallbacks
    def recordWithShortName(self, recordType, shortName, timeoutSeconds=None):

        # First check our cache
        record, doQuery = self.lookupRecord(
            IndexType.shortName,
            (recordType.name, shortName),
            "recordWithShortName"
        )
        if record is None and doQuery:
            record = yield self._directory._wrapped_recordWithShortName(
                recordType, shortName, timeoutSeconds=timeoutSeconds
            )
            if record is not None:
                # Note we do not index on email address; see below.
                self.cacheRecord(
                    record,
                    (IndexType.uid, IndexType.guid, IndexType.shortName)
                )
            else:
                self.negativeCacheRecord(IndexType.shortName, (recordType.name, shortName))

        returnValue(record)

    @inlineCallbacks
    def recordsWithEmailAddress(
        self, emailAddress, limitResults=None, timeoutSeconds=None
    ):

        # First check our cache
        record, doQuery = self.lookupRecord(
            IndexType.emailAddress,
            emailAddress,
            "recordsWithEmailAddress"
        )
        if record is None and doQuery:
            records = yield self._directory._wrapped_recordsWithEmailAddress(
                emailAddress,
                limitResults=limitResults, timeoutSeconds=timeoutSeconds
            )
            if len(records) == 1:
                # Only cache if there was a single match (which is the most
                # common scenario).  Caching multiple records for the exact
                # same key/value complicates the data structures.
                # Also, this is the only situation where we do index a cached
                # record on email address.  Otherwise, say we had faulted in
                # on "uid" and then indexed that record on its email address,
                # the next lookup by email address would only get that record,
                # but there might be others in the directory service with that
                # same email address.
                self.cacheRecord(
                    list(records)[0],
                    (
                        IndexType.uid, IndexType.guid,
                        IndexType.shortName, IndexType.emailAddress
                    )
                )
            elif len(records) == 0:
                self.negativeCacheRecord(IndexType.emailAddress, emailAddress)
        else:
            records = [record]

        returnValue(records)

    # Uncached methods:

    @property
    def recordType(self):
        # Defer to the directory service we're caching
        return self._directory.recordType

    def recordTypes(self):
        # Defer to the directory service we're caching
        return self._directory.recordTypes()

    def recordsFromExpression(
        self, expression, recordTypes=None, records=None,
        limitResults=None, timeoutSeconds=None
    ):
        # Defer to the directory service we're caching
        return self._directory.recordsFromExpression(
            expression, recordTypes=recordTypes, records=records,
            limitResults=limitResults, timeoutSeconds=timeoutSeconds
        )

    def recordsWithFieldValue(
        self, fieldName, value,
        limitResults=None, timeoutSeconds=None
    ):
        # Defer to the directory service we're caching
        return self._directory.recordsWithFieldValue(
            fieldName, value,
            limitResults=limitResults, timeoutSeconds=timeoutSeconds
        )

    def updateRecords(self, records, create=False):
        # Defer to the directory service we're caching
        return self._directory.updateRecords(records, create=create)

    def removeRecords(self, uids):
        # Defer to the directory service we're caching
        return self._directory.removeRecords(uids)

    def recordsWithRecordType(
        self, recordType, limitResults=None, timeoutSeconds=None
    ):
        # Defer to the directory service we're caching
        return self._directory.recordsWithRecordType(
            recordType, limitResults=limitResults, timeoutSeconds=timeoutSeconds
        )

    def recordsMatchingTokens(
        self, tokens, context=None, limitResults=None, timeoutSeconds=None
    ):
        return self._directory.recordsMatchingTokens(
            tokens, context=context,
            limitResults=limitResults, timeoutSeconds=timeoutSeconds
        )

    def recordsMatchingFields(
        self, fields, operand, recordType,
        limitResults=None, timeoutSeconds=None
    ):
        return self._directory.recordsMatchingFields(
            fields, operand, recordType,
            limitResults=limitResults, timeoutSeconds=timeoutSeconds
        )

    def recordsWithDirectoryBasedDelegates(self):
        return self._directory.recordsWithDirectoryBasedDelegates()

    def recordWithCalendarUserAddress(self, cua, timeoutSeconds=None):
        # This will get cached by the underlying recordWith... call
        return CalendarDirectoryServiceMixin.recordWithCalendarUserAddress(
            self, cua, timeoutSeconds=timeoutSeconds
        )

    def serversDB(self):
        return self._directory.serversDB()

    @inlineCallbacks
    def flush(self):
        if self._memcacher is not None:
            self._memcacher.flush()
        self.resetCache()
        yield self._directory.flush()

    def stats(self):
        return self._directory.stats()
