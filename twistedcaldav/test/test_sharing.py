##
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
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

from txweb2 import responsecode
from txweb2.dav.util import allDataFromStream
from txweb2.http_headers import MimeType
from txweb2.iweb import IResponse
from txweb2.stream import MemoryStream

from twisted.internet.defer import inlineCallbacks, returnValue, succeed

from twistedcaldav import customxml
from twistedcaldav.config import config
from twistedcaldav.ical import Component
from twistedcaldav.test.test_cache import StubResponseCacheResource
from twistedcaldav.test.util import norequest, StoreTestCase, SimpleStoreRequest

from txdav.common.datastore.sql_tables import _BIND_MODE_DIRECT
from txdav.xml import element as davxml
from txdav.xml.parser import WebDAVDocument
from txdav.who.wiki import (
    DirectoryRecord as WikiDirectoryRecord,
    DirectoryService as WikiDirectoryService,
    WikiAccessLevel
)

from xml.etree.cElementTree import XML
import urlparse

sharedOwnerType = davxml.ResourceType.sharedownercalendar  # @UndefinedVariable
regularCalendarType = davxml.ResourceType.calendar  # @UndefinedVariable



def normalize(x):
    """
    Normalize some XML by parsing it, collapsing whitespace, and
    pretty-printing.
    """
    return WebDAVDocument.fromString(x).toxml()



