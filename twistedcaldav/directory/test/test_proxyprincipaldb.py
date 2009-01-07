##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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
from twistedcaldav.config import config

import os

from twisted.internet.defer import inlineCallbacks
from twistedcaldav.directory.calendaruserproxy import CalendarUserProxyDatabase
import twistedcaldav.test.util

class ProxyPrincipalDB (twistedcaldav.test.util.TestCase):
    """
    Directory service provisioned principals.
    """
    
    class old_CalendarUserProxyDatabase(CalendarUserProxyDatabase):
        
        def _db_version(self):
            """
            @return: the schema version assigned to this index.
            """
            return "3"
            
        def _db_init_data_tables(self, q):
            """
            Initialise the underlying database tables.
            @param q:           a database cursor to use.
            """
    
            #
            # GROUPS table
            #
            q.execute(
                """
                create table GROUPS (
                    GROUPNAME   text,
                    MEMBER      text
                )
                """
            )

    class new_CalendarUserProxyDatabase(CalendarUserProxyDatabase):
        
        def _db_version(self):
            """
            @return: the schema version assigned to this index.
            """
            return "11"
            
    class newer_CalendarUserProxyDatabase(CalendarUserProxyDatabase):
        
        def _db_version(self):
            """
            @return: the schema version assigned to this index.
            """
            return "51"
    
    @inlineCallbacks
    def test_normalDB(self):
    
        # Get the DB
        db_path = self.mktemp()
        os.mkdir(db_path)
        db = CalendarUserProxyDatabase(db_path)
        yield db.setGroupMembers("A", ("B", "C", "D",))
        
        membersA = yield db.getMembers("A")
        membershipsB = yield db.getMemberships("B")
        
        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))

    def test_DBIndexed(self):
    
        # Get the DB
        db_path = self.mktemp()
        os.mkdir(db_path)
        db = CalendarUserProxyDatabase(db_path)
        self.assertEqual(set([row[1] for row in db._db_execute("PRAGMA index_list(GROUPS)")]), set(("GROUPNAMES", "MEMBERS")))

    def test_OldDB(self):
    
        # Get the DB
        db_path = self.mktemp()
        os.mkdir(db_path)
        db = self.old_CalendarUserProxyDatabase(db_path)
        self.assertEqual(set([row[1] for row in db._db_execute("PRAGMA index_list(GROUPS)")]), set())

    @inlineCallbacks
    def test_DBUpgrade(self):
    
        # Get the DB
        db_path = self.mktemp()
        os.mkdir(db_path)
        db = self.old_CalendarUserProxyDatabase(db_path)
        yield db.setGroupMembers("A", ("B", "C", "D",))

        membersA = yield db.getMembers("A")
        membershipsB = yield db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in db._db_execute("PRAGMA index_list(GROUPS)")]), set())
        db._db_close()
        db = None
        
        db = CalendarUserProxyDatabase(db_path)

        membersA = yield db.getMembers("A")
        membershipsB = yield db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in db._db_execute("PRAGMA index_list(GROUPS)")]), set(("GROUPNAMES", "MEMBERS")))
        db._db_close()
        db = None

    @inlineCallbacks
    def test_DBUpgradeNewer(self):
    
        # Get the DB
        db_path = self.mktemp()
        os.mkdir(db_path)
        db = self.old_CalendarUserProxyDatabase(db_path)
        yield db.setGroupMembers("A", ("B", "C", "D",))

        membersA = yield db.getMembers("A")
        membershipsB = yield db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in db._db_execute("PRAGMA index_list(GROUPS)")]), set())
        db._db_close()
        db = None
        
        db = self.new_CalendarUserProxyDatabase(db_path)

        membersA = yield db.getMembers("A")
        membershipsB = yield db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in db._db_execute("PRAGMA index_list(GROUPS)")]), set(("GROUPNAMES", "MEMBERS")))
        db._db_close()
        db = None

    @inlineCallbacks
    def test_DBNoUpgradeNewer(self):
    
        # Get the DB
        db_path = self.mktemp()
        os.mkdir(db_path)
        db = self.new_CalendarUserProxyDatabase(db_path)
        yield db.setGroupMembers("A", ("B", "C", "D",))

        membersA = yield db.getMembers("A")
        membershipsB = yield db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in db._db_execute("PRAGMA index_list(GROUPS)")]), set(("GROUPNAMES", "MEMBERS")))
        db._db_close()
        db = None
        
        db = self.newer_CalendarUserProxyDatabase(db_path)

        membersA = yield db.getMembers("A")
        membershipsB = yield db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in db._db_execute("PRAGMA index_list(GROUPS)")]), set(("GROUPNAMES", "MEMBERS")))
        db._db_close()
        db = None

    @inlineCallbacks
    def test_cachingDBInsert(self):
    
        for processType in ("Single", "Combined",):
            config.ProcessType = processType

            # Get the DB
            db_path = self.mktemp()
            os.mkdir(db_path)
            db = CalendarUserProxyDatabase(db_path)
            
            # Do one insert and check the result
            yield db.setGroupMembers("A", ("B", "C", "D",))
    
            membersA = yield db.getMembers("A")
            membershipsB = yield db.getMemberships("B")
            membershipsC = yield db.getMemberships("C")
            membershipsD = yield db.getMemberships("D")
            membershipsE = yield db.getMemberships("E")
    
            self.assertEqual(membersA, set(("B", "C", "D",)))
            self.assertEqual(membershipsB, set(("A",)))
            self.assertEqual(membershipsC, set(("A",)))
            self.assertEqual(membershipsD, set(("A",)))
            self.assertEqual(membershipsE, set(()))
            
            # Change and check the result
            yield db.setGroupMembers("A", ("B", "C", "E",))
    
            membersA = yield db.getMembers("A")
            membershipsB = yield db.getMemberships("B")
            membershipsC = yield db.getMemberships("C")
            membershipsD = yield db.getMemberships("D")
            membershipsE = yield db.getMemberships("E")
    
            self.assertEqual(membersA, set(("B", "C", "E",)))
            self.assertEqual(membershipsB, set(("A",)))
            self.assertEqual(membershipsC, set(("A",)))
            self.assertEqual(membershipsD, set())
            self.assertEqual(membershipsE, set(("A",)))

    @inlineCallbacks
    def test_cachingDBRemove(self):
    
        for processType in ("Single", "Combined",):
            config.ProcessType = processType

            # Get the DB
            db_path = self.mktemp()
            os.mkdir(db_path)
            db = CalendarUserProxyDatabase(db_path)
            
            # Do one insert and check the result
            yield db.setGroupMembers("A", ("B", "C", "D",))
            yield db.setGroupMembers("X", ("B", "C",))
    
            membersA = yield db.getMembers("A")
            membersX = yield db.getMembers("X")
            membershipsB = yield db.getMemberships("B")
            membershipsC = yield db.getMemberships("C")
            membershipsD = yield db.getMemberships("D")
    
            self.assertEqual(membersA, set(("B", "C", "D",)))
            self.assertEqual(membersX, set(("B", "C",)))
            self.assertEqual(membershipsB, set(("A", "X",)))
            self.assertEqual(membershipsC, set(("A", "X",)))
            self.assertEqual(membershipsD, set(("A",)))
            
            # Remove and check the result
            yield db.removeGroup("A")
    
            membersA = yield db.getMembers("A")
            membersX = yield db.getMembers("X")
            membershipsB = yield db.getMemberships("B")
            membershipsC = yield db.getMemberships("C")
            membershipsD = yield db.getMemberships("D")
    
            self.assertEqual(membersA, set())
            self.assertEqual(membersX, set(("B", "C",)))
            self.assertEqual(membershipsB, set("X",))
            self.assertEqual(membershipsC, set("X",))
            self.assertEqual(membershipsD, set())

    @inlineCallbacks
    def test_cachingDBRemoveSpecial(self):
    
        for processType in ("Single", "Combined",):
            config.ProcessType = processType

            # Get the DB
            db_path = self.mktemp()
            os.mkdir(db_path)
            db = CalendarUserProxyDatabase(db_path)
            
            # Do one insert and check the result
            yield db.setGroupMembers("A", ("B", "C", "D",))
            yield db.setGroupMembers("X", ("B", "C",))
    
            membershipsB = yield db.getMemberships("B")
            membershipsC = yield db.getMemberships("C")
            membershipsD = yield db.getMemberships("D")
            
            # Remove and check the result
            yield db.removeGroup("A")
    
            membersA = yield db.getMembers("A")
            membersX = yield db.getMembers("X")
            membershipsB = yield db.getMemberships("B")
            membershipsC = yield db.getMemberships("C")
            membershipsD = yield db.getMemberships("D")
    
            self.assertEqual(membersA, set())
            self.assertEqual(membersX, set(("B", "C",)))
            self.assertEqual(membershipsB, set("X",))
            self.assertEqual(membershipsC, set("X",))
            self.assertEqual(membershipsD, set())

    @inlineCallbacks
    def test_cachingDBRemovePrincipal(self):
    
        for processType in ("Single", "Combined",):
            config.ProcessType = processType

            # Get the DB
            db_path = self.mktemp()
            os.mkdir(db_path)
            db = CalendarUserProxyDatabase(db_path)
            
            # Do one insert and check the result
            yield db.setGroupMembers("A", ("B", "C", "D",))
            yield db.setGroupMembers("X", ("B", "C",))
    
            membersA = yield db.getMembers("A")
            membersX = yield db.getMembers("X")
            membershipsB = yield db.getMemberships("B")
            membershipsC = yield db.getMemberships("C")
            membershipsD = yield db.getMemberships("D")
    
            self.assertEqual(membersA, set(("B", "C", "D",)))
            self.assertEqual(membersX, set(("B", "C",)))
            self.assertEqual(membershipsB, set(("A", "X",)))
            self.assertEqual(membershipsC, set(("A", "X",)))
            self.assertEqual(membershipsD, set(("A",)))
            
            # Remove and check the result
            yield db.removePrincipal("B")
    
            membersA = yield db.getMembers("A")
            membersX = yield db.getMembers("X")
            membershipsB = yield db.getMemberships("B")
            membershipsC = yield db.getMemberships("C")
            membershipsD = yield db.getMemberships("D")
    
            self.assertEqual(membersA, set(("C", "D",)))
            self.assertEqual(membersX, set(("C",)))
            self.assertEqual(membershipsB, set())
            self.assertEqual(membershipsC, set(("A", "X",)))
            self.assertEqual(membershipsD, set(("A",),))

    @inlineCallbacks
    def test_cachingDBInsertUncached(self):
    
        for processType in ("Single", "Combined",):
            config.ProcessType = processType

            # Get the DB
            db_path = self.mktemp()
            os.mkdir(db_path)
            db = CalendarUserProxyDatabase(db_path)
            
            # Do one insert and check the result for the one we will remove
            yield db.setGroupMembers("AA", ("BB", "CC", "DD",))
            yield db.getMemberships("DD")
    
            # Change and check the result
            yield db.setGroupMembers("AA", ("BB", "CC", "EE",))
    
            membersAA = yield db.getMembers("AA")
            membershipsBB = yield db.getMemberships("BB")
            membershipsCC = yield db.getMemberships("CC")
            membershipsDD = yield db.getMemberships("DD")
            membershipsEE = yield db.getMemberships("EE")
    
            self.assertEqual(membersAA, set(("BB", "CC", "EE",)))
            self.assertEqual(membershipsBB, set(("AA",)))
            self.assertEqual(membershipsCC, set(("AA",)))
            self.assertEqual(membershipsDD, set())
            self.assertEqual(membershipsEE, set(("AA",)))

