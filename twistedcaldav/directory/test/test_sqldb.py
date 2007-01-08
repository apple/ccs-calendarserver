##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

import os

from twisted.python.filepath import FilePath

import twistedcaldav.directory.test.util
import twistedcaldav.directory.test.test_xmlfile
from twistedcaldav.directory.sqldb import SQLDirectoryService

xmlFile = FilePath(os.path.join(os.path.dirname(__file__), "accounts.xml"))

# FIXME: Add tests for GUID hooey, once we figure out what that means here

class SQLDB (
    twistedcaldav.directory.test.test_xmlfile.XMLFileBase,
    twistedcaldav.directory.test.util.BasicTestCase,
    twistedcaldav.directory.test.util.DigestTestCase
):
    """
    Test SQL directory implementation.
    """
    def service(self):
        return SQLDirectoryService(os.getcwd(), self.xmlFile())

    def test_recordTypes(self):
        super(SQLDB, self).test_recordTypes()

    def test_verifyCredentials_digest(self):
        super(SQLDB, self).test_verifyCredentials_digest()
    test_verifyCredentials_digest.todo = ""

    def test_verifyRealmFromDB(self):

        def _service():
            return SQLDirectoryService(os.getcwd(), None)

        self.assertEquals(_service().realmName, "Test")
