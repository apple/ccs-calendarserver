##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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

from calendarserver.tools.principals import (
    parseCreationArgs, matchStrings,
    recordForPrincipalID, getProxies, setProxies
)
from twext.python.filepath import CachingFilePath as FilePath
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, Deferred, returnValue
from twistedcaldav.config import config
from twistedcaldav.test.util import (
    TestCase, StoreTestCase, CapturingProcessProtocol, ErrorOutput
)



class ManagePrincipalsTestCase(TestCase):

    def setUp(self):
        super(ManagePrincipalsTestCase, self).setUp()

        # # Since this test operates on proxy db, we need to assign the service:
        # calendaruserproxy.ProxyDBService = calendaruserproxy.ProxySqliteDB(os.path.abspath(self.mktemp()))

        testRoot = os.path.join(os.path.dirname(__file__), "principals")
        templateName = os.path.join(testRoot, "caldavd.plist")
        templateFile = open(templateName)
        template = templateFile.read()
        templateFile.close()

        databaseRoot = os.path.abspath("_spawned_scripts_db" + str(os.getpid()))
        newConfig = template % {
            "ServerRoot": os.path.abspath(config.ServerRoot),
            "DataRoot": os.path.abspath(config.DataRoot),
            "DatabaseRoot": databaseRoot,
            "DocumentRoot": os.path.abspath(config.DocumentRoot),
            "LogRoot": os.path.abspath(config.LogRoot),
        }
        configFilePath = FilePath(os.path.join(config.ConfigRoot, "caldavd.plist"))
        configFilePath.setContent(newConfig)

        self.configFileName = configFilePath.path
        config.load(self.configFileName)

        origUsersFile = FilePath(
            os.path.join(
                os.path.dirname(__file__),
                "principals",
                "users-groups.xml"
            )
        )
        copyUsersFile = FilePath(os.path.join(config.DataRoot, "accounts.xml"))
        origUsersFile.copyTo(copyUsersFile)

        origResourcesFile = FilePath(
            os.path.join(
                os.path.dirname(__file__),
                "principals",
                "resources-locations.xml"
            )
        )
        copyResourcesFile = FilePath(os.path.join(config.DataRoot, "resources.xml"))
        origResourcesFile.copyTo(copyResourcesFile)

        origAugmentFile = FilePath(
            os.path.join(
                os.path.dirname(__file__),
                "principals",
                "augments.xml"
            )
        )
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
        self.assertTrue("addresses" in results)


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
        results = yield self.runCommand(
            "--add", "resources",
            "New Resource", "newresource", "newresourceuid"
        )
        self.assertTrue("Added 'New Resource'" in results)

        results = yield self.runCommand(
            "--get-auto-schedule-mode",
            "resources:newresource"
        )
        self.assertTrue(
            results.startswith(
                'Auto-schedule mode for "New Resource" newresourceuid (resource) newresource is Default'
            )
        )

        results = yield self.runCommand("--list-principals=resources")
        self.assertTrue("newresource" in results)

        results = yield self.runCommand(
            "--add", "resources", "New Resource",
            "newresource1", "newresourceuid"
        )
        self.assertTrue("UID already in use: newresourceuid" in results)

        results = yield self.runCommand(
            "--add", "resources", "New Resource",
            "newresource", "uniqueuid"
        )
        self.assertTrue("Record name already in use" in results)

        results = yield self.runCommand("--remove", "resources:newresource")
        self.assertTrue("Removed 'New Resource'" in results)

        results = yield self.runCommand("--list-principals=resources")
        self.assertFalse("newresource" in results)


    def test_parseCreationArgs(self):

        self.assertEquals(
            ("full name", "short name", "uid"),
            parseCreationArgs(("full name", "short name", "uid"))
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
        results = yield self.runCommand(
            "--add-write-proxy=users:user01", "locations:location01"
        )
        self.assertTrue(
            results.startswith('Added "User 01" user01 (user) user01 as a write proxy for "Room 01" location01 (location) location01')
        )

        results = yield self.runCommand(
            "--list-write-proxies", "locations:location01"
        )
        self.assertTrue("User 01" in results)

        results = yield self.runCommand(
            "--remove-proxy=users:user01", "locations:location01"
        )

        results = yield self.runCommand(
            "--list-write-proxies", "locations:location01"
        )
        self.assertTrue(
            'No write proxies for "Room 01" location01 (location) location01' in results
        )


    @inlineCallbacks
    def test_modifyReadProxies(self):
        results = yield self.runCommand(
            "--add-read-proxy=users:user01", "locations:location01"
        )
        self.assertTrue(
            results.startswith('Added "User 01" user01 (user) user01 as a read proxy for "Room 01" location01 (location) location01')
        )

        results = yield self.runCommand(
            "--list-read-proxies", "locations:location01"
        )
        self.assertTrue("User 01" in results)

        results = yield self.runCommand(
            "--remove-proxy=users:user01", "locations:location01"
        )

        results = yield self.runCommand(
            "--list-read-proxies", "locations:location01"
        )
        self.assertTrue(
            'No read proxies for "Room 01" location01 (location) location01' in results
        )


    @inlineCallbacks
    def test_autoScheduleMode(self):
        results = yield self.runCommand(
            "--get-auto-schedule-mode", "locations:location01"
        )
        self.assertTrue(
            results.startswith('Auto-schedule mode for "Room 01" location01 (location) location01 is Default')
        )

        results = yield self.runCommand(
            "--set-auto-schedule-mode=accept-if-free", "locations:location01"
        )
        self.assertTrue(
            results.startswith('Setting auto-schedule-mode to accept if free for "Room 01" location01 (location) location01')
        )

        results = yield self.runCommand(
            "--get-auto-schedule-mode",
            "locations:location01"
        )
        self.assertTrue(
            results.startswith('Auto-schedule mode for "Room 01" location01 (location) location01 is accept if free')
        )

        results = yield self.runCommand(
            "--set-auto-schedule-mode=decline-if-busy", "users:user01"
        )
        self.assertTrue(results.startswith('Setting auto-schedule-mode for "User 01" user01 (user) user01 is not allowed.'))

        try:
            results = yield self.runCommand(
                "--set-auto-schedule-mode=bogus",
                "users:user01"
            )
        except ErrorOutput:
            pass
        else:
            self.fail("Expected command failure")



class SetProxiesTestCase(StoreTestCase):

    @inlineCallbacks
    def test_setProxies(self):
        """
        Read and Write proxies can be set en masse
        """
        directory = self.directory
        record = yield recordForPrincipalID(directory, "users:user01")

        readProxies, writeProxies = yield getProxies(record)
        self.assertEquals(readProxies, [])  # initially empty
        self.assertEquals(writeProxies, [])  # initially empty

        readProxies = [
            (yield recordForPrincipalID(directory, "users:user03")),
            (yield recordForPrincipalID(directory, "users:user04")),
        ]
        writeProxies = [
            (yield recordForPrincipalID(directory, "users:user05")),
        ]
        yield setProxies(record, readProxies, writeProxies)

        readProxies, writeProxies = yield getProxies(record)
        self.assertEquals(set([r.uid for r in readProxies]), set(["user03", "user04"]))
        self.assertEquals(set([r.uid for r in writeProxies]), set(["user05"]))

        # Using None for a proxy list indicates a no-op
        yield setProxies(record, [], None)
        readProxies, writeProxies = yield getProxies(record)
        self.assertEquals(readProxies, [])  # now empty
        self.assertEquals(set([r.uid for r in writeProxies]), set(["user05"]))  # unchanged
