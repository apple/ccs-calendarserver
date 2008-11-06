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

from twisted.trial.unittest import TestCase

from twistedcaldav.config import config
from twistedcaldav.directory.calendaruserproxy import CalendarUserProxyDatabase
from twistedcaldav.upgrade import UpgradeError
from twistedcaldav.upgrade import UpgradeTheServer

import os

class ProxyDBUpgradeTests(TestCase):
    
    def setUpInitialStates(self):
        
        self.setUpOldDocRoot()
        self.setUpOldDocRootWithoutDB()
        self.setUpNewDocRoot()
        
        self.setUpNewDataRoot()
        self.setUpDataRootWithProxyDB()

    def setUpOldDocRoot(self):
        
        # Set up doc root
        self.olddocroot = self.mktemp()
        os.mkdir(self.olddocroot)

        principals = os.path.join(self.olddocroot, "principals")
        os.mkdir(principals)
        os.mkdir(os.path.join(principals, "__uids__"))
        os.mkdir(os.path.join(principals, "users"))
        os.mkdir(os.path.join(principals, "groups"))
        os.mkdir(os.path.join(principals, "locations"))
        os.mkdir(os.path.join(principals, "resources"))
        os.mkdir(os.path.join(principals, "sudoers"))
        os.mkdir(os.path.join(self.olddocroot, "calendars"))

        proxyDB = CalendarUserProxyDatabase(principals)
        proxyDB._db()
        os.rename(
            os.path.join(principals, CalendarUserProxyDatabase.dbFilename),
            os.path.join(principals, CalendarUserProxyDatabase.dbOldFilename),
        )

    def setUpOldDocRootWithoutDB(self):
        
        # Set up doc root
        self.olddocrootnodb = self.mktemp()
        os.mkdir(self.olddocrootnodb)

        principals = os.path.join(self.olddocrootnodb, "principals")
        os.mkdir(principals)
        os.mkdir(os.path.join(principals, "__uids__"))
        os.mkdir(os.path.join(principals, "users"))
        os.mkdir(os.path.join(principals, "groups"))
        os.mkdir(os.path.join(principals, "locations"))
        os.mkdir(os.path.join(principals, "resources"))
        os.mkdir(os.path.join(principals, "sudoers"))
        os.mkdir(os.path.join(self.olddocrootnodb, "calendars"))

    def setUpNewDocRoot(self):
        
        # Set up doc root
        self.newdocroot = self.mktemp()
        os.mkdir(self.newdocroot)

        os.mkdir(os.path.join(self.newdocroot, "calendars"))

    def setUpNewDataRoot(self):
        
        # Set up data root
        self.newdataroot = self.mktemp()
        os.mkdir(self.newdataroot)

    def setUpDataRootWithProxyDB(self):
        
        # Set up data root
        self.existingdataroot = self.mktemp()
        os.mkdir(self.existingdataroot)

        proxyDB = CalendarUserProxyDatabase(self.existingdataroot)
        proxyDB._db()

    def test_normalUpgrade(self):
        """
        Test the behavior of normal upgrade from old server to new.
        """

        self.setUpInitialStates()

        config.DocumentRoot = self.olddocroot
        config.DataRoot = self.newdataroot
        
        # Check pre-conditions
        self.assertTrue(os.path.exists(os.path.join(config.DocumentRoot, "principals")))
        self.assertTrue(os.path.isdir(os.path.join(config.DocumentRoot, "principals")))
        self.assertTrue(os.path.exists(os.path.join(config.DocumentRoot, "principals", CalendarUserProxyDatabase.dbOldFilename)))
        self.assertFalse(os.path.exists(os.path.join(config.DataRoot, CalendarUserProxyDatabase.dbFilename)))

        UpgradeTheServer.doUpgrade()
        
        # Check post-conditions
        self.assertFalse(os.path.exists(os.path.join(config.DocumentRoot, "principals",)))
        self.assertTrue(os.path.exists(os.path.join(config.DataRoot, CalendarUserProxyDatabase.dbFilename)))

    def test_partialUpgrade(self):
        """
        Test the behavior of a partial upgrade (one where /principals exists but the proxy db does not) from old server to new.
        """

        self.setUpInitialStates()

        config.DocumentRoot = self.olddocrootnodb
        config.DataRoot = self.newdataroot
        
        # Check pre-conditions
        self.assertTrue(os.path.exists(os.path.join(config.DocumentRoot, "principals")))
        self.assertTrue(os.path.isdir(os.path.join(config.DocumentRoot, "principals")))
        self.assertFalse(os.path.exists(os.path.join(config.DocumentRoot, "principals", CalendarUserProxyDatabase.dbOldFilename)))
        self.assertFalse(os.path.exists(os.path.join(config.DataRoot, CalendarUserProxyDatabase.dbFilename)))

        UpgradeTheServer.doUpgrade()
        
        # Check post-conditions
        self.assertFalse(os.path.exists(os.path.join(config.DocumentRoot, "principals",)))
        self.assertFalse(os.path.exists(os.path.join(config.DataRoot, CalendarUserProxyDatabase.dbFilename)))

    def test_noUpgrade(self):
        """
        Test the behavior of running on a new server (i.e. no upgrade needed).
        """

        self.setUpInitialStates()

        config.DocumentRoot = self.newdocroot
        config.DataRoot = self.existingdataroot
        
        # Check pre-conditions
        self.assertFalse(os.path.exists(os.path.join(config.DocumentRoot, "principals")))
        self.assertTrue(os.path.exists(os.path.join(config.DataRoot, CalendarUserProxyDatabase.dbFilename)))

        UpgradeTheServer.doUpgrade()
        
        # Check post-conditions
        self.assertFalse(os.path.exists(os.path.join(config.DocumentRoot, "principals",)))
        self.assertTrue(os.path.exists(os.path.join(config.DataRoot, CalendarUserProxyDatabase.dbFilename)))

    def test_failedUpgrade(self):
        """
        Test the behavior of failed upgrade from old server to new where proxy DB exists in two locations.
        """

        self.setUpInitialStates()

        config.DocumentRoot = self.olddocroot
        config.DataRoot = self.existingdataroot
        
        # Check pre-conditions
        self.assertTrue(os.path.exists(os.path.join(config.DocumentRoot, "principals")))
        self.assertTrue(os.path.isdir(os.path.join(config.DocumentRoot, "principals")))
        self.assertTrue(os.path.exists(os.path.join(config.DocumentRoot, "principals", CalendarUserProxyDatabase.dbOldFilename)))
        self.assertTrue(os.path.exists(os.path.join(config.DataRoot, CalendarUserProxyDatabase.dbFilename)))

        self.assertRaises(UpgradeError, UpgradeTheServer.doUpgrade)
        
        # Check post-conditions
        self.assertTrue(os.path.exists(os.path.join(config.DocumentRoot, "principals")))
        self.assertTrue(os.path.isdir(os.path.join(config.DocumentRoot, "principals")))
        self.assertTrue(os.path.exists(os.path.join(config.DocumentRoot, "principals", CalendarUserProxyDatabase.dbOldFilename)))
        self.assertTrue(os.path.exists(os.path.join(config.DataRoot, CalendarUserProxyDatabase.dbFilename)))
        