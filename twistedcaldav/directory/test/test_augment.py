##
# Copyright (c) 2009-2014 Apple Inc. All rights reserved.
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

from twistedcaldav.test.util import TestCase
from twistedcaldav.directory.augment import AugmentXMLDB, AugmentSqliteDB, \
    AugmentPostgreSQLDB, AugmentRecord
from twisted.internet.defer import inlineCallbacks
from twistedcaldav.directory.xmlaugmentsparser import XMLAugmentsParser
import cStringIO
import os
from twext.python.filepath import CachingFilePath as FilePath
from twistedcaldav.xmlutil import readXML
from twistedcaldav.directory import xmlaugmentsparser


xmlFile = os.path.join(os.path.dirname(__file__), "augments-test.xml")
xmlFileDefault = os.path.join(os.path.dirname(__file__), "augments-test-default.xml")
xmlFileNormalization = os.path.join(os.path.dirname(__file__), "augments-normalization.xml")

testRecords = (
    {"uid": "D11F03A0-97EA-48AF-9A6C-FAC7F3975766", "enabled": True, "enabledForCalendaring": False, "enabledForAddressBooks": False, "autoSchedule": False, "autoScheduleMode": "default"},
    {"uid": "6423F94A-6B76-4A3A-815B-D52CFD77935D", "enabled": True, "enabledForCalendaring": True, "enabledForAddressBooks": True, "autoSchedule": False, "autoScheduleMode": "default"},
    {"uid": "5A985493-EE2C-4665-94CF-4DFEA3A89500", "enabled": False, "enabledForCalendaring": False, "enabledForAddressBooks": False, "autoSchedule": False, "autoScheduleMode": "default"},
    {"uid": "8B4288F6-CC82-491D-8EF9-642EF4F3E7D0", "enabled": True, "enabledForCalendaring": False, "enabledForAddressBooks": False, "autoSchedule": False, "autoScheduleMode": "default"},
    {"uid": "5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1", "enabled": True, "enabledForCalendaring": False, "enabledForAddressBooks": False, "autoSchedule": False, "autoScheduleMode": "default"},
    {"uid": "543D28BA-F74F-4D5F-9243-B3E3A61171E5", "enabled": True, "enabledForCalendaring": False, "enabledForAddressBooks": False, "autoSchedule": False, "autoScheduleMode": "default"},
    {"uid": "6A73326A-F781-47E7-A9F8-AF47364D4152", "enabled": True, "enabledForCalendaring": True, "enabledForAddressBooks": True, "autoSchedule": True, "autoScheduleMode": "default"},
    {"uid": "C5BAADEE-6B35-4FD5-A98A-5DF6BBAAC47A", "enabled": True, "enabledForCalendaring": True, "enabledForAddressBooks": True, "autoSchedule": True, "autoScheduleMode": "default"},
    {"uid": "8AB34DF9-0297-4BA3-AADB-DB557DDD21E7", "enabled": True, "enabledForCalendaring": True, "enabledForAddressBooks": True, "autoSchedule": True, "autoScheduleMode": "accept-always"},
    {"uid": "FC674703-8008-4A77-B80E-0DB55A9CE620", "enabledForLogin": False, }, # Explicitly false
    {"uid": "B473DC32-1B0D-45EE-9BAC-DA878AE9CE74", "enabledForLogin": True, }, # Explicitly True
    {"uid": "9F2B176D-B3F5-483A-AA63-0A1FC6E6D54B", "enabledForLogin": True, }, # Default is True
)

