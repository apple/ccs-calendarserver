##
# Copyright (c) 2005-2015 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks
from twistedcaldav.config import config
from twistedcaldav.directory import calendaruserproxy
from twistedcaldav.directory.calendaruserproxy import ProxySqliteDB, \
    ProxyPostgreSQLDB
from twistedcaldav.directory.calendaruserproxyloader import XMLCalendarUserProxyLoader
import twistedcaldav.test.util

import os


class ProxyPrincipalDBSqlite (twistedcaldav.test.util.TestCase):
    """
    Directory service provisioned principals.
    """

    class old_ProxyDB(ProxySqliteDB):

        def _db_version(self):
            """
            @return: the schema version assigned to this index.
            """
            return "3"

        def _db_init_data_tables(self):
            """
            Initialise the underlying database tables.
            @param q:           a database cursor to use.
            """

            #
            # GROUPS table
            #
            return self._db_execute(
                """
                create table GROUPS (
                    GROUPNAME   text,
                    MEMBER      text
                )
                """
            )


    class new_ProxyDB(ProxySqliteDB):

        def _db_version(self):
            """
            @return: the schema version assigned to this index.
            """
            return "11"


    class newer_ProxyDB(ProxySqliteDB):

        def _db_version(self):
            """
            @return: the schema version assigned to this index.
            """
            return "51"


    @inlineCallbacks
    def test_normalDB(self):

        # Get the DB
        db_path = os.path.abspath(self.mktemp())
        db = ProxySqliteDB(db_path)
        yield db.setGroupMembers("A", ("B", "C", "D",))

        membersA = yield db.getMembers("A")
        membershipsB = yield db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))


    @inlineCallbacks
    def test_normalDBNonAscii(self):

        # Get the DB
        db_path = os.path.abspath(self.mktemp())
        db = ProxySqliteDB(db_path)
        principalID = "Test \xe4\xbd\x90\xe8\x97\xa4"
        yield db.setGroupMembers(principalID, ("B", "C", "D",))

        membersA = yield db.getMembers(principalID)
        membershipsB = yield db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set((principalID,)))


    @inlineCallbacks
    def test_DBIndexed(self):

        # Get the DB
        db_path = os.path.abspath(self.mktemp())
        db = ProxySqliteDB(db_path)
        self.assertEqual(set([row[1] for row in (yield db.query("PRAGMA index_list(GROUPS)"))]), set(("GROUPNAMES", "MEMBERS")))


    @inlineCallbacks
    def test_OldDB(self):

        # Get the DB
        db_path = os.path.abspath(self.mktemp())
        db = self.old_ProxyDB(db_path)
        self.assertEqual(set([row[1] for row in (yield db.query("PRAGMA index_list(GROUPS)"))]), set())


    @inlineCallbacks
    def test_DBUpgrade(self):

        # Get the DB
        db_path = os.path.abspath(self.mktemp())
        db = self.old_ProxyDB(db_path)
        yield db.setGroupMembers("A", ("B", "C", "D",))

        membersA = yield db.getMembers("A")
        membershipsB = yield db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in (yield db.query("PRAGMA index_list(GROUPS)"))]), set())
        db.close()
        db = None

        db = ProxySqliteDB(db_path)

        membersA = yield db.getMembers("A")
        membershipsB = yield db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in (yield db.query("PRAGMA index_list(GROUPS)"))]), set(("GROUPNAMES", "MEMBERS")))
        db.close()
        db = None


    @inlineCallbacks
    def test_DBUpgradeNewer(self):

        # Get the DB
        db_path = os.path.abspath(self.mktemp())
        db = self.old_ProxyDB(db_path)
        yield db.setGroupMembers("A", ("B", "C", "D",))

        membersA = yield db.getMembers("A")
        membershipsB = yield db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in (yield db.query("PRAGMA index_list(GROUPS)"))]), set())
        db.close()
        db = None

        db = self.new_ProxyDB(db_path)

        membersA = yield db.getMembers("A")
        membershipsB = yield db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in (yield db.query("PRAGMA index_list(GROUPS)"))]), set(("GROUPNAMES", "MEMBERS")))
        db.close()
        db = None


    @inlineCallbacks
    def test_DBNoUpgradeNewer(self):

        # Get the DB
        db_path = os.path.abspath(self.mktemp())
        db = self.new_ProxyDB(db_path)
        yield db.setGroupMembers("A", ("B", "C", "D",))

        membersA = yield db.getMembers("A")
        membershipsB = yield db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in (yield db.query("PRAGMA index_list(GROUPS)"))]), set(("GROUPNAMES", "MEMBERS")))
        db.close()
        db = None

        db = self.newer_ProxyDB(db_path)

        membersA = yield db.getMembers("A")
        membershipsB = yield db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))
        self.assertEqual(set([row[1] for row in (yield db.query("PRAGMA index_list(GROUPS)"))]), set(("GROUPNAMES", "MEMBERS")))
        db.close()
        db = None


    @inlineCallbacks
    def test_cachingDBInsert(self):

        for processType in ("Single", "Combined",):
            config.ProcessType = processType

            # Get the DB
            db_path = os.path.abspath(self.mktemp())
            db = ProxySqliteDB(db_path)

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

            yield db.clean()


    @inlineCallbacks
    def test_cachingDBRemove(self):

        for processType in ("Single", "Combined",):
            config.ProcessType = processType

            # Get the DB
            db_path = os.path.abspath(self.mktemp())
            db = ProxySqliteDB(db_path)

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

            yield db.clean()


    @inlineCallbacks
    def test_cachingDBRemoveSpecial(self):

        for processType in ("Single", "Combined",):
            config.ProcessType = processType

            # Get the DB
            db_path = os.path.abspath(self.mktemp())
            db = ProxySqliteDB(db_path)

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

            yield db.clean()


    @inlineCallbacks
    def test_cachingDBInsertUncached(self):

        for processType in ("Single", "Combined",):
            config.ProcessType = processType

            # Get the DB
            db_path = os.path.abspath(self.mktemp())
            db = ProxySqliteDB(db_path)

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

            yield db.clean()



