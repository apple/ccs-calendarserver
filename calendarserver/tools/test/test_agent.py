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

try:
    from calendarserver.tools.agent import AgentRealm
    from calendarserver.tools.agent import CustomDigestCredentialFactory
    from calendarserver.tools.agent import DirectoryServiceChecker
    from calendarserver.tools.agent import InactivityDetector
    from twistedcaldav.test.util import TestCase
    from twisted.internet.defer import inlineCallbacks
    from twisted.internet.task import Clock
    from twisted.cred.error import UnauthorizedLogin 
    from twisted.web.resource import IResource
    from twisted.web.resource import ForbiddenResource
    RUN_TESTS = True
except ImportError:
    RUN_TESTS = False




if RUN_TESTS:
    class AgentTestCase(TestCase):

        def test_CustomDigestCredentialFactory(self):
            f = CustomDigestCredentialFactory("md5", "/Local/Default")
            challenge = f.getChallenge(FakeRequest())
            self.assertTrue("qop" not in challenge)
            self.assertEquals(challenge["algorithm"], "md5")
            self.assertEquals(challenge["realm"], "/Local/Default")

        @inlineCallbacks
        def test_DirectoryServiceChecker(self):
            c = DirectoryServiceChecker("/Local/Default")
            fakeOpenDirectory = FakeOpenDirectory()
            c.directoryModule = fakeOpenDirectory

            fields = {
                "username" : "foo",
                "realm" : "/Local/Default",
                "nonce" : 1,
                "uri" : "/gateway",
                "response" : "abc",
                "algorithm" : "md5",
            }
            creds = FakeCredentials("foo", fields)

            # Record does not exist:
            fakeOpenDirectory.returnThisRecord(None)
            try:
                yield c.requestAvatarId(creds)
            except UnauthorizedLogin:
                pass
            else:
                self.fail("Didn't raise UnauthorizedLogin")


            # Record exists, but invalid credentials
            fakeOpenDirectory.returnThisRecord("fooRecord")
            fakeOpenDirectory.returnThisAuthResponse(False)
            try:
                yield c.requestAvatarId(creds)
            except UnauthorizedLogin:
                pass
            else:
                self.fail("Didn't raise UnauthorizedLogin")


            # Record exists, valid credentials
            fakeOpenDirectory.returnThisRecord("fooRecord")
            fakeOpenDirectory.returnThisAuthResponse(True)
            avatar = (yield c.requestAvatarId(creds))
            self.assertEquals(avatar, "foo")


            # Record exists, but missing fields in credentials
            del creds.fields["nonce"]
            fakeOpenDirectory.returnThisRecord("fooRecord")
            fakeOpenDirectory.returnThisAuthResponse(False)
            try:
                yield c.requestAvatarId(creds)
            except UnauthorizedLogin:
                pass
            else:
                self.fail("Didn't raise UnauthorizedLogin")


        def test_AgentRealm(self):
            realm = AgentRealm("root", ["abc"])

            # Valid avatar
            interface, resource, ignored = realm.requestAvatar("abc", None, IResource)
            self.assertEquals(resource, "root")

            # Not allowed avatar
            interface, resource, ignored = realm.requestAvatar("def", None, IResource)
            self.assertTrue(isinstance(resource, ForbiddenResource))

            # Interface unhandled
            try:
                realm.requestAvatar("def", None, None)
            except NotImplementedError:
                pass
            else:
                self.fail("Didn't raise NotImplementedError")



    class InactivityDectectorTestCase(TestCase):

        def test_inactivity(self):
            clock = Clock()

            self.inactivityReached = False
            def becameInactive():
                self.inactivityReached = True

            id = InactivityDetector(clock, 5, becameInactive)

            # After 3 seconds, not inactive
            clock.advance(3)
            self.assertFalse(self.inactivityReached)

            # Activity happens, pushing out the inactivity threshold
            id.activity()
            clock.advance(3)
            self.assertFalse(self.inactivityReached)

            # Time passes without activity
            clock.advance(3)
            self.assertTrue(self.inactivityReached)

            id.stop()

            # Verify a timeout of 0 does not ever fire
            id = InactivityDetector(clock, 0, becameInactive)
            self.assertEquals(clock.getDelayedCalls(), [])


    class FakeRequest(object):

        def getClientIP(self):
            return "127.0.0.1"



    class FakeOpenDirectory(object):

        def returnThisRecord(self, response):
            self.recordResponse = response

        def getUserRecord(self, ignored, username):
            return self.recordResponse

        def returnThisAuthResponse(self, response):
            self.authResponse = response

        def authenticateUserDigest(self, ignored, node, username, challenge, response,
            method):
            return self.authResponse

        ODNSerror = "Error"



    class FakeCredentials(object):

        def __init__(self, username, fields):
            self.username = username
            self.fields = fields
            self.method = "POST"
