##
# Copyright (c) 2008 Apple Inc. All rights reserved.
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

from twisted.internet.defer import succeed
from twisted.internet.protocol import ClientCreator

from twistedcaldav.log import LoggingMixIn
from twistedcaldav.memcache import MemCacheProtocol
from twistedcaldav.config import config
import cPickle

class Memcacher(LoggingMixIn):
    _memcacheProtocol = None

    class memoryCacher():
        """
        A class implementing the memcache client API we care about but
        using a dict to store the results in memory. This can be used
        for caching on a single instance server, and for tests, where
        memcached may not be running.
        """
        
        def __init__(self):
            self._cache = {}

        def set(self, key, value):
            self._cache[key] = value
            return succeed(True)
            
        def get(self, key):
            return succeed((0, self._cache.get(key, None),))
        
        def delete(self, key):
            try:
                del self._cache[key]
                return succeed(True)
            except KeyError:
                return succeed(False)

    #TODO: an sqlite based cacher that can be used for multiple instance servers
    # in the absence of memcached. This is not ideal and we may want to not implement
    # this, but it is being documented for completeness.
    #
    # For now we implement a cacher that does not cache.
    class nullCacher():
        """
        A class implementing the memcache client API we care about but
        does not actually cache anything.
        """
        
        def set(self, key, value):
            return succeed(True)
            
        def get(self, key):
            return succeed((0, None,))
        
        def delete(self, key):
            return succeed(True)

    def __init__(self, namespace, pickle=False):
        self._namespace = namespace
        self._pickle = pickle

        self._host = config.Memcached['BindAddress']
        self._port = config.Memcached['Port']

        from twisted.internet import reactor
        self._reactor = reactor

    def _getMemcacheProtocol(self):
        if Memcacher._memcacheProtocol is not None:
            return succeed(Memcacher._memcacheProtocol)

        if config.Memcached['ClientEnabled']:
            d = ClientCreator(self._reactor, MemCacheProtocol).connectTCP(
                self._host,
                self._port)
    
            def _cacheProtocol(proto):
                Memcacher._memcacheProtocol = proto
                return proto
    
            return d.addCallback(_cacheProtocol)

        elif config.ProcessType == "Single":
            
            Memcacher._memcacheProtocol = Memcacher.memoryCacher()
            return succeed(Memcacher._memcacheProtocol)

        else:
            
            Memcacher._memcacheProtocol = Memcacher.nullCacher()
            return succeed(Memcacher._memcacheProtocol)

    def set(self, key, value):

        def _set(proto):
            my_value = value
            if self._pickle:
                my_value = cPickle.dumps(value)
            return proto.set('%s:%s' % (self._namespace, key), my_value)

        self.log_debug("Changing Cache Token for %s" % (key,))
        d = self._getMemcacheProtocol()
        d.addCallback(_set)
        return d

    def get(self, key):
        
        def _gotit(result):
            _ignore_flags, value = result
            if self._pickle and value is not None:
                value = cPickle.loads(value)
            return value

        def _get(proto):
            d1 = proto.get('%s:%s' % (self._namespace, key))
            d1.addCallback(_gotit)
            return d1

        self.log_debug("Getting Cache Token for %r" % (key,))
        d = self._getMemcacheProtocol()
        d.addCallback(_get)
        return d

    def delete(self, key):
        
        def _delete(proto):
            return proto.delete('%s:%s' % (self._namespace, key))

        self.log_debug("Deleting Cache Token for %r" % (key,))
        d = self._getMemcacheProtocol()
        d.addCallback(_delete)
        return d
