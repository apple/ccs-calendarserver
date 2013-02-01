##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
XML directory service tests
"""

from twisted.python.filepath import FilePath

from twext.who.idirectory import RecordType
from twext.who.xml import DirectoryService

from twext.who.test import test_directory



xmlRealmName = "Test Realm"



class BaseTest(object):
    def _testService(self):
        if not hasattr(self, "_service"):
            filePath = FilePath(self.mktemp())

            filePath.setContent(
                """<?xml version="1.0" encoding="utf-8"?>

<directory realm="xyzzy">

  <record type="user">
    <uid>wsanchez</uid>
    <short-name>wsanchez</short-name>
    <short-name>wilfredo_sanchez</short-name>
    <full-name>Wilfredo Sanchez</full-name>
    <password>zehcnasw</password>
    <email>wsanchez@calendarserver.org</email>
    <email>wsanchez@example.com</email>
  </record>

  <record type="user">
    <uid>glyph</uid>
    <short-name>glyph</short-name>
    <full-name>Glyph Lefkowitz</full-name>
    <password>hpylg</password>
    <email>glyph@calendarserver.org</email>
  </record>

</directory>
"""
            )

            self._service = DirectoryService(filePath)
        return self._service



class DirectoryServiceTest(BaseTest, test_directory.DirectoryServiceTest):
    def test_recordWithUID(self):
        service = self._testService()
        record = service.recordWithUID("wsanchez")
        self.assertEquals(record.uid, "wsanchez")


    def test_recordWithGUID(self):
        service = self._testService()
        record = service.recordWithGUID("wsanchez")
        self.assertEquals(record, None)


    def test_recordsWithRecordType(self):
        service = self._testService()
        records = service.recordsWithRecordType(RecordType.user)
        self.assertEquals(
            set((record.uid for record in records)),
            set(("wsanchez", "glyph")),
        )


    def test_recordWithShortName(self):
        service = self._testService()
        record = service.recordWithShortName(RecordType.user, "wsanchez")
        self.assertEquals(record.uid, "wsanchez")


    def test_recordsWithEmailAddress(self):
        service = self._testService()
        records = service.recordsWithEmailAddress("wsanchez@example.com")
        self.assertEquals(
            set((record.uid for record in records)),
            set(("wsanchez",)),
        )