class BaseSharingTests(StoreTestCase):

    def configure(self):
        """
        Override configuration hook to turn on sharing.
        """
        super(BaseSharingTests, self).configure()
        self.patch(config.Sharing, "Enabled", True)
        self.patch(config.Sharing.Calendars, "Enabled", True)
        self.patch(config.Authentication.Wiki, "Enabled", True)


    @inlineCallbacks
    def setUp(self):
        yield super(BaseSharingTests, self).setUp()
        self.resource = yield self._getResource()


    @inlineCallbacks
    def _refreshRoot(self, request=None):
        if request is None:
            request = norequest()
        result = yield super(BaseSharingTests, self)._refreshRoot(request)
        self.resource = (
            yield self.site.resource.locateChild(request, ["calendar"])
        )[0]
        self.site.resource.responseCache = StubResponseCacheResource()
        self.site.resource.putChild("calendars", self.homeProvisioner)
        returnValue(result)


    @inlineCallbacks
    def _doPOST(self, body, resultcode=responsecode.OK):
        authPrincipal = yield self.actualRoot.findPrincipalForAuthID("user01")
        request = SimpleStoreRequest(self, "POST", "/calendars/__uids__/user01/calendar/", content=body, authPrincipal=authPrincipal)
        request.headers.setHeader("content-type", MimeType("text", "xml"))
        response = yield self.send(request)
        response = IResponse(response)
        self.assertEqual(response.code, resultcode)

        # Reload resource
        self.resource = yield self._getResource()

        if response.stream:
            data = yield allDataFromStream(response.stream)
            returnValue(data)
        else:
            returnValue(None)


    @inlineCallbacks
    def _doPROPFINDHome(self, resultcode=responsecode.MULTI_STATUS):
        body = """<?xml version="1.0" encoding="UTF-8"?>
<A:propfind xmlns:A="DAV:">
  <A:prop>
    <A:add-member/>
    <C:allowed-sharing-modes xmlns:C="http://calendarserver.org/ns/"/>
    <D:autoprovisioned xmlns:D="http://apple.com/ns/ical/"/>
    <E:bulk-requests xmlns:E="http://me.com/_namespace/"/>
    <D:calendar-color xmlns:D="http://apple.com/ns/ical/"/>
    <B:calendar-description xmlns:B="urn:ietf:params:xml:ns:caldav"/>
    <B:calendar-free-busy-set xmlns:B="urn:ietf:params:xml:ns:caldav"/>
    <D:calendar-order xmlns:D="http://apple.com/ns/ical/"/>
    <B:calendar-timezone xmlns:B="urn:ietf:params:xml:ns:caldav"/>
    <A:current-user-privilege-set/>
    <B:default-alarm-vevent-date xmlns:B="urn:ietf:params:xml:ns:caldav"/>
    <B:default-alarm-vevent-datetime xmlns:B="urn:ietf:params:xml:ns:caldav"/>
    <A:displayname/>
    <C:getctag xmlns:C="http://calendarserver.org/ns/"/>
    <C:invite xmlns:C="http://calendarserver.org/ns/"/>
    <D:language-code xmlns:D="http://apple.com/ns/ical/"/>
    <D:location-code xmlns:D="http://apple.com/ns/ical/"/>
    <A:owner/>
    <C:pre-publish-url xmlns:C="http://calendarserver.org/ns/"/>
    <C:publish-url xmlns:C="http://calendarserver.org/ns/"/>
    <C:push-transports xmlns:C="http://calendarserver.org/ns/"/>
    <C:pushkey xmlns:C="http://calendarserver.org/ns/"/>
    <A:quota-available-bytes/>
    <A:quota-used-bytes/>
    <D:refreshrate xmlns:D="http://apple.com/ns/ical/"/>
    <A:resource-id/>
    <A:resourcetype/>
    <B:schedule-calendar-transp xmlns:B="urn:ietf:params:xml:ns:caldav"/>
    <B:schedule-default-calendar-URL xmlns:B="urn:ietf:params:xml:ns:caldav"/>
    <C:source xmlns:C="http://calendarserver.org/ns/"/>
    <C:subscribed-strip-alarms xmlns:C="http://calendarserver.org/ns/"/>
    <C:subscribed-strip-attachments xmlns:C="http://calendarserver.org/ns/"/>
    <C:subscribed-strip-todos xmlns:C="http://calendarserver.org/ns/"/>
    <B:supported-calendar-component-set xmlns:B="urn:ietf:params:xml:ns:caldav"/>
    <B:supported-calendar-component-sets xmlns:B="urn:ietf:params:xml:ns:caldav"/>
    <A:supported-report-set/>
    <A:sync-token/>
  </A:prop>
</A:propfind>
"""
        authPrincipal = yield self.actualRoot.findPrincipalForAuthID("user02")
        request = SimpleStoreRequest(self, "PROPFIND", "/calendars/__uids__/user02/", content=body, authPrincipal=authPrincipal)
        request.headers.setHeader("content-type", MimeType("text", "xml"))
        request.headers.setHeader("depth", "1")
        response = yield self.send(request)
        response = IResponse(response)
        self.assertEqual(response.code, resultcode)

        if response.stream:
            data = yield allDataFromStream(response.stream)
            returnValue(data)
        else:
            returnValue(None)


    @inlineCallbacks
    def _getResource(self):
        request = SimpleStoreRequest(self, "GET", "/calendars/__uids__/user01/calendar/")
        resource = yield request.locateResource("/calendars/__uids__/user01/calendar/")
        returnValue(resource)


    @inlineCallbacks
    def _doPOSTSharerAccept(self, body, resultcode=responsecode.OK, sharer="user02"):
        authPrincipal = yield self.actualRoot.findPrincipalForAuthID(sharer)
        request = SimpleStoreRequest(self, "POST", "/calendars/__uids__/{}/".format(sharer), content=body, authPrincipal=authPrincipal)
        request.headers.setHeader("content-type", MimeType("text", "xml"))
        response = yield self.send(request)
        response = IResponse(response)
        self.assertEqual(response.code, resultcode)

        if response.stream:
            xmldata = yield allDataFromStream(response.stream)
            doc = WebDAVDocument.fromString(xmldata)
            returnValue(doc)
        else:
            returnValue(None)


    @inlineCallbacks
    def _getResourceSharer(self, name):
        request = SimpleStoreRequest(self, "GET", "%s" % (name,))
        resource = yield request.locateResource("%s" % (name,))
        returnValue(resource)


    def _getUIDElementValue(self, xml):

        for user in xml.children:
            for element in user.children:
                if type(element) == customxml.UID:
                    return element.children[0].data
        return None


    def _getUIDElementValues(self, xml):

        results = {}
        for user in xml.children:
            href = str(user.childOfType(davxml.HRef))
            uid = str(user.childOfType(customxml.UID))
            results[href] = uid
        return results


    def _clearUIDElementValue(self, xml):

        for user in xml.children:
            uid = user.childOfType(customxml.UID)
            if uid is not None:
                uid.children[0].data = ""
        return xml


    def _getHRefElementValue(self, xml):

        for href in xml.root_element.children:
            if type(href) == davxml.HRef:
                return href.children[0].data
        return None



