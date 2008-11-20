# Copyright (c) 2007 Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test the memcacher cache abstraction.
"""

from twisted.internet.defer import inlineCallbacks

from twistedcaldav.config import config
from twistedcaldav.memcacher import Memcacher
from twistedcaldav.test.util import TestCase

class MemcacherTestCase(TestCase):
    """
    Test Memcacher abstract cache.
    """

    @inlineCallbacks
    def test_setget(self):

        for processType in ("Single", "Combined",):
            config.processType = processType

            cacher = Memcacher("testing")
    
            result = yield cacher.set("akey", "avalue")
            self.assertTrue(result)

            result = yield cacher.get("akey")
            if isinstance(cacher._memcacheProtocol, Memcacher.nullCacher):
                self.assertEquals(None, result)
            else:
                self.assertEquals("avalue", result)

    @inlineCallbacks
    def test_missingget(self):

        for processType in ("Single", "Combined",):
            config.processType = processType

            cacher = Memcacher("testing")
    
            result = yield cacher.get("akey")
            self.assertEquals(None, result)

    @inlineCallbacks
    def test_delete(self):

        for processType in ("Single", "Combined",):
            config.processType = processType

            cacher = Memcacher("testing")
    
            result = yield cacher.set("akey", "avalue")
            self.assertTrue(result)
    
            result = yield cacher.get("akey")
            if isinstance(cacher._memcacheProtocol, Memcacher.nullCacher):
                self.assertEquals(None, result)
            else:
                self.assertEquals("avalue", result)
    
            result = yield cacher.delete("akey")
            self.assertTrue(result)
    
            result = yield cacher.get("akey")
            self.assertEquals(None, result)

    @inlineCallbacks
    def test_all_pickled(self):

        for processType in ("Single", "Combined",):
            config.processType = processType

            cacher = Memcacher("testing", pickle=True)
    
            result = yield cacher.set("akey", ["1", "2", "3",])
            self.assertTrue(result)
    
            result = yield cacher.get("akey")
            if isinstance(cacher._memcacheProtocol, Memcacher.nullCacher):
                self.assertEquals(None, result)
            else:
                self.assertEquals(["1", "2", "3",], result)
    
            result = yield cacher.delete("akey")
            self.assertTrue(result)
    
            result = yield cacher.get("akey")
            self.assertEquals(None, result)

    @inlineCallbacks
    def test_all_noinvalidation(self):

        for processType in ("Single", "Combined",):
            config.processType = processType

            cacher = Memcacher("testing", no_invalidation=True)
    
            result = yield cacher.set("akey", ["1", "2", "3",])
            self.assertTrue(result)
    
            result = yield cacher.get("akey")
            self.assertEquals(["1", "2", "3",], result)
    
            result = yield cacher.delete("akey")
            self.assertTrue(result)
    
            result = yield cacher.get("akey")
            self.assertEquals(None, result)

