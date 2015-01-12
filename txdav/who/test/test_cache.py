##
# Copyright (c) 2014-2015 Apple Inc. All rights reserved.
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
Caching service tests
"""

from twisted.internet.defer import inlineCallbacks
from twistedcaldav.test.util import StoreTestCase
from txdav.who.cache import (
    CachingDirectoryService, IndexType, SCAN_AFTER_LOOKUP_COUNT
)
from twext.who.idirectory import (
    RecordType
)
from txdav.who.idirectory import (
    RecordType as CalRecordType
)
import uuid


class CacheTest(StoreTestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(CacheTest, self).setUp()

        self.cachingDirectory = CachingDirectoryService(
            self.directory,
            expireSeconds=10
        )
        self.storeUnderTest().setDirectoryService(self.cachingDirectory)


    @inlineCallbacks
    def test_cachingPassThrough(self):
        """
        Verify the CachingDirectoryService can pass through method calls to
        the underlying service.
        """

        dir = self.cachingDirectory

        self.assertTrue(RecordType.user in dir.recordTypes())
        self.assertTrue(RecordType.group in dir.recordTypes())
        self.assertTrue(CalRecordType.location in dir.recordTypes())
        self.assertTrue(CalRecordType.resource in dir.recordTypes())

        records = yield dir.recordsWithRecordType(RecordType.user)
        self.assertEquals(len(records), 244)

        record = yield dir.recordWithGUID(uuid.UUID("8166C681-2D08-4846-90F7-97023A6EDDC5"))
        self.assertEquals(record.uid, u"cache-uid-1")

        record = yield dir.recordWithShortName(RecordType.user, u"cache-name-2")
        self.assertEquals(record.uid, u"cache-uid-2")

        records = yield dir.recordsWithEmailAddress(u"cache-user-1@example.com")
        self.assertEquals(len(records), 2)

        record = yield dir.recordWithCalendarUserAddress(u"mailto:cache-user-2@example.com")
        self.assertEquals(record.uid, u"cache-uid-2")


    @inlineCallbacks
    def test_cachingHitsAndMisses(self):
        """
        Verify faulted in records are indexed appropriately and can be retrieved
        from the cache even by other attributes.
        """

        dir = self.cachingDirectory

        # Caching on UID
        self.assertEquals(dir._hitCount, 0)
        self.assertEquals(dir._requestCount, 0)
        record = yield dir.recordWithUID(u"cache-uid-1")
        self.assertEquals(record.uid, u"cache-uid-1")
        self.assertEquals(dir._hitCount, 0)
        self.assertEquals(dir._requestCount, 1)

        # Repeat the same lookup
        record = yield dir.recordWithUID(u"cache-uid-1")
        self.assertEquals(record.uid, u"cache-uid-1")
        self.assertEquals(dir._hitCount, 1)
        self.assertEquals(dir._requestCount, 2)

        # Lookup the same record, but by GUID
        record = yield dir.recordWithGUID(uuid.UUID("8166C681-2D08-4846-90F7-97023A6EDDC5"))
        self.assertEquals(record.uid, u"cache-uid-1")
        self.assertEquals(dir._hitCount, 2)
        self.assertEquals(dir._requestCount, 3)

        # Lookup by the shortName for that same record, and it should be a hit
        record = yield dir.recordWithShortName(RecordType.user, u"cache-name-1")
        self.assertEquals(record.uid, u"cache-uid-1")
        self.assertEquals(dir._hitCount, 3)
        self.assertEquals(dir._requestCount, 4)

        # Now lookup by a different shortName for that same record, and it
        # should also be a hit
        record = yield dir.recordWithShortName(RecordType.user, u"cache-alt-name-1")
        self.assertEquals(record.uid, u"cache-uid-1")
        self.assertEquals(dir._hitCount, 4)
        self.assertEquals(dir._requestCount, 5)


        dir.resetCache()

        # Look up another record which has a unique email address, first by uid
        # and then by email address and verify this is a cache miss because we
        # intentionally don't index on email address when faulting in by another
        # attribute
        record = yield dir.recordWithUID(u"cache-uid-2")
        self.assertEquals(record.uid, u"cache-uid-2")
        self.assertEquals(dir._hitCount, 0)
        self.assertEquals(dir._requestCount, 1)

        records = yield dir.recordsWithEmailAddress(u"cache-user-2@example.com")
        self.assertEquals(len(records), 1)
        self.assertEquals(dir._hitCount, 0)
        self.assertEquals(dir._requestCount, 2)

        records = yield dir.recordsWithEmailAddress(u"cache-user-2@example.com")
        self.assertEquals(len(records), 1)
        self.assertEquals(dir._hitCount, 1)
        self.assertEquals(dir._requestCount, 3)

        dir.resetCache()

        # Look up a record which has the same email address as another record.
        record = yield dir.recordWithUID(u"cache-uid-2")
        self.assertEquals(record.uid, u"cache-uid-2")
        self.assertEquals(dir._hitCount, 0)
        self.assertEquals(dir._requestCount, 1)

        # Now lookup by the email address for that record, and it should
        # be a miss;  Note, because there are two records with this email
        # address, when we repeat this call it will still be a miss because
        # for simplicity we're only going to cache records when there is a
        # single result.
        records = yield dir.recordsWithEmailAddress(u"cache-user-1@example.com")
        self.assertEquals(len(records), 2)
        self.assertEquals(dir._hitCount, 0)
        self.assertEquals(dir._requestCount, 2)

        records = yield dir.recordsWithEmailAddress(u"cache-user-1@example.com")
        self.assertEquals(len(records), 2)
        self.assertEquals(dir._hitCount, 0)
        self.assertEquals(dir._requestCount, 3)


    @inlineCallbacks
    def test_cachingByCUA(self):
        """
        recordWithCalendarUserAddress does not cache directly; the
        underlying recordWith...() call should do the caching instead.
        """

        dir = self.cachingDirectory

        record = yield dir.recordWithCalendarUserAddress(u"mailto:cache-user-2@example.com")
        self.assertEquals(record.uid, u"cache-uid-2")
        self.assertEquals(dir._hitCount, 0)
        self.assertEquals(dir._requestCount, 1)
        record = yield dir.recordWithCalendarUserAddress(u"mailto:cache-user-2@example.com")
        self.assertEquals(record.uid, u"cache-uid-2")
        self.assertEquals(dir._hitCount, 1)
        self.assertEquals(dir._requestCount, 2)

        dir.resetCache()

        record = yield dir.recordWithCalendarUserAddress(u"urn:x-uid:cache-uid-1")
        self.assertEquals(record.uid, u"cache-uid-1")
        self.assertEquals(dir._hitCount, 0)
        self.assertEquals(dir._requestCount, 1)
        record = yield dir.recordWithCalendarUserAddress(u"urn:x-uid:cache-uid-1")
        self.assertEquals(record.uid, u"cache-uid-1")
        self.assertEquals(dir._hitCount, 1)
        self.assertEquals(dir._requestCount, 2)


    @inlineCallbacks
    def test_cachingExpiration(self):
        """
        Verify records expire at the expected time; in these tests, 10 seconds
        """

        dir = self.cachingDirectory

        dir.setTestTime(1.0)

        record = yield dir.recordWithUID(u"cache-uid-1")
        self.assertEquals(record.uid, u"cache-uid-1")
        self.assertEquals(dir._hitCount, 0)
        self.assertEquals(dir._requestCount, 1)

        # 1 second later, the record is still cached
        dir.setTestTime(2.0)
        record = yield dir.recordWithUID(u"cache-uid-1")
        self.assertEquals(record.uid, u"cache-uid-1")
        self.assertEquals(dir._hitCount, 1)
        self.assertEquals(dir._requestCount, 2)

        # 10 seconds later, the record is no longer cached
        dir.setTestTime(12.0)
        record = yield dir.recordWithUID(u"cache-uid-1")
        self.assertEquals(record.uid, u"cache-uid-1")
        self.assertEquals(dir._hitCount, 1)
        self.assertEquals(dir._requestCount, 3)

        # Wait another 11 seconds, verify it's not cached by other attributes
        dir.setTestTime(23.0)
        record = yield dir.recordWithShortName(RecordType.user, u"cache-alt-name-1")
        self.assertEquals(record.uid, u"cache-uid-1")
        self.assertEquals(dir._hitCount, 1)
        self.assertEquals(dir._requestCount, 4)


    @inlineCallbacks
    def test_cachePurging(self):
        """
        Verify records are purged from cache after a certain amount of requests
        """

        dir = self.cachingDirectory

        dir.setTestTime(1.0)

        record = yield dir.recordWithUID(u"cache-uid-1")
        self.assertEquals(record.uid, u"cache-uid-1")
        self.assertEquals(dir._hitCount, 0)
        self.assertEquals(dir._requestCount, 1)

        # 60 seconds later, the record has expired, but is still present
        dir.setTestTime(60.0)

        self.assertTrue(u"cache-uid-1" in dir._cache[IndexType.uid])

        # After SCAN_AFTER_LOOKUP_COUNT requests, however, that expired entry
        # will be removed

        for _ignore_i in xrange(SCAN_AFTER_LOOKUP_COUNT):
            yield dir.recordWithUID(u"cache-uid-2")

        # cache-uid-1 no longer in cache
        self.assertFalse(u"cache-uid-1" in dir._cache[IndexType.uid])
        # cache-uid-2 still in cache
        self.assertTrue(u"cache-uid-2" in dir._cache[IndexType.uid])
