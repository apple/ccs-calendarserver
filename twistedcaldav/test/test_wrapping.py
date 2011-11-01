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

"""
Tests for the interaction between model-level and protocol-level logic.
"""


from twext.web2.server import Request
from twext.web2.responsecode import UNAUTHORIZED
from twext.web2.http_headers import Headers
from twext.enterprise.ienterprise import AlreadyFinishedError

from twext.web2.dav import davxml
from twistedcaldav.config import config

from twisted.internet.defer import inlineCallbacks, returnValue

from twistedcaldav.ical import Component as VComponent
from twistedcaldav.vcard import Component as VCComponent

from twistedcaldav.storebridge import DropboxCollection,\
    CalendarCollectionResource, AddressBookCollectionResource

from twistedcaldav.test.util import TestCase

from txdav.idav import IDataStore
from txdav.caldav.datastore.test.test_file import event4_text

from txdav.carddav.datastore.test.test_file import vcard4_text

from txdav.common.datastore.test.util import buildStore, assertProvides,\
    StubNotifierFactory


from twext.web2.http import HTTPError
from twext.web2.responsecode import INSUFFICIENT_STORAGE_SPACE
from twext.web2.stream import MemoryStream
from txdav.common.datastore.test.util import deriveQuota
from twistedcaldav.test.util import patchConfig
from twistedcaldav.directory.test.test_xmlfile import XMLFileBase
from txdav.caldav.icalendarstore import ICalendarHome
from txdav.carddav.iaddressbookstore import IAddressBookHome



class FakeChanRequest(object):
    code = 'request-not-finished'

    def writeHeaders(self, code, headers):
        self.code = code
        self.headers = headers
    def registerProducer(self, producer, streaming):
        pass
    def write(self, data):
        pass
    def unregisterProducer(self):
        pass
    def abortConnection(self):
        pass
    def getHostInfo(self):
        return '127.0.0.1', False
    def getRemoteHost(self):
        return '127.0.0.1'
    def finish(self):
        pass

    remoteAddr = '127.0.0.1'



