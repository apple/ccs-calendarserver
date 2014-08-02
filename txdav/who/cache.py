# -*- test-case-name: txdav.who.test.test_cache -*-
##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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

import time

from zope.interface import implementer

from twisted.internet.defer import inlineCallbacks, returnValue
from twext.python.log import Logger
from twext.who.directory import DirectoryService as BaseDirectoryService
from twext.who.idirectory import (
    IDirectoryService, FieldName as BaseFieldName
)
from twext.who.util import ConstantsContainer

from txdav.common.idirectoryservice import IStoreDirectoryService
from txdav.who.directory import (
    CalendarDirectoryServiceMixin,
)
from txdav.who.idirectory import (
    FieldName
)
from twisted.python.constants import Values, ValueConstant

log = Logger()


class IndexType(Values):
    """
    Constants to use for identifying indexes
    """
    uid = ValueConstant("uid")
    guid = ValueConstant("guid")
    shortName = ValueConstant("shortName")
    emailAddress = ValueConstant("emailAddress")


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



    def __init__(self, directory, expireSeconds=30):
        BaseDirectoryService.__init__(self, directory.realmName)
        self._directory = directory
        self._expireSeconds = expireSeconds
        self.resetCache()


    def resetCache(self):
        """
        Clear the cache
        """
        self._cache = {
            IndexType.uid: {},
            IndexType.guid: {},
            IndexType.shortName: {},  # key is (recordType.name, shortName)
            IndexType.emailAddress: {},
        }
        self._hitCount = 0
        self._requestCount = 0


    def setTestTime(self, timestamp):
        self._test_time = timestamp


    def cacheRecord(self, record, indexTypes):
        """
        Store a record in the cache, within the specified indexes

        @param record: the directory record
        @param indexTypes: an iterable of L{IndexType}
        """

        if hasattr(self, "_test_time"):
            timestamp = self._test_time
        else:
            timestamp = time.time()

        if IndexType.uid in indexTypes:
            self._cache[IndexType.uid][record.uid] = (timestamp, record)

        if IndexType.guid in indexTypes:
            try:
                self._cache[IndexType.guid][record.guid] = (timestamp, record)
            except AttributeError:
                pass
        if IndexType.shortName in indexTypes:
            try:
                typeName = record.recordType.name
                for name in record.shortNames:
                    self._cache[IndexType.shortName][(typeName, name)] = (timestamp, record)
            except AttributeError:
                pass
        if IndexType.emailAddress in indexTypes:
            try:
                for emailAddress in record.emailAddresses:
                    self._cache[IndexType.emailAddress][emailAddress] = (timestamp, record)
            except AttributeError:
                pass


    def lookupRecord(self, indexType, key):
        """
        Looks for a record in the specified index, under the specified key

        @param index: an index type
        @type indexType: L{IndexType}

        @param key: the key to look up in the specified index
        @type key: any valid type that can be used as a dictionary key

        @return: the cached directory record, or None
        @rtype: L{DirectoryRecord}
        """

        self._requestCount += 1
        if key in self._cache[indexType]:

            if hasattr(self, "_test_time"):
                now = self._test_time
            else:
                now = time.time()

            cachedTime, record = self._cache[indexType].get(key, (0.0, None))
            if now - self._expireSeconds > cachedTime:
                log.debug(
                    "Directory cache miss (expired): {index} {key}",
                    index=indexType.value,
                    key=key
                )
                # This record has expired
                del self._cache[indexType][key]
                return None

            log.debug(
                "Directory cache hit: {index} {key}",
                index=indexType.value,
                key=key
            )
            self._hitCount += 1
            return record
        else:
            log.debug(
                "Directory cache miss: {index} {key}",
                index=indexType.value,
                key=key
            )
        return None


    # Cached methods:

    @inlineCallbacks
    def recordWithUID(self, uid):

        # First check our cache
        record = self.lookupRecord(IndexType.uid, uid)
        if record is None:
            record = yield self._directory.recordWithUID(uid)
            if record is not None:
                # Note we do not index on email address; see below.
                self.cacheRecord(
                    record,
                    (IndexType.uid, IndexType.guid, IndexType.shortName)
                )

        returnValue(record)


    @inlineCallbacks
    def recordWithGUID(self, guid):

        # First check our cache
        record = self.lookupRecord(IndexType.guid, guid)
        if record is None:
            record = yield self._directory.recordWithGUID(guid)
            if record is not None:
                # Note we do not index on email address; see below.
                self.cacheRecord(
                    record,
                    (IndexType.uid, IndexType.guid, IndexType.shortName)
                )

        returnValue(record)


    @inlineCallbacks
    def recordWithShortName(self, recordType, shortName):

        # First check our cache
        record = self.lookupRecord(
            IndexType.shortName,
            (recordType.name, shortName)
        )
        if record is None:
            record = yield self._directory.recordWithShortName(
                recordType, shortName
            )
            if record is not None:
                # Note we do not index on email address; see below.
                self.cacheRecord(
                    record,
                    (IndexType.uid, IndexType.guid, IndexType.shortName)
                )

        returnValue(record)


    @inlineCallbacks
    def recordsWithEmailAddress(self, emailAddress):

        # First check our cache
        record = self.lookupRecord(IndexType.emailAddress, emailAddress)
        if record is None:
            records = yield self._directory.recordsWithEmailAddress(emailAddress)
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
                    records[0],
                    (
                        IndexType.uid, IndexType.guid,
                        IndexType.shortName, IndexType.emailAddress
                    )
                )
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


    def recordsFromExpression(self, expression, recordTypes=None):
        # Defer to the directory service we're caching
        return self._directory.recordsFromExpression(
            expression, recordTypes=recordTypes
        )


    def recordsWithFieldValue(self, fieldName, value):
        # Defer to the directory service we're caching
        return self._directory.recordsWithFieldValue(
            fieldName, value
        )


    def updateRecords(self, records, create=False):
        # Defer to the directory service we're caching
        return self._directory.updateRecords(records, create=create)


    def removeRecords(self, uids):
        # Defer to the directory service we're caching
        return self._directory.removeRecords(uids)


    def recordsWithRecordType(self, recordType):
        # Defer to the directory service we're caching
        return self._directory.recordsWithRecordType(recordType)


    def recordsMatchingTokens(self, *args, **kwds):
        return CalendarDirectoryServiceMixin.recordsMatchingTokens(
            self, *args, **kwds
        )


    def recordsMatchingFields(self, *args, **kwds):
        return CalendarDirectoryServiceMixin.recordsMatchingFields(
            self, *args, **kwds
        )


    def recordWithCalendarUserAddress(self, *args, **kwds):
        # This will get cached by the underlying recordWith... call
        return CalendarDirectoryServiceMixin.recordWithCalendarUserAddress(
            self, *args, **kwds
        )
