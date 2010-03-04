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


from twistedcaldav.test.util import InMemoryPropertyStore
from twistedcaldav.test.util import TestCase
from twext.web2.dav import davxml
from twistedcaldav.static import CalDAVFile
from twistedcaldav import customxml
from twisted.internet.defer import inlineCallbacks, returnValue
import os
from twistedcaldav.config import config
from twext.web2.test.test_server import SimpleRequest
from twext.web2.stream import MemoryStream
from twext.web2.http_headers import MimeType
from twext.web2 import responsecode


class SharingTests(TestCase):
    def setUp(self):
        TestCase.setUp(self)
        config.EnableSharing = True

        collection = self.mktemp()
        os.mkdir(collection)
        self.resource = CalDAVFile(collection, self.site.resource)
        self.resource._dead_properties = InMemoryPropertyStore()
        self.site.resource.putChild("calendar", self.resource)

    @inlineCallbacks
    def _doPOST(self, body):
        request = SimpleRequest(self.site, "POST", "/calendar/")
        request.headers.setHeader("content-type", MimeType("text", "xml"))
        request.stream = MemoryStream(body)

        response = (yield self.send(request, None))
        self.assertEqual(response.code, responsecode.OK)

    def _clearUIDElementValue(self, xml):
        
        for user in xml.children:
            for element in user.children:
                if type(element) == customxml.UID:
                    element.children[0].data = ""
        return xml

    @inlineCallbacks
    def test_upgradeToShare(self):
        self.resource.writeDeadProperty(davxml.ResourceType.calendar)
        self.assertEquals(self.resource.resourceType(), davxml.ResourceType.calendar)
        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(propInvite, None)

        yield self.resource.upgradeToShare(None)

        self.assertEquals(self.resource.resourceType(), davxml.ResourceType.sharedcalendar)
        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(propInvite, customxml.Invite())
        
        isShared = (yield self.resource.isShared(None))
        self.assertTrue(isShared)
        isVShared = (yield self.resource.isVirtualShare(None))
        self.assertFalse(isVShared)

    @inlineCallbacks
    def test_downgradeFromShare(self):
        self.resource.writeDeadProperty(davxml.ResourceType.sharedcalendar)
        self.resource.writeDeadProperty(customxml.Invite())
        self.assertEquals(self.resource.resourceType(), davxml.ResourceType.sharedcalendar)
        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(propInvite, customxml.Invite())

        yield self.resource.downgradeFromShare(None)

        self.assertEquals(self.resource.resourceType(), davxml.ResourceType.calendar)
        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(propInvite, None)
        
        isShared = (yield self.resource.isShared(None))
        self.assertFalse(isShared)
        isVShared = (yield self.resource.isVirtualShare(None))
        self.assertFalse(isVShared)

    @inlineCallbacks
    def test_POSTaddInviteeAlreadyShared(self):
        
        yield self.resource.upgradeToShare(None)

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
<CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <CS:set>
        <D:href>mailto:user02@example.com</D:href>
        <CS:summary>My Shared Calendar</CS:summary>
        <CS:read-write/>
    </CS:set>
</CS:share>
""")

        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("mailto:user02@example.com"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            )
        ))
        
        isShared = (yield self.resource.isShared(None))
        self.assertTrue(isShared)
        isVShared = (yield self.resource.isVirtualShare(None))
        self.assertFalse(isVShared)

    @inlineCallbacks
    def test_POSTaddInviteeNotAlreadyShared(self):
        
        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
<CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <CS:set>
        <D:href>mailto:user02@example.com</D:href>
        <CS:summary>My Shared Calendar</CS:summary>
        <CS:read-write/>
    </CS:set>
</CS:share>
""")

        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("mailto:user02@example.com"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            )
        ))
        
        isShared = (yield self.resource.isShared(None))
        self.assertTrue(isShared)
        isVShared = (yield self.resource.isVirtualShare(None))
        self.assertFalse(isVShared)

    @inlineCallbacks
    def test_POSTupdateInvitee(self):
        
        yield self.resource.upgradeToShare(None)

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
<CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <CS:set>
        <D:href>mailto:user02@example.com</D:href>
        <CS:summary>My Shared Calendar</CS:summary>
        <CS:read-write/>
    </CS:set>
