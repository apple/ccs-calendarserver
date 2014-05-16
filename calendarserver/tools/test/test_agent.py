##
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

try:
    from calendarserver.tools.agent import AgentRealm
    from calendarserver.tools.agent import InactivityDetector
    from twistedcaldav.test.util import TestCase
    from twisted.internet.task import Clock
    from twisted.web.resource import IResource
    from twisted.web.resource import ForbiddenResource

except ImportError:
    pass

else:
    class FakeRecord(object):

        def __init__(self, shortName):
            self.shortNames = [shortName]


    class AgentTestCase(TestCase):

        def test_AgentRealm(self):
            realm = AgentRealm("root", ["abc"])

            # Valid avatar
            _ignore_interface, resource, ignored = realm.requestAvatar(
                FakeRecord("abc"), None, IResource
            )
            self.assertEquals(resource, "root")

            # Not allowed avatar
            _ignore_interface, resource, ignored = realm.requestAvatar(
                FakeRecord("def"), None, IResource
            )
            self.assertTrue(isinstance(resource, ForbiddenResource))

            # Interface unhandled
            try:
                realm.requestAvatar(FakeRecord("def"), None, None)
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

        def authenticateUserDigest(
            self, ignored, node, username, challenge, response, method
        ):
            return self.authResponse

        ODNSerror = "Error"


    class FakeCredentials(object):

        def __init__(self, username, fields):
            self.username = username
            self.fields = fields
            self.method = "POST"
