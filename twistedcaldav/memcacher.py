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

class Memcacher(LoggingMixIn):
    _memcacheProtocol = None

    def __init__(self, namespace):
        self._namespace = namespace
        self._host = config.Memcached['BindAddress']
        self._port = config.Memcached['Port']

        from twisted.internet import reactor
        self._reactor = reactor

    def _getMemcacheProtocol(self):
        if Memcacher._memcacheProtocol is not None:
            return succeed(self._memcacheProtocol)

        d = ClientCreator(self._reactor, MemCacheProtocol).connectTCP(
            self._host,
            self._port)

        def _cacheProtocol(proto):
            Memcacher._memcacheProtocol = proto
            return proto

        return d.addCallback(_cacheProtocol)

    def set(self, key, value):

        def _set(proto):
            return proto.set('%s:%s' % (self._namespace, key), value)

        self.log_debug("Changing Cache Token for %s" % (key,))
        d = self._getMemcacheProtocol()
        d.addCallback(_set)
        return d

    def get(self, key):
        
        def _gotit(result):
            _ignore_flags, value = result
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