testRecordWildcardDefault = (
    {"uid": "A4318887-F2C7-4A70-9056-B88CC8DB26F1", "enabled": True, "enabledForCalendaring": True, "enabledForAddressBooks": True, "autoSchedule": False, "autoScheduleMode": "default"},
    {"uid": "AA5F935F-3358-4510-A649-B391D63279F2", "enabled": True, "enabledForCalendaring": False, "enabledForAddressBooks": False, "autoSchedule": False, "autoScheduleMode": "default"},
    {"uid": "ABF1A83B-1A29-4E04-BDC3-A6A66ECF27CA", "enabled": False, "enabledForCalendaring": False, "enabledForAddressBooks": False, "autoSchedule": False, "autoScheduleMode": "default"},
    {"uid": "BC22A734-5E41-4FB7-B5C1-51DC0656DC2F", "enabled": True, "enabledForCalendaring": True, "enabledForAddressBooks": True, "autoSchedule": False, "autoScheduleMode": "default"},
    {"uid": "C6DEEBB1-E14A-47F2-98BA-7E3BB4353E3A", "enabled": True, "enabledForCalendaring": True, "enabledForAddressBooks": True, "autoSchedule": True, "autoScheduleMode": "accept-always"},
    {"uid": "AA859321-2C72-4974-ADCF-0CBA0C76F95D", "enabled": True, "enabledForCalendaring": False, "enabledForAddressBooks": False, "autoSchedule": False, "autoScheduleMode": "default"},
    {"uid": "AB7C488B-9ED2-4265-881C-7E2E38A63584", "enabled": False, "enabledForCalendaring": False, "enabledForAddressBooks": False, "autoSchedule": False, "autoScheduleMode": "default"},
    {"uid": "BB0C0DA1-0545-45F6-8D08-917C554D93A4", "enabled": True, "enabledForCalendaring": True, "enabledForAddressBooks": True, "autoSchedule": False, "autoScheduleMode": "default"},
    {"uid": "CCD30AD3-582F-4682-8B65-2EDE92C5656E", "enabled": True, "enabledForCalendaring": True, "enabledForAddressBooks": True, "autoSchedule": True, "autoScheduleMode": "accept-always"},
)

testRecordTypeDefault = (
    ("locations", {"uid": "A4318887-F2C7-4A70-9056-B88CC8DB26F1", "enabled": True, "enabledForCalendaring": True, "enabledForAddressBooks": False, "autoSchedule": True, "autoScheduleMode": "default"}),
    ("locations", {"uid": "AA5F935F-3358-4510-A649-B391D63279F2", "enabled": True, "enabledForCalendaring": True, "enabledForAddressBooks": False, "autoSchedule": True, "autoScheduleMode": "default"}),
    ("resources", {"uid": "A5318887-F2C7-4A70-9056-B88CC8DB26F1", "enabled": True, "enabledForCalendaring": True, "enabledForAddressBooks": False, "autoSchedule": True, "autoScheduleMode": "default"}),
    ("resources", {"uid": "AA6F935F-3358-4510-A649-B391D63279F2", "enabled": True, "enabledForCalendaring": True, "enabledForAddressBooks": False, "autoSchedule": True, "autoScheduleMode": "default"}),
)


testAddRecords = (
    {"uid": "D11F03A0-97EA-48AF-9A6C-FAC7F3975767", "enabled": True, "enabledForCalendaring": False, "enabledForAddressBooks": False, "autoSchedule": False, "autoScheduleMode": "default"},
)

testModifyRecords = (
    {"uid": "D11F03A0-97EA-48AF-9A6C-FAC7F3975767", "enabled": True, "enabledForCalendaring": True, "enabledForAddressBooks": True, "autoSchedule": False, "autoScheduleMode": "default"},
)


class AugmentTests(TestCase):

    @inlineCallbacks
    def _checkRecord(self, db, items, recordType="users"):

        record = (yield db.getAugmentRecord(items["uid"], recordType))
        self.assertTrue(record is not None, "Failed record uid: %s" % (items["uid"],))

        for k, v in items.iteritems():
            self.assertEqual(getattr(record, k), v, "Failed record uid: %s, attribute: %s" % (items["uid"], k,))


    @inlineCallbacks
    def _checkRecordExists(self, db, uid, recordType="users"):

        record = (yield db.getAugmentRecord(uid, recordType))
        self.assertTrue(record is not None, "Failed record uid: %s" % (uid,))



