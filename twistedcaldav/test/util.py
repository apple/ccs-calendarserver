##
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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

from calendarserver.provision.root import RootResource

from twisted.python.failure import Failure
from twisted.internet.base import DelayedCall
from twisted.internet.defer import succeed, fail, inlineCallbacks, returnValue
from twisted.internet.error import ProcessDone
from twisted.internet.protocol import ProcessProtocol

from twext.python.memcacheclient import ClientFactory
from twext.python.filepath import CachingFilePath as FilePath
import twext.web2.dav.test.util
from twext.web2.dav import davxml
from twext.web2.http import HTTPError, StatusResponse

from twistedcaldav import memcacher
from twistedcaldav.bind import doBind
from twistedcaldav.config import config
from twistedcaldav.directory import augment
from twistedcaldav.directory.addressbook import DirectoryAddressBookHomeProvisioningResource
from twistedcaldav.directory.calendar import DirectoryCalendarHomeProvisioningResource
from twistedcaldav.directory.principal import (
    DirectoryPrincipalProvisioningResource)
from twistedcaldav.directory.xmlfile import XMLDirectoryService

from txdav.common.datastore.test.util import deriveQuota
from txdav.common.datastore.file import CommonDataStore


__all__ = [
    "featureUnimplemented",
    "testUnimplemented",
    "todo",
    "TestCase",
]
DelayedCall.debug = True

def _todo(f, why):
    f.todo = why
    return f

featureUnimplemented = lambda f: _todo(f, "Feature unimplemented")
testUnimplemented = lambda f: _todo(f, "Test unimplemented")
todo = lambda why: lambda f: _todo(f, why)

dirTest = FilePath(__file__).parent().sibling("directory").child("test")

xmlFile = dirTest.child("accounts.xml")
augmentsFile = dirTest.child("augments.xml")
proxiesFile = dirTest.child("proxies.xml")



class TestCase(twext.web2.dav.test.util.TestCase):
    resource_class = RootResource

    def createStockDirectoryService(self):
        """
        Create a stock C{directoryService} attribute and assign it.
        """
        self.xmlFile = FilePath(config.DataRoot).child("accounts.xml")
        self.xmlFile.setContent(xmlFile.getContent())


        self.directoryService = XMLDirectoryService(
            {
                "xmlFile" : "accounts.xml",
                "augmentService" :
                    augment.AugmentXMLDB( xmlFiles=(augmentsFile.path,)),
            }
        )

        # FIXME: see FIXME in DirectoryPrincipalProvisioningResource.__init__;
        # this performs a necessary modification to the directory service
        # object for it to be fully functional.
        self.principalsResource = DirectoryPrincipalProvisioningResource(
            "/principals/", self.directoryService
        )


    def createDataStore(self):
        """
        Create an L{IDataStore} that can store calendars (but not
        addressbooks.)  By default returns a L{CommonDataStore}, but this is a
        hook for subclasses to override to provide different data stores.
        """
        return CommonDataStore(FilePath(config.DocumentRoot), None, True, False,
                               quota=deriveQuota(self))


    def setupCalendars(self):
        """
        Set up the resource at /calendars (a
        L{DirectoryCalendarHomeProvisioningResource}), and assign it as
        C{self.calendarCollection}.
        """

        # Need a data store
        self._newStore = self.createDataStore()

        self.calendarCollection = DirectoryCalendarHomeProvisioningResource(
            self.directoryService,
            "/calendars/",
            self._newStore
        )
        self.site.resource.putChild("calendars", self.calendarCollection)

        self.addressbookCollection = DirectoryAddressBookHomeProvisioningResource(
            self.directoryService,
            "/addressbooks/",
            self._newStore
        )
        self.site.resource.putChild("addressbooks", self.addressbookCollection)


    def setUp(self):
        super(TestCase, self).setUp()

        # FIXME: this is only here to workaround circular imports
        doBind()

        config.reset()
        serverroot = self.mktemp()
        os.mkdir(serverroot)
        config.ServerRoot = os.path.abspath(serverroot)
        config.ConfigRoot = "config"
        config.LogRoot = "logs"
        config.RunRoot = "logs"

        if not os.path.exists(config.DataRoot):
            os.makedirs(config.DataRoot)
        if not os.path.exists(config.DocumentRoot):
            os.makedirs(config.DocumentRoot)
        if not os.path.exists(config.ConfigRoot):
            os.makedirs(config.ConfigRoot)
        if not os.path.exists(config.LogRoot):
            os.makedirs(config.LogRoot)

        config.Memcached.Pools.Default.ClientEnabled = False
        config.Memcached.Pools.Default.ServerEnabled = False
        ClientFactory.allowTestCache = True
        memcacher.Memcacher.allowTestCache = True
        memcacher.Memcacher.memoryCacheInstance = None

        config.DirectoryAddressBook.Enabled = False


    def createHierarchy(self, structure, root=None):
        if root is None:
            root = os.path.abspath(self.mktemp())
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
                        try:
                            xattr.setxattr(childPath, attr, value)
                        except IOError:
                            pass

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
                    if childStructure.has_key("@optional"):
                        return True
                    else:
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
                    try:
                        # See if we have xattr support; IOError if not
                        try:
                            xattr.getxattr(childPath, "test")
                        except KeyError:
                            pass

                        xattrs = childStructure["@xattrs"]
                        for attr, value in xattrs.iteritems():
                            if isinstance(value, str):
                                if xattr.getxattr(childPath, attr) != value:
                                    print "Xattr mismatch:", childPath, attr
                                    print (xattr.getxattr(childPath, attr), " != ", value)
                                    return False
                            else: # method
                                if not value(xattr.getxattr(childPath, attr)):
                                    return False

                        for attr, value in xattr.xattr(childPath).iteritems():
                            if attr not in xattrs:
                                return False
                    except IOError:
                        # xattr not enabled/supported
                        pass

            if actual:
                # There are unexpected children
                print "Unexpected:", actual, 'in', parent
                return False

            return True

        return verifyChildren(root, structure)