</CS:share>
""")

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
<CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <CS:set>
        <D:href>mailto:user02@example.com</D:href>
        <CS:summary>My Shared Calendar</CS:summary>
        <CS:read/>
    </CS:set>
</CS:share>
""")

        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("mailto:user02@example.com"),
                customxml.InviteAccess(customxml.ReadAccess()),
                customxml.InviteStatusNoResponse(),
            )
        ))

    @inlineCallbacks
    def test_POSTremoveInvitee(self):
        
        yield self.resource.upgradeToShare(None)

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
<CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <CS:set>
        <D:href>mailto:user02@example.com</D:href>
        <CS:summary>My Shared Calendar</CS:summary>
        <CS:read-write/>
    </CS:set>
</CS:share>
""")

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
<CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <CS:remove>
        <D:href>mailto:user02@example.com</D:href>
    </CS:remove>
</CS:share>
""")

        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite())

    @inlineCallbacks
    def test_POSTaddMoreInvitees(self):
        
        yield self.resource.upgradeToShare(None)

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
<CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <CS:set>
        <D:href>mailto:user02@example.com</D:href>
        <CS:summary>My Shared Calendar</CS:summary>
        <CS:read-write/>
    </CS:set>
</CS:share>
""")
        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
<CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <CS:set>
        <D:href>mailto:user03@example.com</D:href>
        <CS:summary>Your Shared Calendar</CS:summary>
        <CS:read-write/>
    </CS:set>
    <CS:set>
        <D:href>mailto:user04@example.com</D:href>
        <CS:summary>Your Shared Calendar</CS:summary>
        <CS:read-write/>
    </CS:set>
</CS:share>
""")

        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("mailto:user02@example.com"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("mailto:user03@example.com"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("mailto:user04@example.com"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))

    @inlineCallbacks
    def test_POSTaddRemoveInvitees(self):
        
        yield self.resource.upgradeToShare(None)

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
<CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <CS:set>
        <D:href>mailto:user02@example.com</D:href>
        <CS:summary>My Shared Calendar</CS:summary>
        <CS:read-write/>
    </CS:set>
    <CS:set>
        <D:href>mailto:user03@example.com</D:href>
        <CS:summary>My Shared Calendar</CS:summary>
        <CS:read-write/>
    </CS:set>
</CS:share>
""")
        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
<CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <CS:remove>
        <D:href>mailto:user03@example.com</D:href>
    </CS:remove>
    <CS:set>
        <D:href>mailto:user04@example.com</D:href>
        <CS:summary>Your Shared Calendar</CS:summary>
        <CS:read-write/>
    </CS:set>
</CS:share>
""")

        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("mailto:user02@example.com"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("mailto:user04@example.com"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))

    @inlineCallbacks
    def test_POSTaddRemoveSameInvitee(self):
        
        yield self.resource.upgradeToShare(None)

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
<CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <CS:set>
        <D:href>mailto:user02@example.com</D:href>
        <CS:summary>My Shared Calendar</CS:summary>
        <CS:read-write/>
    </CS:set>
    <CS:set>
        <D:href>mailto:user03@example.com</D:href>
        <CS:summary>My Shared Calendar</CS:summary>
        <CS:read-write/>
    </CS:set>
</CS:share>
""")
        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
<CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <CS:remove>
        <D:href>mailto:user03@example.com</D:href>
    </CS:remove>
    <CS:set>
        <D:href>mailto:user03@example.com</D:href>
        <CS:summary>Your Shared Calendar</CS:summary>
        <CS:read/>
    </CS:set>
</CS:share>
""")

        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("mailto:user02@example.com"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("mailto:user03@example.com"),
                customxml.InviteAccess(customxml.ReadAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))
