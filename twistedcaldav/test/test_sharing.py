##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks, returnValue, succeed

from twistedcaldav import customxml
from twistedcaldav.config import config
from twistedcaldav.test.test_cache import StubResponseCacheResource
from twistedcaldav.test.util import norequest, StoreTestCase, SimpleStoreRequest

from txdav.common.datastore.sql_tables import _BIND_MODE_DIRECT
from txdav.xml import element as davxml
from txdav.xml.parser import WebDAVDocument

from xml.etree.cElementTree import XML
from txdav.who.wiki import (
    DirectoryRecord as WikiDirectoryRecord,
    DirectoryService as WikiDirectoryService,
    WikiAccessLevel
)

sharedOwnerType = davxml.ResourceType.sharedownercalendar  # @UndefinedVariable
regularCalendarType = davxml.ResourceType.calendar  # @UndefinedVariable



def normalize(x):
    """
    Normalize some XML by parsing it, collapsing whitespace, and
    pretty-printing.
    """
    return WebDAVDocument.fromString(x).toxml()



class SharingTests(StoreTestCase):

    def configure(self):
        """
        Override configuration hook to turn on sharing.
        """
        super(SharingTests, self).configure()
        self.patch(config.Sharing, "Enabled", True)
        self.patch(config.Sharing.Calendars, "Enabled", True)
        self.patch(config.Authentication.Wiki, "Enabled", True)


    @inlineCallbacks
    def setUp(self):
        yield super(SharingTests, self).setUp()
        self.resource = yield self._getResource()


    @inlineCallbacks
    def _refreshRoot(self, request=None):
        if request is None:
            request = norequest()
        result = yield super(SharingTests, self)._refreshRoot(request)
        self.resource = (
            yield self.site.resource.locateChild(request, ["calendar"])
        )[0]
        self.site.resource.responseCache = StubResponseCacheResource()
        self.site.resource.putChild("calendars", self.homeProvisioner)
        returnValue(result)


    @inlineCallbacks
    def _doPOST(self, body, resultcode=responsecode.OK):
        authRecord = yield self.directory.recordWithUID(u"user01")
        request = SimpleStoreRequest(self, "POST", "/calendars/__uids__/user01/calendar/", content=body, authRecord=authRecord)
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
    def _getResource(self):
        request = SimpleStoreRequest(self, "GET", "/calendars/__uids__/user01/calendar/")
        resource = yield request.locateResource("/calendars/__uids__/user01/calendar/")
        returnValue(resource)


    @inlineCallbacks
    def _doPOSTSharerAccept(self, body, resultcode=responsecode.OK, sharer="user02"):
        authRecord = yield self.directory.recordWithUID(unicode(sharer))
        request = SimpleStoreRequest(self, "POST", "/calendars/__uids__/{}/".format(sharer), content=body, authRecord=authRecord)
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
            authRecord = yield self.directory.recordWithUID(u"user01")
            request = SimpleStoreRequest(self, "PROPFIND", "/calendars/__uids__/user01/", authRecord=authRecord)
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
