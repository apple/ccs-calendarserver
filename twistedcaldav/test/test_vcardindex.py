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

from twisted.internet import reactor
from twisted.internet.task import deferLater

from twistedcaldav.test.util import InMemoryMemcacheProtocol
from twistedcaldav.vcard import Component
from twistedcaldav.vcardindex import AddressBookIndex, MemcachedUIDReserver, ReservationError
import twistedcaldav.test.util

import os

class SQLIndexTests (twistedcaldav.test.util.TestCase):
    """
    Test abstract SQL DB class
    """

    def setUp(self):
        super(SQLIndexTests, self).setUp()
        self.site.resource.isAddressBookCollection = lambda: True
        self.db = AddressBookIndex(self.site.resource)


    def test_reserve_uid_ok(self):
        uid = "test-test-test"
        d = self.db.isReservedUID(uid)
        d.addCallback(self.assertFalse)
        d.addCallback(lambda _: self.db.reserveUID(uid))
        d.addCallback(lambda _: self.db.isReservedUID(uid))
        d.addCallback(self.assertTrue)
        d.addCallback(lambda _: self.db.unreserveUID(uid))
        d.addCallback(lambda _: self.db.isReservedUID(uid))
        d.addCallback(self.assertFalse)

        return d


    def test_reserve_uid_twice(self):
        uid = "test-test-test"
        d = self.db.reserveUID(uid)
        d.addCallback(lambda _: self.db.isReservedUID(uid))
        d.addCallback(self.assertTrue)
        d.addCallback(lambda _:
                      self.assertFailure(self.db.reserveUID(uid),
                                         ReservationError))
        return d


    def test_unreserve_unreserved(self):
        uid = "test-test-test"
        return self.assertFailure(self.db.unreserveUID(uid),
                                  ReservationError)


    def test_reserve_uid_timeout(self):
        # WARNING: This test is fundamentally flawed and will fail
        # intermittently because it uses the real clock.
        uid = "test-test-test"
        from twistedcaldav.config import config
        old_timeout = config.UIDReservationTimeOut
        config.UIDReservationTimeOut = 1

        def _finally():
            config.UIDReservationTimeOut = old_timeout

        d = self.db.isReservedUID(uid)
        d.addCallback(self.assertFalse)
        d.addCallback(lambda _: self.db.reserveUID(uid))
        d.addCallback(lambda _: self.db.isReservedUID(uid))
        d.addCallback(self.assertTrue)
        d.addCallback(lambda _: deferLater(reactor, 2, lambda: None))
        d.addCallback(lambda _: self.db.isReservedUID(uid))
        d.addCallback(self.assertFalse)
        self.addCleanup(_finally)

        return d


    def test_index(self):
        data = (
            (
                "#1.1 Simple component",
                "1.1",
                """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:12345-67890-1.1
FN:Cyrus Daboo
N:Daboo;Cyrus
EMAIL;TYPE=INTERNET,PREF:cyrus@example.com
END:VCARD
""",
            ),
        )

        revision = 0
        for description, name, vcard_txt in data:
            revision += 1
            calendar = Component.fromString(vcard_txt)
            f = open(os.path.join(self.site.resource.fp.path, name), "w")
            f.write(vcard_txt)
            del f

            self.db.addResource(name, calendar, revision)
            self.assertTrue(self.db.resourceExists(name), msg=description)

        self.db._db_recreate()
        for description, name, vcard_txt in data:
            self.assertTrue(self.db.resourceExists(name), msg=description)

    def test_index_revisions(self):
        data1 = """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:12345-67890-1-1.1
FN:Cyrus Daboo
N:Daboo;Cyrus
EMAIL;TYPE=INTERNET,PREF:cyrus@example.com
END:VCARD
"""
        data2 = """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:12345-67890-2-1.1
FN:Wilfredo Sanchez
N:Sanchez;Wilfredo
EMAIL;TYPE=INTERNET,PREF:wsanchez@example.com
END:VCARD
"""
        data3 = """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:12345-67890-3-1.1
FN:Bruce Gaya
N:Gaya;Bruce
EMAIL;TYPE=INTERNET,PREF:bruce@example.com
END:VCARD
"""

        vcard = Component.fromString(data1)
        self.db.addResource("data1.vcf", vcard, 1)
        vcard = Component.fromString(data2)
        self.db.addResource("data2.vcf", vcard, 2)
        vcard = Component.fromString(data3)
        self.db.addResource("data3.vcf", vcard, 3)
        self.db.deleteResource("data3.vcf", 4)

        tests = (
            (0, (["data1.vcf", "data2.vcf",], [],)),
            (1, (["data2.vcf",], [],)),
            (2, ([], [],)),
            (3, ([], ["data3.vcf",],)),
            (4, ([], [],)),
            (5, ([], [],)),
        )
        
        for revision, results in tests:
            self.assertEquals(self.db.whatchanged(revision), results, "Mismatched results for whatchanged with revision %d" % (revision,))

class MemcacheTests(SQLIndexTests):
    def setUp(self):
        super(MemcacheTests, self).setUp()
        self.memcache = InMemoryMemcacheProtocol()
        self.db.reserver = MemcachedUIDReserver(self.db, self.memcache)


    def tearDown(self):
        for _ignore_k, v in self.memcache._timeouts.iteritems():
            if v.active():
                v.cancel()
