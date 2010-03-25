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

import os

from twext.python.filepath import CachingFilePath as FilePath
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, Deferred, returnValue

from twistedcaldav.config import config
from twistedcaldav.test.util import TestCase, CapturingProcessProtocol


class MangePrincipalsTestCase(TestCase):

    def setUp(self):
        super(MangePrincipalsTestCase, self).setUp()

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

        os.makedirs(config.DataRoot)

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
        python = os.path.join(sourceRoot, "python")
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
    def test_modifyWriteProxies(self):
        results = yield self.runCommand("--add-write-proxy=users:user01",
            "locations:location01")
        self.assertTrue(results.startswith("Added (users)user01 as a write proxy for (locations)location01"))

        results = yield self.runCommand("--list-write-proxies",
            "locations:location01")
        self.assertTrue("Read/write proxies for (locations)location01:\n * /principals/__uids__/user01/" in results)

        results = yield self.runCommand("--remove-proxy=users:user01",
            "locations:location01")

        results = yield self.runCommand("--list-write-proxies",
            "locations:location01")
        self.assertTrue("No write proxies for (locations)location01" in results)

    @inlineCallbacks
    def test_modifyReadProxies(self):
        results = yield self.runCommand("--add-read-proxy=users:user01",
            "locations:location01")
        self.assertTrue(results.startswith("Added (users)user01 as a read proxy for (locations)location01"))

        results = yield self.runCommand("--list-read-proxies",
            "locations:location01")
        self.assertTrue("Read-only proxies for (locations)location01:\n * /principals/__uids__/user01/" in results)

        results = yield self.runCommand("--remove-proxy=users:user01",
            "locations:location01")

        results = yield self.runCommand("--list-read-proxies",
            "locations:location01")
        self.assertTrue("No read proxies for (locations)location01" in results)


    @inlineCallbacks
    def test_autoSchedule(self):
        results = yield self.runCommand("--get-auto-schedule",
            "locations:location01")
        self.assertTrue(results.startswith("Autoschedule for (locations)location01 is false"))

        results = yield self.runCommand("--set-auto-schedule=true",
            "locations:location01")
        self.assertTrue(results.startswith("Setting auto-schedule to true for (locations)location01"))

        results = yield self.runCommand("--get-auto-schedule",
            "locations:location01")
        self.assertTrue(results.startswith("Autoschedule for (locations)location01 is true"))
