##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks, Deferred

from twistedcaldav.memcachefifolock import MemcacheFIFOLock

from twistedcaldav.test.util import TestCase
import cPickle
from twistedcaldav.memcachelock import MemcacheLockTimeoutError
from twistedcaldav.memcacher import Memcacher
from twisted.internet import reactor

class MemCacheTestCase(TestCase):
    """
    Test client protocol class L{MemCacheProtocol}.
    """

    @inlineCallbacks
    def test_one_lock(self):

        lock = MemcacheFIFOLock("lock", "test")
        lock.allowTestCache = True

        yield lock.acquire()
        self.assertTrue((yield lock.locked()))

        yield lock.release()
        self.assertFalse((yield lock.locked()))

        self.assertEqual((yield lock.get(lock._ticket_token)), "2")
        self.assertEqual((yield lock.get(lock._nextinline_token)), "0")
        self.assertEqual(cPickle.loads((yield lock.get(lock._queue_token))), [])

    @inlineCallbacks
    def test_two_locks_with_timeout(self):

        lock1 = MemcacheFIFOLock("lock", "test")
        lock1.allowTestCache = True

        lock2 = MemcacheFIFOLock("lock", "test", timeout=0.01)
        lock2.allowTestCache = True
        
        lock1._memcacheProtocol = lock2._memcacheProtocol = Memcacher.memoryCacher()

        yield lock1.acquire()
        self.assertTrue((yield lock1.locked()))

        try:
            yield lock2.acquire()
        except MemcacheLockTimeoutError:
            pass
        else:
            self.fail("Did not timeout lock")

        self.assertTrue((yield lock1.locked()))
        self.assertFalse((yield lock2.locked()))

        self.assertEqual((yield lock1.get(lock1._ticket_token)), "3")
        self.assertEqual((yield lock1.get(lock1._nextinline_token)), "1")
        self.assertEqual(cPickle.loads((yield lock1.get(lock1._queue_token))), [1,])

        yield lock1.release()
        self.assertFalse((yield lock1.locked()))

        self.assertEqual((yield lock1.get(lock1._ticket_token)), "3")
        self.assertEqual((yield lock1.get(lock1._nextinline_token)), "0")
        self.assertEqual(cPickle.loads((yield lock1.get(lock1._queue_token))), [])

    @inlineCallbacks
    def test_two_locks_in_sequence(self):

        lock1 = MemcacheFIFOLock("lock", "test")
        lock1.allowTestCache = True

        lock2 = MemcacheFIFOLock("lock", "test")
        lock2.allowTestCache = True
        
        lock1._memcacheProtocol = lock2._memcacheProtocol = Memcacher.memoryCacher()

        yield lock1.acquire()
        self.assertTrue((yield lock1.locked()))
        self.assertFalse((yield lock2.locked()))

        yield lock1.release()
        self.assertFalse((yield lock1.locked()))
        self.assertFalse((yield lock2.locked()))

        yield lock2.acquire()
        self.assertFalse((yield lock1.locked()))
        self.assertTrue((yield lock2.locked()))

        yield lock2.release()
        self.assertFalse((yield lock1.locked()))
        self.assertFalse((yield lock2.locked()))

        self.assertEqual((yield lock1.get(lock1._ticket_token)), "3")
        self.assertEqual((yield lock1.get(lock1._nextinline_token)), "0")
        self.assertEqual(cPickle.loads((yield lock1.get(lock1._queue_token))), [])

    @inlineCallbacks
    def test_two_locks_in_parallel(self):

        lock1 = MemcacheFIFOLock("lock", "test", timeout=1.0)
        lock1.allowTestCache = True

        lock2 = MemcacheFIFOLock("lock", "test", timeout=1.0)
        lock2.allowTestCache = True
        
        lock1._memcacheProtocol = lock2._memcacheProtocol = Memcacher.memoryCacher()

        yield lock1.acquire()
        self.assertTrue((yield lock1.locked()))
        self.assertFalse((yield lock2.locked()))

        @inlineCallbacks
        def _release1():
            self.assertTrue((yield lock1.locked()))
            self.assertFalse((yield lock2.locked()))
            yield lock1.release()
            self.assertFalse((yield lock1.locked()))
            self.assertFalse((yield lock2.locked()))
        reactor.callLater(0.1, _release1)

        yield lock2.acquire()
        self.assertFalse((yield lock1.locked()))
        self.assertTrue((yield lock2.locked()))

        yield lock2.release()
        self.assertFalse((yield lock1.locked()))
        self.assertFalse((yield lock2.locked()))

        self.assertEqual((yield lock1.get(lock1._ticket_token)), "3")
        self.assertEqual((yield lock1.get(lock1._nextinline_token)), "0")
        self.assertEqual(cPickle.loads((yield lock1.get(lock1._queue_token))), [])


    @inlineCallbacks
    def test_three_in_order(self):
        """
        This tests overlaps a lock on #1 with two attempts on #2 and #3. #3 has
        a very much shorter polling interval than #2 so when #1 releases, #3 will
        poll first. We want to make sure that #3 is not given the lock until after
        #2 has polled and acquired/releases it. i.e., this tests the FIFO behavior.
        """

        lock1 = MemcacheFIFOLock("lock", "test", timeout=2.0)
        lock1.allowTestCache = True

        lock2 = MemcacheFIFOLock("lock", "test", timeout=2.0, retry_interval=0.5)
        lock2.allowTestCache = True
        
        lock3 = MemcacheFIFOLock("lock", "test", timeout=2.0, retry_interval=0.01) # retry a lot faster than #2
        lock3.allowTestCache = True
        
        lock1._memcacheProtocol = \
        lock2._memcacheProtocol = \
        lock3._memcacheProtocol = Memcacher.memoryCacher()

        d = Deferred()

        yield lock1.acquire()
        self.assertTrue((yield lock1.locked()))
        self.assertFalse((yield lock2.locked()))
        self.assertFalse((yield lock3.locked()))

        @inlineCallbacks
        def _release1():
            self.assertTrue((yield lock1.locked()))
            self.assertFalse((yield lock2.locked()))
            self.assertFalse((yield lock3.locked()))
            yield lock1.release()
            self.assertFalse((yield lock1.locked()))
            self.assertFalse((yield lock2.locked()))
            self.assertFalse((yield lock3.locked()))
    
            self.assertEqual((yield lock1.get(lock1._ticket_token)), "4")
            self.assertEqual((yield lock1.get(lock1._nextinline_token)), "2")
            self.assertEqual(cPickle.loads((yield lock1.get(lock1._queue_token))), [2, 3])
        reactor.callLater(0.1, _release1)

        @inlineCallbacks
        def _acquire2():
            self.assertTrue((yield lock1.locked()))
            self.assertFalse((yield lock2.locked()))
            self.assertFalse((yield lock3.locked()))
            
            @inlineCallbacks
            def _release2():
                self.assertFalse((yield lock1.locked()))
                self.assertTrue((yield lock2.locked()))
                self.assertFalse((yield lock3.locked()))
                yield lock2.release()
                self.assertFalse((yield lock1.locked()))
                self.assertFalse((yield lock2.locked()))
                self.assertFalse((yield lock3.locked()))

            yield lock2.acquire()
            reactor.callLater(0.1, _release2)
            self.assertFalse((yield lock1.locked()))
            self.assertTrue((yield lock2.locked()))
            self.assertFalse((yield lock3.locked()))

        reactor.callLater(0.01, _acquire2)

        @inlineCallbacks
        def _acquire3():
            self.assertTrue((yield lock1.locked()))
            self.assertFalse((yield lock2.locked()))
            self.assertFalse((yield lock3.locked()))
            
            @inlineCallbacks
            def _release3():
                self.assertFalse((yield lock1.locked()))
                self.assertFalse((yield lock2.locked()))
                self.assertTrue((yield lock3.locked()))
                yield lock3.release()
                self.assertFalse((yield lock1.locked()))
                self.assertFalse((yield lock2.locked()))
                self.assertFalse((yield lock3.locked()))
        
                self.assertEqual((yield lock1.get(lock1._ticket_token)), "4")
                self.assertEqual((yield lock1.get(lock1._nextinline_token)), "0")
                self.assertEqual(cPickle.loads((yield lock1.get(lock1._queue_token))), [])
                
                d.callback(True)

            yield lock3.acquire()
            reactor.callLater(0.1, _release3)
            self.assertFalse((yield lock1.locked()))
            self.assertFalse((yield lock2.locked()))
            self.assertTrue((yield lock3.locked()))

        reactor.callLater(0.02, _acquire3)

        yield d
