#
# Copyright (c) 2013-2014 Apple Inc. All rights reserved.
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

import os

from twext.who.expression import Operand, MatchType, MatchFlags
from twext.who.idirectory import RecordType
from twisted.cred.credentials import calcResponse, calcHA1, calcHA2
from twisted.internet.defer import inlineCallbacks, succeed
from twisted.protocols.amp import AMP
from twisted.python.filepath import FilePath
from twisted.test.testutils import returnConnected
from twisted.trial import unittest
from txdav.dps.client import DirectoryService
from txdav.dps.server import DirectoryProxyAMPProtocol
from txdav.who.directory import CalendarDirectoryServiceMixin


testMode = "xml"  # "xml" or "od"
if testMode == "xml":
    testShortName = u"wsanchez"
    testUID = u"__wsanchez__"
    testPassword = u"zehcnasw"
    from txdav.who.xml import DirectoryService as XMLDirectoryService

    # Mix in the calendar-specific service methods
    class CalendarXMLDirectoryService(
        XMLDirectoryService,
        CalendarDirectoryServiceMixin
    ):
        pass

elif testMode == "od":
    testShortName = u"becausedigest"
    testUID = u"381D56CA-3B89-4AA1-942A-D4BFBC4F6F69"
    testPassword = u"password"
    from twext.who.opendirectory import DirectoryService as OpenDirectoryService

    # Mix in the calendar-specific service methods
    class CalendarODDirectoryService(
        OpenDirectoryService,
        CalendarDirectoryServiceMixin
    ):
        pass




