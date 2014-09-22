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
import uuid

from twext.who.expression import (
    Operand, MatchType, MatchFlags, MatchExpression
)
from twext.who.idirectory import RecordType, FieldName
from twisted.cred.credentials import calcResponse, calcHA1, calcHA2
from twisted.internet.defer import inlineCallbacks, succeed
from twisted.protocols.amp import AMP
from twisted.python.filepath import FilePath
from twisted.test.testutils import returnConnected
from twisted.trial import unittest
from twistedcaldav.config import config
from twistedcaldav.test.util import StoreTestCase
from txdav.dps.client import DirectoryService
from txdav.dps.server import DirectoryProxyAMPProtocol
from txdav.who.directory import CalendarDirectoryServiceMixin
from txdav.who.groups import GroupCacher
from txdav.who.test.support import (
    TestRecord, CalendarInMemoryDirectoryService
)


testMode = "xml"  # "xml" or "od"
if testMode == "xml":
    testShortName = u"wsanchez"
    testUID = u"__wsanchez__"
    testPassword = u"zehcnasw"
    from txdav.who.xml import DirectoryService as XMLDirectoryService

    # Mix in the calendar-specific service methods
    class CalendarXMLDirectoryService(
        CalendarDirectoryServiceMixin,
        XMLDirectoryService
    ):
        pass

elif testMode == "od":
    testShortName = u"becausedigest"
    testUID = u"381D56CA-3B89-4AA1-942A-D4BFBC4F6F69"
    testPassword = u"password"
    from twext.who.opendirectory import DirectoryService as OpenDirectoryService

    # Mix in the calendar-specific service methods
    class CalendarODDirectoryService(
        CalendarDirectoryServiceMixin,
        OpenDirectoryService
    ):
        pass



