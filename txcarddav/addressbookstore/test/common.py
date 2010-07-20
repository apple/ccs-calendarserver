# -*- test-case-name: txcarddav.addressbookstore -*-
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
Tests for common addressbook store API functions.
"""

from zope.interface.verify import verifyObject
from zope.interface.exceptions import (
    BrokenMethodImplementation, DoesNotImplement
)

from txdav.idav import IPropertyStore, IDataStore
from txdav.propertystore.base import PropertyName

from txdav.common.icommondatastore import (
    HomeChildNameAlreadyExistsError, ICommonTransaction
)
from txdav.common.icommondatastore import InvalidObjectResourceError
from txdav.common.icommondatastore import NoSuchHomeChildError
from txdav.common.icommondatastore import NoSuchObjectResourceError
from txdav.common.icommondatastore import ObjectResourceNameAlreadyExistsError

from txcarddav.iaddressbookstore import (
    IAddressBookObject, IAddressBookHome,
    IAddressBook, IAddressBookTransaction
)
from twistedcaldav.vcard import Component as VComponent

from twext.python.filepath import CachingFilePath as FilePath
from twext.web2.dav import davxml
from twext.web2.dav.element.base import WebDAVUnknownElement


storePath = FilePath(__file__).parent().child("addressbook_store")

homeRoot = storePath.child("ho").child("me").child("home1")

adbk1Root = homeRoot.child("addressbook_1")

addressbook1_objectNames = [
    "1.vcf",
    "2.vcf",
    "3.vcf",
]


home1_addressbookNames = [
    "addressbook_1",
    "addressbook_2",
    "addressbook_empty",
]


vcard4_text = (
    """BEGIN:VCARD
