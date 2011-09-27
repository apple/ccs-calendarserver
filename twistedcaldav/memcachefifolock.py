##
# Copyright (c) 2008-2009 Apple Inc. All rights reserved.
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

from twistedcaldav.memcacher import Memcacher
from twisted.internet.defer import inlineCallbacks, Deferred, returnValue,\
    succeed
from twisted.internet import reactor
import time
from twistedcaldav.memcachelock import MemcacheLock, MemcacheLockTimeoutError
import cPickle

class MemcacheFIFOLock(Memcacher):
    """
    Implements a shared lock with a queue such that lock requests are honored in the order
    in which they are received. This differs from MemcacheLock which does not honor ordering
    of lock requests.
    
    The implementation here uses two memcached entries. One represent a ticket counter - a
    counter incremented and returned each time a lock is requested. The other is the
    "next in line queue" - a sorted list of pending counters. To get a lock the caller
    is given the next ticket value, then polls waiting for their number to come up as
    "next in line". When it does they are given the lock, and upon releasing it their
    "next in line" value is popped off the front of the queue, giving the next a chance
    to get the lock.
    
    One complication here: making sure that we don't get the queue stuck waiting on a
    "next in line" that has gone away - so we need to be careful about maintaining the
    next in line queue appropriately.
    
    TODO: have a timeout for the next in line process to grab the lock. That way if that
    process has dies, at least the others will eventually get a lock.
    
    Note that this is really a temporary solution meant to address the need to order scheduling
    requests in order to be "fair" to clients. Ultimately we want a persistent scheduling queue
    implementation that would effectively manage the next in line work loads and would not depend
    on the presence of any one working process. 
    """

    def __init__(self, namespace, locktoken, timeout=60.0, retry_interval=0.01, expire_time=0):
        """
        
        @param namespace: a unique namespace for this lock's tokens
        @type namespace: C{str}
        @param locktoken: the name of the locktoken
        @type locktoken: C{str}
        @param timeout: the maximum time in seconds that the lock should block
        @type timeout: C{float}
        @param retry_interval: the interval to retry acquiring the lock
        @type retry_interval: C{float}
        @param expiryTime: the time in seconds for the lock to expire. Zero: no expiration.
        @type expiryTime: C{float}
        """

        super(MemcacheFIFOLock, self).__init__(namespace)
        self._locktoken = locktoken
        self._ticket_token = "%s-ticket" % (self._locktoken,)
        self._nextinline_token = "%s-next" % (self._locktoken,)
        self._queue_token = "%s-queue" % (self._locktoken,)
        self._timeout = timeout
        self._retry_interval = retry_interval
        self._expire_time = expire_time
        self._hasLock = False
        self._ticket = None

    def _getMemcacheProtocol(self):
        
        result = super(MemcacheFIFOLock, self)._getMemcacheProtocol()

        if isinstance(result, Memcacher.nullCacher):
            raise AssertionError("No implementation of shared locking without memcached")
        
        return result

    @inlineCallbacks
    def acquire(self):
        
        assert not self._hasLock, "Lock already acquired."
    
        # First make sure the ticket and queue keys exist
        yield self.add(self._ticket_token, "1", self._expire_time)
        yield self.add(self._nextinline_token, "0", self._expire_time)
        
        # Get the next ticket
        self._ticket = (yield self.incr(self._ticket_token)) - 1
        
        # Add ourselves to the pending queue
        yield self._addToQueue()

        timeout_at = time.time() + self._timeout
        waiting = False
        while True:
            
            # Check next in line value
            result = int((yield self.get(self._nextinline_token)))
            if result == self._ticket:
                self._hasLock = True
                if waiting:
                    self.log_debug("Got lock after waiting on %s" % (self._locktoken,))
                break
            
            if self._timeout and time.time() < timeout_at:
                waiting = True
                self.log_debug("Waiting for lock on %s" % (self._locktoken,))
                pause = Deferred()
                def _timedDeferred():
                    pause.callback(True)
                reactor.callLater(self._retry_interval, _timedDeferred)
                yield pause
            else:
                # Must remove our active ticket value otherwise the next in line will stall on
                # this lock which will never happen
                yield self._removeFromQueue()

                self.log_debug("Timed out lock after waiting on %s" % (self._locktoken,))
                raise MemcacheLockTimeoutError()
        
        returnValue(True)

    @inlineCallbacks
    def release(self):
        
        assert self._hasLock, "Lock not acquired."
        self._hasLock = False
    
        # Remove active ticket value - this will bump the next in line value
        yield self._removeFromQueue()
            

    def clean(self):
        
        if self._hasLock:
            return self.release()
        else:
            return succeed(True)

    def locked(self):
        """
        Test if the lock is currently being held.
        """
        
        return succeed(self._hasLock)

    @inlineCallbacks
    def _addToQueue(self):
        """
        Add our ticket to the queue. If it is now the first pending ticket, set the next in line
        value to that.
        """
        
        # We need a shared lock to protect access to the queue
        lock = MemcacheLock(self._namespace, self._locktoken)
        yield lock.acquire()
        
        try:
            queued_value = (yield self.get(self._queue_token))
            queued_items = cPickle.loads(queued_value) if queued_value is not None else []
            queued_items.append(self._ticket)
            queued_items.sort()
            if len(queued_items) == 1:
                yield self.set(self._nextinline_token, str(queued_items[0]))
            yield self.set(self._queue_token, cPickle.dumps(queued_items))
        finally:
            yield lock.release()
        
    @inlineCallbacks
    def _removeFromQueue(self):
        """
        Remove our ticket from the queue. If it was the first next in line value, then bump
        next in line to the new head of the queue value or reset it if the queue is empty.
        """
        
        # We need a shared lock to protect access to the queue
        lock = MemcacheLock(self._namespace, self._locktoken)
        yield lock.acquire()
        
        try:
            queued_value = (yield self.get(self._queue_token))
            queued_items = cPickle.loads(queued_value) if queued_value is not None else []
            
            if queued_items[0] == self._ticket:
                del queued_items[0]
                yield self.set(self._nextinline_token, str(queued_items[0] if queued_items else 0))
            else:
                queued_items.remove(self._ticket)
            queued_items.sort()
            yield self.set(self._queue_token, cPickle.dumps(queued_items))
        finally:
            yield lock.release()