class DPSClientSingleDirectoryTest(unittest.TestCase):
    """
    Tests the client against a single directory service (as opposed to the
    augmented, aggregated structure you get from directoryFromConfig(), which
    is tested in the class below)
    """

    def setUp(self):

        # The "local" directory service
        self.directory = DirectoryService(None)

        # The "remote" directory service
        if testMode == "xml":
            # Need a copy as it might change
            path = FilePath(os.path.join(os.path.dirname(__file__), "test.xml"))
            copy = FilePath(self.mktemp())
            path.copyTo(copy)
            remoteDirectory = CalendarXMLDirectoryService(copy)
        elif testMode == "od":
            remoteDirectory = CalendarODDirectoryService()

        # Connect the two services directly via an IOPump
        client = AMP()
        server = DirectoryProxyAMPProtocol(remoteDirectory)
        pump = returnConnected(server, client)

        # Replace the normal _getConnection method with one that bypasses any
        # actual networking
        self.patch(self.directory, "_getConnection", lambda: succeed(client))

        # Wrap the normal _sendCommand method with one that flushes the IOPump
        # afterwards
        origCall = self.directory._sendCommand

        def newCall(*args, **kwds):
            d = origCall(*args, **kwds)
            pump.flush()
            return d

        self.patch(self.directory, "_sendCommand", newCall)


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
    def test_recordsMatchingFields_nonUnicode(self):
        fields = (
            (u"guid", uuid.UUID("A3B1158F-0564-4F5B-81E4-A89EA5FF81B0"),
                MatchFlags.caseInsensitive, MatchType.equals),
        )
        records = (yield self.directory.recordsMatchingFields(
            fields, operand=Operand.OR, recordType=None
        ))
        matchingShortNames = set()
        for r in records:
            for shortName in r.shortNames:
                matchingShortNames.add(shortName)
        self.assertTrue("dre" in matchingShortNames)
        self.assertFalse("wsanchez" in matchingShortNames)


    @inlineCallbacks
    def test_recordsMatchingFields_not(self):
        fields = (
            (
                u"fullNames", "anche",
                MatchFlags.NOT | MatchFlags.caseInsensitive,
                MatchType.contains
            ),
        )
        records = (yield self.directory.recordsMatchingFields(
            fields, operand=Operand.OR, recordType=None
        ))
        matchingShortNames = set()
        for r in records:
            for shortName in r.shortNames:
                matchingShortNames.add(shortName)
        self.assertTrue("sagen" in matchingShortNames)
        self.assertTrue("dre" not in matchingShortNames)
        self.assertTrue("wsanchez" not in matchingShortNames)
        self.assertTrue("sanchezoffice" not in matchingShortNames)


    @inlineCallbacks
    def test_recordsFromMatchExpression(self):
        expression = MatchExpression(
            FieldName.uid,
            testUID,
            MatchType.equals,
            MatchFlags.none
        )
        records = yield self.directory.recordsFromExpression(expression)
        self.assertEquals(len(records), 1)

    test_recordsFromMatchExpression.todo = "Won't work until we can serialize expressions"


    @inlineCallbacks
    def test_members(self):
        group = yield self.directory.recordWithUID(u"__calendar-dev__")
        members = yield group.members()
        self.assertEquals(len(members), 5)


    @inlineCallbacks
    def test_groups(self):
        # No need to use group cacher as the XML service directly supports
        # groups()
        record = yield self.directory.recordWithUID(u"__sagen__")
        groups = yield record.groups()
        self.assertEquals(len(groups), 1)


    @inlineCallbacks
    def test_group_changes(self):
        group = yield self.directory.recordWithUID(u"__twisted__")
        members = yield group.members()
        self.assertEquals(len(members), 5)

        # Add new member
        group = yield self.directory.recordWithUID(u"__twisted__")
        user = yield self.directory.recordWithUID(u"__cdaboo__")
        yield group.addMembers((user,))
        yield self.directory.updateRecords((group,), False)

        group = yield self.directory.recordWithUID(u"__twisted__")
        members = yield group.members()
        self.assertEquals(len(members), 6)

        # Add existing member
        group = yield self.directory.recordWithUID(u"__twisted__")
        user = yield self.directory.recordWithUID(u"__wsanchez__")
        yield group.addMembers((user,))
        yield self.directory.updateRecords((group,), False)

        group = yield self.directory.recordWithUID(u"__twisted__")
        members = yield group.members()
        self.assertEquals(len(members), 6)

        # Remove existing member
        group = yield self.directory.recordWithUID(u"__twisted__")
        user = yield self.directory.recordWithUID(u"__cdaboo__")
        yield group.removeMembers((user,))
        yield self.directory.updateRecords((group,), False)

        group = yield self.directory.recordWithUID(u"__twisted__")
        members = yield group.members()
        self.assertEquals(len(members), 5)

        # Remove missing member
        group = yield self.directory.recordWithUID(u"__twisted__")
        user = yield self.directory.recordWithUID(u"__cdaboo__")
        yield group.removeMembers((user,))
        yield self.directory.updateRecords((group,), False)

        group = yield self.directory.recordWithUID(u"__twisted__")
        members = yield group.members()
        self.assertEquals(len(members), 5)


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



