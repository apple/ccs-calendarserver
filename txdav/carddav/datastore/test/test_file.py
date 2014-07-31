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

"""
File addressbook store tests.
"""

from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest

from twext.python.filepath import CachingFilePath as FilePath

from twistedcaldav.vcard import Component as VComponent

from txdav.common.icommondatastore import HomeChildNameNotAllowedError
from txdav.common.icommondatastore import ObjectResourceNameNotAllowedError
from txdav.common.icommondatastore import ObjectResourceUIDAlreadyExistsError
from txdav.common.icommondatastore import NoSuchHomeChildError

from txdav.carddav.datastore.file import AddressBookStore, AddressBookHome
from txdav.carddav.datastore.file import AddressBook, AddressBookObject

from txdav.carddav.datastore.test.common import (
    CommonTests, vcard4_text, vcard1modified_text)

from txdav.common.datastore.test.util import StubNotifierFactory

storePath = FilePath(__file__).parent().child("addressbook_store")

def _todo(f, why):
    f.todo = why
    return f



featureUnimplemented = lambda f: _todo(f, "Feature unimplemented")
testUnimplemented = lambda f: _todo(f, "Test unimplemented")
todo = lambda why: lambda f: _todo(f, why)


def setUpAddressBookStore(test):
    test.root = FilePath(test.mktemp())
    test.root.createDirectory()

    storeRootPath = test.storeRootPath = test.root.child("store")
    addressbookPath = storeRootPath.child("addressbooks").child("__uids__")
    addressbookPath.parent().makedirs()
    storePath.copyTo(addressbookPath)

    test.counter = 0
    test.notifierFactory = StubNotifierFactory()
    test.addressbookStore = AddressBookStore(storeRootPath, {"push": test.notifierFactory}, None)
    test.txn = test.addressbookStore.newTransaction(test.id() + " (old)")
    assert test.addressbookStore is not None, "No addressbook store?"



@inlineCallbacks
def setUpHome1(test):
    setUpAddressBookStore(test)
    test.home1 = yield test.txn.addressbookHomeWithUID("home1")
    assert test.home1 is not None, "No addressbook home?"



@inlineCallbacks
def setUpAddressBook1(test):
    yield setUpHome1(test)
    test.addressbook1 = yield test.home1.addressbookWithName("addressbook")
    assert test.addressbook1 is not None, "No addressbook?"



class AddressBookStoreTest(unittest.TestCase):
    """
    Test cases for L{AddressBookStore}.
    """

    def setUp(self):
        setUpAddressBookStore(self)


    @inlineCallbacks
    def test_addressbookHomeWithUID_dot(self):
        """
        Filenames starting with "." are reserved by this
        implementation, so no UIDs may start with ".".
        """
        self.assertEquals((
            yield self.addressbookStore.newTransaction(
                self.id())
            .addressbookHomeWithUID(".xyzzy")),
            None
        )



class AddressBookHomeTest(unittest.TestCase):

    def setUp(self):
        return setUpHome1(self)


    def test_init(self):
        """
        L{AddressBookHome} has C{_path} and L{_addressbookStore} attributes,
        indicating its location on disk and parent store, respectively.
        """
        self.failUnless(
            isinstance(self.home1._path, FilePath),
            self.home1._path
        )
        self.assertEquals(
            self.home1._addressbookStore,
            self.addressbookStore
        )


    def test_addressbookWithName_dot(self):
        """
        Filenames starting with "." are reserved by this
        implementation, so no addressbook names may start with ".".
        """
        name = ".foo"
        self.home1._path.child(name).createDirectory()
        self.assertEquals(self.home1.addressbookWithName(name), None)


    def test_createAddressBookWithName_dot(self):
        """
        Filenames starting with "." are reserved by this
        implementation, so no addressbook names may start with ".".
        """
        self.assertRaises(
            HomeChildNameNotAllowedError,
            self.home1.createAddressBookWithName, ".foo"
        )


    def test_removeAddressBookWithName_dot(self):
        """
        Filenames starting with "." are reserved by this
        implementation, so no addressbook names may start with ".".
        """
        name = ".foo"
        self.home1._path.child(name).createDirectory()
        self.assertRaises(
            NoSuchHomeChildError,
            self.home1.removeAddressBookWithName, name
        )



