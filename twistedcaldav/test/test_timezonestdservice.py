##
# Copyright (c) 2011-2012 Apple Inc. All rights reserved.
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

from twistedcaldav.timezones import TimezoneCache
from twistedcaldav.timezonestdservice import TimezoneInfo, \
    PrimaryTimezoneDatabase
from xml.etree.ElementTree import Element
import hashlib
import os
import twistedcaldav.test.util

class TestTimezoneInfo (twistedcaldav.test.util.TestCase):
    """
    Timezone support tests
    """

    def test_generateXML(self):

        hashed = hashlib.md5("test").hexdigest()
        info = TimezoneInfo("America/New_York", ("US/Eastern",), "20110517T120000Z", hashed)

        node = Element("root")
        info.generateXML(node)

        timezone = node.find("timezone")
        self.assertTrue(timezone is not None)
        self.assertEqual(timezone.findtext("tzid"), "America/New_York")
        self.assertEqual(timezone.findtext("dtstamp"), "20110517T120000Z")
        self.assertEqual(timezone.findtext("alias"), "US/Eastern")
        self.assertEqual(timezone.findtext("md5"), hashed)


    def test_parseXML(self):

        hashed = hashlib.md5("test").hexdigest()
        info1 = TimezoneInfo("America/New_York", ("US/Eastern",), "20110517T120000Z", hashed)

        node = Element("root")
        info1.generateXML(node)
        timezone = node.find("timezone")

        info2 = TimezoneInfo.readXML(timezone)

        self.assertEqual(info2.tzid, "America/New_York")
        self.assertEqual(info2.aliases, ("US/Eastern",))
        self.assertEqual(info2.dtstamp, "20110517T120000Z")
        self.assertEqual(info2.md5, hashed)



class TestPrimaryTimezoneDatabase (twistedcaldav.test.util.TestCase):
    """
    Timezone support tests
    """

    def setUp(self):
        TimezoneCache.create()


    def testCreate(self):

        xmlfile = self.mktemp()
        db = PrimaryTimezoneDatabase(TimezoneCache.getDBPath(), xmlfile)

        db.createNewDatabase()
        self.assertTrue(os.path.exists(xmlfile))
        self.assertTrue(db.dtstamp is not None)
        self.assertTrue(len(db.timezones) > 0)


    def testUpdate(self):

        xmlfile = self.mktemp()
        db = PrimaryTimezoneDatabase(TimezoneCache.getDBPath(), xmlfile)

        db.createNewDatabase()
        self.assertTrue(os.path.exists(xmlfile))

        db.updateDatabase()
        self.assertTrue(db.changeCount == 0)
        self.assertTrue(len(db.changed) == 0)


    def testRead(self):

        xmlfile = self.mktemp()
        db1 = PrimaryTimezoneDatabase(TimezoneCache.getDBPath(), xmlfile)
        db1.createNewDatabase()
        self.assertTrue(os.path.exists(xmlfile))

        db2 = PrimaryTimezoneDatabase(TimezoneCache.getDBPath(), xmlfile)
        db2.readDatabase()
        self.assertEqual(db1.dtstamp, db2.dtstamp)
        self.assertEqual(len(db1.timezones), len(db2.timezones))


    def testList(self):

        xmlfile = self.mktemp()
        db = PrimaryTimezoneDatabase(TimezoneCache.getDBPath(), xmlfile)
        db.createNewDatabase()
        self.assertTrue(os.path.exists(xmlfile))

        tzids = set([tz.tzid for tz in db.listTimezones(None)])
        self.assertTrue("America/New_York" in tzids)
        self.assertTrue("US/Eastern" not in tzids)


    def testListChangedSince(self):

        xmlfile = self.mktemp()
        db = PrimaryTimezoneDatabase(TimezoneCache.getDBPath(), xmlfile)
        db.createNewDatabase()
        self.assertTrue(os.path.exists(xmlfile))

        tzids = set([tz.tzid for tz in db.listTimezones(db.dtstamp)])
        self.assertTrue(len(tzids) == 0)


    def testGetNone(self):

        xmlfile = self.mktemp()
        db = PrimaryTimezoneDatabase(TimezoneCache.getDBPath(), xmlfile)
        db.createNewDatabase()
        self.assertTrue(os.path.exists(xmlfile))

        tz = db.getTimezone("Bogus")
        self.assertEqual(tz, None)


    def testGetOne(self):

        xmlfile = self.mktemp()
        db = PrimaryTimezoneDatabase(TimezoneCache.getDBPath(), xmlfile)
        db.createNewDatabase()
        self.assertTrue(os.path.exists(xmlfile))

        # Original
        tz1 = db.getTimezone("America/New_York")
        self.assertTrue(str(tz1).find("VTIMEZONE") != -1)
        self.assertTrue(str(tz1).find("TZID:America/New_York") != -1)

        # Alias
        tz1 = db.getTimezone("US/Eastern")
        self.assertTrue(str(tz1).find("VTIMEZONE") != -1)
        self.assertTrue(str(tz1).find("TZID:US/Eastern") != -1)