class SharingTests(BaseSharingTests):

    @inlineCallbacks
    def test_upgradeToShare(self):

        rtype = self.resource.resourceType()
        self.assertEquals(rtype, regularCalendarType)
        isShared = self.resource.isShared()
        self.assertFalse(isShared)
        isShareeResource = self.resource.isShareeResource()
        self.assertFalse(isShareeResource)

        yield self.resource.upgradeToShare()

        rtype = self.resource.resourceType()
        self.assertEquals(rtype, sharedOwnerType)
        isShared = self.resource.isShared()
        self.assertTrue(isShared)
        isShareeResource = self.resource.isShareeResource()
        self.assertFalse(isShareeResource)


    @inlineCallbacks
    def test_downgradeFromShare(self):

        yield self.resource.upgradeToShare()

        rtype = self.resource.resourceType()
        self.assertEquals(rtype, sharedOwnerType)
        isShared = self.resource.isShared()
        self.assertTrue(isShared)
        isShareeResource = self.resource.isShareeResource()
        self.assertFalse(isShareeResource)

        yield self.resource.downgradeFromShare(None)

        rtype = self.resource.resourceType()
        self.assertEquals(rtype, regularCalendarType)
        isShared = self.resource.isShared()
        self.assertFalse(isShared)
        isShareeResource = self.resource.isShareeResource()
        self.assertFalse(isShareeResource)


    @inlineCallbacks
    def test_POSTaddInviteeAlreadyShared(self):

        yield self.resource.upgradeToShare()

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
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            )
        ))

        isShared = self.resource.isShared()
        self.assertTrue(isShared)
        isShareeResource = self.resource.isShareeResource()
        self.assertFalse(isShareeResource)


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
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            )
        ))

        isShared = self.resource.isShared()
        self.assertTrue(isShared)
        isShareeResource = (yield self.resource.isShareeResource())
        self.assertFalse(isShareeResource)


    @inlineCallbacks
    def test_POSTupdateInvitee(self):

        isShared = self.resource.isShared()
        self.assertFalse(isShared)

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
            <CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
                <CS:set>
                    <D:href>mailto:user02@example.com</D:href>
                    <CS:summary>My Shared Calendar</CS:summary>
                    <CS:read-write/>
                </CS:set>
            </CS:share>
            """)

        isShared = self.resource.isShared()
        self.assertTrue(isShared)

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
            <CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
                <CS:set>
                    <D:href>mailto:user02@example.com</D:href>
                    <CS:summary>My Shared Calendar</CS:summary>
                    <CS:read/>
                </CS:set>
            </CS:share>
            """)

        isShared = self.resource.isShared()
        self.assertTrue(isShared)

        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadAccess()),
                customxml.InviteStatusNoResponse(),
            )
        ))


    @inlineCallbacks
    def test_POSTremoveInvitee(self):

        isShared = self.resource.isShared()
        self.assertFalse(isShared)

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
            <CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
                <CS:set>
                    <D:href>mailto:user02@example.com</D:href>
                    <CS:summary>My Shared Calendar</CS:summary>
                    <CS:read-write/>
                </CS:set>
            </CS:share>
            """)

        isShared = self.resource.isShared()
        self.assertTrue(isShared)

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
            <CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
                <CS:remove>
                    <D:href>mailto:user02@example.com</D:href>
                </CS:remove>
            </CS:share>
            """)

        isShared = self.resource.isShared()
        self.assertFalse(isShared)

        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(propInvite, None)


    @inlineCallbacks
    def test_POSTaddMoreInvitees(self):

        yield self.resource.upgradeToShare()

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
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user03"),
                customxml.CommonName.fromString("User 03"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user04"),
                customxml.CommonName.fromString("User 04"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))


    @inlineCallbacks
    def test_POSTaddRemoveInvitees(self):

        yield self.resource.upgradeToShare()

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
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user04"),
                customxml.CommonName.fromString("User 04"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))


    @inlineCallbacks
    def test_POSTaddRemoveSameInvitee(self):

        yield self.resource.upgradeToShare()

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
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user03"),
                customxml.CommonName.fromString("User 03"),
                customxml.InviteAccess(customxml.ReadAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))


    @inlineCallbacks
    def test_POSTremoveNonInvitee(self):
        """
        Ensure that removing a sharee that is not currently invited
        doesn't return an error.  The server will just pretend it
        removed the sharee.
        """

        yield self.resource.upgradeToShare()

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
            </CS:share>
            """)
        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
            <CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
                <CS:remove>
                    <D:href>mailto:user02@example.com</D:href>
                </CS:remove>
                <CS:remove>
                    <D:href>mailto:user03@example.com</D:href>
                </CS:remove>
            </CS:share>
            """)

        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(propInvite, None)


    @inlineCallbacks
    def test_POSTaddInvalidInvitee(self):
        yield self.resource.upgradeToShare()

        data = (yield self._doPOST(
            """<?xml version="1.0" encoding="utf-8" ?>
            <CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
                <CS:set>
                    <D:href>mailto:bogus@example.net</D:href>
                    <CS:summary>My Shared Calendar</CS:summary>
                    <CS:read-write/>
                </CS:set>
            </CS:share>
            """,
            responsecode.MULTI_STATUS
        ))
        self.assertXMLEquals(
            data,
            """<?xml version='1.0' encoding='UTF-8'?>
            <multistatus xmlns='DAV:'>
              <response>
                <href>mailto:bogus@example.net</href>
                <status>HTTP/1.1 403 Forbidden</status>
              </response>
            </multistatus>"""
        )
        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(propInvite, None)


    def assertXMLEquals(self, a, b):
        """
        Assert two strings are equivalent as XML.
        """
        self.assertEquals(normalize(a), normalize(b))


    @inlineCallbacks
    def test_POSTremoveInvalidInvitee(self):

        yield self.resource.upgradeToShare()

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
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            )
        ))

        record = yield self.userRecordWithShortName("user02")
        yield self.changeRecord(record, self.directory.fieldName.hasCalendars, False)

        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusInvalid(),
            )
        ))

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
            <CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
                <CS:remove>
                    <D:href>urn:x-uid:user02</D:href>
                </CS:remove>
            </CS:share>
            """)

        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(propInvite, None)


    @inlineCallbacks
    def wikiSetup(self):
        """
        Create a wiki called C{[wiki]testing}, and share it with the user whose
        home is at /.  Return the name of the newly shared calendar in the
        sharee's home.
        """

        wcreate = self._sqlCalendarStore.newTransaction("create wiki")
        yield wcreate.calendarHomeWithUID(
            u"{prefix}testing".format(prefix=WikiDirectoryService.uidPrefix),
            create=True
        )
        yield wcreate.commit()

        txn = self.transactionUnderTest()
        sharee = yield self.homeUnderTest(name="user01", create=True)
        sharer = yield txn.calendarHomeWithUID(
            u"{prefix}testing".format(prefix=WikiDirectoryService.uidPrefix),
        )
        cal = yield sharer.calendarWithName("calendar")
        sharedName = yield cal.shareWith(sharee, _BIND_MODE_DIRECT)
        returnValue(sharedName)


    @inlineCallbacks
    def test_wikiACL(self):
        """
        Ensure shareeAccessControlList( ) honors the access granted by the wiki
        to the sharee, so that delegates of the sharee get the same level of
        access.
        """
        sharedName = yield self.wikiSetup()
        access = WikiAccessLevel.read

        def stubAccessForRecord(*args):
            return succeed(access)

        self.patch(WikiDirectoryRecord, "accessForRecord", stubAccessForRecord)

        request = SimpleStoreRequest(self, "GET", "/calendars/__uids__/user01/")
        collection = yield request.locateResource("/calendars/__uids__/user01/" + sharedName)

        # Simulate the wiki server granting Read access
        acl = (yield collection.shareeAccessControlList(request))
        self.assertFalse("<write/>" in acl.toxml())

        # Simulate the wiki server granting Read-Write access
        access = WikiAccessLevel.write
        acl = (yield collection.shareeAccessControlList(request))
        self.assertTrue("<write/>" in acl.toxml())


    @inlineCallbacks
    def test_noWikiAccess(self):
        """
        If L{SharedResourceMixin.shareeAccessControlList} detects missing
        access controls for a directly shared collection, it will automatically
        un-share that collection.
        """
        sharedName = yield self.wikiSetup()
        access = WikiAccessLevel.write

        def stubAccessForRecord(*args):
            return succeed(access)

        self.patch(WikiDirectoryRecord, "accessForRecord", stubAccessForRecord)

        @inlineCallbacks
        def listChildrenViaPropfind():
            authPrincipal = yield self.actualRoot.findPrincipalForAuthID("user01")
            request = SimpleStoreRequest(self, "PROPFIND", "/calendars/__uids__/user01/", authPrincipal=authPrincipal)
            request.headers.setHeader("depth", "1")
            response = yield self.send(request)
            response = IResponse(response)
            data = yield allDataFromStream(response.stream)

            tree = XML(data)
            seq = [e.text for e in tree.findall("{DAV:}response/{DAV:}href")]
            shortest = min(seq, key=len)
            seq.remove(shortest)
            filtered = [elem[len(shortest):].rstrip("/") for elem in seq]
            returnValue(filtered)

        childNames = yield listChildrenViaPropfind()
        self.assertIn(sharedName, childNames)
        access = WikiAccessLevel.none
        childNames = yield listChildrenViaPropfind()
        self.assertNotIn(sharedName, childNames)


    @inlineCallbacks
    def test_POSTDowngradeWithMissingInvitee(self):

        yield self.resource.upgradeToShare()

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
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))

        yield self.directory.removeRecords(((yield self.userUIDFromShortName("user02")),))
        self.assertTrue((yield self.userUIDFromShortName("user02")) is None)

        yield self.resource.downgradeFromShare(norequest())


    @inlineCallbacks
    def test_POSTRemoveWithMissingInvitee(self):

        yield self.resource.upgradeToShare()

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
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))

        yield self.directory.removeRecords(((yield self.userUIDFromShortName("user02")),))
        self.assertTrue((yield self.userUIDFromShortName("user02")) is None)

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
            <CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
                <CS:remove>
                    <D:href>urn:x-uid:user02</D:href>
                </CS:remove>
            </CS:share>
            """)

        isShared = self.resource.isShared()
        self.assertFalse(isShared)

        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        self.assertEquals(propInvite, None)


    @inlineCallbacks
    def test_POSTShareeRemoveWithDisabledSharer(self):

        yield self.resource.upgradeToShare()

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
        uid = self._getUIDElementValue(propInvite)
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))

        result = (yield self._doPOSTSharerAccept("""<?xml version='1.0' encoding='UTF-8'?>
            <invite-reply xmlns='http://calendarserver.org/ns/'>
              <href xmlns='DAV:'>mailto:user01@example.com</href>
              <invite-accepted/>
              <hosturl>
                <href xmlns='DAV:'>/calendars/__uids__/user01/calendar/</href>
              </hosturl>
              <in-reply-to>%s</in-reply-to>
              <summary>The Shared Calendar</summary>
              <common-name>User 02</common-name>
              <first-name>user</first-name>
              <last-name>02</last-name>
            </invite-reply>
            """ % (uid,))
        )
        href = self._getHRefElementValue(result) + "/"

        record = yield self.userRecordWithShortName("user01")
        yield self.changeRecord(record, self.directory.fieldName.hasCalendars, False)

        resource = (yield self._getResourceSharer(href))
        yield resource.removeShareeResource(SimpleStoreRequest(self, "DELETE", href))

        resource = (yield self._getResourceSharer(href))
        self.assertFalse(resource.exists())


    @inlineCallbacks
    def test_POSTShareeRemoveWithMissingSharer(self):

        yield self.resource.upgradeToShare()

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
        uid = self._getUIDElementValue(propInvite)
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))

        result = (yield self._doPOSTSharerAccept("""<?xml version='1.0' encoding='UTF-8'?>
            <invite-reply xmlns='http://calendarserver.org/ns/'>
              <href xmlns='DAV:'>mailto:user01@example.com</href>
              <invite-accepted/>
              <hosturl>
                <href xmlns='DAV:'>/calendars/__uids__/user01/calendar/</href>
              </hosturl>
              <in-reply-to>%s</in-reply-to>
              <summary>The Shared Calendar</summary>
              <common-name>User 02</common-name>
              <first-name>user</first-name>
              <last-name>02</last-name>
            </invite-reply>
            """ % (uid,))
        )
        href = self._getHRefElementValue(result) + "/"

        yield self.directory.removeRecords(((yield self.userUIDFromShortName("user01")),))
        self.assertTrue((yield self.userUIDFromShortName("user01")) is None)

        resource = (yield self._getResourceSharer(href))
        yield resource.removeShareeResource(SimpleStoreRequest(self, "DELETE", href))

        resource = (yield self._getResourceSharer(href))
        self.assertFalse(resource.exists())


    @inlineCallbacks
    def test_POSTShareeAcceptNewWithMissingSharer(self):

        yield self.resource.upgradeToShare()

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
        uid = self._getUIDElementValue(propInvite)
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))

        yield self.directory.removeRecords(((yield self.userUIDFromShortName("user01")),))
        self.assertTrue((yield self.userUIDFromShortName("user01")) is None)

        yield self._doPOSTSharerAccept("""<?xml version='1.0' encoding='UTF-8'?>
            <invite-reply xmlns='http://calendarserver.org/ns/'>
              <href xmlns='DAV:'>mailto:user01@example.com</href>
              <invite-accepted/>
              <hosturl>
                <href xmlns='DAV:'>/calendars/__uids__/user01/calendar/</href>
              </hosturl>
              <in-reply-to>%s</in-reply-to>
              <summary>The Shared Calendar</summary>
              <common-name>User 02</common-name>
              <first-name>user</first-name>
              <last-name>02</last-name>
            </invite-reply>
            """ % (uid,),
            resultcode=responsecode.FORBIDDEN,
        )


    @inlineCallbacks
    def test_POSTShareeAcceptExistingWithMissingSharer(self):

        yield self.resource.upgradeToShare()

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
        uid = self._getUIDElementValue(propInvite)
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))

        yield self._doPOSTSharerAccept("""<?xml version='1.0' encoding='UTF-8'?>
            <invite-reply xmlns='http://calendarserver.org/ns/'>
              <href xmlns='DAV:'>mailto:user01@example.com</href>
              <invite-accepted/>
              <hosturl>
                <href xmlns='DAV:'>/calendars/__uids__/user01/calendar/</href>
              </hosturl>
              <in-reply-to>%s</in-reply-to>
              <summary>The Shared Calendar</summary>
              <common-name>User 02</common-name>
              <first-name>user</first-name>
              <last-name>02</last-name>
            </invite-reply>
            """ % (uid,),
            resultcode=responsecode.OK,
        )

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
        uid = self._getUIDElementValue(propInvite)
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadAccess()),
                customxml.InviteStatusAccepted(),
            ),
        ))

        yield self.directory.removeRecords(((yield self.userUIDFromShortName("user01")),))
        self.assertTrue((yield self.userUIDFromShortName("user01")) is None)

        yield self._doPOSTSharerAccept("""<?xml version='1.0' encoding='UTF-8'?>
            <invite-reply xmlns='http://calendarserver.org/ns/'>
              <href xmlns='DAV:'>mailto:user01@example.com</href>
              <invite-accepted/>
              <hosturl>
                <href xmlns='DAV:'>/calendars/__uids__/user01/calendar/</href>
              </hosturl>
              <in-reply-to>%s</in-reply-to>
              <summary>The Shared Calendar</summary>
              <common-name>User 02</common-name>
              <first-name>user</first-name>
              <last-name>02</last-name>
            </invite-reply>
            """ % (uid,),
            resultcode=responsecode.OK,
        )


    @inlineCallbacks
    def test_POSTShareeDeclineNewWithMissingSharer(self):

        yield self.resource.upgradeToShare()

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
        uid = self._getUIDElementValue(propInvite)
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))

        yield self.directory.removeRecords(((yield self.userUIDFromShortName("user01")),))
        self.assertTrue((yield self.userUIDFromShortName("user01")) is None)

        yield self._doPOSTSharerAccept("""<?xml version='1.0' encoding='UTF-8'?>
            <invite-reply xmlns='http://calendarserver.org/ns/'>
              <href xmlns='DAV:'>mailto:user01@example.com</href>
              <invite-declined/>
              <hosturl>
                <href xmlns='DAV:'>/calendars/__uids__/user01/calendar/</href>
              </hosturl>
              <in-reply-to>%s</in-reply-to>
              <summary>The Shared Calendar</summary>
              <common-name>User 02</common-name>
              <first-name>user</first-name>
              <last-name>02</last-name>
            </invite-reply>
            """ % (uid,),
            resultcode=responsecode.NO_CONTENT,
        )


    @inlineCallbacks
    def test_POSTShareeDeclineExistingWithMissingSharer(self):

        yield self.resource.upgradeToShare()

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
        uid = self._getUIDElementValue(propInvite)
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))

        yield self._doPOSTSharerAccept("""<?xml version='1.0' encoding='UTF-8'?>
            <invite-reply xmlns='http://calendarserver.org/ns/'>
              <href xmlns='DAV:'>mailto:user01@example.com</href>
              <invite-accepted/>
              <hosturl>
                <href xmlns='DAV:'>/calendars/__uids__/user01/calendar/</href>
              </hosturl>
              <in-reply-to>%s</in-reply-to>
              <summary>The Shared Calendar</summary>
              <common-name>User 02</common-name>
              <first-name>user</first-name>
              <last-name>02</last-name>
            </invite-reply>
            """ % (uid,),
            resultcode=responsecode.OK,
        )

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
        uid = self._getUIDElementValue(propInvite)
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadAccess()),
                customxml.InviteStatusAccepted(),
            ),
        ))

        yield self.directory.removeRecords(((yield self.userUIDFromShortName("user01")),))
        self.assertTrue((yield self.userUIDFromShortName("user01")) is None)

        yield self._doPOSTSharerAccept("""<?xml version='1.0' encoding='UTF-8'?>
            <invite-reply xmlns='http://calendarserver.org/ns/'>
              <href xmlns='DAV:'>mailto:user01@example.com</href>
              <invite-declined/>
              <hosturl>
                <href xmlns='DAV:'>/calendars/__uids__/user01/calendar/</href>
              </hosturl>
              <in-reply-to>%s</in-reply-to>
              <summary>The Shared Calendar</summary>
              <common-name>User 02</common-name>
              <first-name>user</first-name>
              <last-name>02</last-name>
            </invite-reply>
            """ % (uid,),
            resultcode=responsecode.NO_CONTENT,
        )


    @inlineCallbacks
    def test_shareeInviteWithDisabledSharer(self):

        yield self.resource.upgradeToShare()

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
        uid = self._getUIDElementValue(propInvite)
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))

        result = (yield self._doPOSTSharerAccept("""<?xml version='1.0' encoding='UTF-8'?>
            <invite-reply xmlns='http://calendarserver.org/ns/'>
              <href xmlns='DAV:'>mailto:user01@example.com</href>
              <invite-accepted/>
              <hosturl>
                <href xmlns='DAV:'>/calendars/__uids__/user01/calendar/</href>
              </hosturl>
              <in-reply-to>%s</in-reply-to>
              <summary>The Shared Calendar</summary>
              <common-name>User 02</common-name>
              <first-name>user</first-name>
              <last-name>02</last-name>
            </invite-reply>
            """ % (uid,))
        )
        href = self._getHRefElementValue(result) + "/"

        record = yield self.userRecordWithShortName("user01")
        yield self.changeRecord(record, self.directory.fieldName.hasCalendars, False)

        data = yield self._doPROPFINDHome()
        self.assertTrue(data is not None)

        resource = (yield self._getResourceSharer(href))
        propInvite = yield resource.inviteProperty(None)
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.Organizer(
                davxml.HRef.fromString("/principals/__uids__/user01/"),
                customxml.CommonName.fromString("User 01"),
            ),
            customxml.InviteUser(
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusAccepted(),
            ),
        ))


    @inlineCallbacks
    def test_shareeInviteWithMissingSharer(self):

        yield self.resource.upgradeToShare()

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
        uid = self._getUIDElementValue(propInvite)
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))

        result = (yield self._doPOSTSharerAccept("""<?xml version='1.0' encoding='UTF-8'?>
            <invite-reply xmlns='http://calendarserver.org/ns/'>
              <href xmlns='DAV:'>mailto:user01@example.com</href>
              <invite-accepted/>
              <hosturl>
                <href xmlns='DAV:'>/calendars/__uids__/user01/calendar/</href>
              </hosturl>
              <in-reply-to>%s</in-reply-to>
              <summary>The Shared Calendar</summary>
              <common-name>User 02</common-name>
              <first-name>user</first-name>
              <last-name>02</last-name>
            </invite-reply>
            """ % (uid,))
        )
        href = self._getHRefElementValue(result) + "/"

        yield self.directory.removeRecords(((yield self.userUIDFromShortName("user01")),))
        self.assertTrue((yield self.userUIDFromShortName("user01")) is None)

        data = yield self._doPROPFINDHome()
        self.assertTrue(data is not None)

        resource = (yield self._getResourceSharer(href))
        propInvite = yield resource.inviteProperty(None)
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.Organizer(
                davxml.HRef.fromString("invalid"),
                customxml.CommonName.fromString("Invalid"),
            ),
            customxml.InviteUser(
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusAccepted(),
            ),
        ))


    @inlineCallbacks
    def test_shareeNotificationWithMissingSharer(self):

        yield self.resource.upgradeToShare()

        yield self._doPOST("""<?xml version="1.0" encoding="utf-8" ?>
            <CS:share xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
                <CS:set>
                    <D:href>mailto:user02@example.com</D:href>
                    <CS:summary>My Shared Calendar</CS:summary>
                    <CS:read-write/>
                </CS:set>
            </CS:share>
            """)

        yield self.directory.removeRecords(((yield self.userUIDFromShortName("user01")),))
        self.assertTrue((yield self.userUIDFromShortName("user01")) is None)

        request = SimpleStoreRequest(self, "GET", "/calendars/__uids__/user02/notification/")
        notification = yield request.locateResource("/calendars/__uids__/user02/notification/")
        names = yield notification.listChildren()
        self.assertEqual(len(names), 1)
        note_child = yield notification.getChild(names[0])
        note = yield note_child.text()
        self.assertTrue(isinstance(note, str))


    @inlineCallbacks
    def test_hideInvalidSharers(self):

        yield self.resource.upgradeToShare()

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

        propInvite = (yield self.resource.readProperty(customxml.Invite, None))
        uids = self._getUIDElementValues(propInvite)
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user03"),
                customxml.CommonName.fromString("User 03"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusNoResponse(),
            ),
        ))

        yield self._doPOSTSharerAccept("""<?xml version='1.0' encoding='UTF-8'?>
            <invite-reply xmlns='http://calendarserver.org/ns/'>
              <href xmlns='DAV:'>mailto:user01@example.com</href>
              <invite-accepted/>
              <hosturl>
                <href xmlns='DAV:'>/calendars/__uids__/user01/calendar/</href>
              </hosturl>
              <in-reply-to>%s</in-reply-to>
              <summary>The Shared Calendar</summary>
              <common-name>User 02</common-name>
              <first-name>user</first-name>
              <last-name>02</last-name>
            </invite-reply>
            """ % (uids["urn:x-uid:user02"],))

        yield self._doPOSTSharerAccept(
            """<?xml version='1.0' encoding='UTF-8'?>
                <invite-reply xmlns='http://calendarserver.org/ns/'>
                  <href xmlns='DAV:'>mailto:user01@example.com</href>
                  <invite-accepted/>
                  <hosturl>
                    <href xmlns='DAV:'>/calendars/__uids__/user01/calendar/</href>
                  </hosturl>
                  <in-reply-to>%s</in-reply-to>
                  <summary>The Shared Calendar</summary>
                  <common-name>User 03</common-name>
                  <first-name>user</first-name>
                  <last-name>03</last-name>
                </invite-reply>
            """ % (uids["urn:x-uid:user03"],),
            sharer="user03"
        )

        record = yield self.directory.recordWithUID((yield self.userUIDFromShortName("user02")))
        yield self.changeRecord(record, self.directory.fieldName.hasCalendars, False)

        resource = yield self._getResource()
        propInvite = yield resource.inviteProperty(None)
        self.assertEquals(self._clearUIDElementValue(propInvite), customxml.Invite(
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user02"),
                customxml.CommonName.fromString("User 02"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusInvalid(),
            ),
            customxml.InviteUser(
                customxml.UID.fromString(""),
                davxml.HRef.fromString("urn:x-uid:user03"),
                customxml.CommonName.fromString("User 03"),
                customxml.InviteAccess(customxml.ReadWriteAccess()),
                customxml.InviteStatusAccepted(),
            ),
        ))



