# -*- test-case-name: txdav.base.datastore.test.test_subpostgres -*-
# #
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
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
# #

"""
Stub service for Oracle.
"""

from twext.python.log import Logger

from txdav.base.datastore.dbapiclient import DBAPIConnector

from twisted.application.service import MultiService
from twisted.internet.defer import inlineCallbacks

log = Logger()



class OracleService(MultiService):

    def __init__(
        self, dataStoreDirectory, subServiceFactory,
        dsnUser=None,
        testMode=False,
        reactor=None,
    ):
        """
        Initialize a L{OracleService} pointed at a data store directory.

        @param dataStoreDirectory: the directory to
        @type dataStoreDirectory: L{twext.python.filepath.CachingFilePath}

        @param subServiceFactory: a 1-arg callable that will be called with a
            1-arg callable which returns a DB-API cursor.
        @type subServiceFactory: C{callable}
        """

        MultiService.__init__(self)
        self.subServiceFactory = subServiceFactory
        self.dataStoreDirectory = dataStoreDirectory
        self.workingDir = self.dataStoreDirectory.child("working")

        self.dsnUser = dsnUser
        self.testMode = testMode

        self._reactor = reactor


    @property
    def reactor(self):
        if self._reactor is None:
            from twisted.internet import reactor
            self._reactor = reactor
        return self._reactor


    def _connectorFor(self):
        kwargs = {
            "endpoint": "tcp:192.168.56.101:1521",
            "database": "orcl",
            "user": self.dsnUser if self.dsnUser else "hr",
            "password": "oracle",
        }

        return DBAPIConnector.connectorFor("oracle", **kwargs)


    def produceConnection(self, label="<unlabeled>"):
        """
        Produce a DB-API 2.0 connection pointed at this database.
        """
        return self._connectorFor().connect(label)


    def pauseMonitor(self):
        """
        Pause monitoring.
        """
        pass


    def unpauseMonitor(self):
        """
        Unpause monitoring.

        @see: L{pauseMonitor}
        """
        pass


    def startService(self):
        MultiService.startService(self)

        if not self.dataStoreDirectory.isdir():
            log.info("Creating {dir}", dir=self.dataStoreDirectory.path)
            self.dataStoreDirectory.createDirectory()

        if not self.workingDir.isdir():
            log.info("Creating {dir}", dir=self.workingDir.path)
            self.workingDir.createDirectory()

        self.subServiceFactory(
            self.produceConnection, self
        ).setServiceParent(self)


    def hardStop(self):
        """
        Stop quickly by sending it SIGQUIT
        """
        pass



@inlineCallbacks
def cleanDatabase(txn):
    tables = yield txn.execSQL("select table_name from user_tables")
    for table in tables:
        yield txn.execSQL("drop table {} cascade constraints purge".format(table[0]))
    yield txn.execSQL("purge recyclebin")

    sequences = yield txn.execSQL("select sequence_name from user_sequences")
    for sequence in sequences:
        yield txn.execSQL("drop sequence {}".format(sequence[0]))

    indexes = yield txn.execSQL("select index_name from user_indexes")
    for index in indexes:
        yield txn.execSQL("drop index {}".format(index[0]))

    constraints = yield txn.execSQL("select constraint_name from user_constraints")
    for constraint in constraints:
        yield txn.execSQL("drop constraint '{}'".format(constraint[0]))
