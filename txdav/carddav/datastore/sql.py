# -*- test-case-name: txdav.carddav.datastore.test.test_sql -*-
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

__all__ = [
    "AddressBookHome",
    "AddressBook",
    "AddressBookObject",
]

from twext.web2.dav.element.rfc2518 import ResourceType
from twext.web2.http_headers import MimeType

from twistedcaldav import carddavxml, customxml
from twistedcaldav.vcard import Component as VCard

from txdav.common.datastore.sql_legacy import \
    PostgresLegacyABIndexEmulator, SQLLegacyAddressBookInvites,\
    SQLLegacyAddressBookShares

from txdav.carddav.datastore.util import validateAddressBookComponent
from txdav.carddav.iaddressbookstore import IAddressBookHome, IAddressBook,\
    IAddressBookObject

from txdav.common.datastore.sql import CommonHome, CommonHomeChild,\
    CommonObjectResource
from txdav.common.datastore.sql_tables import ADDRESSBOOK_TABLE,\
    ADDRESSBOOK_BIND_TABLE, ADDRESSBOOK_OBJECT_REVISIONS_TABLE,\
    ADDRESSBOOK_OBJECT_TABLE
from txdav.base.propertystore.base import PropertyName

from zope.interface.declarations import implements

class AddressBookHome(CommonHome):

    implements(IAddressBookHome)

    def __init__(self, transaction, ownerUID, resourceID, notifier):
        super(AddressBookHome, self).__init__(transaction, ownerUID, resourceID, notifier)

        self._shares = SQLLegacyAddressBookShares(self)
        self._childClass = AddressBook
        self._childTable = ADDRESSBOOK_TABLE
        self._bindTable = ADDRESSBOOK_BIND_TABLE

    addressbooks = CommonHome.children
    listAddressbooks = CommonHome.listChildren
    addressbookWithName = CommonHome.childWithName
    createAddressBookWithName = CommonHome.createChildWithName
    removeAddressBookWithName = CommonHome.removeChildWithName

    def createdHome(self):
        self.createAddressBookWithName("addressbook")

class AddressBook(CommonHomeChild):
    """
    File-based implementation of L{IAddressBook}.
    """
    implements(IAddressBook)

    def __init__(self, home, name, resourceID, notifier):
        """
        Initialize an addressbook pointing at a path on disk.

        @param name: the subdirectory of addressbookHome where this addressbook
            resides.
        @type name: C{str}

        @param addressbookHome: the home containing this addressbook.
        @type addressbookHome: L{AddressBookHome}

        @param realName: If this addressbook was just created, the name which it
        will eventually have on disk.
        @type realName: C{str}
        """
        
        super(AddressBook, self).__init__(home, name, resourceID, notifier)

        self._index = PostgresLegacyABIndexEmulator(self)
        self._invites = SQLLegacyAddressBookInvites(self)
        self._objectResourceClass = AddressBookObject
        self._bindTable = ADDRESSBOOK_BIND_TABLE
        self._homeChildTable = ADDRESSBOOK_TABLE
        self._revisionsTable = ADDRESSBOOK_OBJECT_REVISIONS_TABLE
        self._objectTable = ADDRESSBOOK_OBJECT_TABLE

    @property
    def _addressbookHome(self):
        return self._home

    def resourceType(self):
        return ResourceType.addressbook #@UndefinedVariable

    ownerAddressBookHome = CommonHomeChild.ownerHome
    addressbookObjects = CommonHomeChild.objectResources
    listAddressbookObjects = CommonHomeChild.listObjectResources
    addressbookObjectWithName = CommonHomeChild.objectResourceWithName
    addressbookObjectWithUID = CommonHomeChild.objectResourceWithUID
    createAddressBookObjectWithName = CommonHomeChild.createObjectResourceWithName
    removeAddressBookObjectWithName = CommonHomeChild.removeObjectResourceWithName
    removeAddressBookObjectWithUID = CommonHomeChild.removeObjectResourceWithUID
    addressbookObjectsSinceToken = CommonHomeChild.objectResourcesSinceToken


    def initPropertyStore(self, props):
        # Setup peruser special properties
        props.setSpecialProperties(
            (
                PropertyName.fromElement(carddavxml.AddressBookDescription),
            ),
            (
                PropertyName.fromElement(customxml.GETCTag),
            ),
        )

    def _doValidate(self, component):
        component.validForCardDAV()

    def contentType(self):
        """
        The content type of Addresbook objects is text/vcard.
        """
        return MimeType.fromString("text/vcard; charset=utf-8")

class AddressBookObject(CommonObjectResource):

    implements(IAddressBookObject)

    def __init__(self, name, addressbook, resid):

        super(AddressBookObject, self).__init__(name, addressbook, resid)

        self._objectTable = ADDRESSBOOK_OBJECT_TABLE

    @property
    def _addressbook(self):
        return self._parentCollection

    def addressbook(self):
        return self._addressbook

    def setComponent(self, component, inserting=False):
        validateAddressBookComponent(self, self._addressbook, component, inserting)

        self.updateDatabase(component, inserting=inserting)
        if inserting:
            self._addressbook._insertRevision(self._name)
        else:
            self._addressbook._updateRevision(self._name)

        self._addressbook.notifyChanged()

    def updateDatabase(self, component, expand_until=None, reCreate=False, inserting=False):
        """
        Update the database tables for the new data being written.

        @param component: addressbook data to store
        @type component: L{Component}
        """

        componentText = str(component)
        self._objectText = componentText

        # ADDRESSBOOK_OBJECT table update
        if inserting:
            self._resourceID = self._txn.execSQL(
                """
                insert into ADDRESSBOOK_OBJECT
                (ADDRESSBOOK_RESOURCE_ID, RESOURCE_NAME, VCARD_TEXT, VCARD_UID)
                 values
                (%s, %s, %s, %s)
                 returning RESOURCE_ID
                """,
                [
                    self._addressbook._resourceID,
                    self._name,
                    componentText,
                    component.resourceUID(),
                ]
            )[0][0]
        else:
            self._txn.execSQL(
                """
                update ADDRESSBOOK_OBJECT set
                (VCARD_TEXT, VCARD_UID, MODIFIED)
                 =
                (%s, %s, timezone('UTC', CURRENT_TIMESTAMP))
                 where RESOURCE_ID = %s
                """,
                [
                    componentText,
                    component.resourceUID(),
                    self._resourceID
                ]
            )

    def component(self):
        return VCard.fromString(self.vCardText())

    def text(self):
        if self._objectText is None:
            text = self._txn.execSQL(
                "select VCARD_TEXT from ADDRESSBOOK_OBJECT where "
                "RESOURCE_ID = %s", [self._resourceID]
            )[0][0]
            self._objectText = text
            return text
        else:
            return self._objectText

    vCardText = text

    def uid(self):
        return self.component().resourceUID()

    def name(self):
        return self._name

    def componentType(self):
        return self.component().mainType()

    # IDataStoreResource
    def contentType(self):
        """
        The content type of Addressbook objects is text/x-vcard.
        """
        return MimeType.fromString("text/vcard; charset=utf-8")
