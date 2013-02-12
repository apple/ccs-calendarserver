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

from time import sleep

from twisted.python.filepath import FilePath
from twisted.internet.defer import inlineCallbacks

from twext.who.idirectory import NoSuchRecordError
from twext.who.idirectory import DirectoryQueryMatchExpression
from twext.who.idirectory import Operand, QueryFlags
from twext.who.xml import ParseError
from twext.who.xml import DirectoryService, DirectoryRecord

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

  <record>
    <uid>__alyssa__</uid>
    <short-name>alyssa</short-name>
    <full-name>Alyssa P. Hacker</full-name>
    <password>assyla</password>
    <email>alyssa@example.com</email>
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

  <record type="group">
    <uid>__developers__</uid>
    <short-name>developers</short-name>
    <full-name>All Developers</full-name>
    <member-uid>__calendar-dev__</member-uid>
    <member-uid>__twisted__</member-uid>
    <member-uid>__alyssa__</member-uid>
  </record>

</directory>
"""



class BaseTest(object):
    def _testService(self, xmlData=None):
        if not hasattr(self, "_service"):
            if xmlData is None:
                xmlData = testXMLConfig

            filePath = FilePath(self.mktemp())
            filePath.setContent(xmlData)

            self._service = DirectoryService(filePath)

        return self._service



class DirectoryServiceTest(BaseTest, test_directory.DirectoryServiceTest):
    def test_repr(self):
        service = self._testService()

        self.assertEquals(repr(service), "<DirectoryService (not loaded)>")
        service.loadRecords()
        self.assertEquals(repr(service), "<DirectoryService 'xyzzy'>")


    def test_realmNameImmutable(self):
        def setRealmName():
            service = self._testService()
            service.realmName = "foo"

        self.assertRaises(AssertionError, setRealmName)


    def test_reloadInterval(self):
        service = self._testService()

        service.loadRecords(stat=False)
        lastRefresh = service._lastRefresh
        self.assertTrue(service._lastRefresh)

        sleep(1)
        service.loadRecords(stat=False)
        self.assertEquals(lastRefresh, service._lastRefresh)


    def test_reloadStat(self):
        service = self._testService()

        service.loadRecords(loadNow=True)
        lastRefresh = service._lastRefresh
        self.assertTrue(service._lastRefresh)

        sleep(1)
        service.loadRecords(loadNow=True)
        self.assertEquals(lastRefresh, service._lastRefresh)


    def test_badXML(self):
        service = self._testService(xmlData="Hello")

        self.assertRaises(ParseError, service.loadRecords)


    def test_badRootElement(self):
        service = self._testService(xmlData=
"""<?xml version="1.0" encoding="utf-8"?>

<frobnitz />
"""
        )

        self.assertRaises(ParseError, service.loadRecords)
        try:
            service.loadRecords()
        except ParseError as e:
            self.assertTrue(str(e).startswith("Incorrect root element"), e)
        else:
            raise AssertionError


    def test_noRealmName(self):
        service = self._testService(xmlData=
"""<?xml version="1.0" encoding="utf-8"?>

<directory />
"""
        )

        self.assertRaises(ParseError, service.loadRecords)
        try:
            service.loadRecords()
        except ParseError as e:
            self.assertTrue(str(e).startswith("No realm name"), e)
        else:
            raise AssertionError


    @inlineCallbacks
    def test_recordWithUID(self):
        service = self._testService()

        record = (yield service.recordWithUID("__null__"))
        self.assertEquals(record, None)

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

        records = (yield service.recordsWithRecordType(object()))
        self.assertEquals(set(records), set())

        records = (yield service.recordsWithRecordType(service.recordType.user))
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
                "__alyssa__",
                "__joe__",
            )),
        )

        records = (yield service.recordsWithRecordType(service.recordType.group))
        self.assertEquals(
            set((record.uid for record in records)),
            set((
                "__calendar-dev__",
                "__twisted__",
                "__developers__",
            ))
        )


    @inlineCallbacks
    def test_recordWithShortName(self):
        service = self._testService()

        record = (yield service.recordWithShortName(service.recordType.user, "null"))
        self.assertEquals(record, None)

        record = (yield service.recordWithShortName(service.recordType.user, "wsanchez"))
        self.assertEquals(record.uid, "__wsanchez__")

        record = (yield service.recordWithShortName(service.recordType.user, "wilfredo_sanchez"))
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


    @inlineCallbacks
    def test_queryAnd(self):
        service = self._testService()
        records = yield service.recordsFromQuery(
            (
                DirectoryQueryMatchExpression(
                    service.fieldName.emailAddresses,
                    "shared@example.com",
                ),
                DirectoryQueryMatchExpression(
                    service.fieldName.shortNames,
                    "sagen",
                ),
            ),
            operand=Operand.AND
        )
        self.assertEquals(
            set((record.uid for record in records)),
            set(("__sagen__",)),
        )


    @inlineCallbacks
    def test_queryOr(self):
        service = self._testService()
        records = yield service.recordsFromQuery(
            (
                DirectoryQueryMatchExpression(
                    service.fieldName.emailAddresses,
                    "shared@example.com",
                ),
                DirectoryQueryMatchExpression(
                    service.fieldName.shortNames,
                    "wsanchez",
                ),
            ),
            operand=Operand.OR
        )
        self.assertEquals(
            set((record.uid for record in records)),
            set(("__sagen__", "__dre__", "__wsanchez__")),
        )


    @inlineCallbacks
    def test_queryNot(self):
        service = self._testService()
        records = yield service.recordsFromQuery(
            (
                DirectoryQueryMatchExpression(
                    service.fieldName.emailAddresses,
                    "shared@example.com",
                ),
                DirectoryQueryMatchExpression(
                    service.fieldName.shortNames,
                    "sagen",
                    flags = QueryFlags.NOT,
                ),
            ),
            operand=Operand.AND
        )
        self.assertEquals(
            set((record.uid for record in records)),
            set(("__dre__",)),
        )

    test_queryNot.todo = "Not implemented."


    @inlineCallbacks
    def test_queryCaseInsensitive(self):
        service = self._testService()
        records = yield service.recordsFromQuery(
            (
                DirectoryQueryMatchExpression(
                    service.fieldName.shortNames,
                    "SagEn",
                    flags = QueryFlags.caseInsensitive,
                ),
            ),
        )
        self.assertEquals(
            set((record.uid for record in records)),
            set(("__sagen__",)),
        )

    test_queryCaseInsensitive.todo = "Not implemented."


    def test_unknownRecordTypesClean(self):
        service = self._testService()
        self.assertEquals(set(service.unknownRecordTypes), set())


    def test_unknownRecordTypesDirty(self):
        service = self._testService(xmlData=
"""<?xml version="1.0" encoding="utf-8"?>

