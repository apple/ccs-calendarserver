##
# Copyright (c) 2014-2015 Apple Inc. All rights reserved.
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

from __future__ import absolute_import
from __future__ import print_function
from twisted.internet.defer import inlineCallbacks
from twisted.python.filepath import FilePath
from twisted.trial import unittest
from txdav.common.datastore.test.util import CommonCommonTests, \
    populateCalendarsFrom, populateAddressBooksFrom
from txdav.who.vcard import vCardFromRecord
import os
from twistedcaldav.config import config



class TestVCard(CommonCommonTests, unittest.TestCase):
    """
    Tests for L{twext.who.vcard}.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(TestVCard, self).setUp()

        accountsFilePath = FilePath(
            os.path.join(os.path.dirname(__file__), "accounts")
        )
        yield self.buildStoreAndDirectory(
            accounts=accountsFilePath.child("vcards.xml"),
        )

        yield self.populate()


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        yield populateAddressBooksFrom(self.requirements, self.storeUnderTest())

    requirements = {
        "id1" : None,
    }


    @inlineCallbacks
    def test_basicVcard(self):
        vcard_result = """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:id1
FN:User 01
KIND:individual
N:01;User;;;
END:VCARD
""".replace("\n", "\r\n")

        record = yield self.directory.recordWithUID("id1")
        vcard = yield vCardFromRecord(record)
        self.assertEqual(str(vcard), vcard_result)


    @inlineCallbacks
    def test_parentURI(self):
        vcard_result = """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:id1
FN:User 01
KIND:individual
N:01;User;;;
SOURCE:https://example.com:8443/contacts/id1.vcf
END:VCARD
""".replace("\n", "\r\n")

        self.patch(config, "EnableSSL", True)
        self.patch(config, "SSLPort", 8443)
        self.patch(config, "ServerHostName", "example.com")

        record = yield self.directory.recordWithUID("id1")
        vcard = yield vCardFromRecord(record, parentURI="/contacts")
        self.assertEqual(str(vcard), vcard_result)


    @inlineCallbacks
    def test_forceKind(self):
        vcard_result = """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:id1
FN:User 01
KIND:foobar
N:01;User;;;
END:VCARD
""".replace("\n", "\r\n")

        record = yield self.directory.recordWithUID("id1")
        vcard = yield vCardFromRecord(record, forceKind="foobar")
        self.assertEqual(str(vcard), vcard_result)


    @inlineCallbacks
    def test_addProps(self):
        vcard_result = """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:id1
FN:User 01
KEY:private
KIND:individual
N:01;User;;;
END:VCARD
""".replace("\n", "\r\n")

        record = yield self.directory.recordWithUID("id1")
        vcard = yield vCardFromRecord(record, addProps={"KEY": "private"})
        self.assertEqual(str(vcard), vcard_result)


    @inlineCallbacks
    def test_email(self):
        vcard_result = """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:id2
EMAIL;TYPE=INTERNET,PREF,WORK:user02@example.com
FN:User 02
KIND:individual
N:02;User;;;
END:VCARD
""".replace("\n", "\r\n")

        record = yield self.directory.recordWithUID("id2")
        vcard = yield vCardFromRecord(record)
        self.assertEqual(str(vcard), vcard_result)


    @inlineCallbacks
    def test_multipleemail(self):
        vcard_result = """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:id3
EMAIL;TYPE=INTERNET,PREF,WORK:user03@example.com
EMAIL;TYPE=INTERNET,WORK:user03+plus@example.com
FN:User 03
KIND:individual
N:03;User;;;
END:VCARD
""".replace("\n", "\r\n")

        record = yield self.directory.recordWithUID("id3")
        vcard = yield vCardFromRecord(record)
        self.assertEqual(str(vcard), vcard_result)


    @inlineCallbacks
    def test_adr(self):
        vcard_result = """BEGIN:VCARD
VERSION:3.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
UID:id4
ADR;LABEL="20300 Stevens Creek Blvd, Cupertino, CA 95014";TYPE=PARCEL,POST
 AL,PREF,WORK:;;20300 Stevens Creek Blvd\\, Cupertino\\, CA 95014;;;;
FN:User 04
KIND:individual
LABEL;TYPE=PARCEL,POSTAL:20300 Stevens Creek Blvd\\, Cupertino\\, CA 95014
N:04;User;;;
END:VCARD
""".replace("\n", "\r\n")

        record = yield self.directory.recordWithUID("id4")
        vcard = yield vCardFromRecord(record)
        self.assertEqual(str(vcard), vcard_result)
