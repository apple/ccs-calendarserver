##
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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

__all__ = [
    "featureUnimplemented",
    "testUnimplemented",
    "todo",
    "TestCase",
]

import os
import xattr

from twisted.python.failure import Failure
from twisted.internet.base import DelayedCall
from twisted.internet.defer import succeed, fail
from twisted.internet.error import ProcessDone
from twisted.internet.protocol import ProcessProtocol

from twext.python.memcacheclient import ClientFactory
import twext.web2.dav.test.util
from twext.web2.http import HTTPError, StatusResponse

from twistedcaldav import memcacher
from twistedcaldav.config import config
from twistedcaldav.static import CalDAVFile

DelayedCall.debug = True

def _todo(f, why):
    f.todo = why
    return f

featureUnimplemented = lambda f: _todo(f, "Feature unimplemented")
testUnimplemented = lambda f: _todo(f, "Test unimplemented")
todo = lambda why: lambda f: _todo(f, why)

class TestCase(twext.web2.dav.test.util.TestCase):
    resource_class = CalDAVFile

    def setUp(self):
        super(TestCase, self).setUp()

        config.reset()
        serverroot = self.mktemp()
        os.mkdir(serverroot)
        config.ServerRoot = serverroot
        config.ConfigRoot = "config"
        
        if not os.path.exists(config.DataRoot):
            os.makedirs(config.DataRoot)
        if not os.path.exists(config.DocumentRoot):
            os.makedirs(config.DocumentRoot)
        if not os.path.exists(config.ConfigRoot):
            os.makedirs(config.ConfigRoot)

        config.Memcached.Pools.Default.ClientEnabled = False
        config.Memcached.Pools.Default.ServerEnabled = False
        ClientFactory.allowTestCache = True
        memcacher.Memcacher.allowTestCache = True

        config.DirectoryAddressBook.Enabled = False

    def createHierarchy(self, structure, root=None):
        if root is None:
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

                if childName.startswith("*"):
                    if "/" in childName:
                        childName, matching = childName.split("/")
                    else:
                        matching = False
                    ext = childName.split(".")[1]
                    found = False
                    for actualFile in actual:
                        if actualFile.endswith(ext):
                            matches = True
                            if matching:
                                matches = False
                                # We want to target only the wildcard file containing
                                # the matching string
                                actualPath = os.path.join(parent, actualFile)
                                with open(actualPath) as child:
                                    contents = child.read()
                                    if matching in contents:
                                        matches = True

                            if matches:
                                actual.remove(actualFile)
                                found = True
                                break
                    if found:
                        # continue
                        childName = actualFile

                childPath = os.path.join(parent, childName)

                if not os.path.exists(childPath):
                    print "Missing:", childPath
                    return False

                if childStructure.has_key("@contents"):
                    # This is a file
                    expectedContents = childStructure["@contents"]
                    if expectedContents is None:
                        # We don't care about the contents
                        pass
                    elif isinstance(expectedContents, tuple):
                        with open(childPath) as child:
                            contents = child.read()
                            for term in expectedContents:
                                if term not in contents:
                                    print "Contents mismatch:", childPath
                                    print "Expecting match:\n%s\n\nActual:\n%s\n" % (term, contents)
                                    return False
                    else:
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
                                    print (xattr.getxattr(childPath, attr), " != ", value)
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
                print "Unexpected:", actual, 'in', parent
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

    def get(self, qname, uid=None):
        qnameuid = qname + (uid,)
        data = self._properties.get(qnameuid)
        if data is None:
            raise HTTPError(StatusResponse(404, "No such property"))
        return data

    def set(self, property, uid=None):
        qnameuid = property.qname() + (uid,)
        self._properties[qnameuid] = property

    def delete(self, qname, uid=None):
        try:
            qnameuid = qname + (uid,)
            del self._properties[qnameuid]
        except KeyError:
            pass

    def contains(self, qname, uid=None):
        qnameuid = qname + (uid,)
        return qnameuid in self._properties

    def list(self, uid=None, filterByUID=True):
        results = self._properties.iterkeys()
        if filterByUID:
            return [ 
                (namespace, name)
                for namespace, name, propuid in results
                if propuid == uid
            ]
        else:
            return results


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





class ErrorOutput(Exception):
    """
    The process produced some error output and exited with a non-zero exit
    code.
    """


class CapturingProcessProtocol(ProcessProtocol):
    """
    A L{ProcessProtocol} that captures its output and error.

    @ivar output: a C{list} of all C{str}s received to stderr.

    @ivar error: a C{list} of all C{str}s received to stderr.
    """

    def __init__(self, deferred, inputData):
        """
        Initialize a L{CapturingProcessProtocol}.

        @param deferred: the L{Deferred} to fire when the process is complete.

        @param inputData: a C{str} to feed to the subprocess's stdin.
        """
        self.deferred = deferred
        self.input = inputData
        self.output = []
        self.error = []


    def connectionMade(self):
        """
        The process started; feed its input on stdin.
        """
        if self.input is not None:
            self.transport.write(self.input)
            self.transport.closeStdin()


    def outReceived(self, data):
        """
        Some output was received on stdout.
        """
        self.output.append(data)


    def errReceived(self, data):
        """
        Some output was received on stderr.
        """
        self.error.append(data)
        # Attempt to exit promptly if a traceback is displayed, so we don't
        # deal with timeouts.
        lines = ''.join(self.error).split("\n")
        if len(lines) > 1:
            errorReportLine = lines[-2].split(": ", 1)
            if len(errorReportLine) == 2 and ' ' not in errorReportLine[0] and '\t' not in errorReportLine[0]:
                self.transport.signalProcess("TERM")


    def processEnded(self, why):
        """
        The process is over, fire the Deferred with the output.
        """
        if why.check(ProcessDone) and not self.error:
            self.deferred.callback(''.join(self.output))
        else:
            self.deferred.errback(ErrorOutput(''.join(self.error)))

