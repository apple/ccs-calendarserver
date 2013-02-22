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
Generic directory service base implementation tests
"""

from zope.interface.verify import verifyObject, BrokenMethodImplementation

from twisted.trial import unittest
from twisted.trial.unittest import SkipTest
from twisted.internet.defer import inlineCallbacks

from twext.who.idirectory import QueryNotSupportedError
from twext.who.idirectory import RecordType, FieldName
from twext.who.idirectory import IDirectoryService, IDirectoryRecord
from twext.who.directory import DirectoryService, DirectoryRecord



class BaseTest(unittest.TestCase):
    realmName = "xyzzy"


    def service(self):
        if not hasattr(self, "_service"):
            self._service = DirectoryService(self.realmName)
        return self._service



class DirectoryServiceTest(BaseTest):
    def test_interface(self):
        service = self.service()
        try:
            verifyObject(IDirectoryService, service)
        except BrokenMethodImplementation as e:
            self.fail(e)


    def test_init(self):
        service = self.service()
        self.assertEquals(service.realmName, self.realmName)


    def test_repr(self):
        service = self.service()
        self.assertEquals(repr(service), "<DirectoryService 'xyzzy'>")


    def test_recordTypes(self):
        service = self.service()
        self.assertEquals(
            set(service.recordTypes()),
            set(service.recordType.iterconstants())
        )


    @inlineCallbacks
    def test_recordsFromQueryNone(self):
        service = self.service()
        records = (yield service.recordsFromQuery(()))
        for record in records:
            self.failTest("No records expected")


    def test_recordsFromQueryBogus(self):
        service = self.service()
        self.assertFailure(service.recordsFromQuery((object(),)), QueryNotSupportedError)


    def test_recordWithUID(self):
        raise SkipTest("Subclasses should implement this test.")

    def test_recordWithGUID(self):
        raise SkipTest("Subclasses should implement this test.")

    def test_recordsWithRecordType(self):
        raise SkipTest("Subclasses should implement this test.")

    def test_recordWithShortName(self):
        raise SkipTest("Subclasses should implement this test.")

    def test_recordsWithEmailAddress(self):
        raise SkipTest("Subclasses should implement this test.")



class DirectoryRecordTest(BaseTest):
    fields_wsanchez = {
        FieldName.uid:            "UID:wsanchez",
        FieldName.recordType:     RecordType.user,
        FieldName.shortNames:     ("wsanchez", "wilfredo_sanchez"),
        FieldName.fullNames:      ("Wilfredo Sanchez", "Wilfredo Sanchez Vega"),
        FieldName.emailAddresses: ("wsanchez@calendarserver.org", "wsanchez@example.com")
    }

    fields_glyph = {
        FieldName.uid:            "UID:glyph",
        FieldName.recordType:     RecordType.user,
        FieldName.shortNames:     ("glyph",),
        FieldName.fullNames:      ("Glyph Lefkowitz",),
        FieldName.emailAddresses: ("glyph@calendarserver.org",)
    }

    fields_sagen = {
        FieldName.uid:            "UID:sagen",
        FieldName.recordType:     RecordType.user,
        FieldName.shortNames:     ("sagen",),
        FieldName.fullNames:      ("Morgen Sagen",),
        FieldName.emailAddresses: ("sagen@CalendarServer.org",)
    }


    def _testRecord(self, fields=None, service=None):
        if fields is None:
            fields = self.fields_wsanchez
        if service is None:
            service = self.service()
        return DirectoryRecord(service, fields)


    def test_interface(self):
        record = self._testRecord()
        try:
            verifyObject(IDirectoryRecord, record)
        except BrokenMethodImplementation as e:
            self.fail(e)


    def test_init(self):
        service  = self.service()
        wsanchez = self._testRecord(self.fields_wsanchez, service=service)

        self.assertEquals(wsanchez.service, service)
        self.assertEquals(wsanchez.fields , self.fields_wsanchez)


    def test_initWithNoUID(self):
        fields = self.fields_wsanchez.copy()
        del fields[FieldName.uid]
        self.assertRaises(ValueError, self._testRecord, fields)

        fields = self.fields_wsanchez.copy()
        fields[FieldName.uid] = ""
        self.assertRaises(ValueError, self._testRecord, fields)


    def test_initWithNoRecordType(self):
        fields = self.fields_wsanchez.copy()
        del fields[FieldName.recordType]
        self.assertRaises(ValueError, self._testRecord, fields)

        fields = self.fields_wsanchez.copy()
        fields[FieldName.recordType] = ""
        self.assertRaises(ValueError, self._testRecord, fields)


    def test_initWithNoShortNames(self):
        fields = self.fields_wsanchez.copy()
        del fields[FieldName.shortNames]
        self.assertRaises(ValueError, self._testRecord, fields)

        fields = self.fields_wsanchez.copy()
        fields[FieldName.shortNames] = ()
        self.assertRaises(ValueError, self._testRecord, fields)

        fields = self.fields_wsanchez.copy()
        fields[FieldName.shortNames] = ("",)
        self.assertRaises(ValueError, self._testRecord, fields)

        fields = self.fields_wsanchez.copy()
        fields[FieldName.shortNames] = ("wsanchez", "")
        self.assertRaises(ValueError, self._testRecord, fields)


    def test_initWithBogusRecordType(self):
        fields = self.fields_wsanchez.copy()
        fields[FieldName.recordType] = object()
        self.assertRaises(ValueError, self._testRecord, fields)


    def test_initNormalize(self):
        sagen = self._testRecord(self.fields_sagen)

        self.assertEquals(
            sagen.fields[FieldName.emailAddresses],
            ("sagen@calendarserver.org",)
        )


    def test_compare(self):
        fields_glyphmod = self.fields_glyph.copy()
        del fields_glyphmod[FieldName.emailAddresses]

        wsanchez    = self._testRecord(self.fields_wsanchez)
        wsanchezmod = self._testRecord(self.fields_wsanchez, DirectoryService("plugh"))
        glyph       = self._testRecord(self.fields_glyph)
        glyphmod    = self._testRecord(fields_glyphmod)

        self.assertEquals(wsanchez, wsanchez)
        self.assertNotEqual(wsanchez, glyph)
        self.assertNotEqual(glyph, glyphmod) # UID matches, other fields do not
        self.assertNotEqual(glyphmod, wsanchez)
        self.assertNotEqual(wsanchez, wsanchezmod) # Different service


    def test_attributeAccess(self):
        wsanchez = self._testRecord(self.fields_wsanchez)

        self.assertEquals(wsanchez.recordType    , wsanchez.fields[FieldName.recordType    ])
        self.assertEquals(wsanchez.uid           , wsanchez.fields[FieldName.uid           ])
        self.assertEquals(wsanchez.shortNames    , wsanchez.fields[FieldName.shortNames    ])
        self.assertEquals(wsanchez.emailAddresses, wsanchez.fields[FieldName.emailAddresses])

    @inlineCallbacks
    def test_members(self):
        wsanchez = self._testRecord(self.fields_wsanchez)

        self.assertEquals(
            set((yield wsanchez.members())),
            set()
        )

        raise SkipTest("Subclasses should implement this test.")

    def test_groups(self):
        raise SkipTest("Subclasses should implement this test.")
