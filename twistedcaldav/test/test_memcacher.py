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
            config.ProcessType = processType

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
            config.ProcessType = processType

            cacher = Memcacher("testing")
    
            result = yield cacher.get("akey")
            self.assertEquals(None, result)

    @inlineCallbacks
    def test_delete(self):

        for processType in ("Single", "Combined",):
            config.ProcessType = processType

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
            config.ProcessType = processType

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
            config.ProcessType = processType

            cacher = Memcacher("testing", no_invalidation=True)
    
            result = yield cacher.set("akey", ["1", "2", "3",])
            self.assertTrue(result)
    
            result = yield cacher.get("akey")
            self.assertEquals(["1", "2", "3",], result)
    
            result = yield cacher.delete("akey")
            self.assertTrue(result)
    
            result = yield cacher.get("akey")
            self.assertEquals(None, result)

    def test_keynormalization(self):

        for processType in ("Single", "Combined",):
            config.ProcessType = processType

            cacher = Memcacher("testing")
            
            self.assertTrue(len(cacher._normalizeKey("A" * 100)) <= 250)
            self.assertTrue(len(cacher._normalizeKey("A" * 512)) <= 250)
            
            key = cacher._normalizeKey(" \n\t\r" * 20)
            self.assertTrue(" " not in key)
            self.assertTrue("\n" not in key)
            self.assertTrue("\t" not in key)
            self.assertTrue("\r" not in key)

    @inlineCallbacks
    def test_expiration(self):

        config.ProcessType = "Single"
        cacher = Memcacher("testing")

        # Expire this key in 10 seconds
        result = yield cacher.set("akey", "avalue", 10)
        self.assertTrue(result)

        result = yield cacher.get("akey")
        self.assertEquals("avalue", result)

        # Advance time 9 seconds, key still there
        cacher._memcacheProtocol.advanceClock(9)
        result = yield cacher.get("akey")
        self.assertEquals("avalue", result)

        # Advance time 1 more second, key expired
        cacher._memcacheProtocol.advanceClock(1)
        result = yield cacher.get("akey")
        self.assertEquals(None, result)

    @inlineCallbacks
    def test_checkAndSet(self):

        config.ProcessType = "Single"
        cacher = Memcacher("testing")

        result = yield cacher.set("akey", "avalue")
        self.assertTrue(result)

        value, identifier = yield cacher.get("akey", withIdentifier=True)
        self.assertEquals("avalue", value)
        self.assertEquals(identifier, "0")

        # Make sure cas identifier changes (we know the test implementation increases
        # by 1 each time)
        result = yield cacher.set("akey", "anothervalue")
        value, identifier = yield cacher.get("akey", withIdentifier=True)
        self.assertEquals("anothervalue", value)
        self.assertEquals(identifier, "1")

        # Should not work because key doesn't exist:
        self.assertFalse((yield cacher.checkAndSet("missingkey", "val", "0")))
        # Should not work because identifier doesn't match:
        self.assertFalse((yield cacher.checkAndSet("akey", "yetanother", "0")))
        # Should work because identifier does match:
        self.assertTrue((yield cacher.checkAndSet("akey", "yetanother", "1")))
