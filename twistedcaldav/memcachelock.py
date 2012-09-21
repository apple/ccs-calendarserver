##
# Copyright (c) 2008-2012 Apple Inc. All rights reserved.
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

class MemcacheLock(Memcacher):

    def __init__(self, namespace, locktoken, timeout=5.0, retry_interval=0.1, expire_time=0):
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

        super(MemcacheLock, self).__init__(namespace)
        self._locktoken = locktoken
        self._timeout = timeout
        self._retry_interval = retry_interval
        self._expire_time = expire_time
        self._hasLock = False

    def _getMemcacheProtocol(self):
        
        result = super(MemcacheLock, self)._getMemcacheProtocol()

        if isinstance(result, Memcacher.nullCacher):
            raise AssertionError("No implementation of shared locking without memcached")
        
        return result

    @inlineCallbacks
    def acquire(self):
        
        assert not self._hasLock, "Lock already acquired."
    
        timeout_at = time.time() + self._timeout
        waiting = False
        while True:
            
            result = (yield self.add(self._locktoken, "1", expireTime=self._expire_time))
            if result:
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
                self.log_debug("Timed out lock after waiting on %s" % (self._locktoken,))
                raise MemcacheLockTimeoutError()
        
        returnValue(True)

    def release(self):
        
        assert self._hasLock, "Lock not acquired."
    
        def _done(result):
            self._hasLock = False
            return result

        d = self.delete(self._locktoken)
        d.addCallback(_done)
        return d

    def clean(self):
        
        if self._hasLock:
            return self.release()
        else:
            return succeed(True)

    def locked(self):
        """
        Test if the lock is currently being held.
        """
        
        def _gotit(value):
            return value is not None

        d = self.get(self._locktoken)
        d.addCallback(_gotit)
        return d

class MemcacheLockTimeoutError(Exception):
    pass
