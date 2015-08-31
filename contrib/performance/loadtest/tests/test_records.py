##
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##
"""
Tests for loadtest.records
"""

from twisted.trial.unittest import TestCase

from contrib.performance.loadtest.records import DirectoryRecord, recordsFromCSVFile

class RecordTests(TestCase):
    def test_loadAccountsFromFile(self):
        """
        L{LoadSimulator.fromCommandLine} takes an account loader from the
        config file and uses it to create user records for use in the
        simulation.
        """
        accounts = FilePath(self.mktemp())
        accounts.setContent("foo,bar,baz,quux,goo\nfoo2,bar2,baz2,quux2,goo2\n")
        config = VALID_CONFIG.copy()
        config["accounts"] = {
            "loader": "contrib.performance.loadtest.sim.recordsFromCSVFile",
            "params": {
                "path": accounts.path
            },
        }
        configpath = FilePath(self.mktemp())
        configpath.setContent(writePlistToString(config))
        io = StringIO()
        sim = LoadSimulator.fromCommandLine(['--config', configpath.path], io)
        self.assertEquals(io.getvalue(), "Loaded 2 accounts.\n")
        self.assertEqual(2, len(sim.records))
        self.assertEqual(sim.records[0].uid, 'foo')
        self.assertEqual(sim.records[0].password, 'bar')
        self.assertEqual(sim.records[0].commonName, 'baz')
        self.assertEqual(sim.records[0].email, 'quux')
        self.assertEqual(sim.records[1].uid, 'foo2')
        self.assertEqual(sim.records[1].password, 'bar2')
        self.assertEqual(sim.records[1].commonName, 'baz2')
        self.assertEqual(sim.records[1].email, 'quux2')


    def test_loadDefaultAccountsFromFile(self):
        """
        L{LoadSimulator.fromCommandLine} takes an account loader (with
        empty path)from the config file and uses it to create user
        records for use in the simulation.
        """
        config = VALID_CONFIG.copy()
        config["accounts"] = {
            "loader": "contrib.performance.loadtest.sim.recordsFromCSVFile",
            "params": {
                "path": ""
            },
        }
        configpath = FilePath(self.mktemp())
        configpath.setContent(writePlistToString(config))
        sim = LoadSimulator.fromCommandLine(['--config', configpath.path],
                                            StringIO())
        self.assertEqual(99, len(sim.records))
        self.assertEqual(sim.records[0].uid, 'user01')
        self.assertEqual(sim.records[0].password, 'user01')
        self.assertEqual(sim.records[0].commonName, 'User 01')
        self.assertEqual(sim.records[0].email, 'user01@example.com')
        self.assertEqual(sim.records[98].uid, 'user99')
        self.assertEqual(sim.records[98].password, 'user99')
        self.assertEqual(sim.records[98].commonName, 'User 99')
        self.assertEqual(sim.records[98].email, 'user99@example.com')


ormance.loadtest.sim.generateRecords",
            "params": {
                "count": 2
            },
        }
        configpath = FilePath(self.mktemp())
        configpath.setContent(writePlistToString(config))
        sim = LoadSimulator.fromCommandLine(['--config', configpath.path],
                                            StringIO())
        self.assertEqual(2, len(sim.records))
        self.assertEqual(sim.records[0].uid, 'user1')
        self.assertEqual(sim.records[0].password, 'user1')
        self.assertEqual(sim.records[0].commonName, 'User 1')
        self.assertEqual(sim.records[0].email, 'user1@example.com')
        self.assertEqual(sim.records[1].uid, 'user2')
        self.assertEqual(sim.records[1].password, 'user2')
        self.assertEqual(sim.records[1].commonName, 'User 2')
        self.assertEqual(sim.records[1].email, 'user2@example.com')


    def test_generateRecordsNonDefaultPatterns(self):
        """
        L{LoadSimulator.fromCommandLine} takes an account loader from the
        config file and uses it to generate user records for use in the
        simulation.
        """
        config = VALID_CONFIG.copy()
        config["accounts"] = {
            "loader": "contrib.performance.loadtest.sim.generateRecords",
            "params": {
                "count": 3,
                "uidPattern": "USER%03d",
                "passwordPattern": "PASSWORD%03d",
                "namePattern": "Test User %03d",
                "emailPattern": "USER%03d@example2.com",
            },
        }
        configpath = FilePath(self.mktemp())
        configpath.setContent(writePlistToString(config))
        sim = LoadSimulator.fromCommandLine(['--config', configpath.path],
                                            StringIO())
        self.assertEqual(3, len(sim.records))
        self.assertEqual(sim.records[0].uid, 'USER001')
        self.assertEqual(sim.records[0].password, 'PASSWORD001')
        self.assertEqual(sim.records[0].commonName, 'Test User 001')
        self.assertEqual(sim.records[0].email, 'USER001@example2.com')
        self.assertEqual(sim.records[2].uid, 'USER003')
        self.assertEqual(sim.records[2].password, 'PASSWORD003')
        self.assertEqual(sim.records[2].commonName, 'Test User 003')
        self.assertEqual(sim.records[2].email, 'USER003@example2.com')