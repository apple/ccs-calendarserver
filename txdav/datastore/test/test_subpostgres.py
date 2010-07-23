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
from txdav.datastore.subpostgres import PostgresService
from twisted.internet.defer import inlineCallbacks, Deferred
from twisted.application.service import Service

"""
Tests for txdav.datastore.subpostgres.
"""

from twext.python.filepath import CachingFilePath
from twisted.trial.unittest import TestCase


class SubprocessStartup(TestCase):
    """
    Tests for starting and stopping the subprocess.
    """

    @inlineCallbacks
    def test_startService(self):
        """
        Assuming a properly configured environment ($PATH points at an 'initdb'
        and 'postgres', $PYTHONPATH includes pgdb), starting a
        L{PostgresService} will start the service passed to it, after executing
        the schema.
        """

        test = self
        class SimpleService(Service):
            instances = []
            rows = []
            ready = Deferred()
            def __init__(self, connectionFactory):
                self.connection = connectionFactory()
                test.addCleanup(self.connection.close)
                print 'CREATING simpleservice'
                self.instances.append(self)

            def startService(self):
                print 'STARTING simpleservice'
                cursor = self.connection.cursor()
                cursor.execute(
                    "insert into test_dummy_table values ('dummy')"
                )
                cursor.close()
                self.ready.callback(None)

        svc = PostgresService(
            CachingFilePath("database"),
            SimpleService,
            "create table TEST_DUMMY_TABLE (stub varchar)",
            "dummy_db"
        )

        svc.startService()
        self.addCleanup(svc.stopService)
        yield SimpleService.ready
        connection = SimpleService.instances[0].connection
        cursor = connection.cursor()
        cursor.execute("select * from test_dummy_table")
        values = list(cursor)
        self.assertEquals(values, [["dummy"]])
