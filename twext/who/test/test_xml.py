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
from twisted.internet.defer import inlineCallbacks

from twext.who.idirectory import RecordType
from twext.who.xml import DirectoryService

from twext.who.test import test_directory



xmlRealmName = "Test Realm"

testXMLConfig = """<?xml version="1.0" encoding="utf-8"?>

<directory realm="xyzzy">

  <record type="user">
    <uid>__wsanchez__</uid>
    <short-name>wsanchez</short-name>
    <short-name>wilfredo_sanchez</short-name>
    <full-name>Wilfredo Sanchez</full-name>
    <password>zehcnasw</password>
    <email>wsanchez@bitbucket.calendarserver.org</email>
    <email>wsanchez@devnull.twistedmatrix.com</email>
  </record>

  <record type="user">
    <uid>__glyph__</uid>
    <short-name>glyph</short-name>
    <full-name>Glyph Lefkowitz</full-name>
    <password>hpylg</password>
    <email>glyph@bitbucket.calendarserver.org</email>
    <email>glyph@devnull.twistedmatrix.com</email>
  </record>

  <record type="user">
    <uid>__sagen__</uid>
    <short-name>sagen</short-name>
    <full-name>Morgen Sagen</full-name>
    <password>negas</password>
    <email>sagen@bitbucket.calendarserver.org</email>
    <email>shared@example.com</email>
  </record>

  <record type="user">
    <uid>__cdaboo__</uid>
    <short-name>cdaboo</short-name>
    <full-name>Cyrus Daboo</full-name>
    <password>suryc</password>
    <email>cdaboo@bitbucket.calendarserver.org</email>
  </record>

  <record type="user">
    <uid>__dre__</uid>
    <short-name>dre</short-name>
    <full-name>Andre LaBranche</full-name>
    <password>erd</password>
    <email>dre@bitbucket.calendarserver.org</email>
    <email>shared@example.com</email>
  </record>

  <record type="user">
    <uid>__exarkun__</uid>
    <short-name>exarkun</short-name>
    <full-name>Jean-Paul Calderone</full-name>
    <password>nucraxe</password>
    <email>exarkun@devnull.twistedmatrix.com</email>
  </record>

  <record type="user">
    <uid>__dreid__</uid>
    <short-name>dreid</short-name>
    <full-name>David Reid</full-name>
    <password>dierd</password>
    <email>dreid@devnull.twistedmatrix.com</email>
  </record>

  <record> <!-- type defaults to "user" -->
    <uid>__joe__</uid>
    <short-name>joe</short-name>
    <full-name>Joe Schmoe</full-name>
    <password>eoj</password>
    <email>joe@example.com</email>
  </record>

  <record type="group">
    <uid>__calendar-dev__</uid>
    <short-name>calendar-dev</short-name>
    <full-name>Calendar Server developers</full-name>
    <email>dev@bitbucket.calendarserver.org</email>
    <member-uid>__wsanchez__</member-uid>
    <member-uid>__glyph__</member-uid>
    <member-uid>__sagen__</member-uid>
    <member-uid>__cdaboo__</member-uid>
    <member-uid>__dre__</member-uid>
  </record>

  <record type="group">
    <uid>__twisted__</uid>
    <short-name>twisted</short-name>
    <full-name>Twisted Matrix Laboratories</full-name>
    <email>hack@devnull.twistedmatrix.com</email>
    <member-uid>__wsanchez__</member-uid>
    <member-uid>__glyph__</member-uid>
    <member-uid>__exarkun__</member-uid>
    <member-uid>__dreid__</member-uid>
    <member-uid>__dre__</member-uid>
  </record>

</directory>
"""



class BaseTest(object):
    def _testService(self):
        if not hasattr(self, "_service"):
            filePath = FilePath(self.mktemp())
            filePath.setContent(testXMLConfig)
            self._service = DirectoryService(filePath)
        return self._service



class DirectoryServiceTest(BaseTest, test_directory.DirectoryServiceTest):
    @inlineCallbacks
    def test_recordWithUID(self):
        service = self._testService()
        record = (yield service.recordWithUID("__wsanchez__"))
        self.assertEquals(record.uid, "__wsanchez__")


    @inlineCallbacks
    def test_recordWithGUID(self):
        service = self._testService()
        record = (yield service.recordWithGUID("6C495FCD-7E78-4D5C-AA66-BC890AD04C9D"))
        self.assertEquals(record, None)

    @inlineCallbacks
    def test_recordsWithRecordType(self):
        service = self._testService()

        records = (yield service.recordsWithRecordType(RecordType.user))
        self.assertEquals(
            set((record.uid for record in records)),
            set((
                "__wsanchez__",
                "__glyph__",
                "__sagen__",
                "__cdaboo__",
                "__dre__",
                "__exarkun__",
                "__dreid__",
                "__joe__",
            )),
        )

        records = (yield service.recordsWithRecordType(RecordType.group))
        self.assertEquals(
            set((record.uid for record in records)),
            set((
                "__calendar-dev__",
                "__twisted__",
            ))
        )


    @inlineCallbacks
    def test_recordWithShortName(self):
        service = self._testService()

        record = (yield service.recordWithShortName(RecordType.user, "wsanchez"))
        self.assertEquals(record.uid, "__wsanchez__")

        record = (yield service.recordWithShortName(RecordType.user, "wilfredo_sanchez"))
        self.assertEquals(record.uid, "__wsanchez__")


    @inlineCallbacks
    def test_recordsWithEmailAddress(self):
        service = self._testService()

        records = (yield service.recordsWithEmailAddress("wsanchez@bitbucket.calendarserver.org"))
        self.assertEquals(
            set((record.uid for record in records)),
            set(("__wsanchez__",)),
        )

        records = (yield service.recordsWithEmailAddress("wsanchez@devnull.twistedmatrix.com"))
        self.assertEquals(
            set((record.uid for record in records)),
            set(("__wsanchez__",)),
        )

        records = (yield service.recordsWithEmailAddress("shared@example.com"))
        self.assertEquals(
            set((record.uid for record in records)),
            set(("__sagen__", "__dre__")),
        )


    def test_unknownRecordTypes(self):
        service = self._testService()
        service.loadRecords()
        self.assertEquals(set(service.unknownRecordTypes), set())


    def test_unknownFieldElements(self):
        service = self._testService()
        service.loadRecords()
        self.assertEquals(set(service.unknownFieldElements), set())


    def test_unknownFieldNames(self):
        service = self._testService()
        service.loadRecords()
        self.assertEquals(set(service.unknownFieldNames), set())



class DirectoryRecordTest(BaseTest, test_directory.DirectoryRecordTest):
    @inlineCallbacks
    def test_members(self):
        service = self._testService()

        wsanchez = (yield service.recordWithUID("__wsanchez__"))
        members = (yield wsanchez.members())
        self.assertEquals(set(members), set())

        wsanchez = (yield service.recordWithUID("__twisted__"))
        members = (yield wsanchez.members())
        self.assertEquals(
            set(members),
            set((
                "__wsanchez__",
                "__glyph__",
                "__exarkun__",
                "__dreid__",
                "__dre__",
            ))
        )

    test_members.todo = "No worky."