class AugmentTestsMixin(object):

    def _db(self, dbpath=None):
        raise NotImplementedError


    @inlineCallbacks
    def test_read(self):

        dbpath = os.path.abspath(self.mktemp())
        db = self._db(dbpath)

        dbxml = AugmentXMLDB((xmlFile,))
        yield db.addAugmentRecords(dbxml.db.values())

        for item in testRecords:
            yield self._checkRecord(db, item)

        # Verify that a default record is returned, even if not specified
        # in the DB
        yield self._checkRecordExists(db, "D11F03A0-97EA-48AF-9A6C-FAC7F3975767")


    @inlineCallbacks
    def test_read_default(self):

        dbpath = os.path.abspath(self.mktemp())
        db = self._db(dbpath)

        dbxml = AugmentXMLDB((xmlFileDefault,))
        yield db.addAugmentRecords(dbxml.db.values())

        for item in testRecords:
            yield self._checkRecord(db, item)

        for item in testRecordWildcardDefault:
            yield self._checkRecord(db, item)

        # Do a second time to test caching
        for item in testRecordWildcardDefault:
            yield self._checkRecord(db, item)


    @inlineCallbacks
    def test_read_typed_default(self):
        """
        Augments key ("uid" element in xml) can be any of the following, in
        this order of precedence:

        full uid
        <recordType>-XX*
        <recordType>-X*
        XX*
        X*
        <recordType>-Default
        Default
        """

        dbpath = os.path.abspath(self.mktemp())
        db = self._db(dbpath)

        dbxml = AugmentXMLDB((xmlFileDefault,))
        yield db.addAugmentRecords(dbxml.db.values())

        for recordType, item in testRecordTypeDefault:
            yield self._checkRecord(db, item, recordType)


    @inlineCallbacks
    def test_add_modify(self):

        dbpath = os.path.abspath(self.mktemp())
        db = self._db(dbpath)

        dbxml = AugmentXMLDB((xmlFile,))
        yield db.addAugmentRecords(dbxml.db.values())

        for item in testRecords:
            yield self._checkRecord(db, item)

        # Verify that a default record is returned, even if not specified
        # in the DB
        yield self._checkRecordExists(db, "D11F03A0-97EA-48AF-9A6C-FAC7F3975767")

        newrecord = AugmentRecord(
            **testAddRecords[0]
        )
        yield db.addAugmentRecords((newrecord,))

        newdb = self._db(dbpath)

        for item in testRecords:
            yield self._checkRecord(newdb, item)
        yield self._checkRecord(newdb, testAddRecords[0])

        newrecord = AugmentRecord(
            **testModifyRecords[0]
        )
        yield db.addAugmentRecords((newrecord,))

        newdb = self._db(dbpath)

        for item in testRecords:
            yield self._checkRecord(newdb, item)
        yield self._checkRecord(newdb, testModifyRecords[0])



