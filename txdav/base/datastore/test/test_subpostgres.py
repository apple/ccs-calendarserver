##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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
Tests for txdav.base.datastore.subpostgres.
"""

from twisted.trial.unittest import TestCase

# NOTE: This import will fail eventually when this functionality is added to
# MemoryReactor:

from twext.python.filepath import CachingFilePath

from txdav.base.datastore.subpostgres import PostgresService
from twisted.internet.defer import inlineCallbacks, Deferred
from twisted.application.service import Service

class SubprocessStartup(TestCase):
    """
    Tests for starting and stopping the subprocess.
    """

    @inlineCallbacks
    def test_startService_Unix(self):
        """
        Assuming a properly configured environment ($PATH points at an 'initdb'
        and 'postgres', $PYTHONPATH includes pgdb), starting a
        L{PostgresService} will start the service passed to it, after executing
        the schema.
        """

        test = self
        class SimpleService1(Service):

            instances = []
            ready = Deferred()

            def __init__(self, connectionFactory, storageService):
                self.connection = connectionFactory()
                test.addCleanup(self.connection.close)
                self.instances.append(self)


            def startService(self):
                cursor = self.connection.cursor()
                try:
                    cursor.execute(
                        "insert into test_dummy_table values ('dummy')"
                    )
                except:
                    self.ready.errback()
                else:
                    self.ready.callback(None)
                finally:
                    cursor.close()

        svc = PostgresService(
            CachingFilePath("postgres_1.pgdb"),
            SimpleService1,
            "create table TEST_DUMMY_TABLE (stub varchar)",
            databaseName="dummy_db",
            testMode=True
        )
        svc.startService()
        self.addCleanup(svc.stopService)
        yield SimpleService1.ready
        connection = SimpleService1.instances[0].connection
        cursor = connection.cursor()
        cursor.execute("select * from test_dummy_table")
        values = cursor.fetchall()
        self.assertEquals(values, [["dummy"]])


    @inlineCallbacks
    def test_startService_Socket(self):
        """
        Assuming a properly configured environment ($PATH points at an 'initdb'
        and 'postgres', $PYTHONPATH includes pgdb), starting a
        L{PostgresService} will start the service passed to it, after executing
        the schema.
        """

        test = self
        class SimpleService2(Service):

            instances = []
            ready = Deferred()

            def __init__(self, connectionFactory, storageService):
                self.connection = connectionFactory()
                test.addCleanup(self.connection.close)
                self.instances.append(self)


            def startService(self):
                cursor = self.connection.cursor()
                try:
                    cursor.execute(
                        "insert into test_dummy_table values ('dummy')"
                    )
                except:
                    self.ready.errback()
                else:
                    self.ready.callback(None)
                finally:
                    cursor.close()

        svc = PostgresService(
            CachingFilePath("postgres_2.pgdb"),
            SimpleService2,
            "create table TEST_DUMMY_TABLE (stub varchar)",
            databaseName="dummy_db",
            listenAddresses=['127.0.0.1', ],
            testMode=True
        )
        svc.startService()
        self.addCleanup(svc.stopService)
        yield SimpleService2.ready
        connection = SimpleService2.instances[0].connection
        cursor = connection.cursor()
        cursor.execute("select * from test_dummy_table")
        values = cursor.fetchall()
        self.assertEquals(values, [["dummy"]])


    @inlineCallbacks
    def test_startService_withDumpFile(self):
        """
        Assuming a properly configured environment ($PATH points at an 'initdb'
        and 'postgres', $PYTHONPATH includes pgdb), starting a
        L{PostgresService} will start the service passed to it, after importing
        an existing dump file.
        """

        test = self
        class SimpleService1(Service):

            instances = []
            ready = Deferred()

            def __init__(self, connectionFactory, storageService):
                self.connection = connectionFactory()
                test.addCleanup(self.connection.close)
                self.instances.append(self)


            def startService(self):
                cursor = self.connection.cursor()
                try:
                    cursor.execute(
                        "insert into import_test_table values ('value2')"
                    )
                except:
                    self.ready.errback()
                else:
                    self.ready.callback(None)
                finally:
                    cursor.close()

        # The SQL in importFile.sql will get executed, including the insertion of "value1"
        importFileName = CachingFilePath(__file__).parent().child("importFile.sql").path
        svc = PostgresService(
            CachingFilePath("postgres_3.pgdb"),
            SimpleService1,
            "",
            databaseName="dummy_db",
            testMode=True,
            importFileName=importFileName
        )
        svc.startService()
        self.addCleanup(svc.stopService)
        yield SimpleService1.ready
        connection = SimpleService1.instances[0].connection
        cursor = connection.cursor()
        cursor.execute("select * from import_test_table")
        values = cursor.fetchall()
        self.assertEquals(values, [["value1"], ["value2"]])


