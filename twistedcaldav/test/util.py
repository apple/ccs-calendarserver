##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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

import twisted.web2.dav.test.util
from twisted.web2.http import HTTPError, StatusResponse

from twisted.internet.defer import succeed

from twistedcaldav.static import CalDAVFile


class TestCase(twisted.web2.dav.test.util.TestCase):
    resource_class = CalDAVFile


class InMemoryPropertyStore(object):
    def __init__(self):
        class _FauxPath(object):
            path = ':memory:'

        class _FauxResource(object):
            fp = _FauxPath()

        self._properties = {}
        self.resource = _FauxResource()

    def get(self, qname):
        data = self._properties.get(qname)
        if data is None:
            raise HTTPError(StatusResponse(404, "No such property"))
        return data

    def set(self, property):
        self._properties[property.qname()] = property



class StubCacheChangeNotifier(object):
    def __init__(self, *args, **kwargs):
        pass

    changedCount = 0

    def changed(self):
        self.changedCount += 1
        return succeed(True)



class InMemoryMemcacheProtocol(object):
    def __init__(self, reactor=None):
        self._cache = {}

        if reactor is None:
            from twisted.internet import reactor

        self._reactor = reactor

        self._timeouts = {}

    def get(self, key):
        if key not in self._cache:
            return succeed((0, None))

        return succeed(self._cache[key])


    def _timeoutKey(self, expireTime, key):
        def _removeKey():
            del self._cache[key]

        if expireTime > 0:
            if key in self._timeouts:
                self._timeouts[key].cancel()

            from twisted.internet.base import DelayedCall
            DelayedCall.debug = True

            self._timeouts[key] = self._reactor.callLater(
                expireTime,
                _removeKey)


    def set(self, key, value, flags=0, expireTime=0):
        try:
            self._cache[key] = (flags, value)

            self._timeoutKey(expireTime, key)

            return succeed(True)

        except Exception, err:
            return fail(Failure())


    def add(self, key, value, flags=0, expireTime=0):
        if key in self._cache:
            return succeed(False)

        return self.set(key, value, flags=flags, expireTime=expireTime)


    def delete(self, key):
        try:
            del self._cache[key]
            if key in self._timeouts:
                self._timeouts[key].cancel()
            return succeed(True)

        except:
            return succeed(False)