class AddressBookTest(unittest.TestCase):

    def setUp(self):
        setUpAddressBook1(self)


    def test_init(self):
        """
        L{AddressBook.__init__} sets private attributes to reflect its constructor
        arguments.
        """
        self.failUnless(
            isinstance(self.addressbook1._path, FilePath),
            self.addressbook1
        )
        self.failUnless(
            isinstance(self.addressbook1._addressbookHome, AddressBookHome),
            self.addressbook1._addressbookHome
        )


    @inlineCallbacks
    def test_useIndexImmediately(self):
        """
        L{AddressBook._index} is usable in the same transaction it is created, with
        a temporary filename.
        """
        self.home1.createAddressBookWithName("addressbook2")
        addressbook = self.home1.addressbookWithName("addressbook2")
        index = addressbook._index
        self.assertEquals(set((yield index.addressbookObjects())),
                          set((yield addressbook.addressbookObjects())))
        yield self.txn.commit()
        self.txn = self.addressbookStore.newTransaction(self.id())
        self.home1 = yield self.txn.addressbookHomeWithUID("home1")
        addressbook = yield self.home1.addressbookWithName("addressbook2")
        # FIXME: we should be curating our own index here, but in order to fix
        # that the code in the old implicit scheduler needs to change.  This
        # test would be more effective if there were actually some objects in
        # this list.
        index = addressbook._index
        self.assertEquals(set((yield index.addressbookObjects())),
                          set((yield addressbook.addressbookObjects())))


    @inlineCallbacks
    def test_addressbookObjectWithName_dot(self):
        """
        Filenames starting with "." are reserved by this
        implementation, so no addressbook object names may start with
        ".".
        """
        name = ".foo.vcf"
        self.home1._path.child(name).touch()
        self.assertEquals(
            (yield self.addressbook1.addressbookObjectWithName(name)),
            None
        )


    @featureUnimplemented
    def test_addressbookObjectWithUID_exists(self):
        """
        Find existing addressbook object by name.
        """
        addressbookObject = yield self.addressbook1.addressbookObjectWithUID("1")
        self.failUnless(
            isinstance(addressbookObject, AddressBookObject),
            addressbookObject
        )
        self.assertEquals(
            addressbookObject.component(),
            (yield self.addressbook1.addressbookObjectWithName("1.vcf")).component()
        )


    def test_createAddressBookObjectWithName_dot(self):
        """
        Filenames starting with "." are reserved by this
        implementation, so no addressbook object names may start with
        ".".
        """
        self.assertRaises(
            ObjectResourceNameNotAllowedError,
            self.addressbook1.createAddressBookObjectWithName,
            ".foo", VComponent.fromString(vcard4_text)
        )


    @featureUnimplemented
    def test_createAddressBookObjectWithName_uidconflict(self):
        """
        Attempt to create a addressbook object with a conflicting UID
        should raise.
        """
        name = "foo.vcf"
        self.assertIdentical(
            (yield self.addressbook1.addressbookObjectWithName(name)),
            None
        )
        component = VComponent.fromString(vcard1modified_text)
        self.assertRaises(
            ObjectResourceUIDAlreadyExistsError,
            self.addressbook1.createAddressBookObjectWithName,
            name, component
        )


    def test_removeAddressBookObject_delayedEffect(self):
        """
        Removing a addressbook object should not immediately remove the underlying
        file; it should only be removed upon commit() of the transaction.
        """
        obj1 = self.addressbook1.addressbookObjectWithName("2.vcf")
        obj1.remove()
        self.failUnless(self.addressbook1._path.child("2.vcf").exists())
        self.txn.commit()
        self.failIf(self.addressbook1._path.child("2.vcf").exists())


    @inlineCallbacks
    def _refresh(self):
        """
        Re-read the (committed) home1 and addressbook1 objects in a new
        transaction.
        """
        self.txn = self.addressbookStore.newTransaction(self.id())
        self.home1 = yield self.txn.addressbookHomeWithUID("home1")
        self.addressbook1 = yield self.home1.addressbookWithName("addressbook")


    @inlineCallbacks
    def test_undoCreateAddressBookObject(self):
        """
        If a addressbook object is created as part of a transaction, it will be
        removed if that transaction has to be aborted.
        """
        # Make sure that the addressbook home is actually committed; rolling back
        # addressbook home creation will remove the whole directory.
        yield self.txn.commit()
        yield self._refresh()
        self.addressbook1.createAddressBookObjectWithName(
            "sample.vcf",
            VComponent.fromString(vcard4_text)
        )
        yield self.txn.abort()
        yield self._refresh()
        self.assertIdentical(
            (yield self.addressbook1.addressbookObjectWithName("sample.vcf")),
            None
        )


    @inlineCallbacks
    def doThenUndo(self):
        """
        Commit the current transaction, but add an operation that will cause it
        to fail at the end.  Finally, refresh all attributes with a new
        transaction so that further oparations can be performed in a valid
        context.
        """
        def fail():
            raise RuntimeError("oops")
        self.txn.addOperation(fail, "dummy failing operation")
        self.assertRaises(RuntimeError, self.txn.commit)
        yield self._refresh()


    @inlineCallbacks
    def test_undoModifyAddressBookObject(self):
        """
        If an existing addressbook object is modified as part of a transaction, it
        should be restored to its previous status if the transaction aborts.
        """
        originalComponent = yield self.addressbook1.addressbookObjectWithName(
            "1.vcf").component()
        (yield self.addressbook1.addressbookObjectWithName("1.vcf")).setComponent(
            VComponent.fromString(vcard1modified_text)
        )
        # Sanity check.
        self.assertEquals(
            (yield self.addressbook1.addressbookObjectWithName("1.vcf")).component(),
            VComponent.fromString(vcard1modified_text)
        )
        yield self.doThenUndo()
        self.assertEquals(
            (yield self.addressbook1.addressbookObjectWithName("1.vcf")).component(),
            originalComponent
        )


    def test_modifyAddressBookObjectCaches(self):
        """
        Modifying a addressbook object should cache the modified component in
        memory, to avoid unnecessary parsing round-trips.
        """
        modifiedComponent = VComponent.fromString(vcard1modified_text)
        (yield self.addressbook1.addressbookObjectWithName("1.vcf")).setComponent(
            modifiedComponent
        )
        self.assertIdentical(
            modifiedComponent,
            (yield self.addressbook1.addressbookObjectWithName("1.vcf")).component()
        )
        self.txn.commit()


    @testUnimplemented
    def test_syncToken(self):
        """
        Sync token is correct.
        """
        raise NotImplementedError()


    @testUnimplemented
    def test_addressbookObjectsSinceToken(self):
        """
        Find addressbook objects that have been modified since a given
        sync token.
        """
        raise NotImplementedError()