class DPSClientTest(unittest.TestCase):

    def setUp(self):

        # The "local" directory service
        self.directory = DirectoryService(None)

        # The "remote" directory service
        if testMode == "xml":
            path = os.path.join(os.path.dirname(__file__), "test.xml")
            remoteDirectory = CalendarXMLDirectoryService(FilePath(path))
        elif testMode == "od":
            remoteDirectory = CalendarODDirectoryService()

        # Connect the two services directly via an IOPump
        client = AMP()
        server = DirectoryProxyAMPProtocol(remoteDirectory)
        pump = returnConnected(server, client)

        # Replace the normal _getConnection method with one that bypasses any
        # actual networking
        self.patch(self.directory, "_getConnection", lambda: succeed(client))

        # Wrap the normal _call method with one that flushes the IOPump
        # afterwards
        origCall = self.directory._call

        def newCall(*args, **kwds):
            d = origCall(*args, **kwds)
            pump.flush()
            return d

        self.patch(self.directory, "_call", newCall)


    @inlineCallbacks
    def test_uid(self):
        record = (yield self.directory.recordWithUID(testUID))
        self.assertTrue(testShortName in record.shortNames)


    @inlineCallbacks
    def test_shortName(self):
        record = (yield self.directory.recordWithShortName(
            RecordType.user,
            testShortName
        ))
        self.assertEquals(record.uid, testUID)


    def test_guid(self):
        if testMode == "od":
            record = (yield self.directory.recordWithGUID(testUID))
            self.assertTrue(testShortName in record.shortNames)


    @inlineCallbacks
    def test_recordType(self):
        if testMode != "od":
            records = (yield self.directory.recordsWithRecordType(
                RecordType.user
            ))
            self.assertEquals(len(records), 9)


    @inlineCallbacks
    def test_emailAddress(self):
        if testMode == "xml":
            records = (yield self.directory.recordsWithEmailAddress(
                u"cdaboo@bitbucket.calendarserver.org"
            ))
            self.assertEquals(len(records), 1)
            self.assertEquals(records[0].shortNames, [u"cdaboo"])


    @inlineCallbacks
    def test_recordsMatchingTokens(self):
        records = (yield self.directory.recordsMatchingTokens(
            [u"anche"]
        ))
        matchingShortNames = set()
        for r in records:
            for shortName in r.shortNames:
                matchingShortNames.add(shortName)
        self.assertTrue("dre" in matchingShortNames)
        self.assertTrue("wsanchez" in matchingShortNames)


    @inlineCallbacks
    def test_recordsMatchingFields_anyType(self):
        fields = (
            (u"fullNames", "anche", MatchFlags.caseInsensitive, MatchType.contains),
            (u"fullNames", "morgen", MatchFlags.caseInsensitive, MatchType.contains),
        )
        records = (yield self.directory.recordsMatchingFields(
            fields, operand=Operand.OR, recordType=None
        ))
        matchingShortNames = set()
        for r in records:
            for shortName in r.shortNames:
                matchingShortNames.add(shortName)
        self.assertTrue("sagen" in matchingShortNames)
        self.assertTrue("dre" in matchingShortNames)
        self.assertTrue("wsanchez" in matchingShortNames)
        self.assertTrue("sanchezoffice" in matchingShortNames)


    @inlineCallbacks
    def test_recordsMatchingFields_oneType(self):
        fields = (
            (u"fullNames", "anche", MatchFlags.caseInsensitive, MatchType.contains),
        )
        records = (yield self.directory.recordsMatchingFields(
            fields, operand=Operand.OR, recordType=RecordType.user
        ))
        matchingShortNames = set()
        for r in records:
            for shortName in r.shortNames:
                matchingShortNames.add(shortName)
        self.assertTrue("dre" in matchingShortNames)
        self.assertTrue("wsanchez" in matchingShortNames)
        # This location should *not* appear in the results
        self.assertFalse("sanchezoffice" in matchingShortNames)


    @inlineCallbacks
    def test_recordsMatchingFields_unsupportedField(self):
        fields = (
            (u"fullNames", "anche", MatchFlags.caseInsensitive, MatchType.contains),
            # This should be ignored:
            (u"foo", "bar", MatchFlags.caseInsensitive, MatchType.contains),
        )
        records = (yield self.directory.recordsMatchingFields(
            fields, operand=Operand.OR, recordType=None
        ))
        matchingShortNames = set()
        for r in records:
            for shortName in r.shortNames:
                matchingShortNames.add(shortName)
        self.assertTrue("dre" in matchingShortNames)
        self.assertTrue("wsanchez" in matchingShortNames)
        self.assertTrue("sanchezoffice" in matchingShortNames)


    @inlineCallbacks
    def test_verifyPlaintextPassword(self):
        expectations = (
            (testPassword, True),  # Correct
            ("wrong", False)  # Incorrect
        )
        record = (
            yield self.directory.recordWithShortName(
                RecordType.user,
                testShortName
            )
        )

        for password, answer in expectations:
            authenticated = (yield record.verifyPlaintextPassword(password))
            self.assertEquals(authenticated, answer)


    @inlineCallbacks
    def test_verifyHTTPDigest(self):
        expectations = (
            (testPassword, True),  # Correct
            ("wrong", False)  # Incorrect
        )
        record = (
            yield self.directory.recordWithShortName(
                RecordType.user,
                testShortName
            )
        )

        realm = "host.example.com"
        nonce = "128446648710842461101646794502"
        algorithm = "md5"
        uri = "http://host.example.com"
        method = "GET"

        for password, answer in expectations:
            for qop, nc, cnonce in (
                ("", "", ""),
                ("auth", "00000001", "/rrD6TqPA3lHRmg+fw/vyU6oWoQgzK7h9yWrsCmv/lE="),
            ):
                response = calcResponse(
                    calcHA1(algorithm, testShortName, realm, password, nonce, cnonce),
                    calcHA2(algorithm, method, uri, qop, None),
                    algorithm, nonce, nc, cnonce, qop)

                authenticated = (
                    yield record.verifyHTTPDigest(
                        testShortName, realm, uri, nonce, cnonce, algorithm, nc, qop,
                        response, method
                    )
                )
                self.assertEquals(authenticated, answer)
