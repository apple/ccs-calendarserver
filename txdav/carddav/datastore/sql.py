# -*- test-case-name: txdav.carddav.datastore.test.test_sql -*-
##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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
SQL backend for CardDAV storage.
"""

__all__ = [
    "AddressBookHome",
    "AddressBook",
    "AddressBookObject",
]

from twext.enterprise.dal.syntax import Delete
from twext.enterprise.dal.syntax import Insert
from twext.enterprise.dal.syntax import Update
from twext.enterprise.dal.syntax import utcNowSQL
from twext.enterprise.locking import NamedLock
from twext.web2.http_headers import MimeType

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import hashlib

from twistedcaldav import carddavxml, customxml
from twistedcaldav.config import config
from twistedcaldav.memcacher import Memcacher
from twistedcaldav.vcard import Component as VCard, InvalidVCardDataError

from txdav.base.propertystore.base import PropertyName
from txdav.carddav.iaddressbookstore import IAddressBookHome, IAddressBook, \
    IAddressBookObject
from txdav.common.datastore.sql import CommonHome, CommonHomeChild, \
    CommonObjectResource, EADDRESSBOOKTYPE
from txdav.common.datastore.sql_legacy import PostgresLegacyABIndexEmulator
from txdav.common.datastore.sql_tables import ADDRESSBOOK_TABLE, \
    ADDRESSBOOK_BIND_TABLE, ADDRESSBOOK_OBJECT_REVISIONS_TABLE, \
    ADDRESSBOOK_OBJECT_TABLE, ADDRESSBOOK_HOME_TABLE, \
    ADDRESSBOOK_HOME_METADATA_TABLE, ADDRESSBOOK_AND_ADDRESSBOOK_BIND, \
    ADDRESSBOOK_OBJECT_AND_BIND_TABLE, \
    ADDRESSBOOK_OBJECT_REVISIONS_AND_BIND_TABLE, schema
from txdav.common.icommondatastore import InternalDataStoreError, \
    InvalidUIDError, UIDExistsError, ObjectResourceTooBigError, \
    InvalidObjectResourceError, InvalidComponentForStoreError
from txdav.xml.rfc2518 import ResourceType

from zope.interface.declarations import implements



class AddressBookHome(CommonHome):

    implements(IAddressBookHome)

    # structured tables.  (new, preferred)
    _homeSchema = schema.ADDRESSBOOK_HOME
    _bindSchema = schema.ADDRESSBOOK_BIND
    _homeMetaDataSchema = schema.ADDRESSBOOK_HOME_METADATA
    _revisionsSchema = schema.ADDRESSBOOK_OBJECT_REVISIONS
    _objectSchema = schema.ADDRESSBOOK_OBJECT

    # string mappings (old, removing)
    _homeTable = ADDRESSBOOK_HOME_TABLE
    _homeMetaDataTable = ADDRESSBOOK_HOME_METADATA_TABLE
    _childTable = ADDRESSBOOK_TABLE
    _bindTable = ADDRESSBOOK_BIND_TABLE
    _objectBindTable = ADDRESSBOOK_OBJECT_AND_BIND_TABLE
    _notifierPrefix = "CardDAV"
    _revisionsTable = ADDRESSBOOK_OBJECT_REVISIONS_TABLE

    _dataVersionKey = "ADDRESSBOOK-DATAVERSION"

    _cacher = Memcacher("SQL.adbkhome", pickle=True, key_normalization=False)

    def __init__(self, transaction, ownerUID, notifiers):

        self._childClass = AddressBook
        super(AddressBookHome, self).__init__(transaction, ownerUID, notifiers)

    addressbooks = CommonHome.children
    listAddressbooks = CommonHome.listChildren
    loadAddressbooks = CommonHome.loadChildren
    addressbookWithName = CommonHome.childWithName
    createAddressBookWithName = CommonHome.createChildWithName
    removeAddressBookWithName = CommonHome.removeChildWithName


    @inlineCallbacks
    def remove(self):
        ah = schema.ADDRESSBOOK_HOME
        ab = schema.ADDRESSBOOK_BIND
        aor = schema.ADDRESSBOOK_OBJECT_REVISIONS
        rp = schema.RESOURCE_PROPERTY

        yield Delete(
            From=ab,
            Where=ab.ADDRESSBOOK_HOME_RESOURCE_ID == self._resourceID
        ).on(self._txn)

        yield Delete(
            From=aor,
            Where=aor.ADDRESSBOOK_HOME_RESOURCE_ID == self._resourceID
        ).on(self._txn)

        yield Delete(
            From=ah,
            Where=ah.RESOURCE_ID == self._resourceID
        ).on(self._txn)

        yield Delete(
            From=rp,
            Where=rp.RESOURCE_ID == self._resourceID
        ).on(self._txn)

        yield self._cacher.delete(str(self._ownerUID))


    def createdHome(self):
        return self.createAddressBookWithName("addressbook")



AddressBookHome._register(EADDRESSBOOKTYPE)



class AddressBook(CommonHomeChild):
    """
    SQL-based implementation of L{IAddressBook}.
    """
    implements(IAddressBook)

    # structured tables.  (new, preferred)
    _homeSchema = schema.ADDRESSBOOK_HOME
    _bindSchema = schema.ADDRESSBOOK_BIND
    _homeChildSchema = schema.ADDRESSBOOK
    _homeChildMetaDataSchema = schema.ADDRESSBOOK_METADATA
    _revisionsSchema = schema.ADDRESSBOOK_OBJECT_REVISIONS
    _objectSchema = schema.ADDRESSBOOK_OBJECT

    # string mappings (old, removing)
    _bindTable = ADDRESSBOOK_BIND_TABLE
    _homeChildTable = ADDRESSBOOK_TABLE
    _homeChildBindTable = ADDRESSBOOK_AND_ADDRESSBOOK_BIND
    _revisionsTable = ADDRESSBOOK_OBJECT_REVISIONS_TABLE
    _revisionsBindTable = ADDRESSBOOK_OBJECT_REVISIONS_AND_BIND_TABLE
    _objectTable = ADDRESSBOOK_OBJECT_TABLE

    def __init__(self, *args, **kw):
        super(AddressBook, self).__init__(*args, **kw)
        self._index = PostgresLegacyABIndexEmulator(self)


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


    def contentType(self):
        """
        The content type of Addresbook objects is text/vcard.
        """
        return MimeType.fromString("text/vcard; charset=utf-8")


    def unshare(self):
        """
        Unshares a collection, regardless of which "direction" it was shared.
        """
        return super(AddressBook, self).unshare(EADDRESSBOOKTYPE)



class AddressBookObject(CommonObjectResource):

    implements(IAddressBookObject)

    _objectTable = ADDRESSBOOK_OBJECT_TABLE
    _objectSchema = schema.ADDRESSBOOK_OBJECT

    def __init__(self, addressbook, name, uid, resourceID=None, options=None):

        super(AddressBookObject, self).__init__(addressbook, name, uid, resourceID)

        # Component caching
        self._cachedComponent = None


    @property
    def _addressbook(self):
        return self._parentCollection


    def addressbook(self):
        return self._addressbook


    # Stuff from put_addressbook_common
    def fullValidation(self, component, inserting):
        """
        Do full validation of source and destination calendar data.
        """

        # Basic validation

        # Valid data sizes
        if config.MaxResourceSize:
            vcardsize = len(str(component))
            if vcardsize > config.MaxResourceSize:
                raise ObjectResourceTooBigError()

        # Valid calendar data checks
        self.validAddressDataCheck(component, inserting)


    def validAddressDataCheck(self, component, inserting):
        """
        Check that the calendar data is valid iCalendar.
        @return:         tuple: (True/False if the calendar data is valid,
                                 log message string).
        """

        # Valid calendar data checks
        if not isinstance(component, VCard):
            raise InvalidObjectResourceError("Wrong type of object: %s" % (type(component),))

        try:
            component.validVCardData()
        except InvalidVCardDataError, e:
            raise InvalidObjectResourceError(str(e))
        try:
            component.validForCardDAV()
        except InvalidVCardDataError, e:
            raise InvalidComponentForStoreError(str(e))


    @inlineCallbacks
    def _lockUID(self, component, inserting):
        """
        Create a lock on the component's UID and verify, after getting the lock, that the incoming UID
        meets the requirements of the store.
        """

        new_uid = component.resourceUID()
        yield NamedLock.acquire(self._txn, "vCardUIDLock:%s" % (hashlib.md5(new_uid).hexdigest(),))

        # UID conflict check - note we do this after reserving the UID to avoid a race condition where two requests
        # try to write the same calendar data to two different resource URIs.

        # Cannot overwrite a resource with different UID
        if not inserting:
            if self._uid != new_uid:
                raise InvalidUIDError("Cannot change the UID in an existing resource.")
        else:
            # New UID must be unique for the owner - no need to do this on an overwrite as we can assume
            # the store is already consistent in this regard
            elsewhere = (yield self.addressbook().addressbookObjectWithUID(new_uid))
            if elsewhere is not None:
                raise UIDExistsError("UID already exists in same addressbook.")


    @inlineCallbacks
    def setComponent(self, component, inserting=False):

        self._componentChanged = False

        # Handle all validation operations here.
        self.fullValidation(component, inserting)

        # UID lock - this will remain active until the end of the current txn
        yield self._lockUID(component, inserting)

        yield self.updateDatabase(component, inserting=inserting)
        if inserting:
            yield self._addressbook._insertRevision(self._name)
        else:
            yield self._addressbook._updateRevision(self._name)

        yield self._addressbook.notifyChanged()

        returnValue(self._componentChanged)


    @inlineCallbacks
    def updateDatabase(self, component, expand_until=None, reCreate=False, inserting=False):
        """
        Update the database tables for the new data being written.

        @param component: addressbook data to store
        @type component: L{Component}
        """

        ao = schema.ADDRESSBOOK_OBJECT

        componentText = str(component)
        self._objectText = componentText
        self._cachedComponent = component

        # ADDRESSBOOK_OBJECT table update
        self._md5 = hashlib.md5(componentText).hexdigest()
        self._size = len(componentText)

        # Special - if migrating we need to preserve the original md5
        if self._txn._migrating and hasattr(component, "md5"):
            self._md5 = component.md5

        if inserting:
            self._resourceID, self._created, self._modified = (
                yield Insert(
                    {ao.ADDRESSBOOK_RESOURCE_ID: self._addressbook._resourceID,
                     ao.RESOURCE_NAME: self._name,
                     ao.VCARD_TEXT: componentText,
                     ao.VCARD_UID: component.resourceUID(),
                     ao.MD5: self._md5},
                    Return=(ao.RESOURCE_ID,
                            ao.CREATED,
                            ao.MODIFIED)
                ).on(self._txn))[0]
        else:
            self._modified = (yield Update(
                {ao.VCARD_TEXT: componentText,
                 ao.VCARD_UID: component.resourceUID(),
                 ao.MD5: self._md5,
                 ao.MODIFIED: utcNowSQL},
                Where=ao.RESOURCE_ID == self._resourceID,
                Return=ao.MODIFIED).on(self._txn))[0][0]


    @inlineCallbacks
    def component(self):
        """
        Read address data and validate/fix it. Do not raise a store error here if there are unfixable
        errors as that could prevent the overall request to fail. Instead we will hand bad data off to
        the caller - that is not ideal but in theory we should have checked everything on the way in and
        only allowed in good data.
        """
        if self._cachedComponent is None:

            text = yield self._text()

            try:
                component = VCard.fromString(text)
            except InvalidVCardDataError, e:
                # This is a really bad situation, so do raise
                raise InternalDataStoreError(
                    "Data corruption detected (%s) in id: %s"
                    % (e, self._resourceID)
                )

            # Fix any bogus data we can
            fixed, unfixed = component.validVCardData(doFix=True, doRaise=False)

            if unfixed:
                self.log_error("Address data id=%s had unfixable problems:\n  %s" % (self._resourceID, "\n  ".join(unfixed),))

            if fixed:
                self.log_error("Address data id=%s had fixable problems:\n  %s" % (self._resourceID, "\n  ".join(fixed),))

            self._cachedComponent = component

        returnValue(self._cachedComponent)


    def moveValidation(self, destination, name):
        """
        Validate whether a move to the specified collection is allowed.

        @param destination: destination calendar collection
        @type destination: L{CalendarCollection}
        @param name: name of new resource
        @type name: C{str}
        """
        pass


    # IDataStoreObject
    def contentType(self):
        """
        The content type of Addressbook objects is text/vcard.
        """
        return MimeType.fromString("text/vcard; charset=utf-8")



AddressBook._objectResourceClass = AddressBookObject