class AddressBookObjectTest(unittest.TestCase):

    @inlineCallbacks
    def setUp(self):
        yield setUpAddressBook1(self)
        self.object1 = yield self.addressbook1.addressbookObjectWithName("1.vcf")


    def test_init(self):
        """
        L{AddressBookObject} has instance attributes, C{_path} and C{_addressbook},
        which refer to its position in the filesystem and the addressbook in which
        it is contained, respectively.
        """
        self.failUnless(
            isinstance(self.object1._path, FilePath),
            self.object1._path
        )
        self.failUnless(
            isinstance(self.object1._addressbook, AddressBook),
            self.object1._addressbook
        )



class FileStorageTests(CommonTests, unittest.TestCase):
    """
    File storage tests.
    """

    addressbookStore = None

    def storeUnderTest(self):
        """
        Create and return a L{AddressBookStore} for testing.
        """
        if self.addressbookStore is None:
            setUpAddressBookStore(self)
        return self.addressbookStore


    def test_init(self):
        """
        L{AddressBookStore} has a C{_path} attribute which refers to its
        constructor argument.
        """
        self.assertEquals(self.storeUnderTest()._path,
                          self.storeRootPath)


    @inlineCallbacks
    def test_addressbookObjectsWithDotFile(self):
        """
        Adding a dotfile to the addressbook home should not create a new
        addressbook object.
        """
        self.homeUnderTest()._path.child(".foo").createDirectory()
        yield self.test_addressbookObjects()


    @inlineCallbacks
    def test_addressbookObjectsWithDirectory(self):
        """
        If a directory appears (even a non-hidden one) within an addressbook, it
        should not show up in the directory listing.
        """
        ((yield self.addressbookUnderTest())._path.child("not-a-vcard")
         .createDirectory())
        yield self.test_addressbookObjects()


    @testUnimplemented
    def test_createAddressBookWithName_absent(self):
        """
        L{IAddressBookHome.createAddressBookWithName} creates a new L{IAddressBook} that
        can be retrieved with L{IAddressBookHome.addressbookWithName}.
        """

    @testUnimplemented
    def test_removeAddressBookWithName_exists(self):
        """
        L{IAddressBookHome.removeAddressBookWithName} removes a addressbook that already
        exists.
        """
