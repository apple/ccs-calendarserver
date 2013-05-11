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

from uuid import uuid4

from twext.enterprise.dal.syntax import Delete, Insert, Len, Parameter, \
    Update, Union, Max, Select, utcNowSQL
from twext.python.clsprop import classproperty
from twext.web2.http import HTTPError
from twext.web2.http_headers import MimeType
from twext.web2.responsecode import FORBIDDEN

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import hashlib
from twistedcaldav import carddavxml, customxml
from twistedcaldav.memcacher import Memcacher
from twistedcaldav.vcard import Component as VCard, InvalidVCardDataError, \
    vCardProductID, Property

from txdav.base.propertystore.base import PropertyName
from txdav.base.propertystore.sql import PropertyStore
from txdav.carddav.datastore.util import validateAddressBookComponent
from txdav.carddav.iaddressbookstore import IAddressBookHome, IAddressBook, \
    IAddressBookObject, GroupForSharedAddressBookDeleteNotAllowedError, \
    GroupWithUnsharedAddressNotAllowedError, SharedGroupDeleteNotAllowedError
from txdav.common.datastore.sql import CommonHome, CommonHomeChild, \
    CommonObjectResource, EADDRESSBOOKTYPE, SharingMixIn
from txdav.common.datastore.sql_legacy import PostgresLegacyABIndexEmulator
from txdav.common.datastore.sql_tables import _ABO_KIND_PERSON, \
    _ABO_KIND_GROUP, _ABO_KIND_RESOURCE, _ABO_KIND_LOCATION, schema, \
    _BIND_MODE_OWN, _BIND_MODE_WRITE, _BIND_STATUS_ACCEPTED, \
    _BIND_STATUS_DECLINED, _BIND_STATUS_INVITED
from txdav.common.icommondatastore import InternalDataStoreError, \
    AllRetriesFailed
from txdav.xml.rfc2518 import ResourceType

from zope.interface.declarations import implements



class AddressBookHome(CommonHome):

    implements(IAddressBookHome)

    # structured tables.  (new, preferred)
    _homeSchema = schema.ADDRESSBOOK_HOME
    _bindSchema = schema.SHARED_ADDRESSBOOK_BIND
    _homeMetaDataSchema = schema.ADDRESSBOOK_HOME_METADATA
    _revisionsSchema = schema.ADDRESSBOOK_OBJECT_REVISIONS
    _objectSchema = schema.ADDRESSBOOK_OBJECT

    _notifierPrefix = "CardDAV"
    _dataVersionKey = "ADDRESSBOOK-DATAVERSION"
    _cacher = Memcacher("SQL.adbkhome", pickle=True, key_normalization=False)


    def __init__(self, transaction, ownerUID):

        self._childClass = AddressBook
        super(AddressBookHome, self).__init__(transaction, ownerUID)
        self._addressbookPropertyStoreID = None
        self._addressbook = None


    def __repr__(self):
        return '<%s: %s("%s")>' % (self.__class__.__name__, self._resourceID, self.name())


    addressbooks = CommonHome.children
    listAddressbooks = CommonHome.listChildren
    loadAddressbooks = CommonHome.loadChildren
    addressbookWithName = CommonHome.childWithName
    createAddressBookWithName = CommonHome.createChildWithName
    removeAddressBookWithName = CommonHome.removeChildWithName


    @classproperty
    def _resourceIDAndHomeResourceIDFromOwnerQuery(cls):  #@NoSelf
        home = cls._homeSchema
        return Select([home.RESOURCE_ID, home.ADDRESSBOOK_PROPERTY_STORE_ID],
                      From=home, Where=home.OWNER_UID == Parameter("ownerUID"))


    @inlineCallbacks
    def initFromStore(self, no_cache=False):
        """
        Initialize this object from the store. We read in and cache all the
        extra meta-data from the DB to avoid having to do DB queries for those
        individually later.
        """
        result = yield self._cacher.get(self._ownerUID)
        if result is None:
            result = yield self._resourceIDAndHomeResourceIDFromOwnerQuery.on(
                self._txn, ownerUID=self._ownerUID)
            if result and not no_cache:
                yield self._cacher.set(self._ownerUID, result)

        if result:
            self._resourceID, self._addressbookPropertyStoreID = result[0]

            queryCacher = self._txn._queryCacher
            if queryCacher:
                # Get cached copy
                cacheKey = queryCacher.keyForHomeMetaData(self._resourceID)
                data = yield queryCacher.get(cacheKey)
            else:
                data = None
            if data is None:
                # Don't have a cached copy
                data = (yield self._metaDataQuery.on(
                    self._txn, resourceID=self._resourceID))[0]
                if queryCacher:
                    # Cache the data
                    yield queryCacher.setAfterCommit(self._txn, cacheKey, data)

            #self._created, self._modified = data
            yield self._loadPropertyStore()

            # created owned address book
            addressbook = AddressBook(
                home=self,
                name="addressbook", resourceID=self._resourceID,
                mode=_BIND_MODE_OWN, status=_BIND_STATUS_ACCEPTED,
            )
            self._created, self._modified = data
            yield addressbook._loadPropertyStore()
            self._addressbook = addressbook

            returnValue(self)
        else:
            returnValue(None)


    @inlineCallbacks
    def remove(self):
        ah = schema.ADDRESSBOOK_HOME
        ahb = schema.SHARED_ADDRESSBOOK_BIND
        aor = schema.ADDRESSBOOK_OBJECT_REVISIONS
        rp = schema.RESOURCE_PROPERTY

        yield Delete(
            From=ahb,
            Where=ahb.ADDRESSBOOK_HOME_RESOURCE_ID == self._resourceID,
        ).on(self._txn)

        yield Delete(
            From=aor,
            Where=aor.ADDRESSBOOK_HOME_RESOURCE_ID == self._resourceID,
        ).on(self._txn)

        yield Delete(
            From=ah,
            Where=ah.RESOURCE_ID == self._resourceID,
        ).on(self._txn)

        yield Delete(
            From=rp,
            Where=(rp.RESOURCE_ID == self._resourceID).Or(
                rp.RESOURCE_ID == self._addressbookPropertyStoreID
            )
        ).on(self._txn)

        yield self._cacher.delete(str(self._ownerUID))


    @inlineCallbacks
    def createdHome(self):
        # initialize synctoken
        yield self.addressbook()._initSyncToken()


    @inlineCallbacks
    def removeUnacceptedShares(self):
        """
        Unbinds any collections that have been shared to this home but not yet
        accepted.  Associated invite entries are also removed.
        """
        super(AddressBookHome, self).removeUnacceptedShares()

        bind = AddressBookObject._bindSchema
        kwds = {"homeResourceID" : self._resourceID}
        yield Delete(
            From=bind,
            Where=(bind.HOME_RESOURCE_ID == Parameter("homeResourceID")
                   ).And(bind.BIND_STATUS != _BIND_STATUS_ACCEPTED)
        ).on(self._txn, **kwds)


    def addressbook(self):
        return self._addressbook


    def shareeAddressBookName(self):
        return self.uid()


    def objectWithShareUID(self, shareUID):
        """
        Retrieve the child with the given bind identifier contained in this
        home.

        @param name: a string.
        @return: an L{ICalendar} or C{None} if no such child exists.
        """
        return self._childClass.objectWithBindName(self, shareUID, accepted=True)


    def invitedObjectWithShareUID(self, shareUID):
        """
        Retrieve the child invitation with the given bind identifier contained in this
        home.

        @param name: a string.
        @return: an L{ICalendar} or C{None} if no such child exists.
        """
        return self._childClass.objectWithBindName(self, shareUID, accepted=False)


    @inlineCallbacks
    def ownerHomeWithChildID(self, resourceID):
        """
        Get the owner home for a shared child ID
        """
        # addressbook and home have same resourceID
        ownerHome = yield self._txn.homeWithResourceID(self._homeType, resourceID)
        returnValue(ownerHome)


    @inlineCallbacks
    def ownerHomeAndChildNameForChildID(self, resourceID):
        """
        Get the owner home for a shared child ID and the owner's name for that bound child.
        Subclasses may override.
        """
        ownerHome = yield self.ownerHomeWithChildID(resourceID)
        ownerName = ownerHome.addressbook().name()
        returnValue((ownerHome, ownerName))


    @classproperty
    def _syncTokenQuery(cls):  #@NoSelf
        """
        DAL Select statement to find the sync token.
        """
        rev = cls._revisionsSchema
        bind = cls._bindSchema
        return Select(
            [Max(rev.REVISION)],
            # active shared address books
            From=Select(
                [rev.REVISION],
                From=rev,
                Where=(
                    rev.RESOURCE_ID.In(
                        Select(
                            [bind.RESOURCE_ID],
                            From=bind,
                            Where=bind.HOME_RESOURCE_ID == Parameter("resourceID"),
                        )
                    )
                ),
                SetExpression=Union(
                    # deleted shared address books
                    Select(
                        [rev.REVISION],
                        From=rev,
                        Where=(rev.HOME_RESOURCE_ID == Parameter("resourceID")).And(rev.RESOURCE_ID == None),
                        SetExpression=Union(
                            # owned address book: owned address book cannot be deleted: See AddressBook.remove()
                            Select(
                                [rev.REVISION],
                                From=rev,
                                Where=(rev.HOME_RESOURCE_ID == Parameter("resourceID")).And(rev.RESOURCE_ID == rev.HOME_RESOURCE_ID),
                            ),
                            optype=Union.OPTYPE_ALL,
                        )
                    ),
                    optype=Union.OPTYPE_ALL,
                )
            ),
        )


    @classproperty
    def _changesQuery(cls):  #@NoSelf
        rev = cls._revisionsSchema
        return Select(
            [rev.RESOURCE_NAME, rev.DELETED],
            From=rev,
            Where=(rev.REVISION > Parameter("token")).And(
                rev.HOME_RESOURCE_ID == Parameter("resourceID")).And(
                rev.RESOURCE_ID == rev.HOME_RESOURCE_ID)
        )

    @inlineCallbacks
    def changesSinceToken(self, token):
        """
        return list of (path, name, wasdeleted) of changes since token
        Subclasses may override
        """
        results = [
            (
                self.addressbook().name(),
                name if name else "",
                wasdeleted
            )
            for name, wasdeleted in (
                yield self._changesQuery.on(
                    self._txn,
                    resourceID=self._resourceID,
                    token=token
                )
            )
        ]
        returnValue(results)


AddressBookHome._register(EADDRESSBOOKTYPE)



