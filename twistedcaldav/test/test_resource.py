##
# Copyright (c) 2008-2013 Apple Inc. All rights reserved.
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

from txdav.xml.element import HRef, Principal, Unauthenticated
from txweb2.http import HTTPError
from txweb2.test.test_server import SimpleRequest

from twisted.internet.defer import inlineCallbacks

from twistedcaldav import carddavxml
from twistedcaldav.config import config
from twistedcaldav.resource import CalDAVResource, CommonHomeResource, \
 CalendarHomeResource, AddressBookHomeResource
from twistedcaldav.test.util import InMemoryPropertyStore, StoreTestCase, \
    SimpleStoreRequest
from twistedcaldav.test.util import TestCase
from twistedcaldav.notifications import NotificationCollectionResource


class StubProperty(object):
    def qname(self):
        return "StubQnamespace", "StubQname"



class StubHome(object):
    def properties(self):
        return []


    def addNotifier(self, factory_name, notifier):
        pass


    def nodeName(self):
        return "xyzzy" if self.pushWorking else None


    def notifierID(self):
        return "xyzzy"


    def setPushWorking(self, status):
        self.pushWorking = status



class CalDAVResourceTests(TestCase):
    def setUp(self):
        TestCase.setUp(self)
        self.resource = CalDAVResource()
        self.resource._dead_properties = InMemoryPropertyStore()


    def test_writeDeadPropertyWritesProperty(self):
        prop = StubProperty()
        self.resource.writeDeadProperty(prop)
        self.assertEquals(self.resource._dead_properties.get(("StubQnamespace", "StubQname")),
                          prop)



class CommonHomeResourceTests(TestCase):

    def test_commonHomeliveProperties(self):
        resource = CommonHomeResource(None, None, None, StubHome())
        self.assertTrue(('http://calendarserver.org/ns/', 'push-transports') in resource.liveProperties())
        self.assertTrue(('http://calendarserver.org/ns/', 'pushkey') in resource.liveProperties())


    def test_calendarHomeliveProperties(self):
        resource = CalendarHomeResource(None, None, None, StubHome())
        self.assertTrue(('http://calendarserver.org/ns/', 'push-transports') in resource.liveProperties())
        self.assertTrue(('http://calendarserver.org/ns/', 'pushkey') in resource.liveProperties())


    def test_addressBookHomeliveProperties(self):
        resource = AddressBookHomeResource(None, None, None, StubHome())
        self.assertTrue(('http://calendarserver.org/ns/', 'push-transports') in resource.liveProperties())
        self.assertTrue(('http://calendarserver.org/ns/', 'pushkey') in resource.liveProperties())


    def test_notificationCollectionLiveProperties(self):
        resource = NotificationCollectionResource()
        self.assertTrue(('http://calendarserver.org/ns/', 'getctag') in resource.liveProperties())