class AugmentXMLTests(AugmentTests):

    @inlineCallbacks
    def test_read(self):

        db = AugmentXMLDB((xmlFile,))

        for item in testRecords:
            yield self._checkRecord(db, item)

        # Verify that a default record is returned, even if not specified
        # in the DB
        yield self._checkRecordExists(db, "D11F03A0-97EA-48AF-9A6C-FAC7F3975767")


    @inlineCallbacks
    def test_read_default(self):

        db = AugmentXMLDB((xmlFileDefault,))

        for item in testRecords:
            yield self._checkRecord(db, item)

        for item in testRecordWildcardDefault:
            yield self._checkRecord(db, item)


    def test_parseErrors(self):

        db = {}
        self.assertRaises(RuntimeError, XMLAugmentsParser, cStringIO.StringIO(""), db)
        self.assertRaises(RuntimeError, XMLAugmentsParser, cStringIO.StringIO("""<?xml version="1.0" encoding="utf-8"?>
<accounts>
    <foo/>
</accounts>
"""), db)
        self.assertRaises(RuntimeError, XMLAugmentsParser, cStringIO.StringIO("""<?xml version="1.0" encoding="utf-8"?>
<augments>
    <foo/>
</augments>
"""), db)
        self.assertRaises(RuntimeError, XMLAugmentsParser, cStringIO.StringIO("""<?xml version="1.0" encoding="utf-8"?>
<augments>
  <record>
    <enable>true</enable>
  </record>
</augments>
"""), db)
        self.assertRaises(RuntimeError, XMLAugmentsParser, cStringIO.StringIO("""<?xml version="1.0" encoding="utf-8"?>
  <record>
    <uid>admin</uid>
    <enable>true</enable>
    <foo/>
  </record>
"""), db)


    @inlineCallbacks
    def test_add_modify(self):

        # Duplicate file as we will change it
        newxmlfile = FilePath(self.mktemp())
        FilePath(xmlFile).copyTo(newxmlfile)

        db = AugmentXMLDB((newxmlfile.path,))

        for item in testRecords:
            yield self._checkRecord(db, item)

        newrecord = AugmentRecord(
            **testAddRecords[0]
        )
        yield db.addAugmentRecords((newrecord,))

        newdb = AugmentXMLDB((newxmlfile.path,))

        for item in testRecords:
            yield self._checkRecord(newdb, item)
        yield self._checkRecord(newdb, testAddRecords[0])

        newrecord = AugmentRecord(
            **testModifyRecords[0]
        )
        yield db.addAugmentRecords((newrecord,))

        newdb = AugmentXMLDB((newxmlfile.path,))

        for item in testRecords:
            yield self._checkRecord(newdb, item)
        yield self._checkRecord(newdb, testModifyRecords[0])


    def test_shouldReparse(self):
        """
        Verify that a change to the file will get noticed
        """
        newxmlfile = FilePath(self.mktemp())
        FilePath(xmlFile).copyTo(newxmlfile)
        db = AugmentXMLDB((newxmlfile.path,))
        self.assertFalse(db._shouldReparse([newxmlfile.path])) # No need to parse
        newxmlfile.setContent("") # Change the file
        self.assertTrue(db._shouldReparse([newxmlfile.path])) # Need to parse


    def test_refresh(self):
        """
        Ensure that a refresh without any file changes doesn't zero out the
        cache
        """
        dbxml = AugmentXMLDB((xmlFile,))
        keys = dbxml.db.keys()
        dbxml.refresh()
        self.assertEquals(keys, dbxml.db.keys())


    def uidsFromFile(self, filename):
        """
        Return all uids from the augments xml file
        """

        _ignore_etree, augments_node = readXML(filename)
        for record_node in augments_node:
            if record_node.tag != xmlaugmentsparser.ELEMENT_RECORD:
                continue
            uid = record_node.find(xmlaugmentsparser.ELEMENT_UID).text
            yield uid


    def test_normalize(self):
        """
        Ensure augment uids are normalized upon opening
        """
        newxmlfile = FilePath(self.mktemp())
        FilePath(xmlFileNormalization).copyTo(newxmlfile)
        uids = list(self.uidsFromFile(newxmlfile.path))
        self.assertEquals(uids, ['aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'])
        AugmentXMLDB((newxmlfile.path,))
        uids = list(self.uidsFromFile(newxmlfile.path))
        self.assertEquals(uids, ['AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA'])



class AugmentSqliteTests(AugmentTests, AugmentTestsMixin):

    def _db(self, dbpath=None):
        return AugmentSqliteDB(dbpath if dbpath else os.path.abspath(self.mktemp()))



class AugmentPostgreSQLTests(AugmentTests, AugmentTestsMixin):

    def _db(self, dbpath=None):
        return AugmentPostgreSQLDB("localhost", "augments")

try:
    import pgdb
except ImportError:
    AugmentPostgreSQLTests.skip = True
else:
    try:
        db = pgdb.connect(host="localhost", database="augments")
    except:
        AugmentPostgreSQLTests.skip = True
