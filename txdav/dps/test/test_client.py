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

from twext.who.idirectory import RecordType
from twisted.cred.credentials import calcResponse, calcHA1, calcHA2
from twisted.internet.defer import inlineCallbacks, succeed
from twisted.protocols.amp import AMP
from twisted.python.filepath import FilePath
from twisted.test.testutils import returnConnected
from twisted.trial import unittest
from txdav.dps.client import DirectoryService
from txdav.dps.server import DirectoryProxyAMPProtocol
from txdav.who.xml import DirectoryService as XMLDirectoryService


class DPSClientTest(unittest.TestCase):

    def setUp(self):

        # The "local" directory service
        self.directory = DirectoryService(None)

        # The "remote" directory service
        path = os.path.join(os.path.dirname(__file__), "test.xml")
        remoteDirectory = XMLDirectoryService(FilePath(path))

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
        record = (yield self.directory.recordWithUID("__dre__"))
        self.assertEquals(record.shortNames, [u"dre"])


    @inlineCallbacks
    def test_shortName(self):
        record = (yield self.directory.recordWithShortName(
            RecordType.user,
            "wsanchez"
        ))
        self.assertEquals(record.shortNames, [u'wsanchez', u'wilfredo_sanchez'])


    @inlineCallbacks
    def test_guid(self):
        record = (yield self.directory.recordWithGUID(
            "A3B1158F-0564-4F5B-81E4-A89EA5FF81B0"
        ))
        self.assertEquals(record.shortNames, [u'dre'])


    @inlineCallbacks
    def test_recordType(self):
        records = (yield self.directory.recordsWithRecordType(
            RecordType.user
        ))
        self.assertEquals(len(records), 9)


    @inlineCallbacks
    def test_emailAddress(self):
        records = (yield self.directory.recordsWithEmailAddress(
            "cdaboo@bitbucket.calendarserver.org"
        ))
        self.assertEquals(len(records), 1)
        self.assertEquals(records[0].shortNames, [u"cdaboo"])


    @inlineCallbacks
    def test_verifyPlaintextPassword(self):
        record = (yield self.directory.recordWithUID("__dre__"))

        # Correct password
        authenticated = (yield record.verifyPlaintextPassword("erd"))
        self.assertTrue(authenticated)

        # Incorrect password
        authenticated = (yield record.verifyPlaintextPassword("wrong"))
        self.assertFalse(authenticated)


    @inlineCallbacks
    def test_verifyHTTPDigest(self):
        username = "dre"
        record = (yield self.directory.recordWithShortName(
            RecordType.user, username))
        realm = u"xyzzy"
        nonce = "128446648710842461101646794502"
        nc = "00000001"
        cnonce = "/rrD6TqPA3lHRmg+fw/vyU6oWoQgzK7h9yWrsCmv/lE="
        algo = "md5"
        uri = "http://host.example.com"
        method = "GET"
        qop = ""

        # Correct password
        password = "erd"
        expected = calcResponse(
            calcHA1(algo, username, realm, password, nonce, cnonce),
            calcHA2(algo, method, uri, qop, None),
            algo, nonce, nc, cnonce, qop)

        authenticated = (
            yield record.verifyHTTPDigest(
                username, realm, uri, nonce, cnonce, algo, nc, qop,
                expected, method
            )
        )
        self.assertTrue(authenticated)

        # Incorrect password
        password = "wrong"
        expected = calcResponse(
            calcHA1(algo, username, realm, password, nonce, cnonce),
            calcHA2(algo, method, uri, qop, None),
            algo, nonce, nc, cnonce, qop)

        authenticated = (
            yield record.verifyHTTPDigest(
                username, realm, uri, nonce, cnonce, algo, nc, qop,
                expected, method
            )
        )
        self.assertFalse(authenticated)