class DropboxSharingTests(BaseSharingTests):

    def configure(self):
        """
        Override configuration hook to turn on dropbox.
        """
        super(DropboxSharingTests, self).configure()
        self.patch(config, "EnableDropBox", True)
        self.patch(config, "EnableManagedAttachments", False)


    @inlineCallbacks
    def test_dropboxWithMissingInvitee(self):

        yield self.resource.upgradeToShare()

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
        uid = self._getUIDElementValue(propInvite)

        yield self._doPOSTSharerAccept("""<?xml version='1.0' encoding='UTF-8'?>
            <invite-reply xmlns='http://calendarserver.org/ns/'>
              <href xmlns='DAV:'>mailto:user01@example.com</href>
              <invite-accepted/>
              <hosturl>
                <href xmlns='DAV:'>/calendars/__uids__/user01/calendar/</href>
              </hosturl>
              <in-reply-to>%s</in-reply-to>
              <summary>The Shared Calendar</summary>
              <common-name>User 02</common-name>
              <first-name>user</first-name>
              <last-name>02</last-name>
            </invite-reply>
            """ % (uid,)
        )

        calendar = yield self.calendarUnderTest(name="calendar", home="user01")
        component = Component.fromString("""BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20060101T100000Z
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
ATTACH;VALUE=URI:/calendars/users/home1/some-dropbox-id/some-dropbox-id/caldavd.plist
X-APPLE-DROPBOX:/calendars/users/home1/dropbox/some-dropbox-id
END:VEVENT
END:VCALENDAR
""")
        yield calendar.createCalendarObjectWithName("dropbox.ics", component)
        yield self.commit()

        yield self.directory.removeRecords(((yield self.userUIDFromShortName("user02")),))
        self.assertTrue((yield self.userUIDFromShortName("user02")) is None)

        # Get dropbox and test ACLs
        request = SimpleStoreRequest(self, "GET", "/calendars/__uids__/user01/dropbox/some-dropbox-id/")
        resource = yield request.locateResource("/calendars/__uids__/user01/dropbox/some-dropbox-id/")
        acl = yield resource.accessControlList(request)
        self.assertTrue(acl is not None)



