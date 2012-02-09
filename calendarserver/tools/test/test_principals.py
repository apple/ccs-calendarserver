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

import os
import sys

from twext.python.filepath import CachingFilePath as FilePath
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, Deferred, returnValue

from twistedcaldav.config import config
from twistedcaldav.directory.directory import DirectoryError
from twistedcaldav.directory import calendaruserproxy

from twistedcaldav.test.util import TestCase, CapturingProcessProtocol,\
    ErrorOutput

from calendarserver.tap.util import directoryFromConfig
from calendarserver.tools.principals import parseCreationArgs, matchStrings, updateRecord, principalForPrincipalID, getProxies, setProxies


class ManagePrincipalsTestCase(TestCase):

    def setUp(self):
        super(ManagePrincipalsTestCase, self).setUp()

        # Since this test operates on proxy db, we need to assign the service:
        calendaruserproxy.ProxyDBService = calendaruserproxy.ProxySqliteDB(os.path.abspath(self.mktemp()))

        config.GlobalAddressBook.Enabled = False

        testRoot = os.path.join(os.path.dirname(__file__), "principals")
        templateName = os.path.join(testRoot, "caldavd.plist")
        templateFile = open(templateName)
        template = templateFile.read()
        templateFile.close()

        newConfig = template % {
            "ServerRoot" : os.path.abspath(config.ServerRoot),
        }
        configFilePath = FilePath(os.path.join(config.ConfigRoot, "caldavd.plist"))
        configFilePath.setContent(newConfig)

        self.configFileName = configFilePath.path
        config.load(self.configFileName)

        origUsersFile = FilePath(os.path.join(os.path.dirname(__file__),
            "principals", "users-groups.xml"))
        copyUsersFile = FilePath(os.path.join(config.DataRoot, "accounts.xml"))
        origUsersFile.copyTo(copyUsersFile)

        origResourcesFile = FilePath(os.path.join(os.path.dirname(__file__),
            "principals", "resources-locations.xml"))
        copyResourcesFile = FilePath(os.path.join(config.DataRoot, "resources.xml"))
        origResourcesFile.copyTo(copyResourcesFile)

        origAugmentFile = FilePath(os.path.join(os.path.dirname(__file__),
            "principals", "augments.xml"))
        copyAugmentFile = FilePath(os.path.join(config.DataRoot, "augments.xml"))
        origAugmentFile.copyTo(copyAugmentFile)

        # Make sure trial puts the reactor in the right state, by letting it
        # run one reactor iteration.  (Ignore me, please.)
        d = Deferred()
        reactor.callLater(0, d.callback, True)
        return d


    @inlineCallbacks
    def runCommand(self, *additional):
        """
        Run calendarserver_manage_principals, passing additional as args.
        """
        sourceRoot = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        python = sys.executable
        script = os.path.join(sourceRoot, "bin", "calendarserver_manage_principals")

        args = [python, script, "-f", self.configFileName]
        args.extend(additional)
        cwd = sourceRoot

        deferred = Deferred()
        reactor.spawnProcess(CapturingProcessProtocol(deferred, None), python, args, env=os.environ, path=cwd)
        output = yield deferred
        returnValue(output)

    @inlineCallbacks
    def test_help(self):
        results = yield self.runCommand("--help")
        self.assertTrue(results.startswith("usage:"))

    @inlineCallbacks
    def test_principalTypes(self):
        results = yield self.runCommand("--list-principal-types")
        self.assertTrue("groups" in results)
        self.assertTrue("users" in results)
        self.assertTrue("locations" in results)
        self.assertTrue("resources" in results)

    @inlineCallbacks
    def test_listPrincipals(self):
        results = yield self.runCommand("--list-principals=users")
        for i in xrange(1, 10):
            self.assertTrue("user%02d" % (i,) in results)

    @inlineCallbacks
    def test_search(self):
        results = yield self.runCommand("--search=user")
        self.assertTrue("10 matches found" in results)
        for i in xrange(1, 10):
            self.assertTrue("user%02d" % (i,) in results)

    @inlineCallbacks
    def test_addRemove(self):
        results = yield self.runCommand("--add", "resources", "New Resource",
            "newresource", "edaa6ae6-011b-4d89-ace3-6b688cdd91d9")
        self.assertTrue("Added 'New Resource'" in results)

        results = yield self.runCommand("--get-auto-schedule",
            "resources:newresource")
        self.assertTrue(results.startswith('Auto-schedule for "New Resource" (resources:newresource) is true'))

        results = yield self.runCommand("--get-auto-schedule-mode",
            "resources:newresource")
        self.assertTrue(results.startswith('Auto-schedule mode for "New Resource" (resources:newresource) is default'))

        results = yield self.runCommand("--list-principals=resources")
        self.assertTrue("newresource" in results)

        results = yield self.runCommand("--add", "resources", "New Resource",
            "newresource1", "edaa6ae6-011b-4d89-ace3-6b688cdd91d9")
        self.assertTrue("Duplicate guid" in results)

        results = yield self.runCommand("--add", "resources", "New Resource",
            "newresource", "fdaa6ae6-011b-4d89-ace3-6b688cdd91d9")
        self.assertTrue("Duplicate shortName" in results)

        results = yield self.runCommand("--remove", "resources:newresource")
        self.assertTrue("Removed 'New Resource'" in results)

        results = yield self.runCommand("--list-principals=resources")
        self.assertFalse("newresource" in results)

    def test_parseCreationArgs(self):

        self.assertEquals(("full name", None, None),
            parseCreationArgs(("full name",)))

        self.assertEquals(("full name", "short name", None),
            parseCreationArgs(("full name", "short name")))

        guid = "02C3DE93-E655-4856-47B76B8BB1A7BDCE"

        self.assertEquals(("full name", "short name", guid),
            parseCreationArgs(("full name", "short name", guid)))

        self.assertEquals(("full name", "short name", guid),
            parseCreationArgs(("full name", guid, "short name")))

        self.assertEquals(("full name", None, guid),
            parseCreationArgs(("full name", guid)))

        self.assertRaises(
            ValueError,
            parseCreationArgs, ("full name", "non guid", "non guid")
        )

    def test_matchStrings(self):
        self.assertEquals("abc", matchStrings("a", ("abc", "def")))
        self.assertEquals("def", matchStrings("de", ("abc", "def")))
        self.assertRaises(
            ValueError,
            matchStrings, "foo", ("abc", "def")
        )

    @inlineCallbacks
    def test_modifyWriteProxies(self):
        results = yield self.runCommand("--add-write-proxy=users:user01",
            "locations:location01")
        self.assertTrue(results.startswith('Added "Test User 01" (users:user01) as a write proxy for "Room 01" (locations:location01)'))

        results = yield self.runCommand("--list-write-proxies",
            "locations:location01")
        self.assertTrue("Test User 01" in results)

        results = yield self.runCommand("--remove-proxy=users:user01",
            "locations:location01")

        results = yield self.runCommand("--list-write-proxies",
            "locations:location01")
        self.assertTrue('No write proxies for "Room 01" (locations:location01)' in results)

    @inlineCallbacks
    def test_modifyReadProxies(self):
        results = yield self.runCommand("--add-read-proxy=users:user01",
            "locations:location01")
        self.assertTrue(results.startswith('Added "Test User 01" (users:user01) as a read proxy for "Room 01" (locations:location01)'))

        results = yield self.runCommand("--list-read-proxies",
            "locations:location01")
        self.assertTrue("Test User 01" in results)

        results = yield self.runCommand("--remove-proxy=users:user01",
            "locations:location01")

        results = yield self.runCommand("--list-read-proxies",
            "locations:location01")
        self.assertTrue('No read proxies for "Room 01" (locations:location01)' in results)


    @inlineCallbacks
    def test_autoSchedule(self):
        results = yield self.runCommand("--get-auto-schedule",
            "locations:location01")
        self.assertTrue(results.startswith('Auto-schedule for "Room 01" (locations:location01) is false'))

        results = yield self.runCommand("--set-auto-schedule=true",
            "locations:location01")
        self.assertTrue(results.startswith('Setting auto-schedule to true for "Room 01" (locations:location01)'))

        results = yield self.runCommand("--get-auto-schedule",
            "locations:location01")
        self.assertTrue(results.startswith('Auto-schedule for "Room 01" (locations:location01) is true'))

        results = yield self.runCommand("--set-auto-schedule=true",
            "users:user01")
        self.assertTrue(results.startswith('Enabling auto-schedule for (users)user01 is not allowed.'))


    @inlineCallbacks
    def test_autoScheduleMode(self):
        results = yield self.runCommand("--get-auto-schedule-mode",
            "locations:location01")
        self.assertTrue(results.startswith('Auto-schedule mode for "Room 01" (locations:location01) is default'))

        results = yield self.runCommand("--set-auto-schedule-mode=accept-if-free",
            "locations:location01")
        self.assertTrue(results.startswith('Setting auto-schedule mode to accept-if-free for "Room 01" (locations:location01)'))

        results = yield self.runCommand("--get-auto-schedule-mode",
            "locations:location01")
        self.assertTrue(results.startswith('Auto-schedule mode for "Room 01" (locations:location01) is accept-if-free'))

        results = yield self.runCommand("--set-auto-schedule-mode=decline-if-busy",
            "users:user01")
        self.assertTrue(results.startswith('Setting auto-schedule mode for (users)user01 is not allowed.'))

        try:
            results = yield self.runCommand("--set-auto-schedule-mode=bogus",
                "users:user01")
        except ErrorOutput:
            pass
        else:
            self.fail("Expected command failure")


    @inlineCallbacks
    def test_updateRecord(self):
        directory = directoryFromConfig(config)
        guid = "EEE28807-A8C5-46C8-A558-A08281C558A7"

        (yield updateRecord(True, directory, "locations",
            guid=guid, fullName="Test Location", shortNames=["testlocation",],)
        )
        try:
            (yield updateRecord(True, directory, "locations",
                guid=guid, fullName="Test Location", shortNames=["testlocation",],)
            )
        except DirectoryError:
            # We're expecting an error for trying to create a record with
            # an existing GUID
            pass
        else:
            raise self.failureException("Duplicate guid expected")

        record = directory.recordWithGUID(guid)
        self.assertTrue(record is not None)
        self.assertEquals(record.fullName, "Test Location")
        self.assertTrue(record.autoSchedule)

        (yield updateRecord(False, directory, "locations",
            guid=guid, fullName="Changed", shortNames=["testlocation",],)
        )
        record = directory.recordWithGUID(guid)
        self.assertTrue(record is not None)
        self.assertEquals(record.fullName, "Changed")

        directory.destroyRecord("locations", guid=guid)
        record = directory.recordWithGUID(guid)
        self.assertTrue(record is None)


        # Create a user, change autoSchedule
        guid = "F0DE73A8-39D4-4830-8D32-1FA03ABA3470"
        (yield updateRecord(True, directory, "users",
            guid=guid, fullName="Test User", shortNames=["testuser",],
            autoSchedule=True)
        )
        record = directory.recordWithGUID(guid)
        self.assertTrue(record is not None)
        self.assertEquals(record.fullName, "Test User")
        self.assertTrue(record.autoSchedule)

        (yield updateRecord(False, directory, "users",
            guid=guid, fullName="Test User", shortNames=["testuser",],
            autoSchedule=False)
        )
        record = directory.recordWithGUID(guid)
        self.assertTrue(record is not None)
        self.assertEquals(record.fullName, "Test User")
        self.assertFalse(record.autoSchedule)


    @inlineCallbacks
    def test_setProxies(self):
        """
        Read and Write proxies can be set en masse
        """
        directory = directoryFromConfig(config)

        principal = principalForPrincipalID("users:user01", directory=directory)
        readProxies, writeProxies = (yield getProxies(principal, directory=directory))
        self.assertEquals(readProxies, []) # initially empty
        self.assertEquals(writeProxies, []) # initially empty

        (yield setProxies(principal, ["users:user03", "users:user04"], ["users:user05"], directory=directory))
        readProxies, writeProxies = (yield getProxies(principal, directory=directory))
        self.assertEquals(set(readProxies), set(["user03", "user04"]))
        self.assertEquals(set(writeProxies), set(["user05"]))

        # Using None for a proxy list indicates a no-op
        (yield setProxies(principal, [], None, directory=directory))
        readProxies, writeProxies = (yield getProxies(principal, directory=directory))
        self.assertEquals(readProxies, []) # now empty
        self.assertEquals(set(writeProxies), set(["user05"])) # unchanged