<directory realm="Unknown Record Types">
  <record type="camera">
    <uid>__d600__</uid>
    <short-name>d600</short-name>
    <full-name>Nikon D600</full-name>
  </record>
</directory>
"""
        )
        self.assertEquals(set(service.unknownRecordTypes), set(("camera",)))


    def test_unknownFieldElementsClean(self):
        service = self._testService()
        self.assertEquals(set(service.unknownFieldElements), set())


    def test_unknownFieldElementsDirty(self):
        service = self._testService(xmlData=
"""<?xml version="1.0" encoding="utf-8"?>

<directory realm="Unknown Record Types">
  <record type="user">
    <uid>__wsanchez__</uid>
    <short-name>wsanchez</short-name>
    <political-affiliation>Community and Freedom Party</political-affiliation>
  </record>
</directory>
"""
        )
        self.assertEquals(set(service.unknownFieldElements), set(("political-affiliation",)))


    @inlineCallbacks
    def test_updateRecord(self):
        service = self._testService()

        record = (yield service.recordWithUID("__wsanchez__"))

        fields = record.fields.copy()
        fields[service.fieldName.fullNames] = ["Wilfredo Sanchez Vega"]

        updatedRecord = DirectoryRecord(service, fields)
        yield service.updateRecords((updatedRecord,))

        # Verify change is present immediately
        record = (yield service.recordWithUID("__wsanchez__"))
        self.assertEquals(set(record.fullNames), set(("Wilfredo Sanchez Vega",)))

        # Verify change is persisted
        service.flush()
        record = (yield service.recordWithUID("__wsanchez__"))
        self.assertEquals(set(record.fullNames), set(("Wilfredo Sanchez Vega",)))


    @inlineCallbacks
    def test_addRecord(self):
        service = self._testService()

        newRecord = DirectoryRecord(
            service,
            fields = {
                service.fieldName.uid:        "__plugh__",
                service.fieldName.recordType: service.recordType.user,
                service.fieldName.shortNames: ("plugh",),
            }
        )

        yield service.updateRecords((newRecord,), create=True)

        # Verify change is present immediately
        record = (yield service.recordWithUID("__plugh__"))
        self.assertEquals(set(record.shortNames), set(("plugh",)))

        # Verify change is persisted
        service.flush()
        record = (yield service.recordWithUID("__plugh__"))
        self.assertEquals(set(record.shortNames), set(("plugh",)))


    def test_addRecordNoCreate(self):
        service = self._testService()

        newRecord = DirectoryRecord(
            service,
            fields = {
                service.fieldName.uid:        "__plugh__",
                service.fieldName.recordType: service.recordType.user,
                service.fieldName.shortNames: ("plugh",),
            }
        )

        self.assertFailure(service.updateRecords((newRecord,)), NoSuchRecordError)


    @inlineCallbacks
    def test_removeRecord(self):
        service = self._testService()

        yield service.removeRecords(("__wsanchez__",))

        # Verify change is present immediately
        self.assertEquals((yield service.recordWithUID("__wsanchez__")), None)

        # Verify change is persisted
        service.flush()
        self.assertEquals((yield service.recordWithUID("__wsanchez__")), None)


    def test_removeRecordNoExist(self):
        service = self._testService()

        return service.removeRecords(("__plugh__",))



class DirectoryRecordTest(BaseTest, test_directory.DirectoryRecordTest):
    @inlineCallbacks
    def test_members(self):
        service = self._testService()

        record = (yield service.recordWithUID("__wsanchez__"))
        members = (yield record.members())
        self.assertEquals(set(members), set())

        record = (yield service.recordWithUID("__twisted__"))
        members = (yield record.members())
        self.assertEquals(
            set((member.uid for member in members)),
            set((
                "__wsanchez__",
                "__glyph__",
                "__exarkun__",
                "__dreid__",
                "__dre__",
            ))
        )

        record = (yield service.recordWithUID("__developers__"))
        members = (yield record.members())
        self.assertEquals(
            set((member.uid for member in members)),
            set((
                "__calendar-dev__",
                "__twisted__",
                "__alyssa__",
            ))
        )

    @inlineCallbacks
    def test_groups(self):
        service = self._testService()

        record = (yield service.recordWithUID("__wsanchez__"))
        groups = (yield record.groups())
        self.assertEquals(
            set(group.uid for group in groups),
            set((
                "__calendar-dev__",
                "__twisted__",
            ))
        )
