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

from __future__ import with_statement

import os
import xattr

from twisted.python.failure import Failure
from twisted.internet.defer import succeed, fail
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav.config import config
from twistedcaldav.static import CalDAVFile
import memcacheclient

import twisted.web2.dav.test.util


class TestCase(twisted.web2.dav.test.util.TestCase):
    resource_class = CalDAVFile

    def setUp(self):
        super(TestCase, self).setUp()

        dataroot = self.mktemp()
        os.mkdir(dataroot)
        config.DataRoot = dataroot
        config.Memcached.ClientEnabled = False
        config.Memcached.ServerEnabled = False
        memcacheclient.ClientFactory.allowTestCache = True

    def createHierarchy(self, structure):
        root = self.mktemp()
        os.mkdir(root)

        def createChildren(parent, subStructure):
            for childName, childStructure in subStructure.iteritems():

                if childName.startswith("@"):
                    continue

                childPath = os.path.join(parent, childName)
                if childStructure.has_key("@contents"):
                    # This is a file
                    with open(childPath, "w") as child:
                        child.write(childStructure["@contents"])

                else:
                    # This is a directory
                    os.mkdir(childPath)
                    createChildren(childPath, childStructure)

                if childStructure.has_key("@xattrs"):
                    xattrs = childStructure["@xattrs"]
                    for attr, value in xattrs.iteritems():
                        xattr.setxattr(childPath, attr, value)

        createChildren(root, structure)
        return root

    def verifyHierarchy(self, root, structure):

        def verifyChildren(parent, subStructure):

            actual = set([child for child in os.listdir(parent)])

            for childName, childStructure in subStructure.iteritems():

                if childName.startswith("@"):
                    continue

                if childName in actual:
                    actual.remove(childName)

                childPath = os.path.join(parent, childName)

                if not os.path.exists(childPath):
                    print "Missing:", childPath
                    return False

                if childStructure.has_key("@contents"):
                    # This is a file
                    with open(childPath) as child:
                        contents = child.read()
                        if contents != childStructure["@contents"]:
                            print "Contents mismatch:", childPath
                            print "Expected:\n%s\n\nActual:\n%s\n" % (childStructure["@contents"], contents)
                            return False

                else:
                    # This is a directory
                    if not verifyChildren(childPath, childStructure):
                        return False

                if childStructure.has_key("@xattrs"):
                    xattrs = childStructure["@xattrs"]
                    for attr, value in xattrs.iteritems():
                        if isinstance(value, str):
                            try:
                                if xattr.getxattr(childPath, attr) != value:
                                    print "Xattr mismatch:", childPath, attr
                                    return False
                            except:
                                return False
                        else: # method
                            if not value(xattr.getxattr(childPath, attr)):
                                return False

                    for attr, value in xattr.xattr(childPath).iteritems():
                        if attr not in xattrs:
                            return False

            if actual:
                # There are unexpected children
                return False

            return True

        return verifyChildren(root, structure)


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

        except Exception:
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