VERSION:3.0
N:Thompson;Default;;;
FN:Default Thompson
EMAIL;type=INTERNET;type=WORK;type=pref:lthompson@example.com
TEL;type=WORK;type=pref:1-555-555-5555
TEL;type=CELL:1-444-444-4444
item1.ADR;type=WORK;type=pref:;;1245 Test;Sesame Street;California;11111;USA
item1.X-ABADR:us
UID:uid4
END:VCARD
""".replace("\n", "\r\n")
)



vcard4notCardDAV_text = ( # Missing UID, N and FN
"""BEGIN:VCARD
VERSION:3.0
EMAIL;type=INTERNET;type=WORK;type=pref:lthompson@example.com
TEL;type=WORK;type=pref:1-555-555-5555
TEL;type=CELL:1-444-444-4444
item1.ADR;type=WORK;type=pref:;;1245 Test;Sesame Street;California;11111;USA
item1.X-ABADR:us
END:VCARD
""".replace("\n", "\r\n")
)



vcard1modified_text = vcard4_text.replace(
    "\r\nUID:uid4\r\n",
    "\r\nUID:uid1\r\n"
)



class CommonTests(object):
    """
    Tests for common functionality of interfaces defined in
    L{txcarddav.iaddressbookstore}.
    """

    requirements = {
        "home1": {
            "addressbook_1": {
                "1.vcf": adbk1Root.child("1.vcf").getContent(),
                "2.vcf": adbk1Root.child("2.vcf").getContent(),
                "3.vcf": adbk1Root.child("3.vcf").getContent()
            },
            "addressbook_empty": {},
            "not_a_addressbook": None
        },
        "not_a_home": None
    }

    def storeUnderTest(self):
        """
        Subclasses must override this to return an L{IAddressBookStore}
        provider which adheres to the structure detailed by
        L{CommonTests.requirements}. This attribute is a dict of dict of dicts;
        the outermost layer representing UIDs mapping to addressbook homes,
        then addressbook names mapping to addressbook collections, and finally
        addressbook object names mapping to addressbook object text.
        """
        raise NotImplementedError()


    lastTransaction = None
    savedStore = None

    def transactionUnderTest(self):
        """
        Create a transaction from C{storeUnderTest} and save it as
        C[lastTransaction}.  Also makes sure to use the same store, saving the
        value from C{storeUnderTest}.
        """
        if self.lastTransaction is not None:
            return self.lastTransaction
        if self.savedStore is None:
            self.savedStore = self.storeUnderTest()
        txn = self.lastTransaction = self.savedStore.newTransaction()
        return txn


    def commit(self):
        """
        Commit the last transaction created from C{transactionUnderTest}, and
        clear it.
        """
        self.lastTransaction.commit()
        self.lastTransaction = None


    def abort(self):
        """
        Abort the last transaction created from C[transactionUnderTest}, and
        clear it.
        """
        self.lastTransaction.abort()
        self.lastTransaction = None


    def homeUnderTest(self):
        """
        Get the addressbook home detailed by C{requirements['home1']}.
        """
        return self.transactionUnderTest().addressbookHomeWithUID("home1")


    def addressbookUnderTest(self):
        """
        Get the addressbook detailed by C{requirements['home1']['addressbook_1']}.
        """
        return self.homeUnderTest().addressbookWithName("addressbook_1")


    def addressbookObjectUnderTest(self):
        """
        Get the addressbook detailed by
        C{requirements['home1']['addressbook_1']['1.vcf']}.
        """
        return self.addressbookUnderTest().addressbookObjectWithName("1.vcf")


    def assertProvides(self, interface, provider):
        """
        Verify that C{provider} properly provides C{interface}

        @type interface: L{zope.interface.Interface}
        @type provider: C{provider}
        """
        try:
            verifyObject(interface, provider)
        except BrokenMethodImplementation, e:
            self.fail(e)
        except DoesNotImplement, e:
            self.fail("%r does not provide %s.%s" %
                (provider, interface.__module__, interface.getName()))


    def test_addressbookStoreProvides(self):
        """
        The addressbook store provides L{IAddressBookStore} and its required
        attributes.
        """
        addressbookStore = self.storeUnderTest()
        self.assertProvides(IDataStore, addressbookStore)


    def test_transactionProvides(self):
        """
        The transactions generated by the addressbook store provide
        L{IAddressBookStoreTransaction} and its required attributes.
        """
        txn = self.storeUnderTest().newTransaction()
        self.assertProvides(ICommonTransaction, txn)
        self.assertProvides(IAddressBookTransaction, txn)


    def test_homeProvides(self):
        """
        The addressbook homes generated by the addressbook store provide
        L{IAddressBookHome} and its required attributes.
        """
        self.assertProvides(IAddressBookHome, self.homeUnderTest())


    def test_addressbookProvides(self):
        """
        The addressbooks generated by the addressbook store provide L{IAddressBook} and
        its required attributes.
        """
        self.assertProvides(IAddressBook, self.addressbookUnderTest())


    def test_addressbookObjectProvides(self):
        """
        The addressbook objects generated by the addressbook store provide
        L{IAddressBookObject} and its required attributes.
        """
        self.assertProvides(IAddressBookObject, self.addressbookObjectUnderTest())


    def test_addressbookHomeWithUID_exists(self):
        """
        Finding an existing addressbook home by UID results in an object that
        provides L{IAddressBookHome} and has a C{uid()} method that returns the
        same value that was passed in.
        """
        addressbookHome = (self.storeUnderTest().newTransaction()
                        .addressbookHomeWithUID("home1"))

        self.assertEquals(addressbookHome.uid(), "home1")
        self.assertProvides(IAddressBookHome, addressbookHome)


    def test_addressbookHomeWithUID_absent(self):
        """
        L{IAddressBookStoreTransaction.addressbookHomeWithUID} should return C{None}
        when asked for a non-existent addressbook home.
        """
        self.assertEquals(
            self.storeUnderTest().newTransaction()
            .addressbookHomeWithUID("xyzzy"),
            None
        )


    def test_addressbookWithName_exists(self):
        """
        L{IAddressBookHome.addressbookWithName} returns an L{IAddressBook} provider,
        whose name matches the one passed in.
        """
        home = self.homeUnderTest()
        for name in home1_addressbookNames:
            addressbook = home.addressbookWithName(name)
            self.assertProvides(IAddressBook, addressbook)
            self.assertEquals(addressbook.name(), name)


    def test_addressbookRename(self):
        """
        L{IAddressBook.rename} changes the name of the L{IAddressBook}.
        """
        home = self.homeUnderTest()
        addressbook = home.addressbookWithName("addressbook_1")
        addressbook.rename("some_other_name")
        def positiveAssertions():
            self.assertEquals(addressbook.name(), "some_other_name")
            self.assertEquals(addressbook, home.addressbookWithName("some_other_name"))
            self.assertEquals(None, home.addressbookWithName("addressbook_1"))
        positiveAssertions()
        self.commit()
        home = self.homeUnderTest()
        addressbook = home.addressbookWithName("some_other_name")
        positiveAssertions()
        # FIXME: revert
        # FIXME: test for multiple renames
        # FIXME: test for conflicting renames (a->b, c->a in the same txn)


    def test_addressbookWithName_absent(self):
        """
        L{IAddressBookHome.addressbookWithName} returns C{None} for addressbooks which
        do not exist.
        """
        self.assertEquals(self.homeUnderTest().addressbookWithName("xyzzy"),
                          None)


    def test_createAddressBookWithName_absent(self):
        """
        L{IAddressBookHome.createAddressBookWithName} creates a new L{IAddressBook} that
        can be retrieved with L{IAddressBookHome.addressbookWithName}.
        """
        home = self.homeUnderTest()
        name = "new"
        self.assertIdentical(home.addressbookWithName(name), None)
        home.createAddressBookWithName(name)
        self.assertNotIdentical(home.addressbookWithName(name), None)
        def checkProperties():
            addressbookProperties = home.addressbookWithName(name).properties()
            self.assertEquals(
                addressbookProperties[
                    PropertyName.fromString(davxml.ResourceType.sname())
                ],
                davxml.ResourceType.addressbook) #@UndefinedVariable
        checkProperties()
        self.commit()

        # Make sure it's available in a new transaction; i.e. test the commit.
        home = self.homeUnderTest()
        self.assertNotIdentical(home.addressbookWithName(name), None)
        home = self.addressbookStore.newTransaction().addressbookHomeWithUID(
            "home1")
        # Sanity check: are the properties actually persisted?
        # FIXME: no independent testing of this right now
        checkProperties()


    def test_createAddressBookWithName_exists(self):
        """
        L{IAddressBookHome.createAddressBookWithName} raises
        L{AddressBookAlreadyExistsError} when the name conflicts with an already-
        existing address book.
        """
        for name in home1_addressbookNames:
            self.assertRaises(
                HomeChildNameAlreadyExistsError,
                self.homeUnderTest().createAddressBookWithName, name
            )


    def test_removeAddressBookWithName_exists(self):
        """
        L{IAddressBookHome.removeAddressBookWithName} removes a addressbook that already
        exists.
        """
        home = self.homeUnderTest()
        # FIXME: test transactions
        for name in home1_addressbookNames:
            self.assertNotIdentical(home.addressbookWithName(name), None)
            home.removeAddressBookWithName(name)
            self.assertEquals(home.addressbookWithName(name), None)


    def test_removeAddressBookWithName_absent(self):
        """
        Attempt to remove an non-existing addressbook should raise.
        """
        home = self.homeUnderTest()
        self.assertRaises(NoSuchHomeChildError,
                          home.removeAddressBookWithName, "xyzzy")


    def test_addressbookObjects(self):
        """
        L{IAddressBook.addressbookObjects} will enumerate the addressbook objects present
        in the filesystem, in name order, but skip those with hidden names.
        """
        addressbook1 = self.addressbookUnderTest()
        addressbookObjects = list(addressbook1.addressbookObjects())

        for addressbookObject in addressbookObjects:
            self.assertProvides(IAddressBookObject, addressbookObject)
            self.assertEquals(
                addressbook1.addressbookObjectWithName(addressbookObject.name()),
                addressbookObject
            )

        self.assertEquals(
            list(o.name() for o in addressbookObjects),
            addressbook1_objectNames
        )


    def test_addressbookObjectsWithRemovedObject(self):
        """
        L{IAddressBook.addressbookObjects} skips those objects which have been
        removed by L{AddressBook.removeAddressBookObjectWithName} in the same
        transaction, even if it has not yet been committed.
        """
        addressbook1 = self.addressbookUnderTest()
        addressbook1.removeAddressBookObjectWithName("2.vcf")
        addressbookObjects = list(addressbook1.addressbookObjects())
        self.assertEquals(set(o.name() for o in addressbookObjects),
                          set(addressbook1_objectNames) - set(["2.vcf"]))


    def test_ownerAddressBookHome(self):
        """
        L{IAddressBook.ownerAddressBookHome} should match the home UID.
        """
        self.assertEquals(
            self.addressbookUnderTest().ownerAddressBookHome().uid(),
            self.homeUnderTest().uid()
        )


    def test_addressbookObjectWithName_exists(self):
        """
        L{IAddressBook.addressbookObjectWithName} returns an L{IAddressBookObject}
        provider for addressbooks which already exist.
        """
        addressbook1 = self.addressbookUnderTest()
        for name in addressbook1_objectNames:
            addressbookObject = addressbook1.addressbookObjectWithName(name)
            self.assertProvides(IAddressBookObject, addressbookObject)
            self.assertEquals(addressbookObject.name(), name)
            # FIXME: add more tests based on CommonTests.requirements


    def test_addressbookObjectWithName_absent(self):
        """
        L{IAddressBook.addressbookObjectWithName} returns C{None} for addressbooks which
        don't exist.
        """
        addressbook1 = self.addressbookUnderTest()
        self.assertEquals(addressbook1.addressbookObjectWithName("xyzzy"), None)


    def test_removeAddressBookObjectWithUID_exists(self):
        """
        Remove an existing addressbook object.
        """
        addressbook = self.addressbookUnderTest()
        for name in addressbook1_objectNames:
            uid = (u'uid' + name.rstrip(".vcf"))
            self.assertNotIdentical(addressbook.addressbookObjectWithUID(uid),
                                    None)
            addressbook.removeAddressBookObjectWithUID(uid)
            self.assertEquals(
                addressbook.addressbookObjectWithUID(uid),
                None
            )
            self.assertEquals(
                addressbook.addressbookObjectWithName(name),
                None
            )


    def test_removeAddressBookObjectWithName_exists(self):
        """
        Remove an existing addressbook object.
        """
        addressbook = self.addressbookUnderTest()
        for name in addressbook1_objectNames:
            self.assertNotIdentical(
                addressbook.addressbookObjectWithName(name), None
            )
            addressbook.removeAddressBookObjectWithName(name)
            self.assertIdentical(
                addressbook.addressbookObjectWithName(name), None
            )


    def test_removeAddressBookObjectWithName_absent(self):
        """
        Attempt to remove an non-existing addressbook object should raise.
        """
        addressbook = self.addressbookUnderTest()
        self.assertRaises(
            NoSuchObjectResourceError,
            addressbook.removeAddressBookObjectWithName, "xyzzy"
        )


    def test_addressbookName(self):
        """
        L{AddressBook.name} reflects the name of the addressbook.
        """
        self.assertEquals(self.addressbookUnderTest().name(), "addressbook_1")


    def test_addressbookObjectName(self):
        """
        L{IAddressBookObject.name} reflects the name of the addressbook object.
        """
        self.assertEquals(self.addressbookObjectUnderTest().name(), "1.vcf")


    def test_component(self):
        """
        L{IAddressBookObject.component} returns a L{VComponent} describing the
        addressbook data underlying that addressbook object.
        """
        component = self.addressbookObjectUnderTest().component()

        self.failUnless(
            isinstance(component, VComponent),
            component
        )

        self.assertEquals(component.name(), "VCARD")
        self.assertEquals(component.resourceUID(), "uid1")


    def test_iAddressBookText(self):
        """
        L{IAddressBookObject.iAddressBookText} returns a C{str} describing the same
        data provided by L{IAddressBookObject.component}.
        """
        text = self.addressbookObjectUnderTest().vCardText()
        self.assertIsInstance(text, str)
        self.failUnless(text.startswith("BEGIN:VCARD\r\n"))
        self.assertIn("\r\nUID:uid1\r\n", text)
        self.failUnless(text.endswith("\r\nEND:VCARD\r\n"))


    def test_addressbookObjectUID(self):
        """
        L{IAddressBookObject.uid} returns a C{str} describing the C{UID} property
        of the addressbook object's component.
        """
        self.assertEquals(self.addressbookObjectUnderTest().uid(), "uid1")


    def test_addressbookObjectWithUID_absent(self):
        """
        L{IAddressBook.addressbookObjectWithUID} returns C{None} for addressbooks which
        don't exist.
        """
        addressbook1 = self.addressbookUnderTest()
        self.assertEquals(addressbook1.addressbookObjectWithUID("xyzzy"), None)


    def test_addressbooks(self):
        """
        L{IAddressBookHome.addressbooks} returns an iterable of L{IAddressBook}
        providers, which are consistent with the results from
        L{IAddressBook.addressbookWithName}.
        """
        # Add a dot directory to make sure we don't find it
        # self.home1._path.child(".foo").createDirectory()
        home = self.homeUnderTest()
        addressbooks = list(home.addressbooks())

        for addressbook in addressbooks:
            self.assertProvides(IAddressBook, addressbook)
            self.assertEquals(addressbook,
                              home.addressbookWithName(addressbook.name()))

        self.assertEquals(
            list(c.name() for c in addressbooks),
            home1_addressbookNames
        )


    def test_addressbooksAfterAddAddressBook(self):
        """
        L{IAddressBookHome.addressbooks} includes addressbooks recently added with
        L{IAddressBookHome.createAddressBookWithName}.
        """
        home = self.homeUnderTest()
        before = set(x.name() for x in home.addressbooks())
        home.createAddressBookWithName("new-name")
        after = set(x.name() for x in home.addressbooks())
        self.assertEquals(before | set(['new-name']), after)


    def test_createAddressBookObjectWithName_absent(self):
        """
        L{IAddressBook.createAddressBookObjectWithName} creates a new
        L{IAddressBookObject}.
        """
        addressbook1 = self.addressbookUnderTest()
        name = "4.vcf"
        self.assertIdentical(addressbook1.addressbookObjectWithName(name), None)
        component = VComponent.fromString(vcard4_text)
        addressbook1.createAddressBookObjectWithName(name, component)

        addressbookObject = addressbook1.addressbookObjectWithName(name)
        self.assertEquals(addressbookObject.component(), component)


    def test_createAddressBookObjectWithName_exists(self):
        """
        L{IAddressBook.createAddressBookObjectWithName} raises
        L{AddressBookObjectNameAlreadyExistsError} if a addressbook object with the
        given name already exists in that addressbook.
        """
        self.assertRaises(
            ObjectResourceNameAlreadyExistsError,
            self.addressbookUnderTest().createAddressBookObjectWithName,
            "1.vcf", VComponent.fromString(vcard4_text)
        )


    def test_createAddressBookObjectWithName_invalid(self):
        """
        L{IAddressBook.createAddressBookObjectWithName} raises
        L{InvalidAddressBookComponentError} if presented with invalid iAddressBook
        text.
        """
        self.assertRaises(
            InvalidObjectResourceError,
            self.addressbookUnderTest().createAddressBookObjectWithName,
            "new", VComponent.fromString(vcard4notCardDAV_text)
        )


    def test_setComponent_invalid(self):
        """
        L{IAddressBookObject.setComponent} raises L{InvalidIAddressBookDataError} if
        presented with invalid iAddressBook text.
        """
        addressbookObject = self.addressbookObjectUnderTest()
        self.assertRaises(
            InvalidObjectResourceError,
            addressbookObject.setComponent,
            VComponent.fromString(vcard4notCardDAV_text)
        )


    def test_setComponent_uidchanged(self):
        """
        L{IAddressBookObject.setComponent} raises L{InvalidAddressBookComponentError}
        when given a L{VComponent} whose UID does not match its existing UID.
        """
        addressbook1 = self.addressbookUnderTest()
        component = VComponent.fromString(vcard4_text)
        addressbookObject = addressbook1.addressbookObjectWithName("1.vcf")
        self.assertRaises(
            InvalidObjectResourceError,
            addressbookObject.setComponent, component
        )


    def test_addressbookHomeWithUID_create(self):
        """
        L{IAddressBookStoreTransaction.addressbookHomeWithUID} with C{create=True}
        will create a addressbook home that doesn't exist yet.
        """
        txn = self.transactionUnderTest()
        noHomeUID = "xyzzy"
        addressbookHome = txn.addressbookHomeWithUID(
            noHomeUID,
            create=True
        )
        def readOtherTxn():
            return self.savedStore.newTransaction().addressbookHomeWithUID(
                noHomeUID)
        self.assertProvides(IAddressBookHome, addressbookHome)
        # A concurrent transaction shouldn't be able to read it yet:
        self.assertIdentical(readOtherTxn(), None)
        txn.commit()
        # But once it's committed, other transactions should see it.
        self.assertProvides(IAddressBookHome, readOtherTxn())


    def test_setComponent(self):
        """
        L{AddressBookObject.setComponent} changes the result of
        L{AddressBookObject.component} within the same transaction.
        """
        component = VComponent.fromString(vcard1modified_text)

        addressbook1 = self.addressbookUnderTest()
        addressbookObject = addressbook1.addressbookObjectWithName("1.vcf")
        oldComponent = addressbookObject.component()
        self.assertNotEqual(component, oldComponent)
        addressbookObject.setComponent(component)
        self.assertEquals(addressbookObject.component(), component)

        # Also check a new instance
        addressbookObject = addressbook1.addressbookObjectWithName("1.vcf")
        self.assertEquals(addressbookObject.component(), component)


    def checkPropertiesMethod(self, thunk):
        """
        Verify that the given object has a properties method that returns an
        L{IPropertyStore}.
        """
        properties = thunk.properties()
        self.assertProvides(IPropertyStore, properties)


    def test_homeProperties(self):
        """
        L{IAddressBookHome.properties} returns a property store.
        """
        self.checkPropertiesMethod(self.homeUnderTest())


    def test_addressbookProperties(self):
        """
        L{IAddressBook.properties} returns a property store.
        """
        self.checkPropertiesMethod(self.addressbookUnderTest())


    def test_addressbookObjectProperties(self):
        """
        L{IAddressBookObject.properties} returns a property store.
        """
        self.checkPropertiesMethod(self.addressbookObjectUnderTest())


    def test_newAddressBookObjectProperties(self):
        """
        L{IAddressBookObject.properties} returns an empty property store for a
        addressbook object which has been created but not committed.
        """
        addressbook = self.addressbookUnderTest()
        addressbook.createAddressBookObjectWithName(
            "4.vcf", VComponent.fromString(vcard4_text)
        )
        newEvent = addressbook.addressbookObjectWithName("4.vcf")
        self.assertEquals(newEvent.properties().items(), [])


    def test_setComponentPreservesProperties(self):
        """
        L{IAddressBookObject.setComponent} preserves properties.

        (Some implementations must go to extra trouble to provide this
        behavior; for example, file storage must copy extended attributes from
        the existing file to the temporary file replacing it.)
        """
        propertyName = PropertyName("http://example.com/ns", "example")
        propertyContent = WebDAVUnknownElement("sample content")
        propertyContent.name = propertyName.name
        propertyContent.namespace = propertyName.namespace

        self.addressbookObjectUnderTest().properties()[
            propertyName] = propertyContent
        self.commit()
        # Sanity check; are properties even readable in a separate transaction?
        # Should probably be a separate test.
        self.assertEquals(
            self.addressbookObjectUnderTest().properties()[propertyName],
            propertyContent)
        obj = self.addressbookObjectUnderTest()
        vcard1_text = obj.vCardText()
        vcard1_text_withDifferentNote = vcard1_text.replace(
            "NOTE:CardDAV protocol updates",
            "NOTE:Changed"
        )
        # Sanity check; make sure the test has the right idea of the subject.
        self.assertNotEquals(vcard1_text, vcard1_text_withDifferentNote)
        newComponent = VComponent.fromString(vcard1_text_withDifferentNote)
        obj.setComponent(newComponent)

        # Putting everything into a separate transaction to account for any
        # caching that may take place.
        self.commit()
        self.assertEquals(
            self.addressbookObjectUnderTest().properties()[propertyName],
            propertyContent
        )


