##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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

from __future__ import print_function
from __future__ import absolute_import

"""
Tests for L{txdav.who.xml}.
"""

from textwrap import dedent

from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest

from twext.who.test.test_xml import xmlService

from ..idirectory import (
    RecordType, FieldName, AutoScheduleMode
)
from ..xml import DirectoryService



class ExtendedSchemaTest(unittest.TestCase):
    """
    Tests for calendar and contacts schema extensions.
    """

    def makeRecord(
        self, typeValue=u"user", elementName=u"password", elementValue=u"123"
    ):
        uid = u"id"

        xmlData = dedent(
            b"""
            <?xml version="1.0" encoding="utf-8"?>

            <directory realm="Test Realm">
              <record type="{type}">
                <uid>{uid}</uid>
                <short-name>{uid}</short-name>
                <{element}>{value}</{element}>
              </record>
            </directory>
            """[1:]
            .format(
                type=typeValue.encode("utf-8"),
                uid=uid.encode("utf-8"),
                element=elementName.encode("utf-8"),
                value=elementValue.encode("utf-8"),
            )
        )

        # print("-" * 80)
        # print(xmlData)
        # print("-" * 80)

        service = xmlService(
            self.mktemp(), xmlData=xmlData, serviceClass=DirectoryService
        )

        # print("Unknown record types:", service.unknownRecordTypes)
        # print("Unknown fields:", service.unknownFieldElements)

        return service.recordWithUID(uid)


    @inlineCallbacks
    def test_unicodeElements(self):
        for field, element in (
            (FieldName.serviceNodeUID, u"service-node"),
            (FieldName.autoAcceptGroup, u"auto-accept-group"),
        ):
            record = yield self.makeRecord(
                elementName=element, elementValue=u"xyzzy"
            )
            self.assertEquals(record.fields[field], u"xyzzy")


    @inlineCallbacks
    def test_booleanElements(self):
        for field, element in (
            (FieldName.loginAllowed, u"login-allowed"),
            (FieldName.hasCalendars, u"has-calendars"),
            (FieldName.hasContacts, u"has-contacts"),
        ):
            record = yield self.makeRecord(
                elementName=element, elementValue=u"<true />"
            )
            self.assertIdentical(record.fields[field], True, field)


    @inlineCallbacks
    def test_autoScheduleMode(self):
        for mode, value in (
            (AutoScheduleMode.none, u"none"),
            (AutoScheduleMode.accept, u"accept"),
            (AutoScheduleMode.decline, u"decline"),
            (AutoScheduleMode.acceptIfFree, u"accept-if-free"),
            (AutoScheduleMode.declineIfBusy, u"decline-if-busy"),
            (
                AutoScheduleMode.acceptIfFreeDeclineIfBusy,
                u"accept-if-free-decline-if-busy"
            ),
        ):
            field = FieldName.autoScheduleMode
            record = yield self.makeRecord(
                elementName=u"auto-schedule-mode",
                elementValue=u"<{0} />".format(value),
            )
            self.assertIdentical(record.fields[field], mode)


    @inlineCallbacks
    def test_recordTypes(self):
        for recordType, value in (
            (RecordType.location, u"location"),
            (RecordType.resource, u"resource"),
            (RecordType.address, u"address"),
        ):
            record = yield self.makeRecord(typeValue=value)
            self.assertIdentical(record.recordType, recordType)