class OwnershipTests(TestCase):
    """
    L{CalDAVResource.isOwner} determines if the authenticated principal of the
    given request is the owner of that resource.
    """

    @inlineCallbacks
    def test_isOwnerUnauthenticated(self):
        """
        L{CalDAVResource.isOwner} returns C{False} for unauthenticated requests.
        """
        site = None
        request = SimpleRequest(site, "GET", "/not/a/real/url/")
        request.authzUser = request.authnUser = Principal(Unauthenticated())
        rsrc = CalDAVResource()
        rsrc.owner = lambda igreq: HRef("/somebody/")
        self.assertEquals((yield rsrc.isOwner(request)), False)


    @inlineCallbacks
    def test_isOwnerNo(self):
        """
        L{CalDAVResource.isOwner} returns C{True} for authenticated requests
        with a principal that matches the resource's owner.
        """
        site = None
        request = SimpleRequest(site, "GET", "/not/a/real/url/")
        theOwner = Principal(HRef("/yes-i-am-the-owner/"))
        request.authzUser = request.authnUser = theOwner
        rsrc = CalDAVResource()
        rsrc.owner = lambda igreq: HRef("/no-i-am-not-the-owner/")
        self.assertEquals((yield rsrc.isOwner(request)), False)


    @inlineCallbacks
    def test_isOwnerYes(self):
        """
        L{CalDAVResource.isOwner} returns C{True} for authenticated requests
        with a principal that matches the resource's owner.
        """
        site = None
        request = SimpleRequest(site, "GET", "/not/a/real/url/")
        theOwner = Principal(HRef("/yes-i-am-the-owner/"))
        request.authzUser = request.authnUser = theOwner
        rsrc = CalDAVResource()
        rsrc.owner = lambda igreq: HRef("/yes-i-am-the-owner/")
        self.assertEquals((yield rsrc.isOwner(request)), True)


    @inlineCallbacks
    def test_isOwnerAdmin(self):
        """
        L{CalDAVResource.isOwner} returns C{True} for authenticated requests
        with a principal that matches any principal configured in the
        L{AdminPrincipals} list.
        """
        theAdmin = "/read-write-admin/"
        self.patch(config, "AdminPrincipals", [theAdmin])
        site = None
        request = SimpleRequest(site, "GET", "/not/a/real/url/")
        request.authzUser = request.authnUser = Principal(HRef(theAdmin))
        rsrc = CalDAVResource()
        rsrc.owner = lambda igreq: HRef("/some-other-user/")
        self.assertEquals((yield rsrc.isOwner(request)), True)


    @inlineCallbacks
    def test_isOwnerReadPrincipal(self):
        """
        L{CalDAVResource.isOwner} returns C{True} for authenticated requests
        with a principal that matches any principal configured in the
        L{AdminPrincipals} list.
        """
        theAdmin = "/read-only-admin/"
        self.patch(config, "ReadPrincipals", [theAdmin])
        site = None
        request = SimpleRequest(site, "GET", "/not/a/real/url/")
        request.authzUser = request.authnUser = Principal(HRef(theAdmin))
        rsrc = CalDAVResource()
        rsrc.owner = lambda igreq: HRef("/some-other-user/")
        self.assertEquals((yield rsrc.isOwner(request)), True)



class DefaultAddressBook (StoreTestCase):

    @inlineCallbacks
    def test_pick_default_addressbook(self):
        """
        Get adbk
        """

        request = SimpleStoreRequest(self, "GET", "/addressbooks/users/wsanchez/", authid="wsanchez")
        home = yield request.locateResource("/addressbooks/users/wsanchez")

        # default property initially not present
        try:
            home.readDeadProperty(carddavxml.DefaultAddressBookURL)
        except HTTPError:
            pass
        else:
            self.fail("carddavxml.DefaultAddressBookURL is not empty")

        yield home.pickNewDefaultAddressBook(request)

        try:
            default = home.readDeadProperty(carddavxml.DefaultAddressBookURL)
        except HTTPError:
            self.fail("carddavxml.DefaultAddressBookURL is not present")
        else:
            self.assertEqual(str(default.children[0]), "/addressbooks/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/addressbook/")


    @inlineCallbacks
    def test_fix_shared_default(self):
        # I think this would include a test of http_GET()
        raise NotImplementedError()
    test_fix_shared_default.todo = "Rewrite with real shared address book"
    '''
        """
        Get adbk
        """

        request = SimpleStoreRequest(self, "GET", "/addressbooks/users/wsanchez/", authid="wsanchez")
        home = yield request.locateResource("/addressbooks/users/wsanchez")

        # Create a new default adbk
        newadbk = yield request.locateResource("/addressbooks/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/newadbk/")
        yield newadbk.createAddressBookCollection()
        home.writeDeadProperty(carddavxml.DefaultAddressBookURL(
            HRef("/addressbooks/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/newadbk/")
        ))
        try:
            default = yield home.readProperty(carddavxml.DefaultAddressBookURL, request)
        except HTTPError:
            self.fail("carddavxml.DefaultAddressBookURL is not present")
        else:
            self.assertEqual(str(default.children[0]), "/addressbooks/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/newadbk/")

        # Force the new calendar to think it is a sharee collection
        newadbk._isShareeResource = True

        try:
            default = yield home.readProperty(carddavxml.DefaultAddressBookURL, request)
        except HTTPError:
            self.fail("carddavxml.DefaultAddressBookURL is not present")
        else:
            self.assertEqual(str(default.children[0]), "/addressbooks/__uids__/6423F94A-6B76-4A3A-815B-D52CFD77935D/addressbook/")
    '''