class AddressBook(CommonHomeChild, SharingMixIn):
    """
    SQL-based implementation of L{IAddressBook}.
    """
    implements(IAddressBook)

    # structured tables.  (new, preferred)
    _homeSchema = schema.ADDRESSBOOK_HOME
    _bindSchema = schema.SHARED_ADDRESSBOOK_BIND
    _homeChildSchema = schema.ADDRESSBOOK_HOME
    _homeChildMetaDataSchema = schema.ADDRESSBOOK_HOME_METADATA
    _revisionsSchema = schema.ADDRESSBOOK_OBJECT_REVISIONS
    _objectSchema = schema.ADDRESSBOOK_OBJECT


    def __init__(self, home, name, resourceID, mode, status, message=None, ownerHome=None, bindName=None):
        ownerName = ownerHome.addressbook().name() if ownerHome else None
        super(AddressBook, self).__init__(home, name, resourceID, mode, status, message=message, ownerHome=ownerHome, ownerName=ownerName)
        self._index = PostgresLegacyABIndexEmulator(self)
        self._bindName = bindName


    def __repr__(self):
        return '<%s: %s("%s")>' % (self.__class__.__name__, self._resourceID, self.name())


    def getCreated(self):
        return self.ownerHome()._created


    def setCreated(self, newValue):
        self.ownerHome()._created = newValue


    def getModified(self):
        return self.ownerHome()._modified


    def setModified(self, newValue):
        self.ownerHome()._modified = newValue


    _created = property(getCreated, setCreated,)
    _modified = property(getModified, setModified,)


    @property
    def _addressbookHome(self):
        return self._home


    def resourceType(self):
        return ResourceType.addressbook  #@UndefinedVariable


    #FIXME: Only used for shared group resouretype in SharedResourceMixin.upgradeToShare() and SharedResourceMixin.downgradeFromShare()
    def objectResourcesHaveProperties(self):
        return True


    ownerAddressBookHome = CommonHomeChild.ownerHome
    viewerAddressBookHome = CommonHomeChild.viewerHome
    addressbookObjects = CommonHomeChild.objectResources
    listAddressBookObjects = CommonHomeChild.listObjectResources
    addressbookObjectWithName = CommonHomeChild.objectResourceWithName
    addressbookObjectWithUID = CommonHomeChild.objectResourceWithUID
    createAddressBookObjectWithName = CommonHomeChild.createObjectResourceWithName
    addressbookObjectsSinceToken = CommonHomeChild.objectResourcesSinceToken


    def shareeAddressBookName(self):
        return self._home.shareeAddressBookName()


    @inlineCallbacks
    def _loadPropertyStore(self, props=None):
        if props is None:
            props = yield PropertyStore.load(
                self.ownerHome().uid(),
                self.viewerHome().uid(),
                self._txn,
                self.ownerHome()._addressbookPropertyStoreID,  # not ._resourceID as in CommonHomeChild._loadPropertyStore()
                notifyCallback=self.notifyChanged
            )
        super(AddressBook, self)._loadPropertyStore(props)


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
        The content type of addressbook objects is text/vcard.
        """
        return MimeType.fromString("text/vcard; charset=utf-8")


    @classmethod
    def create(cls, home, name):
        if name == home.addressbook().name():
            #raise HomeChildNameAlreadyExistsError
            pass
        else:
            #raise HomeChildNameNotAllowedError
            raise HTTPError(FORBIDDEN)


    @inlineCallbacks
    def remove(self):

        if self._resourceID == self._home._resourceID:
            # allow remove, as a way to reset the address book to an empty state
            for abo in (yield self.objectResources()):
                yield abo.remove()
                yield self.removedObjectResource(abo)

            yield self.unshare()  # storebridge should already have done this

            # don't delete. Note that revision table is NOT queried for removes
            # yield self._deletedSyncToken()
            yield self._updateRevision(self.name())

            # TODO:  See why the following 2 lines do not work reliably
            # yield self.properties()._removeResource()
            # yield self._loadPropertyStore()
            for prop in self.properties():
                self.properties().pop(prop, None)
            self.properties()[
                PropertyName.fromElement(ResourceType)
            ] = self.resourceType()

            yield self.notifyChanged()
            yield self._home.bumpModified()
        else:
            returnValue((yield super(AddressBook, self).remove()))


    def rename(self, name):
        # better error?
        # raise HomeChildNameNotAllowedError
        raise HTTPError(FORBIDDEN)


    @classmethod
    def _objectResourceNamesWithResourceIDsQuery(cls, resourceIDs):
        """
        DAL statement to retrieve addressbook object name with given resourceIDs
        """
        obj = cls._objectSchema
        return Select([obj.RESOURCE_NAME], From=obj,
                      Where=obj.RESOURCE_ID.In(Parameter("resourceIDs", len(resourceIDs))),)


    @inlineCallbacks
    def listObjectResources(self):
        if self._objectNames is None:
            if self.owned() or self.fullyShared():
                rows = yield self._objectResourceNamesQuery.on(
                    self._txn, resourceID=self._resourceID)
            else:
                acceptedGroupIDs = yield self.acceptedGroupIDs()
                allowedObjectIDs = yield self.expandGroupIDs(self._txn, acceptedGroupIDs)
                rows = (yield self._objectResourceNamesWithResourceIDsQuery(allowedObjectIDs).on(
                    self._txn, resourceIDs=allowedObjectIDs
                ))
            objectNames = [row[0] for row in rows]

            # account for fully-shared address book group
            if self.fullyShared():
                if not self._fullySharedAddressBookGroupName() in objectNames:
                    objectNames.append(self._fullySharedAddressBookGroupName())
            self._objectNames = sorted(objectNames)

        returnValue(self._objectNames)


    @inlineCallbacks
    def countObjectResources(self):
        if self._objectNames is None:
            if self.owned() or self.fullyShared():
                rows = yield self._objectCountQuery.on(
                    self._txn, resourceID=self._resourceID
                )
                count = rows[0][0]
            else:
                acceptedGroupIDs = yield self.acceptedGroupIDs()
                count = len((yield self.expandGroupIDs(self._txn, acceptedGroupIDs)))

            # account for fully-shared address book group
            if self.fullyShared():
                count += 1
            returnValue(count)

        returnValue(len(self._objectNames))


    @classmethod
    def _abObjectColumnsWithAddressBookResourceID(cls, columns):
        """
        DAL statement to retrieve addressbook object rows with given columns.
        """
        obj = cls._objectSchema
        return Select(columns, From=obj,
                      Where=obj.ADDRESSBOOK_HOME_RESOURCE_ID == Parameter("addressbookResourceID"),)


    def _fullySharedAddressBookGroupRow(self):  #@NoSelf
        return [
            self._resourceID,  # obj.ADDRESSBOOK_HOME_RESOURCE_ID,
            self._resourceID,  # obj.RESOURCE_ID,
            self._fullySharedAddressBookGroupName(),  # obj.RESOURCE_NAME, shared name is UID and thus avoids collisions
            self._fullySharedAddressBookGroupUID(),  # obj.UID, shared name is uuid
            _ABO_KIND_GROUP,  # obj.KIND,
            "1",  # obj.MD5, unused
            "1",  # Len(obj.TEXT), unused
            self._created,  # obj.CREATED,
            self._modified,  # obj.CREATED,
        ]


    def _fullySharedAddressBookGroupName(self):
        return self.ownerHome().addressbook().name() + ".vcf"


    def _fullySharedAddressBookGroupUID(self):
        return self.name()


    @inlineCallbacks
    def _fullySharedAddressBookGroupComponent(self):

        n = self.ownerHome().shareeAddressBookName()
        fn = n
        uid = self.name()

        #  store bridge should substitute principal name and full name
        #      owner = yield CalDAVResource.principalForUID(self.ownerHome().uid())
        #      n = owner.name()
        #      fn = owner.displayName()

        component = VCard.fromString(
            """BEGIN:VCARD
