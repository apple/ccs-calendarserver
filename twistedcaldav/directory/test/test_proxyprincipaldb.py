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

import os

from twisted.internet.defer import deferredGenerator
from twisted.internet.defer import waitForDeferred
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
    
    @deferredGenerator
    def test_normalDB(self):
    
        # Get the DB
        db_path = self.mktemp()
        os.mkdir(db_path)
        db = CalendarUserProxyDatabase(db_path)
        d = waitForDeferred(db.setGroupMembers("A", ("B", "C", "D",)))
        yield d
        d.getResult()
        
        d = waitForDeferred(db.getMembers("A"))
        yield d
        membersA = d.getResult()
        
        d = waitForDeferred(db.getMemberships("B"))
        yield d
        membershipsB = d.getResult()
        
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

    def test_DBUpgrade(self):
    
        # Get the DB
        db_path = self.mktemp()
        os.mkdir(db_path)
        db = self.old_CalendarUserProxyDatabase(db_path)
        d = waitForDeferred(db.setGroupMembers("A", ("B", "C", "D",)))
        yield d
        d.getResult()

        d = waitForDeferred(db.getMembers("A"))
        yield d
        membersA = d.getResult()

        d = waitForDeferred(db.getMemberships("B"))
        yield d
        membershipsB = d.getResult()

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in db._db_execute("PRAGMA index_list(GROUPS)")]), set())
        db._db_close()
        db = None
        
        db = CalendarUserProxyDatabase(db_path)

        d = waitForDeferred(db.getMembers("A"))
        yield d
        membersA = d.getResult()

        d = waitForDeferred(db.getMemberships("B"))
        yield d
        membershipsB = d.getResult()

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in db._db_execute("PRAGMA index_list(GROUPS)")]), set(("GROUPNAMES", "MEMBERS")))
        db._db_close()
        db = None

    def test_DBUpgradeNewer(self):
    
        # Get the DB
        db_path = self.mktemp()
        os.mkdir(db_path)
        db = self.old_CalendarUserProxyDatabase(db_path)
        d = waitForDeferred(db.setGroupMembers("A", ("B", "C", "D",)))
        yield d
        d.getResult()

        d = waitForDeferred(db.getMembers("A"))
        yield d
        membersA = d.getResult()

        d = waitForDeferred(db.getMemberships("B"))
        yield d
        membershipsB = d.getResult()

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in db._db_execute("PRAGMA index_list(GROUPS)")]), set())
        db._db_close()
        db = None
        
        db = self.new_CalendarUserProxyDatabase(db_path)

        d = waitForDeferred(db.getMembers("A"))
        yield d
        membersA = d.getResult()

        d = waitForDeferred(db.getMemberships("B"))
        yield d
        membershipsB = d.getResult()

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in db._db_execute("PRAGMA index_list(GROUPS)")]), set(("GROUPNAMES", "MEMBERS")))
        db._db_close()
        db = None

    def test_DBNoUpgradeNewer(self):
    
        # Get the DB
        db_path = self.mktemp()
        os.mkdir(db_path)
        db = self.new_CalendarUserProxyDatabase(db_path)
        d = waitForDeferred(db.setGroupMembers("A", ("B", "C", "D",)))
        yield d
        d.getResult()

        d = waitForDeferred(db.getMembers("A"))
        yield d
        membersA = d.getResult()

        d = waitForDeferred(db.getMemberships("B"))
        yield d
        membershipsB = d.getResult()

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in db._db_execute("PRAGMA index_list(GROUPS)")]), set(("GROUPNAMES", "MEMBERS")))
        db._db_close()
        db = None
        
        db = self.newer_CalendarUserProxyDatabase(db_path)

        d = waitForDeferred(db.getMembers("A"))
        yield d
        membersA = d.getResult()

        d = waitForDeferred(db.getMemberships("B"))
        yield d
        membershipsB = d.getResult()

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in db._db_execute("PRAGMA index_list(GROUPS)")]), set(("GROUPNAMES", "MEMBERS")))
        db._db_close()
        db = None

    def test_cachingDBInsert(self):
    
        # Get the DB
        db_path = self.mktemp()
        os.mkdir(db_path)
        db = CalendarUserProxyDatabase(db_path)
        
        # Do one insert and check the result
        d = waitForDeferred(db.setGroupMembers("A", ("B", "C", "D",)))
        yield d
        d.getResult()

        d = waitForDeferred(db.getMembers("A"))
        yield d
        membersA = d.getResult()

        d = waitForDeferred(db.getMemberships("B"))
        yield d
        membershipsB = d.getResult()

        d = waitForDeferred(db.getMemberships("C"))
        yield d
        membershipsC = d.getResult()

        d = waitForDeferred(db.getMemberships("D"))
        yield d
        membershipsD = d.getResult()

        d = waitForDeferred(db.getMemberships("E"))
        yield d
        membershipsE = d.getResult()

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(membershipsC, set(("A",)))
        self.assertEqual(membershipsD, set(("A",)))
        self.assertEqual(membershipsE, set(()))
        
        # Change and check the result
        d = waitForDeferred(db.setGroupMembers("A", ("B", "C", "E",)))
        yield d
        d.getResult()

        d = waitForDeferred(db.getMembers("A"))
        yield d
        membersA = d.getResult()

        d = waitForDeferred(db.getMemberships("B"))
        yield d
        membershipsB = d.getResult()

        d = waitForDeferred(db.getMemberships("C"))
        yield d
        membershipsC = d.getResult()

        d = waitForDeferred(db.getMemberships("D"))
        yield d
        membershipsD = d.getResult()

        d = waitForDeferred(db.getMemberships("E"))
        yield d
        membershipsE = d.getResult()

        self.assertEqual(db.membersA, set(("B", "C", "E",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(membershipsC, set(("A",)))
        self.assertEqual(membershipsD, set())
        self.assertEqual(membershipsE, set(("A",)))

    def test_cachingDBRemove(self):
    
        # Get the DB
        db_path = self.mktemp()
        os.mkdir(db_path)
        db = CalendarUserProxyDatabase(db_path)
        
        # Do one insert and check the result
        d = waitForDeferred(db.setGroupMembers("A", ("B", "C", "D",)))
        yield d
        d.getResult()

        d = waitForDeferred(db.setGroupMembers("X", ("B", "C",)))
        yield d
        d.getResult()

        d = waitForDeferred(db.getMembers("A"))
        yield d
        membersA = d.getResult()

        d = waitForDeferred(db.getMembers("X"))
        yield d
        membersX = d.getResult()

        d = waitForDeferred(db.getMemberships("B"))
        yield d
        membershipsB = d.getResult()

        d = waitForDeferred(db.getMemberships("C"))
        yield d
        membershipsC = d.getResult()

        d = waitForDeferred(db.getMemberships("D"))
        yield d
        membershipsD = d.getResult()

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membersX, set(("B", "C",)))
        self.assertEqual(membershipsB, set(("A", "X",)))
        self.assertEqual(membershipsC, set(("A", "X",)))
        self.assertEqual(membershipsD, set(("A",)))
        
        # Remove and check the result
        d = waitForDeferred(db.removeGroup("A"))
        yield d
        d.getResult()

        d = waitForDeferred(db.getMembers("A"))
        yield d
        membersA = d.getResult()

        d = waitForDeferred(db.getMemberships("B"))
        yield d
        membershipsB = d.getResult()

        d = waitForDeferred(db.getMemberships("C"))
        yield d
        membershipsC = d.getResult()

        d = waitForDeferred(db.getMemberships("D"))
        yield d
        membershipsD = d.getResult()

        self.assertEqual(membersA, set())
        self.assertEqual(membershipsB, set("X",))
        self.assertEqual(membershipsC, set("X",))
        self.assertEqual(membershipsD, set())
        