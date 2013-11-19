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
XML directory service tests.
"""

from time import sleep
from uuid import UUID
from textwrap import dedent

from twisted.trial import unittest
from twisted.python.filepath import FilePath
from twisted.internet.defer import inlineCallbacks

from twext.who.idirectory import NoSuchRecordError
from twext.who.expression import CompoundExpression, Operand
from twext.who.expression import MatchExpression, MatchType, MatchFlags
from twext.who.xml import ParseError
from twext.who.xml import DirectoryService, DirectoryRecord

from twext.who.test import test_index



class BaseTest(object):
    def service(self, xmlData=None):
        return xmlService(self.mktemp(), xmlData)


    def assertRecords(self, records, uids):
        self.assertEquals(
            frozenset((record.uid for record in records)),
            frozenset((uids)),
        )



class DirectoryServiceTest(
    unittest.TestCase,
    BaseTest,
    test_index.BaseDirectoryServiceTest,
):
    serviceClass = DirectoryService
    directoryRecordClass = DirectoryRecord

    def test_repr(self):
        service = self.service()

        self.assertEquals(repr(service), "<TestService (not loaded)>")
        service.loadRecords()
        self.assertEquals(repr(service), "<TestService u'xyzzy'>")


    @inlineCallbacks
    def test_recordWithUID(self):
        service = self.service()

        record = (yield service.recordWithUID(u"__null__"))
        self.assertEquals(record, None)

        record = (yield service.recordWithUID(u"__wsanchez__"))
        self.assertEquals(record.uid, u"__wsanchez__")


    @inlineCallbacks
    def test_recordWithGUID(self):
        service = self.service()
        record = (
            yield service.recordWithGUID(
                UUID("6C495FCD-7E78-4D5C-AA66-BC890AD04C9D")
            )
        )
        self.assertEquals(record, None)

    @inlineCallbacks
    def test_recordsWithRecordType(self):
        service = self.service()

        records = (yield service.recordsWithRecordType(object()))
        self.assertEquals(set(records), set())

        records = (
            yield service.recordsWithRecordType(service.recordType.user)
        )
        self.assertRecords(
            records,
            (
                u"__wsanchez__",
                u"__glyph__",
                u"__sagen__",
                u"__cdaboo__",
                u"__dre__",
                u"__exarkun__",
                u"__dreid__",
                u"__alyssa__",
                u"__joe__",
            ),
        )

        records = (
            yield service.recordsWithRecordType(service.recordType.group)
        )
        self.assertRecords(
            records,
            (
                u"__calendar-dev__",
                u"__twisted__",
                u"__developers__",
            ),
        )


    @inlineCallbacks
    def test_recordWithShortName(self):
        service = self.service()

        record = (
            yield service.recordWithShortName(
                service.recordType.user,
                u"null",
            )
        )
        self.assertEquals(record, None)

        record = (
            yield service.recordWithShortName(
                service.recordType.user,
                u"wsanchez",
            )
        )
        self.assertEquals(record.uid, u"__wsanchez__")

        record = (
            yield service.recordWithShortName(
                service.recordType.user,
                u"wilfredo_sanchez",
            )
        )
        self.assertEquals(record.uid, u"__wsanchez__")


    @inlineCallbacks
    def test_recordsWithEmailAddress(self):
        service = self.service()

        records = (
            yield service.recordsWithEmailAddress(
                u"wsanchez@bitbucket.calendarserver.org"
            )
        )
        self.assertRecords(records, (u"__wsanchez__",))

        records = (
            yield service.recordsWithEmailAddress(
                u"wsanchez@devnull.twistedmatrix.com"
            )
        )
        self.assertRecords(records, (u"__wsanchez__",))

        records = (
            yield service.recordsWithEmailAddress(
                u"shared@example.com"
            )
        )
        self.assertRecords(records, (u"__sagen__", u"__dre__"))



class DirectoryServiceRealmTest(unittest.TestCase, BaseTest):
    def test_realmNameImmutable(self):
        def setRealmName():
            service = self.service()
            service.realmName = u"foo"

        self.assertRaises(AssertionError, setRealmName)



class DirectoryServiceParsingTest(unittest.TestCase, BaseTest):
    def test_reloadInterval(self):
        service = self.service()

        service.loadRecords(stat=False)
        lastRefresh = service._lastRefresh
        self.assertTrue(service._lastRefresh)

        sleep(1)
        service.loadRecords(stat=False)
        self.assertEquals(lastRefresh, service._lastRefresh)


    def test_reloadStat(self):
        service = self.service()

        service.loadRecords(loadNow=True)
        lastRefresh = service._lastRefresh
        self.assertTrue(service._lastRefresh)

        sleep(1)
        service.loadRecords(loadNow=True)
        self.assertEquals(lastRefresh, service._lastRefresh)


    def test_badXML(self):
        service = self.service(xmlData="Hello")

        self.assertRaises(ParseError, service.loadRecords)


    def test_badRootElement(self):
        service = self.service(xmlData=(dedent(
            b"""
            <?xml version="1.0" encoding="utf-8"?>

            <frobnitz />
            """[1:]
        )))

        self.assertRaises(ParseError, service.loadRecords)
        try:
            service.loadRecords()
        except ParseError as e:
            self.assertTrue(str(e).startswith("Incorrect root element"), e)
        else:
            raise AssertionError("Expected ParseError")


    def test_noRealmName(self):
        service = self.service(xmlData=(dedent(
            b"""
            <?xml version="1.0" encoding="utf-8"?>

            <directory />
            """[1:]
        )))

        self.assertRaises(ParseError, service.loadRecords)
        try:
            service.loadRecords()
        except ParseError as e:
            self.assertTrue(str(e).startswith("No realm name"), e)
        else:
            raise AssertionError("Expected ParseError")


    def test_unknownFieldElementsClean(self):
        service = self.service()
        self.assertEquals(set(service.unknownFieldElements), set())


    def test_unknownFieldElementsDirty(self):
        service = self.service(xmlData=(dedent(
            b"""
            <?xml version="1.0" encoding="utf-8"?>

            <directory realm="Unknown Record Types">
              <record type="user">
                <uid>__wsanchez__</uid>
                <short-name>wsanchez</short-name>
                <political-affiliation>Community and Freedom Party</political-affiliation>
              </record>
            </directory>
            """[1:]
        )))
        self.assertEquals(
            set(service.unknownFieldElements),
            set((u"political-affiliation",))
        )


    def test_unknownRecordTypesClean(self):
        service = self.service()
        self.assertEquals(set(service.unknownRecordTypes), set())


    def test_unknownRecordTypesDirty(self):
        service = self.service(xmlData=(dedent(
            b"""
            <?xml version="1.0" encoding="utf-8"?>

            <directory realm="Unknown Record Types">
              <record type="camera">
                <uid>__d600__</uid>
                <short-name>d600</short-name>
                <full-name>Nikon D600</full-name>
              </record>
            </directory>
            """[1:]
        )))
        self.assertEquals(set(service.unknownRecordTypes), set((u"camera",)))



class DirectoryServiceQueryTest(unittest.TestCase, BaseTest):
    @inlineCallbacks
    def test_queryAnd(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            CompoundExpression(
                (
                    service.query(u"emailAddresses", u"shared@example.com"),
                    service.query(u"shortNames", u"sagen"),
                ),
                operand=Operand.AND
            )
        )
        self.assertRecords(records, (u"__sagen__",))


    @inlineCallbacks
    def test_queryAndNoneFirst(self):
        """
        Test optimized case, where first expression yields no results.
        """
        service = self.service()
        records = yield service.recordsFromExpression(
            CompoundExpression(
                (
                    service.query(u"emailAddresses", u"nobody@example.com"),
                    service.query(u"shortNames", u"sagen"),
                ),
                operand=Operand.AND
            )
        )
        self.assertRecords(records, ())


    @inlineCallbacks
    def test_queryOr(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            CompoundExpression(
                (
                    service.query(u"emailAddresses", u"shared@example.com"),
                    service.query(u"shortNames", u"wsanchez"),
                ),
                operand=Operand.OR
            )
        )
        self.assertRecords(
            records,
            (u"__sagen__", u"__dre__", u"__wsanchez__")
        )


    @inlineCallbacks
    def test_queryNot(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            CompoundExpression(
                (
                    service.query(
                        u"emailAddresses", u"shared@example.com"
                    ),
                    service.query(
                        u"shortNames", u"sagen",
                        flags=MatchFlags.NOT
                    ),
                ),
                operand=Operand.AND
            )
        )
        self.assertRecords(records, (u"__dre__",))


    @inlineCallbacks
    def test_queryNotNoIndex(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            CompoundExpression(
                (
                    service.query(u"emailAddresses", u"shared@example.com"),
                    service.query(
                        u"fullNames", u"Andre LaBranche",
                        flags=MatchFlags.NOT
                    ),
                ),
                operand=Operand.AND
            )
        )
        self.assertRecords(records, (u"__sagen__",))


    @inlineCallbacks
    def test_queryCaseInsensitive(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"shortNames", u"SagEn",
                flags=MatchFlags.caseInsensitive
            )
        )
        self.assertRecords(records, (u"__sagen__",))


    @inlineCallbacks
    def test_queryCaseInsensitiveNoIndex(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"fullNames", u"moRGen SAGen",
                flags=MatchFlags.caseInsensitive
            )
        )
        self.assertRecords(records, (u"__sagen__",))


    @inlineCallbacks
    def test_queryStartsWith(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"shortNames", u"wil",
                matchType=MatchType.startsWith
            )
        )
        self.assertRecords(records, (u"__wsanchez__",))


    @inlineCallbacks
    def test_queryStartsWithNoIndex(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"fullNames", u"Wilfredo",
                matchType=MatchType.startsWith
            )
        )
        self.assertRecords(records, (u"__wsanchez__",))


    @inlineCallbacks
    def test_queryStartsWithNot(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"shortNames", u"w",
                matchType=MatchType.startsWith,
                flags=MatchFlags.NOT,
            )
        )
        self.assertRecords(
            records,
            (
                u"__alyssa__",
                u"__calendar-dev__",
                u"__cdaboo__",
                u"__developers__",
                u"__dre__",
                u"__dreid__",
                u"__exarkun__",
                u"__glyph__",
                u"__joe__",
                u"__sagen__",
                u"__twisted__",
            ),
        )


    @inlineCallbacks
    def test_queryStartsWithNotAny(self):
        """
        FIXME?: In the this case, the record __wsanchez__ has two
        shortNames, and one doesn't match the query.  Should it be
        included or not?  It is, because one matches the query, but
        should NOT require that all match?
        """
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"shortNames", u"wil",
                matchType=MatchType.startsWith,
                flags=MatchFlags.NOT,
            )
        )
        self.assertRecords(
            records,
            (
                u"__alyssa__",
                u"__calendar-dev__",
                u"__cdaboo__",
                u"__developers__",
                u"__dre__",
                u"__dreid__",
                u"__exarkun__",
                u"__glyph__",
                u"__joe__",
                u"__sagen__",
                u"__twisted__",
                u"__wsanchez__",
            ),
        )


    @inlineCallbacks
    def test_queryStartsWithNotNoIndex(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"fullNames", u"Wilfredo",
                matchType=MatchType.startsWith,
                flags=MatchFlags.NOT,
            )
        )
        self.assertRecords(
            records,
            (
                u"__alyssa__",
                u"__calendar-dev__",
                u"__cdaboo__",
                u"__developers__",
                u"__dre__",
                u"__dreid__",
                u"__exarkun__",
                u"__glyph__",
                u"__joe__",
                u"__sagen__",
                u"__twisted__",
            ),
        )


    @inlineCallbacks
    def test_queryStartsWithCaseInsensitive(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"shortNames", u"WIL",
                matchType=MatchType.startsWith,
                flags=MatchFlags.caseInsensitive,
            )
        )
        self.assertRecords(records, (u"__wsanchez__",))


    @inlineCallbacks
    def test_queryStartsWithCaseInsensitiveNoIndex(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"fullNames", u"wilfrEdo",
                matchType=MatchType.startsWith,
                flags=MatchFlags.caseInsensitive,
            )
        )
        self.assertRecords(records, (u"__wsanchez__",))


    @inlineCallbacks
    def test_queryContains(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"shortNames", u"sanchez",
                matchType=MatchType.contains,
            )
        )
        self.assertRecords(records, (u"__wsanchez__",))


    @inlineCallbacks
    def test_queryContainsNoIndex(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"fullNames", u"fred",
                matchType=MatchType.contains,
            )
        )
        self.assertRecords(records, (u"__wsanchez__",))


    @inlineCallbacks
    def test_queryContainsNot(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"shortNames", u"sanchez",
                matchType=MatchType.contains,
                flags=MatchFlags.NOT,
            )
        )
        self.assertRecords(
            records,
            (
                u"__alyssa__",
                u"__calendar-dev__",
                u"__cdaboo__",
                u"__developers__",
                u"__dre__",
                u"__dreid__",
                u"__exarkun__",
                u"__glyph__",
                u"__joe__",
                u"__sagen__",
                u"__twisted__",
            ),
        )


    @inlineCallbacks
    def test_queryContainsNotNoIndex(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"fullNames", u"fred",
                matchType=MatchType.contains,
                flags=MatchFlags.NOT,
            )
        )
        self.assertRecords(
            records,
            (
                u"__alyssa__",
                u"__calendar-dev__",
                u"__cdaboo__",
                u"__developers__",
                u"__dre__",
                u"__dreid__",
                u"__exarkun__",
                u"__glyph__",
                u"__joe__",
                u"__sagen__",
                u"__twisted__",
            ),
        )


    @inlineCallbacks
    def test_queryContainsCaseInsensitive(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"shortNames", u"Sanchez",
                matchType=MatchType.contains,
                flags=MatchFlags.caseInsensitive,
            )
        )
        self.assertRecords(records, (u"__wsanchez__",))


    @inlineCallbacks
    def test_queryContainsCaseInsensitiveNoIndex(self):
        service = self.service()
        records = yield service.recordsFromExpression(
            service.query(
                u"fullNames", u"frEdo",
                matchType=MatchType.contains,
                flags=MatchFlags.caseInsensitive,
            )
        )
        self.assertRecords(records, (u"__wsanchez__",))



class DirectoryServiceMutableTest(unittest.TestCase, BaseTest):
    @inlineCallbacks
    def test_updateRecord(self):
        service = self.service()

        record = (yield service.recordWithUID(u"__wsanchez__"))

        fields = record.fields.copy()
        fields[service.fieldName.fullNames] = [u"Wilfredo Sanchez Vega"]

        updatedRecord = DirectoryRecord(service, fields)
        yield service.updateRecords((updatedRecord,))

        # Verify change is present immediately
        record = (yield service.recordWithUID(u"__wsanchez__"))
        self.assertEquals(
            set(record.fullNames),
            set((u"Wilfredo Sanchez Vega",))
        )

        # Verify change is persisted
        service.flush()
        record = (yield service.recordWithUID(u"__wsanchez__"))
        self.assertEquals(
            set(record.fullNames),
            set((u"Wilfredo Sanchez Vega",))
        )


    @inlineCallbacks
    def test_addRecord(self):
        service = self.service()

        newRecord = DirectoryRecord(
            service,
            fields={
                service.fieldName.uid: u"__plugh__",
                service.fieldName.recordType: service.recordType.user,
                service.fieldName.shortNames: (u"plugh",),
            }
        )

        yield service.updateRecords((newRecord,), create=True)

        # Verify change is present immediately
        record = (yield service.recordWithUID(u"__plugh__"))
        self.assertEquals(set(record.shortNames), set((u"plugh",)))

        # Verify change is persisted
        service.flush()
        record = (yield service.recordWithUID(u"__plugh__"))
        self.assertEquals(set(record.shortNames), set((u"plugh",)))


    def test_addRecordNoCreate(self):
        service = self.service()

        newRecord = DirectoryRecord(
            service,
            fields={
                service.fieldName.uid: u"__plugh__",
                service.fieldName.recordType: service.recordType.user,
                service.fieldName.shortNames: (u"plugh",),
            }
        )

        self.assertFailure(
            service.updateRecords((newRecord,)),
            NoSuchRecordError
        )


    @inlineCallbacks
    def test_removeRecord(self):
        service = self.service()

        yield service.removeRecords((u"__wsanchez__",))

        # Verify change is present immediately
        self.assertEquals((yield service.recordWithUID(u"__wsanchez__")), None)

        # Verify change is persisted
        service.flush()
        self.assertEquals((yield service.recordWithUID(u"__wsanchez__")), None)


    def test_removeRecordNoExist(self):
        service = self.service()

        return service.removeRecords((u"__plugh__",))



class DirectoryRecordTest(
    unittest.TestCase,
    BaseTest,
    test_index.BaseDirectoryRecordTest
):
    serviceClass = DirectoryService
    directoryRecordClass = DirectoryRecord

    @inlineCallbacks
    def test_members_group(self):
        service = self.service()

        record = (yield service.recordWithUID(u"__wsanchez__"))
        members = (yield record.members())
        self.assertEquals(set(members), set())

        record = (yield service.recordWithUID(u"__twisted__"))
        members = (yield record.members())
        self.assertEquals(
            set((member.uid for member in members)),
            set((
                u"__wsanchez__",
                u"__glyph__",
                u"__exarkun__",
                u"__dreid__",
                u"__dre__",
            ))
        )

        record = (yield service.recordWithUID(u"__developers__"))
        members = (yield record.members())
        self.assertEquals(
            set((member.uid for member in members)),
            set((
                u"__calendar-dev__",
                u"__twisted__",
                u"__alyssa__",
            ))
        )

    @inlineCallbacks
    def test_memberships(self):
        service = self.service()

        record = (yield service.recordWithUID(u"__wsanchez__"))
        groups = (yield record.groups())
        self.assertEquals(
            set(group.uid for group in groups),
            set((
                u"__calendar-dev__",
                u"__twisted__",
            ))
        )



class QueryMixIn(object):
    def query(self, field, value, matchType=MatchType.equals, flags=None):
        name = getattr(self.fieldName, field)
        assert name is not None
        return MatchExpression(
            name, value,
            matchType=matchType,
            flags=flags,
        )



class TestService(DirectoryService, QueryMixIn):
    pass



def xmlService(tmp, xmlData=None, serviceClass=None):
    if xmlData is None:
        xmlData = testXMLConfig

    if serviceClass is None:
        serviceClass = TestService

    filePath = FilePath(tmp)
    filePath.setContent(xmlData)

    return serviceClass(filePath)



testXMLConfig = b"""<?xml version="1.0" encoding="utf-8"?>

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

  <record> <!-- type defaults to "user" -->
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
