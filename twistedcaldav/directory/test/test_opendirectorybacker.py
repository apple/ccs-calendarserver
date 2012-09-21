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

from twistedcaldav.directory.opendirectorybacker import VCardRecord
from twistedcaldav.test.util import TestCase

class VCardRecordTestCase(TestCase):


    def test_multiplePhoneNumbersAndEmailAddresses(self):
        attributes={u'dsAttrTypeStandard:AppleMetaRecordName': ['uid=odtestamanda,cn=users,dc=dalek,dc=example,dc=com'], u'dsAttrTypeStandard:ModificationTimestamp': '20111017170937Z', u'dsAttrTypeStandard:PhoneNumber': ['408 555-1212', '415 555-1212'], u'dsAttrTypeStandard:RecordType': ['dsRecTypeStandard:Users'], u'dsAttrTypeStandard:AppleMetaNodeLocation': ['/LDAPv3/127.0.0.1'], u'dsAttrTypeStandard:RecordName': ['odtestamanda'], u'dsAttrTypeStandard:FirstName': 'Amanda', u'dsAttrTypeStandard:GeneratedUID': '9DC04A70-E6DD-11DF-9492-0800200C9A66', u'dsAttrTypeStandard:LastName': 'Test', u'dsAttrTypeStandard:CreationTimestamp': '20110927182945Z', u'dsAttrTypeStandard:EMailAddress': ['amanda@example.com', 'second@example.com'], u'dsAttrTypeStandard:RealName': 'Amanda Test'}
        vcardRecord = VCardRecord(StubService(), attributes)
        vcard = vcardRecord.vCard()
        properties = set([prop.value() for prop in vcard.properties("TEL")])
        self.assertEquals(properties, set(["408 555-1212", "415 555-1212"]))
        properties = set([prop.value() for prop in vcard.properties("EMAIL")])
        self.assertEquals(properties, set(["amanda@example.com", "second@example.com"]))


class StubService(object):
    addDSAttrXProperties = False
    directoryBackedAddressBook = None
    appleInternalServer = False
    realmName = "testing"