class MamnagedAttachmentSharingTests(BaseSharingTests):

    def configure(self):
        """
        Override configuration hook to turn on managed attachments.
        """
        super(MamnagedAttachmentSharingTests, self).configure()
        self.patch(config, "EnableDropBox", False)
        self.patch(config, "EnableManagedAttachments", True)


    @inlineCallbacks
    def test_attachmentWithMissingInvitee(self):

        yield self.resource.upgradeToShare()

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
        uid = self._getUIDElementValue(propInvite)

        yield self._doPOSTSharerAccept("""<?xml version='1.0' encoding='UTF-8'?>
            <invite-reply xmlns='http://calendarserver.org/ns/'>
              <href xmlns='DAV:'>mailto:user01@example.com</href>
              <invite-accepted/>
              <hosturl>
                <href xmlns='DAV:'>/calendars/__uids__/user01/calendar/</href>
              </hosturl>
              <in-reply-to>%s</in-reply-to>
              <summary>The Shared Calendar</summary>
              <common-name>User 02</common-name>
              <first-name>user</first-name>
              <last-name>02</last-name>
            </invite-reply>
            """ % (uid,)
        )

        calendar = yield self.calendarUnderTest(name="calendar", home="user01")
        component = Component.fromString("""BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART:20060101T100000Z
DURATION:PT1H
SUMMARY:event 1
UID:event1@ninevah.local
END:VEVENT
END:VCALENDAR
""")
        obj = yield calendar.createCalendarObjectWithName("dropbox.ics", component)
        _ignore_attachment, location = yield obj.addAttachment(None, MimeType("text", "plain"), "new.txt", MemoryStream("new attachment text"))
        yield self.commit()

        yield self.directory.removeRecords(((yield self.userUIDFromShortName("user02")),))
        self.assertTrue((yield self.userUIDFromShortName("user02")) is None)

        # Get dropbox and test ACLs
        location = urlparse.urlparse(location)[2]
        location = "/".join(location.split("/")[:-1])
        request = SimpleStoreRequest(self, "GET", location)
        resource = yield request.locateResource(location)
        acl = yield resource.accessControlList(request)
        self.assertTrue(acl is not None)