VERSION:3.0
PRODID:%s
UID:%s
FN:%s
N:%s;;;;
X-ADDRESSBOOKSERVER-KIND:group
END:VCARD
""".replace("\n", "\r\n") % (vCardProductID, uid, n, fn,)
        )

        # then get member UIDs
        abo = schema.ADDRESSBOOK_OBJECT
        memberUIDRows = yield self._abObjectColumnsWithAddressBookResourceID(
            [abo.VCARD_UID]
        ).on(self._txn, addressbookResourceID=self._resourceID)
        memberUIDs = [memberUIDRow[0] for memberUIDRow in memberUIDRows]

        # add prefix to get property string
        memberAddresses = ["urn:uuid:" + memberUID for memberUID in memberUIDs]

        # now add the properties to the component
        for memberAddress in sorted(memberAddresses):
            component.addProperty(Property("X-ADDRESSBOOKSERVER-MEMBER", memberAddress))

        returnValue(component)


    @inlineCallbacks
    def bumpModified(self):
        # TODO: The next line seems the next line work too.  Why?
        # returnValue((yield self.ownerHome().bumpModified()))
        #
        if self._resourceID == self._home._resourceID:
            returnValue((yield self._home.bumpModified()))
        else:
            returnValue((yield super(AddressBook, self).bumpModified()))


    @classmethod
    @inlineCallbacks
    def loadAllObjects(cls, home):
        """
        Load all L{CommonHomeChild} instances which are children of a given
        L{CommonHome} and return a L{Deferred} firing a list of them.  This must
        create the child classes and initialize them using "batched" SQL
        operations to keep this constant wrt the number of children.  This is an
        optimization for Depth:1 operations on the home.
        """
        results = [home.addressbook(), ]
        ownerHomeToDataRowMap = {}

        # Load from the main table first
        dataRows = yield cls._childrenAndMetadataForHomeID.on(
            home._txn, homeID=home._resourceID
        )
        # get ownerHomeIDs
        for dataRow in dataRows:
            bindMode, homeID, resourceID, bindName, bindStatus, bindMessage = dataRow[:6]  #@UnusedVariable
            ownerHome = yield home.ownerHomeWithChildID(resourceID)
            ownerHomeToDataRowMap[ownerHome] = dataRow

        # now get group rows:
        groupBindRows = yield AddressBookObject._childrenAndMetadataForHomeID.on(
            home._txn, homeID=home._resourceID
        )
        for groupBindRow in groupBindRows:
            bindMode, homeID, resourceID, bindName, bindStatus, bindMessage = groupBindRow[:6]  #@UnusedVariable
            ownerAddressBookID = yield AddressBookObject.ownerAddressBookFromGroupID(home._txn, resourceID)
            ownerHome = yield home.ownerHomeWithChildID(ownerAddressBookID)
            if ownerHome not in ownerHomeToDataRowMap:
                groupBindRow[0] = _BIND_MODE_WRITE
                groupBindRow[3] = None  # bindName
                groupBindRow[4] = None  # bindStatus
                groupBindRow[5] = None  # bindMessage
                ownerHomeToDataRowMap[ownerHome] = groupBindRow

        if ownerHomeToDataRowMap:
            # Get property stores for all these child resources (if any found)
            addressbookPropertyStoreIDs = [ownerHome._addressbookPropertyStoreID for ownerHome in ownerHomeToDataRowMap]
            propertyStores = yield PropertyStore.forMultipleResourcesWithResourceIDs(
                home.uid(), home._txn, addressbookPropertyStoreIDs
            )
            addressbookResourceIDs = [ownerHome._resourceID for ownerHome in ownerHomeToDataRowMap]
            revisions = yield cls._revisionsForResourceIDs(addressbookPropertyStoreIDs).on(home._txn, resourceIDs=addressbookResourceIDs)
            revisions = dict(revisions)

            # Create the actual objects merging in properties
            for ownerHome, dataRow in ownerHomeToDataRowMap.iteritems():
                bindMode, homeID, resourceID, bindName, bindStatus, bindMessage = dataRow[:6]  #@UnusedVariable
                metadata = dataRow[6:]

                child = cls(
                    home=home,
                    name=ownerHome.shareeAddressBookName(),
                    resourceID=ownerHome._resourceID,
                    mode=bindMode, status=bindStatus,
                    message=bindMessage, ownerHome=ownerHome,
                    bindName=bindName
                )

                for attr, value in zip(cls.metadataAttributes(), metadata):
                    setattr(child, attr, value)
                child._syncTokenRevision = revisions[child._resourceID]
                propstore = propertyStores.get(ownerHome._addressbookPropertyStoreID, None)
                # We have to re-adjust the property store object to account for possible shared
                # collections as previously we loaded them all as if they were owned
                propstore._setDefaultUserUID(ownerHome.uid())
                yield child._loadPropertyStore(propstore)
                results.append(child)

        returnValue(results)


    @classmethod
    @inlineCallbacks
    def objectWithName(cls, home, name, accepted=True):
        """
        Retrieve the child with the given C{name} contained in the given
        C{home}.

        @param home: a L{CommonHome}.

        @param name: a string; the name of the L{CommonHomeChild} to retrieve.

        @return: an L{CommonHomeChild} or C{None} if no such child
            exists.
        """
        if accepted and name == home.addressbook().name():
            returnValue(home.addressbook())

        #all shared address books now
        rows = None
        queryCacher = home._txn._queryCacher
        ownerHome = None

        if queryCacher:
            # Retrieve data from cache
            cacheKey = queryCacher.keyForObjectWithName(home._resourceID, name)
            rows = yield queryCacher.get(cacheKey)

        if rows is None:

            # name must be a home uid
            ownerHome = yield home._txn.addressbookHomeWithUID(name)
            if ownerHome:
                # see if address book resource id in bind table
                ownerAddressBook = ownerHome.addressbook()
                rows = yield cls._bindForResourceIDAndHomeID.on(
                    home._txn, resourceID=ownerAddressBook._resourceID, homeID=home._resourceID
                )
                if rows:
                    rows[0].append(ownerAddressBook._resourceID)
                    rows[0].append(rows[0][4])  # cachedStatus = bindStatus
                else:
                    groupBindRows = yield AddressBookObject._bindWithHomeIDAndAddressBookID.on(
                            home._txn, homeID=home._resourceID, addressbookID=ownerAddressBook._resourceID
                    )
                    if groupBindRows:
                        groupBindRow = groupBindRows[0]
                        cachedBindStatus = groupBindRow[4]  # save off bindStatus
                        groupBindRow[0] = _BIND_MODE_WRITE
                        groupBindRow[3] = None  # bindName
                        groupBindRow[4] = None  # bindStatus
                        groupBindRow[5] = None  # bindMessage
                        groupBindRow.append(ownerAddressBook._resourceID)
                        groupBindRow.append(cachedBindStatus)
                        rows = [groupBindRow]

            if rows and queryCacher:
                # Cache the result
                queryCacher.setAfterCommit(home._txn, cacheKey, rows)

        if not rows:
            returnValue(None)

        bindMode, homeID, resourceID, bindName, bindStatus, bindMessage, ownerAddressBookID, cachedBindStatus = rows[0]  #@UnusedVariable
        # if wrong status, exit here.  Item is in queryCache
        if (cachedBindStatus == _BIND_STATUS_ACCEPTED) != bool(accepted):
            returnValue(None)

        ownerHome = yield home.ownerHomeWithChildID(ownerAddressBookID)
        ownerAddressBook = ownerHome.addressbook()
        child = cls(
                home=home,
                name=ownerAddressBook.shareeAddressBookName(), resourceID=ownerAddressBookID,
                mode=bindMode, status=bindStatus,
                message=bindMessage, ownerHome=ownerHome,
                bindName=bindName,
            )
        yield child.initFromStore()
        returnValue(child)


    @classmethod
    @inlineCallbacks
    def objectWithBindName(cls, home, name, accepted):
        """
        Retrieve the child or objectResource with the given bind name C{name} contained in the given
        C{home}.

        @param home: a L{CommonHome}.

        @param name: a string; the name of the L{CommonHomeChild} to retrieve.

        @return: an L{CommonHomeChild} or L{ObjectResource} or C{None} if no such child
            exists.
        """
        bindRows = yield cls._bindForNameAndHomeID.on(home._txn, name=name, homeID=home._resourceID)
        if bindRows:
            bindMode, homeID, resourceID, bindName, bindStatus, bindMessage = bindRows[0]  #@UnusedVariable
            if (bindStatus == _BIND_STATUS_ACCEPTED) != bool(accepted):
                returnValue(None)

            # alt:
            # returnValue((yield cls.objectWithID(home, resourceID)))
            ownerHome = yield home.ownerHomeWithChildID(resourceID)
            if accepted:
                returnValue((yield home.childWithName(ownerHome.shareeAddressBookName())))
            else:
                returnValue((yield cls.objectWithName(home, ownerHome.shareeAddressBookName(), accepted=False)))

        groupBindRows = yield AddressBookObject._bindForNameAndHomeID.on(
            home._txn, name=name, homeID=home._resourceID
        )
        if groupBindRows:
            bindMode, homeID, resourceID, bindName, bindStatus, bindMessage = groupBindRows[0]  #@UnusedVariable
            if (bindStatus == _BIND_STATUS_ACCEPTED) != bool(accepted):
                returnValue(None)

            ownerAddressBookID = yield AddressBookObject.ownerAddressBookFromGroupID(home._txn, resourceID)
            # alt:
            # addressbook = yield cls.objectWithID(home, ownerAddressBookID)
            ownerHome = yield home.ownerHomeWithChildID(ownerAddressBookID)
            addressbook = yield home.childWithName(ownerHome.shareeAddressBookName())
            if not addressbook:
                addressbook = yield cls.objectWithName(home, ownerHome.shareeAddressBookName(), accepted=False)

            if accepted:
                returnValue((yield addressbook.objectResourceWithID(resourceID)))
            else:
                returnValue((yield AddressBookObject.objectWithID(addressbook, resourceID)))  # avoids object cache

        returnValue(None)


    @classmethod
    @inlineCallbacks
    def objectWithID(cls, home, resourceID, accepted=True):
        """
        Retrieve the child with the given C{resourceID} contained in the given
        C{home}.

        @param home: a L{CommonHome}.
        @param resourceID: a string.
        @return: an L{CommonHomeChild} or C{None} if no such child
            exists.
        """
        if home._resourceID == resourceID:
            returnValue(home.addressbook())

        bindRows = yield cls._bindForResourceIDAndHomeID.on(
            home._txn, resourceID=resourceID, homeID=home._resourceID
        )
        if bindRows:
            bindMode, homeID, resourceID, bindName, bindStatus, bindMessage = bindRows[0]  #@UnusedVariable
            if (bindStatus == _BIND_STATUS_ACCEPTED) != bool(accepted):
                returnValue(None)

            ownerHome = yield home.ownerHomeWithChildID(resourceID)
            if accepted:
                returnValue((yield home.childWithName(ownerHome.shareeAddressBookName())))
            else:
                returnValue((yield cls.objectWithName(home, ownerHome.shareeAddressBookName(), accepted=False)))

        groupBindRows = yield AddressBookObject._bindWithHomeIDAndAddressBookID.on(
                    home._txn, homeID=home._resourceID, addressbookID=resourceID
        )
        if groupBindRows:
            bindMode, homeID, resourceID, bindName, bindStatus, bindMessage = groupBindRows[0]  #@UnusedVariable
            if (bindStatus == _BIND_STATUS_ACCEPTED) != bool(accepted):
                returnValue(None)

            ownerAddressBookID = yield AddressBookObject.ownerAddressBookFromGroupID(home._txn, resourceID)
            ownerHome = yield home.ownerHomeWithChildID(ownerAddressBookID)
            if accepted:
                returnValue((yield home.childWithName(ownerHome.shareeAddressBookName())))
            else:
                returnValue((yield cls.objectWithName(home, ownerHome.shareeAddressBookName(), accepted=False)))

        returnValue(None)


    def shareUID(self):
        """
        @see: L{ICalendar.shareUID}
        """
        return self._bindName


    def fullyShared(self):
        return not self.owned() and self._bindStatus == _BIND_STATUS_ACCEPTED


    @classmethod
    @inlineCallbacks
    def listObjects(cls, home):
        """
        Retrieve the names of the children with invitations in the given home.

        @return: an iterable of C{str}s.
        """
        names = set([home.addressbook().name()])

        rows = yield cls._acceptedBindForHomeID.on(
            home._txn, homeID=home._resourceID
        )
        rows.extend((yield AddressBookObject._acceptedBindForHomeID.on(
            home._txn, homeID=home._resourceID
        )))
        for bindMode, homeID, resourceID, bindName, bindStatus, bindMessage in rows:  #@UnusedVariable
            ownerHome = yield home._txn.homeWithResourceID(home._homeType, homeID)
            names |= set([ownerHome.shareeAddressBookName()])
        returnValue(tuple(names))


    @classmethod
    def _memberIDsWithGroupIDsQuery(cls, groupIDs):
        """
        DAL query to load all object resource names for a home child.
        """
        aboMembers = schema.ABO_MEMBERS
        return Select([aboMembers.MEMBER_ID], From=aboMembers,
                      Where=aboMembers.GROUP_ID.In(Parameter("groupIDs", len(groupIDs))),
                      )


    @classmethod
    @inlineCallbacks
    def expandGroupIDs(cls, txn, groupIDs, includeGroupIDs=True):
        """
        Get all AddressBookObject resource IDs contains in the given shared groups with the given groupIDs
        """
        objectIDs = set(groupIDs) if includeGroupIDs else set()
        examinedIDs = set()
        remainingIDs = set(groupIDs)
        while remainingIDs:
            memberRows = yield cls._memberIDsWithGroupIDsQuery(remainingIDs).on(
                txn, groupIDs=remainingIDs
            )
            objectIDs |= set(memberRow[0] for memberRow in memberRows)
            examinedIDs |= remainingIDs
            remainingIDs = objectIDs - examinedIDs

        returnValue(tuple(objectIDs))


    @inlineCallbacks
    def unacceptedGroupIDs(self):
        if self.owned():
            returnValue([])
        else:
            groupBindRows = yield AddressBookObject._unacceptedBindWithHomeIDAndAddressBookID.on(
                    self._txn, homeID=self._home._resourceID, addressbookID=self._resourceID
            )
            #for bindMode, homeID, resourceID, bindName, bindStatus, bindMessage in groupBindRows: #@UnusedVariable
            returnValue([groupBindRow[2] for groupBindRow in groupBindRows])


    @inlineCallbacks
    def acceptedGroupIDs(self):
        if self.owned():
            returnValue([])
        else:
            groupBindRows = yield AddressBookObject._acceptedBindWithHomeIDAndAddressBookID.on(
                    self._txn, homeID=self._home._resourceID, addressbookID=self._resourceID
            )
            #for bindMode, homeID, resourceID, bindName, bindStatus, bindMessage in groupBindRows: #@UnusedVariable
            returnValue([groupBindRow[2] for groupBindRow in groupBindRows])


    @inlineCallbacks
    def accessControlGroupIDs(self):
        if self.owned():
            returnValue(([], []))
        else:
            groupBindRows = yield AddressBookObject._acceptedBindWithHomeIDAndAddressBookID.on(
                    self._txn, homeID=self._home._resourceID, addressbookID=self._resourceID
            )
            readWriteGroupIDs = []
            readOnlyGroupIDs = []
            for bindMode, homeID, resourceID, bindName, bindStatus, bindMessage in groupBindRows:  #@UnusedVariable
                if bindMode == _BIND_MODE_WRITE:
                    readWriteGroupIDs.append(resourceID)
                else:
                    readOnlyGroupIDs.append(resourceID)

            if readOnlyGroupIDs and readWriteGroupIDs:
                # expand read-write groups and remove any subgroups from read-only group list
                allWriteableIDs = yield self.expandGroupIDs(self._txn, readWriteGroupIDs)
                adjustedReadOnlyGroupIDs = set(readOnlyGroupIDs) - set(allWriteableIDs)
                adjustedReadWriteGroupIDs = set(readWriteGroupIDs) | (set(readOnlyGroupIDs) - adjustedReadOnlyGroupIDs)
            else:
                adjustedReadOnlyGroupIDs = readOnlyGroupIDs
                adjustedReadWriteGroupIDs = readWriteGroupIDs
            returnValue((tuple(adjustedReadOnlyGroupIDs), tuple(adjustedReadWriteGroupIDs)))

    #FIXME: Unused
    @inlineCallbacks
    def readOnlyGroupIDs(self):
        returnValue((yield self.accessControlGroupIDs())[0])


    @inlineCallbacks
    def readWriteGroupIDs(self):
        returnValue((yield self.accessControlGroupIDs())[1])


    #FIXME: Unused:  Use for caching access
    @inlineCallbacks
    def accessControlObjectIDs(self):
        readOnlyIDs = set()
        readWriteIDs = set()
        if self.owned() or self.fullyShared():
            rows = yield self._allColumnsWithParent(self)
            ids = set([row[1] for row in rows])
            if self.fullyShared():
                ids |= set([self._resourceID, ])
            if self.owned() or self._bindMode == _BIND_MODE_WRITE:
                returnValue(tuple(readOnlyIDs), tuple(readWriteIDs))
            readOnlyIDs = set(ids)

        groupBindRows = yield AddressBookObject._acceptedBindWithHomeIDAndAddressBookID.on(
                self._txn, homeID=self._home._resourceID, addressbookID=self._resourceID
        )
        readWriteGroupIDs = []
        readOnlyGroupIDs = []
        for bindMode, homeID, resourceID, bindName, bindStatus, bindMessage in groupBindRows:  #@UnusedVariable
            if bindMode == _BIND_MODE_WRITE:
                readWriteGroupIDs.append(resourceID)
            else:
                readOnlyGroupIDs.append(resourceID)

        if readOnlyGroupIDs:
            readOnlyIDs |= set((yield self.expandGroupIDs(self._txn, readOnlyGroupIDs)))
        if readWriteGroupIDs:
            readWriteIDs |= set((yield self.expandGroupIDs(self._txn, readWriteGroupIDs)))
        readOnlyIDs -= readWriteIDs
        returnValue(tuple(readOnlyIDs), tuple(readWriteIDs))


    #FIXME: Unused:  Use for caching access
    @inlineCallbacks
    def readOnlyObjectIDs(self):
        returnValue((yield self.accessControlObjectIDs())[1])


    #FIXME: Unused:  Use for caching access
    @inlineCallbacks
    def readWriteObjectIDs(self):
        returnValue((yield self.accessControlObjectIDs())[1])


    #FIXME: Unused:  Use for caching access
    @inlineCallbacks
    def allObjectIDs(self):
        readOnlyIDs, readWriteIDs = yield self.accessControlObjectIDs()
        returnValue((readOnlyIDs + readWriteIDs))


    @inlineCallbacks
    def updateShare(self, shareeView, mode=None, status=None, message=None, name=None):
        """
        Update share mode, status, and message for a home child shared with
        this (owned) L{CommonHomeChild}.

        @param shareeView: The sharee home child that shares this.
        @type shareeView: L{CommonHomeChild}

        @param mode: The sharing mode; L{_BIND_MODE_READ} or
            L{_BIND_MODE_WRITE} or None to not update
        @type mode: L{str}

        @param status: The sharing status; L{_BIND_STATUS_INVITED} or
            L{_BIND_STATUS_ACCEPTED} or L{_BIND_STATUS_DECLINED} or
            L{_BIND_STATUS_INVALID}  or None to not update
        @type status: L{str}

        @param message: The proposed message to go along with the share, which
            will be used as the default display name, or None to not update
        @type message: L{str}

        @param name: The bind resource name or None to not update
        @type message: L{str}

        @return: the name of the shared item in the sharee's home.
        @rtype: a L{Deferred} which fires with a L{str}
        """
        # TODO: raise a nice exception if shareeView is not, in fact, a shared
        # version of this same L{CommonHomeChild}

        #remove None parameters, and substitute None for empty string
        bind = self._bindSchema
        columnMap = dict([(k, v if v else None)
                          for k, v in {bind.BIND_MODE:mode,
                            bind.BIND_STATUS:status,
                            bind.MESSAGE:message,
                            bind.RESOURCE_NAME:name}.iteritems() if v is not None])

        if len(columnMap):

            # count accepted
            if status is not None:
                previouslyAcceptedBindCount = 1 if shareeView.fullyShared() else 0
                previouslyAcceptedBindCount += len((yield AddressBookObject._acceptedBindWithHomeIDAndAddressBookID.on(
                        self._txn, homeID=shareeView._home._resourceID, addressbookID=shareeView._resourceID
                )))

            sharedname = yield self._updateBindColumnsQuery(columnMap).on(
                self._txn,
                resourceID=self._resourceID, homeID=shareeView._home._resourceID
            )

            #update affected attributes
            if mode is not None:
                shareeView._bindMode = columnMap[bind.BIND_MODE]

            if status is not None:
                shareeView._bindStatus = columnMap[bind.BIND_STATUS]
                if shareeView._bindStatus == _BIND_STATUS_ACCEPTED:
                    if 0 == previouslyAcceptedBindCount:
                        yield shareeView._initSyncToken()
                        shareeView._home._children[shareeView._name] = shareeView
                        shareeView._home._children[shareeView._resourceID] = shareeView
                elif shareeView._bindStatus == _BIND_STATUS_DECLINED:
                    if 1 == previouslyAcceptedBindCount:
                        shareeView._deletedSyncToken(sharedRemoval=True)
                        shareeView._home._children.pop(shareeView._name, None)
                        shareeView._home._children.pop(shareeView._resourceID, None)


            if message is not None:
                shareeView._bindMessage = columnMap[bind.MESSAGE]

            queryCacher = self._txn._queryCacher
            if queryCacher:
                cacheKey = queryCacher.keyForObjectWithName(shareeView._home._resourceID, shareeView._name)
                queryCacher.invalidateAfterCommit(self._txn, cacheKey)

            shareeView._name = sharedname[0][0]

            # Must send notification to ensure cache invalidation occurs
            yield self.notifyChanged()

        returnValue(shareeView._name)


    @inlineCallbacks
    def asShared(self):
        """
        Retrieve all the versions of this L{CommonHomeChild} as it is shared to
        everyone.

        @see: L{ICalendarHome.asShared}

        @return: L{CommonHomeChild} objects that represent this
            L{CommonHomeChild} as a child of different L{CommonHome}s
        @rtype: a L{Deferred} which fires with a L{list} of L{ICalendar}s.
        """
        result = []
        if self.owned():
            # get all accepted shared binds
            bindRows = yield self._sharedBindForResourceID.on(
                self._txn, resourceID=self._resourceID, homeID=self._home._resourceID
            )
            for bindMode, homeID, resourceID, bindName, bindStatus, bindMessage in bindRows:  #@UnusedVariable
                home = yield self._txn.homeWithResourceID(self._home._homeType, homeID)
                new = yield home.childWithName(self.shareeAddressBookName())
                result.append(new)

        returnValue(result)


    @inlineCallbacks
    def asInvited(self):
        """
        Retrieve all the versions of this L{CommonHomeChild} as it is invited to
        everyone.

        @see: L{ICalendarHome.asInvited}

        @return: L{CommonHomeChild} objects that represent this
            L{CommonHomeChild} as a child of different L{CommonHome}s
        @rtype: a L{Deferred} which fires with a L{list} of L{ICalendar}s.
        """
        result = []
        if self.owned():
            # get all accepted shared binds
            bindRows = yield self._unacceptedBindForResourceID.on(
                self._txn, resourceID=self._resourceID
            )
            for bindMode, homeID, resourceID, bindName, bindStatus, bindMessage in bindRows:  #@UnusedVariable
                home = yield self._txn.homeWithResourceID(self._home._homeType, homeID)
                new = yield self.objectWithName(home, self.shareeAddressBookName(), accepted=False)
                result.append(new)

        returnValue(result)


    @inlineCallbacks
    def unshareWith(self, shareeHome):
        """
        Remove the shared version of this (owned) L{CommonHomeChild} from the
        referenced L{CommonHome}.

        @see: L{CommonHomeChild.shareWith}

        @param shareeHome: The home with which this L{CommonHomeChild} was
            previously shared.

        @return: a L{Deferred} which will fire with the previous shareUID
        """
        sharedAddressBook = yield shareeHome.addressbookWithName(self.shareeAddressBookName())
        if sharedAddressBook:

            acceptedBindCount = 1 if sharedAddressBook.fullyShared() else 0
            acceptedBindCount += len((yield AddressBookObject._acceptedBindWithHomeIDAndAddressBookID.on(
                    self._txn, homeID=shareeHome._resourceID, addressbookID=sharedAddressBook._resourceID
            )))
            if acceptedBindCount == 1:
                sharedAddressBook._deletedSyncToken(sharedRemoval=True)
                shareeHome._children.pop(self.sharedAddressBook.name(), None)
                shareeHome._children.pop(self.sharedAddressBook._resourceID, None)
            elif not sharedAddressBook.fullyShared():
                #FIXME: remove objects for this group only using self.removeObjectResource
                self._objectNames = None

            # Must send notification to ensure cache invalidation occurs
            yield self.notifyChanged()

        # delete binds including invites
        deletedBindNameRows = yield self._deleteBindWithResourceIDAndHomeID.on(self._txn, resourceID=self._resourceID,
             homeID=shareeHome._resourceID
        )
        if deletedBindNameRows:
            deletedBindName = deletedBindNameRows[0][0]
            queryCacher = self._txn._queryCacher
            if queryCacher:
                cacheKey = queryCacher.keyForObjectWithName(shareeHome._resourceID, self.shareeAddressBookName())
                queryCacher.invalidateAfterCommit(self._txn, cacheKey)
        else:
            deletedBindName = None

        returnValue(deletedBindName)



class AddressBookObject(CommonObjectResource, SharingMixIn):

    implements(IAddressBookObject)

    _objectSchema = schema.ADDRESSBOOK_OBJECT
    _bindSchema = schema.SHARED_GROUP_BIND

    # used by CommonHomeChild._childrenAndMetadataForHomeID() only
    #_homeChildSchema = schema.ADDRESSBOOK_OBJECT
    #_homeChildMetaDataSchema = schema.ADDRESSBOOK_OBJECT


    def __init__(self, addressbook, name, uid, resourceID=None, options=None):  #@UnusedVariable

        self._kind = None
        self._ownerAddressBookResourceID = None
        # _self._component is the cached, current component
        # super._objectText now contains the text as read of the database only,
        #     not including group member text
        self._component = None
        self._bindMode = None
        self._bindStatus = None
        self._bindMessage = None
        self._bindName = None
        super(AddressBookObject, self).__init__(addressbook, name, uid, resourceID, options)


    def __repr__(self):
        return '<%s: %s("%s")>' % (self.__class__.__name__, self._resourceID, self.name())


    @property
    def _addressbook(self):
        return self._parentCollection


    def addressbook(self):
        return self._addressbook


    def kind(self):
        return self._kind


    @classmethod
    def _deleteMembersWithMemberIDAndGroupIDsQuery(cls, memberID, groupIDs):
        aboMembers = schema.ABO_MEMBERS
        return Delete(
            aboMembers,
            Where=(aboMembers.MEMBER_ID == memberID).And(
                    aboMembers.GROUP_ID.In(Parameter("groupIDs", len(groupIDs)))))


    @inlineCallbacks
    def remove(self):

        if self.owned():
            # storebridge should already have done this
            yield self.unshare()
        else:
            # Can't delete a share here with notification so raise.
            if self._resourceID == self._addressbook._resourceID:
                raise GroupForSharedAddressBookDeleteNotAllowedError
            elif self.shareUID():
                raise SharedGroupDeleteNotAllowedError

        if not self.owned() and not self._addressbook.fullyShared():
            # convert delete in sharee shared group address book to remove of memberships
            # that make this object visible to the sharee

            readWriteGroupIDs = yield self._addressbook.readWriteGroupIDs()
            if readWriteGroupIDs:
                objectsIDs = yield self._addressbook.expandGroupIDs(self._txn, readWriteGroupIDs)
                yield self._deleteMembersWithMemberIDAndGroupIDsQuery(self._resourceID, objectsIDs).on(
                    self._txn, groupIDs=objectsIDs
                )

            yield self._changeAddressBookRevision(self.ownerHome().addressbook())

        else:
            # delete members table rows for this object,...
            aboMembers = schema.ABO_MEMBERS
            aboForeignMembers = schema.ABO_FOREIGN_MEMBERS

            groupIDRows = yield Delete(
                aboMembers,
                Where=aboMembers.MEMBER_ID == self._resourceID,
                Return=aboMembers.GROUP_ID
            ).on(self._txn)

            # add to foreign member table row by UID
            memberAddress = "urn:uuid:" + self._uid
            for groupID in [groupIDRow[0] for groupIDRow in groupIDRows]:
                if groupID != self._ownerAddressBookResourceID:  # no aboForeignMembers on address books
                    yield Insert(
                        {aboForeignMembers.GROUP_ID: groupID,
                         aboForeignMembers.ADDRESSBOOK_ID: self._ownerAddressBookResourceID,
                         aboForeignMembers.MEMBER_ADDRESS: memberAddress, }
                    ).on(self._txn)

            yield super(AddressBookObject, self).remove()
            self._kind = None
            self._ownerAddressBookResourceID = None
            self._component = None


    @inlineCallbacks
    def readWriteAccess(self):
        assert not self.owned(), "Don't call items in owned address book"

        # if fully shared and rw, must be RW since sharing group read-only has no affect
        if self._addressbook.fullyShared() and self._addressbook.shareMode() == _BIND_MODE_WRITE:
            yield None
            returnValue(True)

        readWriteGroupIDs = yield self._addressbook.readWriteGroupIDs()
        if self._resourceID in (yield self._addressbook.expandGroupIDs(self._txn, readWriteGroupIDs)):
            returnValue(True)

        returnValue(False)


    @classmethod
    def _allColumnsWithResourceIDsAnd(cls, resourceIDs, column, paramName):
        """
        DAL query for all columns where PARENT_RESOURCE_ID matches a parentID
        parameter and a given instance column matches a given parameter name.
        """
        obj = cls._objectSchema
        return Select(
            cls._allColumns, From=obj,
            Where=(column == Parameter(paramName)).And(
                obj.RESOURCE_ID.In(Parameter("resourceIDs", len(resourceIDs)))),
        )


    @classmethod
    def _allColumnsWithResourceIDsAndName(cls, resourceIDs):
        return cls._allColumnsWithResourceIDsAnd(resourceIDs, cls._objectSchema.RESOURCE_NAME, "name")


    @classmethod
    def _allColumnsWithResourceIDsAndUID(cls, resourceIDs):
        return cls._allColumnsWithResourceIDsAnd(resourceIDs, cls._objectSchema.UID, "uid")


    @classproperty
    def _allColumnsWithResourceID(cls):  #@NoSelf
        obj = cls._objectSchema
        return Select(
            cls._allColumns, From=obj,
            Where=obj.RESOURCE_ID == Parameter("resourceID"),)


    @inlineCallbacks
    def initFromStore(self):
        """
        Initialise this object from the store. We read in and cache all the
        extra metadata from the DB to avoid having to do DB queries for those
        individually later. Either the name or uid is present, so we have to
        tweak the query accordingly.

        @return: L{self} if object exists in the DB, else C{None}
        """
        rows = None
        if self.owned() or self._addressbook.fullyShared():  # owned or fully shared
            if self._name:
                rows = yield self._allColumnsWithParentAndName.on(
                    self._txn, name=self._name,
                    parentID=self._parentCollection._resourceID
                )
            elif self._uid:
                rows = yield self._allColumnsWithParentAndUID.on(
                    self._txn, uid=self._uid,
                    parentID=self._parentCollection._resourceID
                )
            elif self._resourceID:
                rows = yield self._allColumnsWithParentAndID.on(
                    self._txn, resourceID=self._resourceID,
                    parentID=self._parentCollection._resourceID
                )

            if not rows and self._addressbook.fullyShared():  # perhaps add special group
                if self._name:
                    if self._name == self._addressbook._fullySharedAddressBookGroupName():
                        rows = [self._addressbook._fullySharedAddressBookGroupRow()]
                elif self._uid:
                    if self._uid == (yield self._addressbook._fullySharedAddressBookGroupUID()):
                        rows = [self._addressbook._fullySharedAddressBookGroupRow()]
                elif self._resourceID:
                    if self._resourceID == self._addressbook._resourceID:
                        rows = [self._addressbook._fullySharedAddressBookGroupRow()]
        else:
            acceptedGroupIDs = yield self._addressbook.acceptedGroupIDs()
            allowedObjectIDs = yield self._addressbook.expandGroupIDs(self._txn, acceptedGroupIDs)
            if self._name:
                if allowedObjectIDs:
                    rows = (yield self._allColumnsWithResourceIDsAndName(allowedObjectIDs).on(
                        self._txn, name=self._name,
                        resourceIDs=allowedObjectIDs,
                    ))
            elif self._uid:
                if allowedObjectIDs:
                    rows = (yield self._allColumnsWithResourceIDsAndUID(allowedObjectIDs).on(
                        self._txn, uid=self._uid,
                        resourceIDs=allowedObjectIDs,
                    ))
            elif self._resourceID:
                if self._resourceID not in allowedObjectIDs:
                    # allow invited groups
                    allowedObjectIDs = yield self._addressbook.unacceptedGroupIDs()
                if self._resourceID in allowedObjectIDs:
                    rows = (yield self._allColumnsWithResourceID.on(
                        self._txn, resourceID=self._resourceID,
                    ))

        if rows:
            self._initFromRow(tuple(rows[0]))

            if self._kind == _ABO_KIND_GROUP:
                # generate "X-ADDRESSBOOKSERVER-MEMBER" properties
                # calc md5 and set size
                componentText = str((yield self.component()))
                self._md5 = hashlib.md5(componentText).hexdigest()
                self._size = len(componentText)

                groupBindRows = yield AddressBookObject._bindForResourceIDAndHomeID.on(
                    self._txn, resourceID=self._resourceID, homeID=self._home._resourceID
                )

                if groupBindRows:
                    bindMode, homeID, resourceID, bindName, bindStatus, bindMessage = groupBindRows[0]  #@UnusedVariable
                    self._bindMode = bindMode
                    self._bindStatus = bindStatus
                    self._bindMessage = bindMessage
                    self._bindName = bindName

            yield self._loadPropertyStore()

            returnValue(self)
        else:
            returnValue(None)


    @classproperty
    def _allColumns(cls):  #@NoSelf
        """
        Full set of columns in the object table that need to be loaded to
        initialize the object resource state.
        """
        obj = cls._objectSchema
        return [
            obj.ADDRESSBOOK_HOME_RESOURCE_ID,
            obj.RESOURCE_ID,
            obj.RESOURCE_NAME,
            obj.UID,
            obj.KIND,
            obj.MD5,
            Len(obj.TEXT),
            obj.CREATED,
            obj.MODIFIED,
        ]


    def _initFromRow(self, row):
        """
        Given a select result using the columns from L{_allColumns}, initialize
        the object resource state.
        """
        (self._ownerAddressBookResourceID,
         self._resourceID,
         self._name,
         self._uid,
         self._kind,
         self._md5,
         self._size,
         self._created,
         self._modified,) = tuple(row)


    @classmethod
    def _columnsWithResourceIDsQuery(cls, columns, resourceIDs):
        """
        DAL statement to retrieve addressbook object rows with given columns.
        """
        obj = cls._objectSchema
        return Select(columns, From=obj,
                      Where=obj.RESOURCE_ID.In(Parameter("resourceIDs", len(resourceIDs))),)


    @classmethod
    @inlineCallbacks
    def _allColumnsWithParent(cls, addressbook):
        if addressbook.owned() or addressbook.fullyShared():
            rows = yield super(AddressBookObject, cls)._allColumnsWithParent(addressbook)
            if addressbook.fullyShared():
                rows.append(addressbook._fullySharedAddressBookGroupRow())
        else:
            acceptedGroupIDs = yield addressbook.acceptedGroupIDs()
            allowedObjectIDs = yield addressbook.expandGroupIDs(addressbook._txn, acceptedGroupIDs)
            rows = yield cls._columnsWithResourceIDsQuery(cls._allColumns, allowedObjectIDs).on(
                addressbook._txn, resourceIDs=allowedObjectIDs
            )
        returnValue(rows)


    @classmethod
    def _allColumnsWithResourceIDsAndNamesQuery(cls, resourceIDs, names):
        obj = cls._objectSchema
        return Select(cls._allColumns, From=obj,
                      Where=(obj.RESOURCE_ID.In(Parameter("resourceIDs", len(resourceIDs))).And(
                          obj.RESOURCE_NAME.In(Parameter("names", len(names))))),)


    @classmethod
    @inlineCallbacks
    def _allColumnsWithParentAndNames(cls, addressbook, names):

        if addressbook.owned() or addressbook.fullyShared():
            rows = yield super(AddressBookObject, cls)._allColumnsWithParentAndNames(addressbook, names)
            if addressbook.fullyShared() and addressbook._fullySharedAddressBookGroupName() in names:
                rows.append(addressbook._fullySharedAddressBookGroupRow())
        else:
            acceptedGroupIDs = yield addressbook.acceptedGroupIDs()
            allowedObjectIDs = yield addressbook.expandGroupIDs(addressbook._txn, acceptedGroupIDs)
            rows = yield cls._allColumnsWithResourceIDsAndNamesQuery(allowedObjectIDs, names).on(
                addressbook._txn, resourceIDs=allowedObjectIDs, names=names
            )
        returnValue(rows)


    @inlineCallbacks
    def _changeAddressBookRevision(self, addressbook, inserting=False):
        if inserting:
            yield addressbook._insertRevision(self._name)
        else:
            yield addressbook._updateRevision(self._name)

        yield addressbook.notifyChanged()


    @inlineCallbacks
    def setComponent(self, component, inserting=False):

        self._componentChanged = False
        validateAddressBookComponent(self, self._addressbook, component, inserting)
        yield self.updateDatabase(component, inserting=inserting)
        yield self._changeAddressBookRevision(self._addressbook, inserting)

        if self.owned():
            # update revision table of the sharee group address book
            if self._kind == _ABO_KIND_GROUP:  # optimization
                for shareeAddressBook in (yield self.asShared()):
                    yield self._changeAddressBookRevision(shareeAddressBook, inserting)
                    # one is enough because all have the same resourceID
                    break
        else:
            if self._addressbook._resourceID != self._ownerAddressBookResourceID:
                # update revisions table of shared group's containing address book
                yield self._changeAddressBookRevision(self.ownerHome().addressbook(), inserting)

        # TODO:  a better job here!
        self._componentChanged = (self._component != component)
        self._component = component
        returnValue(self._componentChanged)


    @classmethod
    def _resourceIDAndUIDForUIDsAndAddressBookResourceIDQuery(cls, uids):
        abo = schema.ADDRESSBOOK_OBJECT
        return Select([abo.RESOURCE_ID, abo.VCARD_UID],
                      From=abo,
                      Where=((abo.ADDRESSBOOK_HOME_RESOURCE_ID == Parameter("addressbookResourceID")
                              ).And(
                                    abo.VCARD_UID.In(Parameter("uids", len(uids))))),
                      )


    @classmethod
    def _deleteMembersWithGroupIDAndMemberIDsQuery(cls, groupID, memberIDs):
        aboMembers = schema.ABO_MEMBERS
        return Delete(
            aboMembers,
            Where=(aboMembers.GROUP_ID == groupID).And(
                    aboMembers.MEMBER_ID.In(Parameter("memberIDs", len(memberIDs)))))


    @classmethod
    def _deleteForeignMembersWithGroupIDAndMembeAddrsQuery(cls, groupID, memberAddrs):
        aboForeignMembers = schema.ABO_FOREIGN_MEMBERS
        return Delete(
            aboForeignMembers,
            Where=(aboForeignMembers.GROUP_ID == groupID).And(
                    aboForeignMembers.MEMBER_ADDRESS.In(Parameter("memberAddrs", len(memberAddrs)))))


    @classproperty
    def _insertABObject(cls):  #@NoSelf
        """
        DAL statement to create an addressbook object with all default values.
        """
        abo = schema.ADDRESSBOOK_OBJECT
        return Insert(
            {abo.RESOURCE_ID: schema.RESOURCE_ID_SEQ,
             abo.ADDRESSBOOK_HOME_RESOURCE_ID: Parameter("addressbookResourceID"),
             abo.RESOURCE_NAME: Parameter("name"),
             abo.VCARD_TEXT: Parameter("text"),
             abo.VCARD_UID: Parameter("uid"),
             abo.KIND: Parameter("kind"),
             abo.MD5: Parameter("md5"),
             },
            Return=(abo.RESOURCE_ID,
                    abo.CREATED,
                    abo.MODIFIED))


    @inlineCallbacks
    def updateDatabase(self, component, expand_until=None, reCreate=False,  #@UnusedVariable
                       inserting=False):
        """
        Update the database tables for the new data being written.

        @param component: addressbook data to store
        @type component: L{Component}
        """

        componentResourceKindToAddressBookObjectKindMap = {
            "person": _ABO_KIND_PERSON,
            "group": _ABO_KIND_GROUP,
            "resource": _ABO_KIND_RESOURCE,
            "location": _ABO_KIND_LOCATION,
        }
        lcResourceKind = component.resourceKind().lower() if component.resourceKind() else component.resourceKind();
        kind = componentResourceKindToAddressBookObjectKindMap.get(lcResourceKind, _ABO_KIND_PERSON)
        assert inserting or self._kind == kind  # can't change kind. Should be checked in upper layers
        self._kind = kind

        # For shared groups:  Non owner may NOT add group members not currently in group!
        # (Or it would be possible to troll for unshared vCard UIDs and make them shared.)
        if not self._ownerAddressBookResourceID:
            self._ownerAddressBookResourceID = self.ownerHome().addressbook()._resourceID

        if self._kind == _ABO_KIND_GROUP:

            # get member ids
            memberUIDs = []
            foreignMemberAddrs = []
            for memberAddr in component.resourceMemberAddresses():
                if len(memberAddr) > len("urn:uuid:") and memberAddr.startswith("urn:uuid:"):
                    memberUIDs.append(memberAddr[len("urn:uuid:"):])
                else:
                    foreignMemberAddrs.append(memberAddr)

            memberRows = yield self._resourceIDAndUIDForUIDsAndAddressBookResourceIDQuery(memberUIDs).on(
                self._txn, addressbookResourceID=self._ownerAddressBookResourceID, uids=memberUIDs
            ) if memberUIDs else []
            memberIDs = [memberRow[0] for memberRow in memberRows]
            foundUIDs = [memberRow[1] for memberRow in memberRows]
            foreignMemberAddrs.extend(["urn:uuid:" + missingUID for missingUID in set(memberUIDs) - set(foundUIDs)])

            if not self.owned():
                if not self._addressbook.fullyShared():
                    #in shared ab defined by groups, all members must be inside the shared groups

                    #FIXME: does this apply to whole-shared address books too?
                    if foreignMemberAddrs:
                        raise GroupWithUnsharedAddressNotAllowedError

                    acceptedGroupIDs = yield self._addressbook.acceptedGroupIDs()
                    allowedObjectIDs = yield self._addressbook.expandGroupIDs(self._txn, acceptedGroupIDs)
                    if set(memberIDs) - set(allowedObjectIDs):
                        raise GroupWithUnsharedAddressNotAllowedError

            # don't store group members in object text

            # sort addresses in component text
            memberAddresses = component.resourceMemberAddresses()
            component.removeProperties("X-ADDRESSBOOKSERVER-MEMBER")
            for memberAddress in sorted(memberAddresses):
                component.addProperty(Property("X-ADDRESSBOOKSERVER-MEMBER", memberAddress))

            # use sorted test to get size and md5
            componentText = str(component)
            self._md5 = hashlib.md5(componentText).hexdigest()
            self._size = len(componentText)

            # remove members from component get new text
            component.removeProperties("X-ADDRESSBOOKSERVER-MEMBER")
            componentText = str(component)
            self._objectText = componentText

        else:
            componentText = str(component)
            self._md5 = hashlib.md5(componentText).hexdigest()
            self._size = len(componentText)
            self._objectText = componentText

        uid = component.resourceUID()
        assert inserting or self._uid == uid  # can't change UID. Should be checked in upper layers
        self._uid = uid

        # Special - if migrating we need to preserve the original md5
        if self._txn._migrating and hasattr(component, "md5"):
            self._md5 = component.md5

        abo = schema.ADDRESSBOOK_OBJECT
        aboForeignMembers = schema.ABO_FOREIGN_MEMBERS
        aboMembers = schema.ABO_MEMBERS

        if inserting:

            self._resourceID, self._created, self._modified = (
                yield self._insertABObject.on(
                    self._txn,
                    addressbookResourceID=self._ownerAddressBookResourceID,
                    name=self._name,
                    text=self._objectText,
                    uid=self._uid,
                    md5=self._md5,
                    kind=self._kind,
                )
            )[0]

            # delete foreign members table row for this object
            groupIDRows = yield Delete(
                aboForeignMembers,
                # should this be scoped to the owner address book?
                Where=aboForeignMembers.MEMBER_ADDRESS == "urn:uuid:" + self._uid,
                Return=aboForeignMembers.GROUP_ID
            ).on(self._txn)
            groupIDs = [groupIDRow[0] for groupIDRow in groupIDRows]

            # FIXME: Is this correct? Write test case
            if not self.owned():
                if not self._addressbook.fullyShared() or self._addressbook.shareMode() != _BIND_MODE_WRITE:
                    readWriteGroupIDs = yield self._addressbook.readWriteGroupIDs()
                    assert readWriteGroupIDs, "no access"
                    groupIDs.extend(readWriteGroupIDs)

            # add to member table rows
            for groupID in groupIDs:
                yield Insert(
                    {aboMembers.GROUP_ID: groupID,
                     aboMembers.ADDRESSBOOK_ID: self._ownerAddressBookResourceID,
                     aboMembers.MEMBER_ID: self._resourceID, }
                ).on(self._txn)

        else:
            self._modified = (yield Update(
                {abo.VCARD_TEXT: self._objectText,
                 abo.MD5: self._md5,
                 abo.MODIFIED: utcNowSQL},
                Where=abo.RESOURCE_ID == self._resourceID,
                Return=abo.MODIFIED).on(self._txn))[0][0]

        if self._kind == _ABO_KIND_GROUP:

            #get current members
            currentMemberRows = yield Select([aboMembers.MEMBER_ID],
                 From=aboMembers,
                 Where=aboMembers.GROUP_ID == self._resourceID,).on(self._txn)
            currentMemberIDs = [currentMemberRow[0] for currentMemberRow in currentMemberRows]

            memberIDsToDelete = set(currentMemberIDs) - set(memberIDs)
            memberIDsToAdd = set(memberIDs) - set(currentMemberIDs)

            if memberIDsToDelete:
                yield self._deleteMembersWithGroupIDAndMemberIDsQuery(self._resourceID, memberIDsToDelete).on(
                    self._txn, memberIDs=memberIDsToDelete
                )

            for memberIDToAdd in memberIDsToAdd:
                yield Insert(
                    {aboMembers.GROUP_ID: self._resourceID,
                     aboMembers.ADDRESSBOOK_ID: self._ownerAddressBookResourceID,
                     aboMembers.MEMBER_ID: memberIDToAdd, }
                ).on(self._txn)

            # don't bother with aboForeignMembers on address books
            if self._resourceID != self._ownerAddressBookResourceID:

                #get current foreign members
                currentForeignMemberRows = yield Select(
                    [aboForeignMembers.MEMBER_ADDRESS],
                     From=aboForeignMembers,
                     Where=aboForeignMembers.GROUP_ID == self._resourceID,).on(self._txn)
                currentForeignMemberAddrs = [currentForeignMemberRow[0] for currentForeignMemberRow in currentForeignMemberRows]

                foreignMemberAddrsToDelete = set(currentForeignMemberAddrs) - set(foreignMemberAddrs)
                foreignMemberAddrsToAdd = set(foreignMemberAddrs) - set(currentForeignMemberAddrs)

                if foreignMemberAddrsToDelete:
                    yield self._deleteForeignMembersWithGroupIDAndMembeAddrsQuery(self._resourceID, foreignMemberAddrsToDelete).on(
                        self._txn, memberAddrs=foreignMemberAddrsToDelete
                    )

                for foreignMemberAddrToAdd in foreignMemberAddrsToAdd:
                    yield Insert(
                        {aboForeignMembers.GROUP_ID: self._resourceID,
                         aboForeignMembers.ADDRESSBOOK_ID: self._ownerAddressBookResourceID,
                         aboForeignMembers.MEMBER_ADDRESS: foreignMemberAddrToAdd, }
                    ).on(self._txn)


    @inlineCallbacks
    def component(self):
        """
        Read address data and validate/fix it. Do not raise a store error here if there are unfixable
        errors as that could prevent the overall request to fail. Instead we will hand bad data off to
        the caller - that is not ideal but in theory we should have checked everything on the way in and
        only allowed in good data.
        """

        if self._component is None:

            if not self.owned() and  self._resourceID == self._addressbook._resourceID:
                component = yield self._addressbook._fullySharedAddressBookGroupComponent()
            else:
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

                if self._kind == _ABO_KIND_GROUP:
                    assert not component.hasProperty("X-ADDRESSBOOKSERVER-MEMBER"), "database group vCard text contains members %s" % (component,)

                    # generate "X-ADDRESSBOOKSERVER-MEMBER" properties
                    # first get member resource ids
                    aboMembers = schema.ABO_MEMBERS
                    memberRows = yield Select(
                        [aboMembers.MEMBER_ID],
                         From=aboMembers,
                         Where=aboMembers.GROUP_ID == self._resourceID,
                    ).on(self._txn)
                    memberIDs = [memberRow[0] for memberRow in memberRows]

                    # then get member UIDs
                    abo = schema.ADDRESSBOOK_OBJECT
                    memberUIDRows = (
                        yield self._columnsWithResourceIDsQuery(
                            [abo.VCARD_UID],
                            memberIDs
                        ).on(self._txn, resourceIDs=memberIDs)
                    ) if memberIDs else []
                    memberUIDs = [memberUIDRow[0] for memberUIDRow in memberUIDRows]

                    # add prefix to get property string
                    memberAddresses = ["urn:uuid:" + memberUID for memberUID in memberUIDs]

                    # get foreign members
                    aboForeignMembers = schema.ABO_FOREIGN_MEMBERS
                    foreignMemberRows = yield Select(
                         [aboForeignMembers.MEMBER_ADDRESS],
                         From=aboForeignMembers,
                         Where=aboForeignMembers.GROUP_ID == self._resourceID,
                    ).on(self._txn)
                    foreignMembers = [foreignMemberRow[0] for foreignMemberRow in foreignMemberRows]

                    # now add the properties to the component
                    for memberAddress in sorted(memberAddresses + foreignMembers):
                        component.addProperty(Property("X-ADDRESSBOOKSERVER-MEMBER", memberAddress))

            self._component = component

        returnValue(self._component)


    # IDataStoreObject
    def contentType(self):
        """
        The content type of Addressbook objects is text/vcard.
        """
        return MimeType.fromString("text/vcard; charset=utf-8")


    def owned(self):
        return self._addressbook.owned()


    def ownerHome(self):
        return self._addressbook.ownerHome()


    def viewerHome(self):
        return self._addressbook.viewerHome()


    def shareUID(self):
        """
        @see: L{ICalendar.shareUID}
        """
        return self._bindName

    @classmethod
    def metadataColumns(cls):
        """
        Return a list of column name for retrieval of metadata. This allows
        different child classes to have their own type specific data, but still make use of the
        common base logic.
        """
        # Common behavior is to have created and modified
        return (
            cls._objectSchema.CREATED,
            cls._objectSchema.MODIFIED,
        )


    # same as CommonHomeChild._childrenAndMetadataForHomeID() w/o metadata join
    @classproperty
    def _childrenAndMetadataForHomeID(cls):  #@NoSelf
        bind = cls._bindSchema
        child = cls._objectSchema
        columns = cls._bindColumns() + cls.metadataColumns()
        return Select(columns,
                     From=child.join(
                         bind, child.RESOURCE_ID == bind.RESOURCE_ID,
                         'left outer'),
                     Where=(bind.HOME_RESOURCE_ID == Parameter("homeID")
                           ).And(bind.BIND_STATUS == _BIND_STATUS_ACCEPTED))



    def notifyChanged(self):
        return self._addressbook.notifyChanged()


    @inlineCallbacks
    def asShared(self):
        """
        Retrieve all the versions of this L{AddressBookObject} as it is shared to
        everyone.

        @see: L{ICalendarHome.asShared}

        @return: L{AddressBookObject} objects that represent this
            L{AddressBookObject} as a child of different L{AddressBooks}s 
            in different L{CommonHome}s
        @rtype: a L{Deferred} which fires with a L{list} of L{AddressBookObject}s.
        """
        result = []
        if self.owned():
            # get all accepted shared binds
            groupBindRows = yield self._sharedBindForResourceID.on(
                self._txn, resourceID=self._resourceID, homeID=self._home._resourceID
            )
            for bindMode, homeID, resourceID, bindName, bindStatus, bindMessage in groupBindRows:  #@UnusedVariable
                home = yield self._txn.homeWithResourceID(self._home._homeType, homeID)
                addressbook = yield home.childWithName(self._home.shareeAddressBookName())
                new = yield addressbook.objectResourceWithID(resourceID)
                result.append(new)

        returnValue(result)


    @inlineCallbacks
    def asInvited(self):
        """
        Retrieve all the versions of this L{AddressBookObject} as it is shared to
        everyone.

        @see: L{ICalendarHome.asShared}

        @return: L{AddressBookObject} objects that represent this
            L{AddressBookObject} as a child of different L{AddressBooks}s 
            in different L{CommonHome}s
        @rtype: a L{Deferred} which fires with a L{list} of L{AddressBookObject}s.
        """
        result = []
        if self.owned():
            # get all accepted shared binds
            groupBindRows = yield self._unacceptedBindForResourceID.on(
                self._txn, resourceID=self._resourceID
            )
            for bindMode, homeID, resourceID, bindName, bindStatus, bindMessage in groupBindRows:  #@UnusedVariable
                home = yield self._txn.homeWithResourceID(self._home._homeType, homeID)
                addressbook = yield home.childWithName(self._home.shareeAddressBookName())
                if not addressbook:
                    addressbook = yield AddressBook.objectWithName(home, self._home.shareeAddressBookName(), accepted=False)
                new = yield AddressBookObject.objectWithID(addressbook, resourceID)  # avoids object cache
                result.append(new)

        returnValue(result)


    @classproperty
    def _addressbookIDForResourceID(cls):  #@NoSelf
        obj = cls._objectSchema
        return Select([obj.PARENT_RESOURCE_ID],
                      From=obj,
                      Where=obj.RESOURCE_ID == Parameter("resourceID")
                    )


    @classmethod
    @inlineCallbacks
    def ownerAddressBookFromGroupID(cls, txn, resourceID):
        ownerAddressBookIDRows = yield cls._addressbookIDForResourceID.on(txn, resourceID=resourceID)
        returnValue(ownerAddressBookIDRows[0][0])


    @inlineCallbacks
    def unshare(self):
        """
        Unshares a group, regardless of which "direction" it was shared.
        """
        if self._kind == _ABO_KIND_GROUP:
            if self.owned():
                # This collection may be shared to others
                for sharedToHome in [x.viewerHome() for x in (yield self.asShared())]:
                    yield self.unshareWith(sharedToHome)
            else:
                # This collection is shared to me
                ownerAddressBook = self._addressbook.ownerHome().addressbook()
                ownerGroup = yield ownerAddressBook.objectResourceWithID(self._resourceID)
                if ownerGroup:
                    yield ownerGroup.unshareWith(self._home)


    @inlineCallbacks
    def unshareWith(self, shareeHome):
        """
        Remove the shared version of this (owned) L{CommonHomeChild} from the
        referenced L{CommonHome}.

        @see: L{CommonHomeChild.shareWith}

        @param shareeHome: The home with which this L{CommonHomeChild} was
            previously shared.

        @return: a L{Deferred} which will fire with the previously-used name.
        """
        sharedAddressBook = yield shareeHome.addressbookWithName(self._addressbook.shareeAddressBookName())
        if sharedAddressBook:

            acceptedBindCount = 1 if sharedAddressBook.fullyShared() else 0
            acceptedBindCount += len((
                yield AddressBookObject._acceptedBindWithHomeIDAndAddressBookID.on(
                    self._txn, homeID=shareeHome._resourceID, addressbookID=sharedAddressBook._resourceID
                )
            ))

            if acceptedBindCount == 1:
                sharedAddressBook._deletedSyncToken(sharedRemoval=True)
                shareeHome._children.pop(self._addressbook.shareeAddressBookName(), None)
                shareeHome._children.pop(self._addressbook._resourceID, None)

            # Must send notification to ensure cache invalidation occurs
            yield self.notifyChanged()

        # delete binds including invites
        deletedBindNameRows = yield self._deleteBindWithResourceIDAndHomeID.on(
            self._txn, resourceID=self._resourceID,
             homeID=shareeHome._resourceID
        )
        if deletedBindNameRows:
            deletedBindName = deletedBindNameRows[0][0]
            queryCacher = self._txn._queryCacher
            if queryCacher:
                cacheKey = queryCacher.keyForObjectWithName(shareeHome._resourceID, self._addressbook.shareeAddressBookName())
                queryCacher.invalidateAfterCommit(self._txn, cacheKey)
        else:
            deletedBindName = None

        returnValue(deletedBindName)


    @inlineCallbacks
    def shareWith(self, shareeHome, mode, status=None, message=None):
        """
        Share this (owned) L{AddressBookObject} with another home.

        @param shareeHome: The home of the sharee.
        @type shareeHome: L{CommonHome}

        @param mode: The sharing mode; L{_BIND_MODE_READ} or
            L{_BIND_MODE_WRITE} or L{_BIND_MODE_DIRECT}
        @type mode: L{str}

        @param status: The sharing status; L{_BIND_STATUS_INVITED} or
            L{_BIND_STATUS_ACCEPTED}
        @type mode: L{str}

        @param message: The proposed message to go along with the share, which
            will be used as the default display name.
        @type mode: L{str}

        @return: the name of the shared group in the sharee home.
        @rtype: L{str}
        """

        if status is None:
            status = _BIND_STATUS_ACCEPTED

        @inlineCallbacks
        def doInsert(subt):
            newName = str(uuid4())
            yield self._bindInsertQuery.on(
                subt, homeID=shareeHome._resourceID,
                resourceID=self._resourceID, name=newName,
                mode=mode, bindStatus=status, message=message
            )
            returnValue(newName)
        try:
            bindName = yield self._txn.subtransaction(doInsert)
        except AllRetriesFailed:
            # FIXME: catch more specific exception
            groupBindRows = yield self._bindForResourceIDAndHomeID.on(
                self._txn, resourceID=self._resourceID, homeID=shareeHome._resourceID
            )
            bindMode, homeID, resourceID, bindName, bindStatus, bindMessage = groupBindRows[0]  #@UnusedVariable
            if bindStatus == _BIND_STATUS_ACCEPTED:
                group = yield shareeHome.objectForShareUID(bindName)
            else:
                group = yield shareeHome.invitedObjectForShareUID(bindName)
            bindName = yield self.updateShare(
                group, mode=mode, status=status,
                message=message
            )

        # Must send notification to ensure cache invalidation occurs
        yield self.notifyChanged()

        returnValue(bindName)

    @inlineCallbacks
    #TODO:  This is almost the same as AddressBook.updateShare(): combine
    def updateShare(self, shareeView, mode=None, status=None, message=None, name=None):
        """
        Update share mode, status, and message for a home child shared with
        this (owned) L{CommonHomeChild}.

        @param shareeView: The sharee home child that shares this.
        @type shareeView: L{CommonHomeChild}

        @param mode: The sharing mode; L{_BIND_MODE_READ} or
            L{_BIND_MODE_WRITE} or None to not update
        @type mode: L{str}

        @param status: The sharing status; L{_BIND_STATUS_INVITED} or
            L{_BIND_STATUS_ACCEPTED} or L{_BIND_STATUS_DECLINED} or
            L{_BIND_STATUS_INVALID}  or None to not update
        @type status: L{str}

        @param message: The proposed message to go along with the share, which
            will be used as the default display name, or None to not update
        @type message: L{str}

        @param name: The bind resource name or None to not update
        @type message: L{str}

        @return: the name of the shared item in the sharee's home.
        @rtype: a L{Deferred} which fires with a L{str}
        """
        # TODO: raise a nice exception if shareeView is not, in fact, a shared
        # version of this same L{CommonHomeChild}


        #remove None parameters, and substitute None for empty string
        bind = self._bindSchema
        columnMap = dict([(k, v if v else None)
                          for k, v in {bind.BIND_MODE:mode,
                            bind.BIND_STATUS:status,
                            bind.MESSAGE:message,
                            bind.RESOURCE_NAME:name}.iteritems() if v is not None])

        if len(columnMap):

            # count accepted
            if status is not None:
                previouslyAcceptedBindCount = 1 if shareeView._addressbook.fullyShared() else 0
                previouslyAcceptedBindCount += len((
                    yield AddressBookObject._acceptedBindWithHomeIDAndAddressBookID.on(
                        self._txn, homeID=shareeView._home._resourceID, addressbookID=self._addressbook._resourceID
                    )
                ))

            sharedname = yield self._updateBindColumnsQuery(columnMap).on(
                self._txn,
                resourceID=self._resourceID, homeID=shareeView._home._resourceID
            )

            #update affected attributes
            if mode is not None:
                shareeView._bindMode = columnMap[bind.BIND_MODE]

            if status is not None:
                shareeView._bindStatus = columnMap[bind.BIND_STATUS]
                if shareeView._bindStatus == _BIND_STATUS_ACCEPTED:
                    if 0 == previouslyAcceptedBindCount:
                        yield shareeView._addressbook._initSyncToken()
                        shareeView._home._children[shareeView._addressbook._name] = shareeView._addressbook
                        shareeView._home._children[shareeView._addressbook._resourceID] = shareeView._addressbook
                elif shareeView._bindStatus != _BIND_STATUS_INVITED:
                    if 1 == previouslyAcceptedBindCount:
                        shareeView._addressbook._deletedSyncToken(sharedRemoval=True)
                        shareeView._home._children.pop(shareeView._addressbook._name, None)
                        shareeView._home._children.pop(shareeView._addressbook._resourceID, None)

            if message is not None:
                shareeView._bindMessage = columnMap[bind.MESSAGE]

            # safer to just invalidate in all cases rather than calculate when to invalidate
            queryCacher = self._txn._queryCacher
            if queryCacher:
                cacheKey = queryCacher.keyForObjectWithName(shareeView._home._resourceID, shareeView._addressbook._name)
                queryCacher.invalidateAfterCommit(self._txn, cacheKey)

            shareeView._name = sharedname[0][0]

            # Must send notification to ensure cache invalidation occurs
            yield self.notifyChanged()

        returnValue(shareeView._name)


    @classproperty
    def _acceptedBindWithHomeIDAndAddressBookID(cls):  #@NoSelf
        bind = cls._bindSchema
        abo = cls._objectSchema
        return Select(
                  cls._bindColumns(),
                  From=bind.join(abo),
                  Where=(bind.BIND_STATUS == _BIND_STATUS_ACCEPTED)
                        .And(bind.RESOURCE_ID == abo.RESOURCE_ID)
                        .And(bind.HOME_RESOURCE_ID == Parameter("homeID"))
                        .And(abo.ADDRESSBOOK_HOME_RESOURCE_ID == Parameter("addressbookID"))
        )


    @classproperty
    def _unacceptedBindWithHomeIDAndAddressBookID(cls):  #@NoSelf
        bind = cls._bindSchema
        abo = cls._objectSchema
        return Select(
                  cls._bindColumns(),
                  From=bind.join(abo),
                  Where=(bind.BIND_STATUS != _BIND_STATUS_ACCEPTED)
                        .And(bind.RESOURCE_ID == abo.RESOURCE_ID)
                        .And(bind.HOME_RESOURCE_ID == Parameter("homeID"))
                        .And(abo.ADDRESSBOOK_HOME_RESOURCE_ID == Parameter("addressbookID"))
        )


    @classproperty
    def _bindWithHomeIDAndAddressBookID(cls):  #@NoSelf
        bind = cls._bindSchema
        abo = cls._objectSchema
        return Select(
                  cls._bindColumns(),
                  From=bind.join(abo),
                  Where=(bind.RESOURCE_ID == abo.RESOURCE_ID)
                        .And(bind.HOME_RESOURCE_ID == Parameter("homeID"))
                        .And(abo.ADDRESSBOOK_HOME_RESOURCE_ID == Parameter("addressbookID"))
        )


AddressBook._objectResourceClass = AddressBookObject
