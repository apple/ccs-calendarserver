# -*- test-case-name: txdav.datastore.test.test_subpostgres -*-
##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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

"""
Run and manage PostgreSQL as a subprocess.
"""
import os
import pgdb

from twisted.python.procutils import which
from twisted.internet.utils import getProcessOutput
from twisted.internet.protocol import ProcessProtocol

from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor
from twisted.internet.defer import Deferred, succeed

from twisted.application.service import MultiService


_MAGIC_READY_COOKIE = "database system is ready to accept connections"


class _PostgresMonitor(ProcessProtocol):
    """
    A monitoring protocol which watches the postgres subprocess.
    """

    def __init__(self, svc):
        self.lineReceiver = LineReceiver()
        self.lineReceiver.delimiter = '\n'
        self.lineReceiver.lineReceived = self.lineReceived
        self.svc = svc
        self.isReady = False
        self.completionDeferred = Deferred()


    def lineReceived(self, line):
        if not self.isReady:
            if _MAGIC_READY_COOKIE in line:
                self.svc.ready()
        print 'log output:', repr(line)


    disconnecting = False
    def connectionMade(self):
        self.lineReceiver.makeConnection(self)


    def outReceived(self, out):
        print 'received postgres output', out
        # self.lineReceiver.dataReceived(out)


    def errReceived(self, err):
        print 'postgress err received', repr(err)
        self.lineReceiver.dataReceived(err)


    def processEnded(self, reason):
        self.lineReceiver.connectionLost(reason)
        self.completionDeferred.callback(None)



class PostgresService(MultiService):

    def __init__(self, dataStoreDirectory, subServiceFactory,
                 schema, databaseName='subpostgres'):
        """
        Initialize a L{PostgresService} pointed at a data store directory.

        @param dataStoreDirectory: the directory to
        @type dataStoreDirectory: L{twext.python.filepath.CachingFilePath}

        @param subServiceFactory: a 1-arg callable that will be called with a
            1-arg callable which returns a DB-API cursor.
        @type subServiceFactory: C{callable}
        """
        MultiService.__init__(self)
        self.subServiceFactory = subServiceFactory
        self.dataStoreDirectory = dataStoreDirectory
        self.databaseName = databaseName
        self.schema = schema
        self.monitor = None


    def produceConnection(self):
        """
        Produce a DB-API 2.0 connection pointed at this database.
        """
        return pgdb.connect(
            "%s:dbname=%s" % (
                self.socketDir.path,
                self.databaseName
            )
        )


    def ready(self):
        """
        Subprocess is ready.  Time to initialize the subservice.
        """
        if self.firstTime:
            createDatabaseConn = pgdb.connect(
                self.socketDir.path + ":dbname=template1"
            )
            createDatabaseCursor = createDatabaseConn.cursor()
            createDatabaseCursor.execute("commit")
            createDatabaseCursor.execute(
                "create database %s" % (self.databaseName)
            )
            createDatabaseCursor.close()
            createDatabaseConn.close()
            print 'executing schema', repr(self.schema)
            connection = self.produceConnection()
            cursor = connection.cursor()
            cursor.execute(self.schema)
            connection.commit()
            connection.close()
        print 'creating subservice'
        self.subServiceFactory(self.produceConnection).setServiceParent(self)
        print 'subservice created'


    def startDatabase(self):
        """
        Start the database and initialize the subservice.
        """
        monitor = _PostgresMonitor(self)
        postgres = which("postgres")[0]
        # check consistency of initdb and postgres?
        reactor.spawnProcess(
            monitor, postgres,
            [
                postgres,
                "-k", self.socketDir.path,
                # "-N", "5000",
            ],
            self.env
        )
        self.monitor = monitor


    def startService(self):
        MultiService.startService(self)
        self.dataStoreDirectory.createDirectory()
        clusterDir = self.dataStoreDirectory.child("cluster")
        self.socketDir = self.dataStoreDirectory.child("socket")
        self.socketDir.createDirectory()
        workingDir = self.dataStoreDirectory.child("working")
        env = self.env = os.environ.copy()
        env.update(PGDATA=clusterDir.path)
        initdb = which("initdb")[0]
        if clusterDir.isdir():
            self.firstTime = False
            self.startDatabase()
        else:
            workingDir.createDirectory()
            self.firstTime = True
            print 'Creating database'
            dbInited = getProcessOutput(
                initdb, [], env, workingDir.path, errortoo=True
            )
            def doCreate(result):
                print '--- initdb ---'
                print result
                print '/// initdb ///'
                self.startDatabase()
            dbInited.addCallback(
                doCreate
            )
            def showme(result):
                print 'SHOW ME:', result.getTraceback()
            dbInited.addErrback(showme)


    def stopService(self):
        """
        Stop all child services, then stop the subprocess, if it's running.
        """
        d = MultiService.stopService(self)
        def maybeStopSubprocess(result):
            if self.monitor is not None:
                self.monitor.transport.signalProcess("INT")
                return self.monitor.completionDeferred
            return result
        d.addCallback(maybeStopSubprocess)
        return d