class ProxyPrincipalDBPostgreSQL (twistedcaldav.test.util.TestCase):
    """
    Directory service provisioned principals.
    """

    @inlineCallbacks
    def setUp(self):

        super(ProxyPrincipalDBPostgreSQL, self).setUp()
        self.db = ProxyPostgreSQLDB(host="localhost", database="proxies")
        yield self.db.clean()


    @inlineCallbacks
    def tearDown(self):
        yield self.db.close()
        self.db = None


    @inlineCallbacks
    def test_normalDB(self):

        # Get the DB
        yield self.db.clean()

        calendaruserproxy.ProxyDBService = self.db
        loader = XMLCalendarUserProxyLoader("/Volumes/Data/Users/cyrusdaboo/Documents/Development/Apple/eclipse/CalendarServer-3/conf/auth/proxies-test.xml")
        yield loader.updateProxyDB()

        yield self.db.setGroupMembers("A", ("B", "C", "D",))

        membersA = yield self.db.getMembers("A")
        membershipsB = yield self.db.getMemberships("B")

        self.assertEqual(membersA, set(("B", "C", "D",)))
        self.assertEqual(membershipsB, set(("A",)))


    @inlineCallbacks
    def test_DBIndexed(self):

        # Get the DB
        yield self.db.clean()
        self.assertTrue((yield self.db.queryOne("select hasindexes from pg_tables where tablename = 'groups'")))


    @inlineCallbacks
    def test_cachingDBInsert(self):

        for processType in ("Single", "Combined",):
            config.ProcessType = processType

            # Get the DB
            yield self.db.clean()

            # Do one insert and check the result
            yield self.db.setGroupMembers("A", ("B", "C", "D",))

            membersA = yield self.db.getMembers("A")
            membershipsB = yield self.db.getMemberships("B")
            membershipsC = yield self.db.getMemberships("C")
            membershipsD = yield self.db.getMemberships("D")
            membershipsE = yield self.db.getMemberships("E")

            self.assertEqual(membersA, set(("B", "C", "D",)))
            self.assertEqual(membershipsB, set(("A",)))
            self.assertEqual(membershipsC, set(("A",)))
            self.assertEqual(membershipsD, set(("A",)))
            self.assertEqual(membershipsE, set(()))

            # Change and check the result
            yield self.db.setGroupMembers("A", ("B", "C", "E",))

            membersA = yield self.db.getMembers("A")
            membershipsB = yield self.db.getMemberships("B")
            membershipsC = yield self.db.getMemberships("C")
            membershipsD = yield self.db.getMemberships("D")
            membershipsE = yield self.db.getMemberships("E")

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
            yield self.db.clean()

            # Do one insert and check the result
            yield self.db.setGroupMembers("A", ("B", "C", "D",))
            yield self.db.setGroupMembers("X", ("B", "C",))

            membersA = yield self.db.getMembers("A")
            membersX = yield self.db.getMembers("X")
            membershipsB = yield self.db.getMemberships("B")
            membershipsC = yield self.db.getMemberships("C")
            membershipsD = yield self.db.getMemberships("D")

            self.assertEqual(membersA, set(("B", "C", "D",)))
            self.assertEqual(membersX, set(("B", "C",)))
            self.assertEqual(membershipsB, set(("A", "X",)))
            self.assertEqual(membershipsC, set(("A", "X",)))
            self.assertEqual(membershipsD, set(("A",)))

            # Remove and check the result
            yield self.db.removeGroup("A")

            membersA = yield self.db.getMembers("A")
            membersX = yield self.db.getMembers("X")
            membershipsB = yield self.db.getMemberships("B")
            membershipsC = yield self.db.getMemberships("C")
            membershipsD = yield self.db.getMemberships("D")

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
            yield self.db.clean()

            # Do one insert and check the result
            yield self.db.setGroupMembers("A", ("B", "C", "D",))
            yield self.db.setGroupMembers("X", ("B", "C",))

            membershipsB = yield self.db.getMemberships("B")
            membershipsC = yield self.db.getMemberships("C")
            membershipsD = yield self.db.getMemberships("D")

            # Remove and check the result
            yield self.db.removeGroup("A")

            membersA = yield self.db.getMembers("A")
            membersX = yield self.db.getMembers("X")
            membershipsB = yield self.db.getMemberships("B")
            membershipsC = yield self.db.getMemberships("C")
            membershipsD = yield self.db.getMemberships("D")

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
            yield self.db.clean()

            # Do one insert and check the result
            yield self.db.setGroupMembers("A", ("B", "C", "D",))
            yield self.db.setGroupMembers("X", ("B", "C",))

            membersA = yield self.db.getMembers("A")
            membersX = yield self.db.getMembers("X")
            membershipsB = yield self.db.getMemberships("B")
            membershipsC = yield self.db.getMemberships("C")
            membershipsD = yield self.db.getMemberships("D")

            self.assertEqual(membersA, set(("B", "C", "D",)))
            self.assertEqual(membersX, set(("B", "C",)))
            self.assertEqual(membershipsB, set(("A", "X",)))
            self.assertEqual(membershipsC, set(("A", "X",)))
            self.assertEqual(membershipsD, set(("A",)))

            # Remove and check the result
            yield self.db.removePrincipal("B")

            membersA = yield self.db.getMembers("A")
            membersX = yield self.db.getMembers("X")
            membershipsB = yield self.db.getMemberships("B")
            membershipsC = yield self.db.getMemberships("C")
            membershipsD = yield self.db.getMemberships("D")

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
            yield self.db.clean()

            # Do one insert and check the result for the one we will remove
            yield self.db.setGroupMembers("AA", ("BB", "CC", "DD",))
            yield self.db.getMemberships("DD")

            # Change and check the result
            yield self.db.setGroupMembers("AA", ("BB", "CC", "EE",))

            membersAA = yield self.db.getMembers("AA")
            membershipsBB = yield self.db.getMemberships("BB")
            membershipsCC = yield self.db.getMemberships("CC")
            membershipsDD = yield self.db.getMemberships("DD")
            membershipsEE = yield self.db.getMemberships("EE")

            self.assertEqual(membersAA, set(("BB", "CC", "EE",)))
            self.assertEqual(membershipsBB, set(("AA",)))
            self.assertEqual(membershipsCC, set(("AA",)))
            self.assertEqual(membershipsDD, set())
            self.assertEqual(membershipsEE, set(("AA",)))


try:
    import pgdb
except ImportError:
    ProxyPrincipalDBPostgreSQL.skip = True
else:
    try:
        db = pgdb.connect(host="localhost", database="proxies")
    except:
        ProxyPrincipalDBPostgreSQL.skip = True