class WrappingTests(TestCase):
    """
    Tests for L{twistedcaldav.static.CalDAVResource} creating the appropriate type
    of txdav.caldav.datastore.file underlying object when it can determine what
    type it really represents.
    """

    def setUp(self):
        # Mostly copied from
        # twistedcaldav.directory.test.test_calendar.ProvisionedCalendars; this
        # should probably be refactored, perhaps even to call (some part of) the
        # actual root-resource construction logic?
        super(WrappingTests, self).setUp()

        # Setup the initial directory
        self.createStockDirectoryService()
        self.setupCalendars()


    @inlineCallbacks
    def populateOneObject(self, objectName, objectText):
        """
        Populate one calendar object in the test user's calendar.

        @param objectName: The name of a calendar object.
        @type objectName: str
        @param objectText: Some iCalendar text to populate it with.
        @type objectText: str
        """
        record = self.directoryService.recordWithShortName("users", "wsanchez")
        uid = record.uid
        # XXX there should be a more test-friendly way to ensure the directory
        # actually exists
        try:
            self.calendarCollection._newStore._path.createDirectory()
        except:
            pass
        txn = self.calendarCollection._newStore.newTransaction()
        home = yield txn.calendarHomeWithUID(uid, True)
        cal = yield home.calendarWithName("calendar")
        yield cal.createCalendarObjectWithName(
            objectName, VComponent.fromString(objectText)
        )
        yield txn.commit()


    @inlineCallbacks
    def populateOneAddressBookObject(self, objectName, objectText):
        """
        Populate one addressbook object in the test user's addressbook.

        @param objectName: The name of a addressbook object.
        @type objectName: str
        @param objectText: Some iVcard text to populate it with.
        @type objectText: str
        """
        record = self.directoryService.recordWithShortName("users", "wsanchez")
        uid = record.uid
        # XXX there should be a more test-friendly way to ensure the directory
        # actually exists
        try:
            self.addressbookCollection._newStore._path.createDirectory()
        except:
            pass
        txn = self.addressbookCollection._newStore.newTransaction()
        home = yield txn.addressbookHomeWithUID(uid, True)
        adbk = yield home.addressbookWithName("addressbook")
        if adbk is None:
            yield home.createAddressBookWithName("addressbook")
            adbk = yield home.addressbookWithName("addressbook")
        yield adbk.createAddressBookObjectWithName(
            objectName, VCComponent.fromString(objectText)
        )
        yield txn.commit()


    requestUnderTest = None

    @inlineCallbacks
    def getResource(self, path, method='GET', user=None):
        """
        Retrieve a resource from the site.

        @param path: the path from the root of the site (not starting with a
            slash)

        @type path: C{str}

        @param method: the HTTP method to initialize the request with.
            Defaults to GET.  (This should I{mostly} be irrelevant to path
            traversal, but may be interesting to subsequent operations on
            C{self.requestUnderTest}).

        @param user: the username (shortname in the test XML file) of the user
            to forcibly authenticate this request as.

        @return: a L{Deferred} that fires with an L{IResource}.
        """
        if self.requestUnderTest is None:
            req = self.requestForPath(path, method)
            self.requestUnderTest = req
        else:
            # How should this handle mismatched methods?
            req = self.requestUnderTest
        aResource = yield req.locateResource(
            "http://localhost:8008/" + path
        )
        if user is not None:
            guid = XMLFileBase.users[user]["guid"]
            req.authnUser = req.authzUser = (
                davxml.Principal(davxml.HRef('/principals/__uids__/' + guid + '/'))
            )
        returnValue(aResource)


    def commit(self):
        """
        Since C{getResource} treats this test case as a resource, it will have
        an associated transaction.  Commit that transaction to bring the
        filesystem into a consistent state.
        """
        return self.requestUnderTest._newStoreTransaction.commit()


    def requestForPath(self, path, method='GET'):
        """
        Get a L{Request} with a L{FakeChanRequest} for a given path and method.
        """
        headers = Headers()
        headers.addRawHeader("Host", "localhost:8008")
        chanReq = FakeChanRequest()
        req = Request(
            site=self.site,
            chanRequest=chanReq,
            command=method,
            path=path,
            version=('1', '1'),
            contentLength=0,
            headers=headers
        )

        # 'process()' normally sets these.  Shame on web2, having so much
        # partially-initialized stuff floating around.
        req.remoteAddr = '127.0.0.1'
        req.path = path
        req.credentialFactories = {}
        return req


    pathTypes = ['calendar', 'addressbook']


    @inlineCallbacks
    def test_autoRevertUnCommitted(self):
        """
        Resources that need to read from the back-end in a transaction will be
        reverted by a response filter in the case where the request does not
        commit them.  This can happen, for example, with resources that are
        children of non-existent (proto-)resources.
        """
        for pathType in self.pathTypes:
            req = self.requestForPath('/%ss/users/wsanchez/%s/forget/it'
                                      % (pathType, pathType))
            yield req.process()
            self.assertEquals(req.chanRequest.code, 404)
            self.assertRaises(AlreadyFinishedError,
                              req._newStoreTransaction.commit)


    @inlineCallbacks
    def test_simpleRequest(self):
        """
        Sanity check and integration test: an unauthorized request of calendar
        and addressbook resources results in an L{UNAUTHORIZED} response code.
        """
        for pathType in self.pathTypes:
            req = self.requestForPath('/%ss/users/wsanchez/%s/'
                                      % (pathType, pathType))
            yield req.process()
            self.assertEquals(req.chanRequest.code, UNAUTHORIZED)


    def test_createStore(self):
        """
        Creating a DirectoryCalendarHomeProvisioningResource will create a paired
        CalendarStore.
        """
        assertProvides(self, IDataStore, self.calendarCollection._newStore)


    @inlineCallbacks
    def test_lookupCalendarHome(self):
        """
        When a L{CalDAVResource} representing an existing calendar home is looked
        up in a CalendarHomeResource, it will create a corresponding
        L{CalendarHome} via C{newTransaction().calendarHomeWithUID}.
        """
        calDavFile = yield self.getResource("calendars/users/wsanchez/")
        yield self.commit()
        assertProvides(self, ICalendarHome, calDavFile._newStoreHome)


    @inlineCallbacks
    def test_lookupDropboxHome(self):
        """
        When dropboxes are enabled, the 'dropbox' child of the user's calendar
        home should be a L{DropboxCollection} wrapper around the user's
        calendar home, with the dropbox-home resource type.
        """
        self.patch(config, "EnableDropBox", True)
        dropBoxResource = yield self.getResource(
            "calendars/users/wsanchez/dropbox"
        )
        yield self.commit()
        self.assertIsInstance(dropBoxResource, DropboxCollection)
        dropboxHomeType = davxml.ResourceType.dropboxhome #@UndefinedVariable
        self.assertEquals(dropBoxResource.resourceType(),
                          dropboxHomeType)


    @inlineCallbacks
    def test_lookupExistingCalendar(self):
        """
        When a L{CalDAVResource} representing an existing calendar collection is
        looked up in a L{CalendarHomeResource} representing a calendar home, it
        will create a corresponding L{Calendar} via
        C{CalendarHome.calendarWithName}.
        """
        calDavFile = yield self.getResource("calendars/users/wsanchez/calendar")
        regularCalendarType = davxml.ResourceType.calendar #@UndefinedVariable
        self.assertEquals(calDavFile.resourceType(),
                          regularCalendarType)
        yield self.commit()


    @inlineCallbacks
    def test_lookupNewCalendar(self):
        """
        When a L{CalDAVResource} which represents a not-yet-created calendar
        collection is looked up in a L{CalendarHomeResource} representing a
        calendar home, it will initially have a new storage backend set to
        C{None}, but when the calendar is created via a protocol action, the
        backend will be initialized to match.
        """
        calDavFile = yield self.getResource("calendars/users/wsanchez/frobozz")
        self.assertIsInstance(calDavFile, CalendarCollectionResource)
        self.assertFalse(calDavFile.exists())
        yield calDavFile.createCalendarCollection()
        self.assertTrue(calDavFile.exists())
        yield self.commit()


    @inlineCallbacks
    def test_lookupSpecial(self):
        """
        When a L{CalDAVResource} I{not} representing a calendar collection - one of
        the special collections, like the dropbox or freebusy URLs - is looked
        up in a L{CalendarHomeResource} representing a calendar home, it will I{not}
        create a corresponding L{Calendar} via C{CalendarHome.calendarWithName}.
        """
        for specialName in ['dropbox', 'freebusy', 'notifications']:
            calDavFile = yield self.getResource(
                "calendars/users/wsanchez/%s" % (specialName,)
            )
            self.assertIdentical(
                getattr(calDavFile, "_newStoreObject", None), None
            )
        yield self.commit()


    @inlineCallbacks
    def test_transactionPropagation(self):
        """
        L{CalendarHomeResource} propagates its transaction to all of its
        children.
        """
        variousNames = ['dropbox', 'freebusy', 'notifications',
                        'inbox', 'outbox', 'calendar']
        homeResource = yield self.getResource("calendars/users/wsanchez")
        homeTransaction = homeResource._associatedTransaction
        self.assertNotIdentical(homeTransaction, None)
        self.addCleanup(self.commit)
        for name in variousNames:
            homeChild = yield self.getResource(
                "calendars/users/wsanchez/" + name)
            self.assertIdentical(
                homeChild._associatedTransaction,
                homeTransaction,
                "transaction mismatch on %s; %r is not %r " %
                    (name, homeChild._associatedTransaction, homeTransaction))


    @inlineCallbacks
    def test_lookupCalendarObject(self):
        """
        When a L{CalDAVResource} representing an existing calendar object is
        looked up on a L{CalDAVResource} representing a calendar collection, a
        parallel L{CalendarObject} will be created.  Its principal collections
        and transaction should match.
        """
        yield self.populateOneObject("1.ics", event4_text)
        calendarHome = yield self.getResource("calendars/users/wsanchez")
        calDavFileCalendar = yield self.getResource(
            "calendars/users/wsanchez/calendar/1.ics"
        )
        yield self.commit()
        self.assertEquals(calDavFileCalendar._principalCollections,
                          frozenset([self.principalsResource]))
        self.assertEquals(calDavFileCalendar._associatedTransaction,
                          calendarHome._associatedTransaction)


    @inlineCallbacks
    def test_attachmentQuotaExceeded(self):
        """
        Exceeding quota on an attachment returns an HTTP error code.
        """
        patchConfig(testCase=self, EnableDropBox=True)
        yield self.populateOneObject("1.ics", event4_text)
        calendarObject = yield self.getResource(
            "/calendars/users/wsanchez/dropbox/uid4.dropbox/too-big-attachment",
            "PUT", "wsanchez"
        )
        self.requestUnderTest.stream = MemoryStream(
            "x" * deriveQuota(self) * 2)
        try:
            result = yield calendarObject.http_PUT(self.requestUnderTest)
        except HTTPError, he:
            self.assertEquals(he.response.code, INSUFFICIENT_STORAGE_SPACE)
        else:
            self.fail("Error not raised, %r returned instead." %
                      (result,))


    @inlineCallbacks
    def test_lookupNewCalendarObject(self):
        """
        When a L{CalDAVResource} representing a new calendar object on a
        L{CalDAVResource} representing an existing calendar collection, the list of
        principal collections will be propagated down to it.
        """
        calDavFileCalendar = yield self.getResource(
            "calendars/users/wsanchez/calendar/xyzzy.ics"
        )
        yield self.commit()
        self.assertEquals(calDavFileCalendar._principalCollections,
                          frozenset([self.principalsResource]))


    def test_createAddressBookStore(self):
        """
        Creating a AddressBookHomeProvisioningFile will create a paired
        AddressBookStore.
        """
        assertProvides(self, IDataStore, self.addressbookCollection._newStore)


    @inlineCallbacks
    def test_lookupAddressBookHome(self):
        """
        When a L{CalDAVResource} representing an existing addressbook home is looked up
        in a AddressBookHomeFile, it will create a corresponding L{AddressBookHome}
        via C{newTransaction().addressbookHomeWithUID}.
        """
        calDavFile = yield self.getResource("addressbooks/users/wsanchez/")
        yield self.commit()
        assertProvides(self, IAddressBookHome, calDavFile._newStoreHome)


    @inlineCallbacks
    def test_lookupExistingAddressBook(self):
        """
        When a L{CalDAVResource} representing an existing addressbook collection is
        looked up in a L{AddressBookHomeFile} representing a addressbook home, it will
        create a corresponding L{AddressBook} via C{AddressBookHome.addressbookWithName}.
        """
        calDavFile = yield self.getResource("addressbooks/users/wsanchez/addressbook")
        yield self.commit()
        self.assertEquals(calDavFile._principalCollections,
                          frozenset([self.principalsResource]))


    @inlineCallbacks
    def test_lookupNewAddressBook(self):
        """
        When a L{CalDAVResource} which represents a not-yet-created addressbook
        collection is looked up in a L{AddressBookHomeFile} representing a addressbook
        home, it will initially have a new storage backend set to C{None}, but
        when the addressbook is created via a protocol action, the backend will be
        initialized to match.
        """
        calDavFile = yield self.getResource("addressbooks/users/wsanchez/frobozz")
        self.assertIsInstance(calDavFile, AddressBookCollectionResource)
        self.assertFalse(calDavFile.exists())
        yield calDavFile.createAddressBookCollection()
        self.assertTrue(calDavFile.exists())
        yield self.commit()
        self.assertEquals(calDavFile._principalCollections,
                          frozenset([self.principalsResource]))


    @inlineCallbacks
    def test_lookupAddressBookObject(self):
        """
        When a L{CalDAVResource} representing an existing addressbook object is looked
        up on a L{CalDAVResource} representing a addressbook collection, a parallel
        L{AddressBookObject} will be created (with a matching FilePath).
        """
        yield self.populateOneAddressBookObject("1.vcf", vcard4_text)
        calDavFileAddressBook = yield self.getResource(
            "addressbooks/users/wsanchez/addressbook/1.vcf"
        )
        yield self.commit()
        self.assertEquals(calDavFileAddressBook._principalCollections,
                          frozenset([self.principalsResource]))


    @inlineCallbacks
    def test_lookupNewAddressBookObject(self):
        """
        When a L{CalDAVResource} representing a new addressbook object on a
        L{CalDAVResource} representing an existing addressbook collection, the list of
        principal collections will be propagated down to it.
        """
        calDavFileAddressBook = yield self.getResource(
            "addressbooks/users/wsanchez/addressbook/xyzzy.ics"
        )
        yield self.commit()
        self.assertEquals(calDavFileAddressBook._principalCollections,
                          frozenset([self.principalsResource]))



class DatabaseWrappingTests(WrappingTests):

    @inlineCallbacks
    def setUp(self):
        self.calendarStore = yield buildStore(self, StubNotifierFactory())
        super(DatabaseWrappingTests, self).setUp()


    def createDataStore(self):
        return self.calendarStore