class norequest(object):
    def addResponseFilter(self, filter):
        "stub; ignore me"


class HomeTestCase(TestCase):
    """
    Utility class for tests which wish to interact with a calendar home rather
    than a top-level resource hierarchy.
    """

    def createDataStore(self):
        # FIXME: AddressBookHomeTestCase needs the same treatment.
        fp = FilePath(self.mktemp())
        fp.createDirectory()
        return CommonDataStore(fp, None, True, False)


    def setUp(self):
        """
        Replace self.site.resource with an appropriately provisioned
        CalendarHomeResource, and replace self.docroot with a path pointing at that
        file.
        """
        super(HomeTestCase, self).setUp()

        self.createStockDirectoryService()

        # Need a data store
        _newStore = self.createDataStore()

        self.homeProvisioner = DirectoryCalendarHomeProvisioningResource(
            self.directoryService, "/calendars/",
            _newStore
        )
        
        def _defer(user):
            # Commit the transaction
            self.addCleanup(self.noRenderCommit)
            # FIXME: nothing should use docroot any more.
            aPath = getattr(user._newStoreHome, "_path", None)
            if aPath is not None:
                self.docroot = aPath.path

        return self._refreshRoot().addCallback(_defer)


    committed = True

    def noRenderCommit(self):
        """
        A resource was retrieved but will not be rendered, so commit.
        """
        if not self.committed:
            self.committed = True
            return self.site.resource._associatedTransaction.commit()


    @inlineCallbacks
    def _refreshRoot(self, request=None):
        """
        Refresh the user resource positioned at the root of this site, to give
        it a new transaction.
        """
        yield self.noRenderCommit()
        if request is None:
            request = norequest()
        users = yield self.homeProvisioner.getChild("users")

        user, ignored = (yield users.locateChild(request, ["wsanchez"]))

        # Force the request to succeed regardless of the implementation of
        # accessControlList.
        user.accessControlList = lambda request, *a, **k: succeed(
            self.grantInherit(davxml.All())
        )

        # Fix the site to point directly at the user's calendar home so that we
        # can focus on testing just that rather than hierarchy traversal..
        self.site.resource = user
        self.committed = False
        returnValue(user)


    @inlineCallbacks
    def send(self, request, callback=None):
        """
        Override C{send} in order to refresh the 'user' resource each time, to
        get a new transaction to associate with the calendar home.
        """
        yield self.noRenderCommit()
        yield self._refreshRoot(request)
        result = (yield super(HomeTestCase, self).send(request))
        self.committed = True
        yield self._refreshRoot()
        if callback is not None:
            result = yield callback(result)
        returnValue(result)



class AddressBookHomeTestCase(TestCase):
    """
    Utility class for tests which wish to interact with a addressbook home rather
    than a top-level resource hierarchy.
    """

    def setUp(self):
        """
        Replace self.site.resource with an appropriately provisioned
        AddressBookHomeFile, and replace self.docroot with a path pointing at that
        file.
        """
        super(AddressBookHomeTestCase, self).setUp()

        fp = FilePath(self.mktemp())
        fp.createDirectory()

        self.createStockDirectoryService()

        # Need a data store
        _newStore = CommonDataStore(fp, None, True, False)

        self.homeProvisioner = DirectoryAddressBookHomeProvisioningResource(
            self.directoryService, "/addressbooks/",
            _newStore
        )

        @inlineCallbacks
        def _defer(user):
            # Commit the transaction
            yield self.site.resource._associatedTransaction.commit()
            self.docroot = user._newStoreHome._path.path

        return self._refreshRoot().addCallback(_defer)

    @inlineCallbacks
    def _refreshRoot(self):
        """
        Refresh the user resource positioned at the root of this site, to give
        it a new transaction.
        """
        users = self.homeProvisioner.getChild("users")
        user, ignored = (yield users.locateChild(norequest(), ["wsanchez"]))

        # Force the request to succeed regardless of the implementation of
        # accessControlList.
        user.accessControlList = lambda request, *a, **k: succeed(
            self.grantInherit(davxml.All())
        )

        # Fix the site to point directly at the user's calendar home so that we
        # can focus on testing just that rather than hierarchy traversal..
        self.site.resource = user
        returnValue(user)


    @inlineCallbacks
    def send(self, request, callback=None):
        """
        Override C{send} in order to refresh the 'user' resource each time, to
        get a new transaction to associate with the calendar home.
        """
        yield self._refreshRoot()
        result = (yield super(AddressBookHomeTestCase, self).send(request, callback))
        returnValue(result)



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



def patchConfig(testCase, **kw):
    """
    Patch the global configuration (including running the appropriate hooks) for
    the duration of the given test.
    """
    preserved = {}
    for k in kw:
        preserved[k] = config.get(k, None)
    def reUpdate():
        config.update(preserved)
    testCase.addCleanup(reUpdate)
    config.update(kw)



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