class DPSClientAugmentedAggregateDirectoryTest(StoreTestCase):
    """
    Similar to the above tests, but in the context of the directory structure
    that directoryFromConfig() returns
    """

    wsanchezUID = u"6423F94A-6B76-4A3A-815B-D52CFD77935D"

    @inlineCallbacks
    def setUp(self):
        yield super(DPSClientAugmentedAggregateDirectoryTest, self).setUp()

        # The "local" directory service
        self.client = DirectoryService(None)

        # The "remote" directory service
        remoteDirectory = self.directory

        # Connect the two services directly via an IOPump
        client = AMP()
        server = DirectoryProxyAMPProtocol(remoteDirectory)
        pump = returnConnected(server, client)

        # Replace the normal _getConnection method with one that bypasses any
        # actual networking
        self.patch(self.client, "_getConnection", lambda: succeed(client))

        # Wrap the normal _sendCommand method with one that flushes the IOPump
        # afterwards
        origCall = self.client._sendCommand

        def newCall(*args, **kwds):
            d = origCall(*args, **kwds)
            pump.flush()
            return d

        self.patch(self.client, "_sendCommand", newCall)


    def configure(self):
        """
        Override configuration hook to turn on wiki.
        """
        super(DPSClientAugmentedAggregateDirectoryTest, self).configure()
        self.patch(config.Authentication.Wiki, "Enabled", True)


    @inlineCallbacks
    def test_uid(self):
        record = (yield self.client.recordWithUID(self.wsanchezUID))
        self.assertTrue(u"wsanchez" in record.shortNames)


    @inlineCallbacks
    def test_shortName(self):
        record = (yield self.client.recordWithShortName(
            RecordType.user,
            u"wsanchez"
        ))
        self.assertEquals(record.uid, self.wsanchezUID)


    def test_guid(self):
        record = yield self.client.recordWithGUID(self.wsanchezUID)
        self.assertTrue(u"wsanchez" in record.shortNames)


    @inlineCallbacks
    def test_recordType(self):
        records = (yield self.client.recordsWithRecordType(
            RecordType.user
        ))
        self.assertEquals(len(records), 243)


    @inlineCallbacks
    def test_emailAddress(self):
        records = (yield self.client.recordsWithEmailAddress(
            u"wsanchez@example.com"
        ))
        self.assertEquals(len(records), 1)
        self.assertEquals(records[0].shortNames, [u"wsanchez"])


    @inlineCallbacks
    def test_recordsMatchingTokens(self):
        records = (yield self.client.recordsMatchingTokens(
            [u"anche"]
        ))
        matchingShortNames = set()
        for r in records:
            for shortName in r.shortNames:
                matchingShortNames.add(shortName)
        self.assertTrue("dre" in matchingShortNames)
        self.assertTrue("wsanchez" in matchingShortNames)


    @inlineCallbacks
    def test_recordsMatchingTokensWithContext(self):

        testData = [
            # (
            #     tokens,
            #     context,
            #     short names expected to be in results,
            #     short names not expected to be in results
            # ),
            (
                [u"an"],
                "user",  # just users
                (u"dre", u"wsanchez"),
                (u"transporter", u"managers"),
            ),
            (
                [u"an"],
                "group",  # just groups
                (u"managers",),
                (u"dre", u"wsanchez", u"transporter"),
            ),
            (
                [u"an"],
                "location",  # just locations
                (u"sanchezoffice",),
                (u"dre", u"wsanchez", u"transporter", u"managers"),
            ),
            (
                [u"an"],
                "resource",  # just resources
                (u"transporter", u"ftlcpu"),
                (u"dre", u"wsanchez", u"managers", u"sanchezoffice"),
            ),
            (
                [u"an"],
                "attendee",  # just users, groups, resources
                (
                    u"dre", u"wsanchez", u"managers",
                    u"transporter", u"ftlcpu"
                ),
                (u"sanchezoffice",),
            ),
            (
                [u"an"],
                None,   # any type
                (
                    u"dre", u"wsanchez", u"managers", u"sanchezoffice",
                    u"transporter", u"ftlcpu"
                ),
                (),
            ),
        ]

        for tokens, context, expected, unexpected in testData:
            # print("Tokens", tokens, "context", context)
            records = yield self.directory.recordsMatchingTokens(
                tokens, context
            )
            matchingShortNames = set()
            for r in records:
                for shortName in r.shortNames:
                    matchingShortNames.add(shortName)
            for name in expected:
                self.assertTrue(name in matchingShortNames)
            for name in unexpected:
                self.assertFalse(name in matchingShortNames)


    @inlineCallbacks
    def test_recordsMatchingFields_anyType(self):
        fields = (
            (u"fullNames", "anche", MatchFlags.caseInsensitive, MatchType.contains),
            (u"fullNames", "morgen", MatchFlags.caseInsensitive, MatchType.contains),
        )
        records = (yield self.client.recordsMatchingFields(
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
        records = (yield self.client.recordsMatchingFields(
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
        records = (yield self.client.recordsMatchingFields(
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
    def test_recordsFromMatchExpression(self):
        expression = MatchExpression(
            FieldName.uid,
            u"wsanchez",
            MatchType.equals,
            MatchFlags.none
        )
        records = yield self.client.recordsFromExpression(expression)
        self.assertEquals(len(records), 1)

    test_recordsFromMatchExpression.todo = "Won't work until we can serialize expressions"


    @inlineCallbacks
    def test_members(self):
        group = yield self.client.recordWithUID(u"__top_group_1__")
        members = yield group.members()
        self.assertEquals(len(members), 3)

        group = yield self.client.recordWithUID(u"emptygroup")
        members = yield group.members()
        self.assertEquals(len(members), 0)


    @inlineCallbacks
    def test_expandedMemberUIDs(self):
        group = yield self.client.recordWithUID(u"__top_group_1__")
        memberUIDs = yield group.expandedMemberUIDs()
        self.assertEquals(
            set(memberUIDs),
            set(
                [u'__wsanchez1__', u'__cdaboo1__', u'__glyph1__', u'__sagen1__']
            )
        )


    @inlineCallbacks
    def test_groups(self):

        # A group must first be "refreshed" into the DB otherwise we won't
        # consider it for group memberships
        txn = self.store.newTransaction()
        groupCacher = GroupCacher(self.directory)
        yield groupCacher.refreshGroup(txn, u"__sub_group_1__")
        yield txn.commit()

        # record = yield self.client.recordWithUID(u"__sagen1__")
        # FIXME: this call hangs during unit tests, but not in a real server:
        # groups = yield record.groups()
        # self.assertEquals(len(groups), 1)

    test_groups.todo = "Figure out why this hangs"


    @inlineCallbacks
    def test_group_changes(self):
        group = yield self.directory.recordWithUID(u"__top_group_1__")
        members = yield group.members()
        self.assertEquals(len(members), 3)

        # Add new member
        group = yield self.directory.recordWithUID(u"__top_group_1__")
        user = yield self.directory.recordWithUID(u"__cdaboo1__")
        yield group.addMembers((user,))
        yield self.directory.updateRecords((group,), False)

        group = yield self.directory.recordWithUID(u"__top_group_1__")
        members = yield group.members()
        self.assertEquals(len(members), 4)

        # Add existing member
        group = yield self.directory.recordWithUID(u"__top_group_1__")
        user = yield self.directory.recordWithUID(u"__wsanchez1__")
        yield group.addMembers((user,))
        yield self.directory.updateRecords((group,), False)

        group = yield self.directory.recordWithUID(u"__top_group_1__")
        members = yield group.members()
        self.assertEquals(len(members), 4)

        # Remove existing member
        group = yield self.directory.recordWithUID(u"__top_group_1__")
        user = yield self.directory.recordWithUID(u"__cdaboo1__")
        yield group.removeMembers((user,))
        yield self.directory.updateRecords((group,), False)

        group = yield self.directory.recordWithUID(u"__top_group_1__")
        members = yield group.members()
        self.assertEquals(len(members), 3)

        # Remove missing member
        group = yield self.directory.recordWithUID(u"__top_group_1__")
        user = yield self.directory.recordWithUID(u"__cdaboo1__")
        yield group.removeMembers((user,))
        yield self.directory.updateRecords((group,), False)

        group = yield self.directory.recordWithUID(u"__top_group_1__")
        members = yield group.members()
        self.assertEquals(len(members), 3)


    @inlineCallbacks
    def test_verifyPlaintextPassword(self):
        expectations = (
            (u"zehcnasw", True),  # Correct
            ("wrong", False)  # Incorrect
        )
        record = (
            yield self.client.recordWithShortName(
                RecordType.user,
                u"wsanchez"
            )
        )

        for password, answer in expectations:
            authenticated = (yield record.verifyPlaintextPassword(password))
            self.assertEquals(authenticated, answer)


    @inlineCallbacks
    def test_verifyHTTPDigest(self):
        expectations = (
            (u"zehcnasw", True),  # Correct
            ("wrong", False)  # Incorrect
        )
        record = (
            yield self.client.recordWithShortName(
                RecordType.user,
                u"wsanchez"
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
                    calcHA1(algorithm, u"wsanchez", realm, password, nonce, cnonce),
                    calcHA2(algorithm, method, uri, qop, None),
                    algorithm, nonce, nc, cnonce, qop)

                authenticated = (
                    yield record.verifyHTTPDigest(
                        u"wsanchez", realm, uri, nonce, cnonce, algorithm, nc, qop,
                        response, method
                    )
                )
                self.assertEquals(authenticated, answer)



class DPSClientLargeResultsTest(unittest.TestCase):
    """
    Tests the client against a single directory service (as opposed to the
    augmented, aggregated structure you get from directoryFromConfig(), which
    is tested in the class below)
    """

    @inlineCallbacks
    def setUp(self):

        self.numUsers = 1000

        # The "local" directory service
        self.directory = DirectoryService(None)

        # The "remote" directory service
        remoteDirectory = CalendarInMemoryDirectoryService(None)

        # Add users
        records = []
        fieldName = remoteDirectory.fieldName
        for i in xrange(self.numUsers):
            records.append(
                TestRecord(
                    remoteDirectory,
                    {
                        fieldName.uid: u"foo{ctr:05d}".format(ctr=i),
                        fieldName.shortNames: (u"foo{ctr:05d}".format(ctr=i),),
                        fieldName.fullNames: (u"foo{ctr:05d}".format(ctr=i),),
                        fieldName.recordType: RecordType.user,
                    }
                )
            )

        # Add a big group
        records.append(
            TestRecord(
                remoteDirectory,
                {
                    fieldName.uid: u"bigGroup",
                    fieldName.recordType: RecordType.group,
                }
            )
        )

        yield remoteDirectory.updateRecords(records, create=True)

        group = yield remoteDirectory.recordWithUID(u"bigGroup")
        members = yield remoteDirectory.recordsWithRecordType(RecordType.user)
        yield group.setMembers(members)

        # Connect the two services directly via an IOPump
        client = AMP()
        self.server = DirectoryProxyAMPProtocol(remoteDirectory)
        pump = returnConnected(self.server, client)

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
    def test_tooBigResults(self):
        """
        The AMP protocol limits values to 65,535 bytes, so the DPS server
        breaks up the responses to fit.  This test uses 1000 records to verify
        the various methods work seamlessly in the face of large results.
        Normally only a couple hundred records would fit in a single response.
        """

        # recordsMatchingTokens
        records = yield self.directory.recordsMatchingTokens([u"foo"])
        self.assertEquals(len(records), self.numUsers)

        # recordsMatchingFields
        fields = (
            (u"fullNames", "foo", MatchFlags.caseInsensitive, MatchType.contains),
        )
        records = yield self.directory.recordsMatchingFields(
            fields, operand=Operand.OR, recordType=RecordType.user
        )
        self.assertEquals(len(records), self.numUsers)

        # recordsWithRecordType
        records = yield self.directory.recordsWithRecordType(
            RecordType.user
        )
        self.assertEquals(len(records), self.numUsers)

        # members()
        group = yield self.directory.recordWithUID(u"bigGroup")
        members = yield group.members()
        self.assertEquals(len(members), self.numUsers)

        # force the limit small so continuations happen
        self.server._maxSize = 500
        # expandedMemberUIDs
        memberUIDs = yield group.expandedMemberUIDs()
        self.assertEquals(len(memberUIDs), self.numUsers)
