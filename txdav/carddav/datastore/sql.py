# -*- test-case-name: txdav.carddav.datastore.test.test_sql -*-
##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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
from txdav.common.icommondatastore import InternalDataStoreError

"""
SQL backend for CardDAV storage.
"""

__all__ = [
    "AddressBookHome",
    "AddressBook",
    "AddressBookObject",
]

from twext.enterprise.dal.syntax import Delete, Insert, Len, Parameter, \
    Update, Union, Max, Select, utcNowSQL

from twext.python.clsprop import classproperty
from twext.web2.http_headers import MimeType

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import hashlib
from twistedcaldav import carddavxml, customxml
from twistedcaldav.memcacher import Memcacher
from twistedcaldav.vcard import Component as VCard, InvalidVCardDataError, \
    vCardProductID, Property

from txdav.base.propertystore.base import PropertyName
from txdav.carddav.datastore.util import validateAddressBookComponent
from txdav.carddav.iaddressbookstore import IAddressBookHome, IAddressBook, \
    IAddressBookObject, GroupWithUnsharedAddressNotAllowedError, \
    DeleteOfShadowGroupNotAllowedError
from txdav.common.datastore.sql import CommonHome, CommonHomeChild, \
    CommonObjectResource, EADDRESSBOOKTYPE, SharingMixIn
from txdav.common.datastore.sql_legacy import PostgresLegacyABIndexEmulator
from txdav.common.datastore.sql_tables import ADDRESSBOOK_TABLE, \
    ADDRESSBOOK_BIND_TABLE, ADDRESSBOOK_OBJECT_REVISIONS_TABLE, \
    ADDRESSBOOK_OBJECT_TABLE, ADDRESSBOOK_HOME_TABLE, \
    ADDRESSBOOK_HOME_METADATA_TABLE, ADDRESSBOOK_AND_ADDRESSBOOK_BIND, \
    ADDRESSBOOK_OBJECT_AND_BIND_TABLE, \
    ADDRESSBOOK_OBJECT_REVISIONS_AND_BIND_TABLE, \
    _ABO_KIND_PERSON, _ABO_KIND_GROUP, _ABO_KIND_RESOURCE, \
    _ABO_KIND_LOCATION, schema, \
    _BIND_MODE_OWN, _BIND_STATUS_ACCEPTED

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
            Where=ab.ADDRESSBOOK_HOME_RESOURCE_ID == self._resourceID,
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
            Where=rp.RESOURCE_ID == self._resourceID,
        ).on(self._txn)

        yield self._cacher.delete(str(self._ownerUID))


    def createdHome(self):
        return self.createAddressBookWithName("addressbook")


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
            Where=(bind.HOME_RESOURCE_ID == Parameter("homeResourceID")).And(bind.BIND_STATUS != _BIND_STATUS_ACCEPTED)
        ).on(self._txn, **kwds)


AddressBookHome._register(EADDRESSBOOKTYPE)


class AddressBook(CommonHomeChild, SharingMixIn):
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


    #FIXME: Only used for shared group resouretype in SharedResourceMixin.upgradeToShare() and SharedResourceMixin.downgradeFromShare()
    def objectResourcesHaveProperties(self):
        return True


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


    @inlineCallbacks
    def listObjectResources(self):

        result = yield super(AddressBook, self).listObjectResources()
        if not self.owned():
            sharedABGroupName = yield self._groupForSharedAddressBookName()
            if not sharedABGroupName in result:
                result.append(sharedABGroupName)
        returnValue(result)


    @inlineCallbacks
    def countObjectResources(self):
        if self.owned():
            result = yield super(AddressBook, self).countObjectResources()
        else:
            result = len((yield self.listObjectResources()))
        returnValue(result)


    @inlineCallbacks
    def _ownerGroupAndAddressBook(self):
        """ 
        Find the owner shared group and owner address book.  owner shared group may be None 
        """
        ownerGroup = None
        if self.owned():
            yield None
            ownerAddressBook = self
        else:
            ownerAddressBook = yield self.ownerAddressBookHome().childWithID(self._resourceID)
            if not ownerAddressBook:
                for addressbook in (yield self.ownerAddressBookHome().addressbooks()):
                    ownerGroup = yield addressbook.objectResourceWithID(self._resourceID)
                    if ownerGroup:
                        ownerAddressBook = addressbook
                        break

        returnValue((ownerGroup, ownerAddressBook))


    @inlineCallbacks
    def ownerGroup(self):
        if not hasattr(self, "_ownerGroup"):
            self._ownerGroup, self._ownerAddressBook = yield self._ownerGroupAndAddressBook()
        returnValue(self._ownerGroup)


    @inlineCallbacks
    def ownerAddressBook(self):
        if not hasattr(self, "_ownerAddressBook"):
            self._ownerGroup, self._ownerAddressBook = yield self._ownerGroupAndAddressBook()
        returnValue(self._ownerAddressBook)


    @classmethod
    def _abObjectColumnsWithAddressBookResourceID(cls, columns,): #@NoSelf
        """
        DAL statement to retrieve addressbook object rows with given columns.
        """
        obj = cls._objectSchema
        return Select(columns, From=obj,
                      Where=obj.ADDRESSBOOK_RESOURCE_ID == Parameter("addressbookResourceID"),)


    @inlineCallbacks
    def _groupForSharedAddressBookRow(self): #@NoSelf

        returnValue([
            self._resourceID, # obj.ADDRESSBOOK_RESOURCE_ID,
            self._resourceID, # obj.RESOURCE_ID,
            (yield self._groupForSharedAddressBookName()), # obj.RESOURCE_NAME, shared name is UID and thus avoids collisions
            (yield self._groupForSharedAddressBookUID()), # obj.UID, shared name is uuid
            _ABO_KIND_GROUP, # obj.KIND,
            "1", # obj.MD5, unused
            "1", # Len(obj.TEXT), unused
            self._created, # obj.CREATED,
            self._modified, # obj.CREATED,
        ])


    @inlineCallbacks
    def _groupForSharedAddressBookName(self):
        ownerGroup = yield self.ownerGroup()
        if ownerGroup:
            returnValue(ownerGroup.name())
        else:
            returnValue((yield self.ownerAddressBook()).name() + ".vcf")


    @inlineCallbacks
    def _groupForSharedAddressBookUID(self):
        yield None
        returnValue(self.name())

    @inlineCallbacks
    def _groupForSharedAddressBookComponent(self):

        ownerGroup = yield self.ownerGroup()
        if ownerGroup:
            returnValue((yield ownerGroup.component()))
        else:
            n = (yield self.ownerAddressBook()).name()
            fn = n
            uid = self.name()

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
                             [abo.VCARD_UID]).on(
                                self._txn, addressbookResourceID=self._resourceID)
            memberUIDs = [memberUIDRow[0] for memberUIDRow in memberUIDRows]

            # add prefix to get property string
            memberAddresses = ["urn:uuid:" + memberUID for memberUID in memberUIDs]

            # now add the properties to the component
            for memberAddress in sorted(memberAddresses):
                component.addProperty(Property("X-ADDRESSBOOKSERVER-MEMBER", memberAddress))

            returnValue(component)


    @classproperty
    def _childNamesForHomeID(cls): #@NoSelf
        def columns(bind): #@NoSelf
            return [bind.RESOURCE_NAME, ]

        def where(bind): #@NoSelf
            return ((bind.HOME_RESOURCE_ID ==
                             Parameter("homeID")).And
                                (bind.BIND_STATUS == _BIND_STATUS_ACCEPTED))

        addressbookBind = cls._bindSchema
        aboBind = AddressBookObject._bindSchema
        return Select(
            columns(addressbookBind),
            From=addressbookBind,
            Where=where(addressbookBind),
            SetExpression=Union(
                Select(
                    columns(aboBind),
                    From=aboBind,
                    Where=where(aboBind),
                    ),
                optype=Union.OPTYPE_ALL,
            )
        )

    @classmethod
    def _bindsFor(cls, where): #@NoSelf

        def columns(bind): #@NoSelf
            return [bind.BIND_MODE,
                    bind.HOME_RESOURCE_ID,
                    bind.RESOURCE_ID,
                    bind.RESOURCE_NAME,
                    bind.BIND_STATUS,
                    bind.MESSAGE]

        addressbookBind = cls._bindSchema
        aboBind = AddressBookObject._bindSchema
        return Select(
            columns(addressbookBind),
            From=addressbookBind,
            Where=where(addressbookBind),
            SetExpression=Union(
                Select(
                    columns(aboBind),
                    From=aboBind,
                    Where=where(aboBind),
                    ),
                optype=Union.OPTYPE_ALL,
            )
        )


    @classproperty
    def _invitedBindForResourceID(cls): #@NoSelf
        return cls._bindsFor(lambda bind: ((bind.RESOURCE_ID == Parameter("resourceID"))
                            .And(bind.BIND_STATUS != _BIND_STATUS_ACCEPTED)
                            ))


    @classproperty
    def _sharedBindForResourceID(cls): #@NoSelf
        return cls._bindsFor(lambda bind: ((bind.RESOURCE_ID == Parameter("resourceID"))
                            .And(bind.BIND_STATUS == _BIND_STATUS_ACCEPTED)
                            .And(bind.BIND_MODE != _BIND_MODE_OWN)
                            ))


    @classproperty
    def _invitedBindForHomeID(cls): #@NoSelf
        return cls._bindsFor(lambda bind: ((bind.HOME_RESOURCE_ID == Parameter("homeID"))
                            .And(bind.BIND_STATUS != _BIND_STATUS_ACCEPTED)
                            ))


    @classproperty
    def _invitedBindForNameAndHomeID(cls): #@NoSelf
        return cls._bindsFor(lambda bind: ((bind.RESOURCE_NAME == Parameter("name"))
                               .And(bind.HOME_RESOURCE_ID == Parameter("homeID"))
                               .And(bind.BIND_STATUS != _BIND_STATUS_ACCEPTED)
                               ))


    @classproperty
    def _childForNameAndHomeID(cls): #@NoSelf
        return cls._bindsFor(lambda bind: ((bind.RESOURCE_NAME == Parameter("name"))
                               .And(bind.HOME_RESOURCE_ID == Parameter("homeID"))
                               .And(bind.BIND_STATUS == _BIND_STATUS_ACCEPTED)
                               ))


    @classproperty
    def _bindForResourceIDAndHomeID(cls): #@NoSelf
        return cls._bindsFor(lambda bind: ((bind.RESOURCE_ID == Parameter("resourceID"))
                               .And(bind.HOME_RESOURCE_ID == Parameter("homeID"))
                               ))


    @classproperty
    def _metadataByIDQuery(cls): #@NoSelf
        """
        DAL query to retrieve created/modified dates based on a resource ID.
        """
        child = cls._homeChildMetaDataSchema
        abo = schema.ADDRESSBOOK_OBJECT
        return Select(
            cls.metadataColumns(),
            From=child,
            Where=child.RESOURCE_ID == Parameter("resourceID"),
            SetExpression=Union(
                Select(
                    [abo.CREATED, abo.MODIFIED],
                    From=abo,
                    Where=abo.RESOURCE_ID == Parameter("resourceID"),
                    ),
                optype=Union.OPTYPE_ALL,
            )
        )


    @classproperty
    def _changeABForSharedGroupLastModifiedQuery(cls): #@NoSelf
        schema = AddressBookObject._objectSchema
        return Update({schema.MODIFIED: utcNowSQL},
                      Where=schema.RESOURCE_ID == Parameter("resourceID"),
                      Return=schema.MODIFIED)


    @inlineCallbacks
    def _bumpModified(self, subtxn):

        yield self._lockLastModifiedQuery.on(subtxn, resourceID=self._resourceID)

        # can't call self.ownerGroup() on a subtranaction,
        # So just try AB schema first, then ABOBject schema 
        # The following line makes shared groups faster, but a bit of a hack
        #if hasattr(self, "_ownerGroup") and not (yield self.ownerGroup()):
        result = yield self._changeLastModifiedQuery.on(subtxn, resourceID=self._resourceID)

        if not result:
            result = yield self._changeABForSharedGroupLastModifiedQuery.on(subtxn, resourceID=self._resourceID)

        returnValue(result)


    @classproperty
    def _childrenAndMetadataForHomeID(cls): #@NoSelf

        def columns(bind, metaColumns):
            cols = [bind.BIND_MODE,
                    bind.HOME_RESOURCE_ID,
                    bind.RESOURCE_ID,
                    bind.RESOURCE_NAME,
                    bind.BIND_STATUS,
                    bind.MESSAGE,
                   ]
            cols.extend(metaColumns)
            return cols

        def _from(bind, child, childMetaData=None):
            if childMetaData:
                return child.join(
                                 bind, child.RESOURCE_ID == bind.RESOURCE_ID,
                                 'left outer').join(
                                 childMetaData, childMetaData.RESOURCE_ID == bind.RESOURCE_ID,
                                 'left outer')
            else:
                return child.join(
                                 bind, child.RESOURCE_ID == bind.RESOURCE_ID,
                                 'left outer')

        def where(bind):
            return ((bind.HOME_RESOURCE_ID == Parameter("homeID")
                               ).And(bind.BIND_STATUS == _BIND_STATUS_ACCEPTED))

        addressbookBind = cls._bindSchema
        addressbookSchema = cls._homeChildSchema
        addressbookMetaDataSchema = cls._homeChildMetaDataSchema
        addressbookMetaDataColumns = cls.metadataColumns()

        aboBind = AddressBookObject._bindSchema
        aboSchema = AddressBookObject._objectSchema
        aboMetaDataColumns = [aboSchema.CREATED, aboSchema.MODIFIED, ]

        return Select(columns(addressbookBind, addressbookMetaDataColumns),
                         From=_from(addressbookBind, addressbookSchema, addressbookMetaDataSchema),
                         Where=where(addressbookBind),
                         SetExpression=Union(
                            Select(
                                   columns(aboBind, aboMetaDataColumns),
                                   From=_from(aboBind, aboSchema),
                                   Where=where(aboBind),
                                ),
                            optype=Union.OPTYPE_ALL,
                        ),
                )


    @classproperty
    def _revisionsForHomeID(cls): #@NoSelf

        rev = cls._revisionsSchema
        def columns():
            return [rev.RESOURCE_ID, Max(rev.REVISION)]

        def _from(bind):
            return rev.join(bind, rev.RESOURCE_ID == bind.RESOURCE_ID, 'left')

        def where(bind):
            return ((bind.HOME_RESOURCE_ID == Parameter("homeID")).
                And((rev.RESOURCE_NAME != None).Or(rev.DELETED == False)))

        addressbookBind = cls._bindSchema
        aboBind = cls._bindSchema
        return Select(
            columns(),
            From=_from(addressbookBind),
            Where=where(addressbookBind),
            GroupBy=rev.RESOURCE_ID,
            SetExpression=Union(
                Select(
                    columns(),
                    From=_from(aboBind),
                    Where=where(aboBind),
                    GroupBy=rev.RESOURCE_ID
                    ),
                optype=Union.OPTYPE_ALL,
           ),
        )



class AddressBookObject(CommonObjectResource, SharingMixIn):

    implements(IAddressBookObject)

    _objectTable = ADDRESSBOOK_OBJECT_TABLE
    _objectSchema = schema.ADDRESSBOOK_OBJECT
    _bindSchema = schema.GROUP_ADDRESSBOOK_BIND


    def __init__(self, addressbook, name, uid, resourceID=None, metadata=None):

        self._kind = None
        self._ownerAddressBookResourceID = None
        # _self._component is the cached, current component
        # super._objectText now contains the text as read of the database only,
        #     not including group member text
        self._component = None
        super(AddressBookObject, self).__init__(addressbook, name, uid, resourceID)


    @property
    def _addressbook(self):
        return self._parentCollection


    def addressbook(self):
        return self._addressbook


    def kind(self):
        return self._kind


    @classmethod
    def _deleteMembersWithMemberIDAndGroupIDsQuery(cls, memberID, groupIDs): #@NoSelf
        aboMembers = schema.ABO_MEMBERS
        return Delete(
            aboMembers,
            Where=(aboMembers.MEMBER_ID == memberID).And(
                    aboMembers.GROUP_ID.In(Parameter("groupIDs", len(groupIDs)))))


    @inlineCallbacks
    def remove(self):

        if self._addressbook.owned():
            if self._kind == _ABO_KIND_GROUP: # optimization
                # need to invalidate queryCacher of sharee's home
                queryCacher = self._txn._queryCacher
                if queryCacher:
                    for shareeAddressBook in (yield self.asShared()):
                        cacheKey = queryCacher.keyForObjectWithName(shareeAddressBook._home._resourceID, shareeAddressBook._name)
                        yield queryCacher.invalidateAfterCommit(self._txn, cacheKey)
        else:
            # sharee cannot delete group representing shared address book
            if self._resourceID == self._addressbook._resourceID:
                raise DeleteOfShadowGroupNotAllowedError


        aboMembers = schema.ABO_MEMBERS
        aboForeignMembers = schema.ABO_FOREIGN_MEMBERS

        ownerGroup = yield self._addressbook.ownerGroup()
        if ownerGroup:
            # convert delete in sharee shared group address book to remove of memberships
            # that make this object visible to the sharee

            objectIDs = yield ownerGroup._allGroupObjectIDs()
            assert self._ownerAddressBookResourceID not in objectIDs, "self._ownerAddressBookResourceID=%s not in objectIDs=%s" % (self._ownerAddressBookResourceID, objectIDs,)

            if objectIDs:
                yield self._deleteMembersWithMemberIDAndGroupIDsQuery(self._resourceID, objectIDs).on(
                    self._txn, groupIDs=objectIDs)

            ownerAddressBook = yield self._addressbook.ownerAddressBook()
            yield self._changeAddressBookRevision(ownerAddressBook)

        else:
            # delete members table rows for this object,...
            groupIDRows = yield Delete(
                aboMembers,
                Where=aboMembers.MEMBER_ID == self._resourceID,
                Return=aboMembers.GROUP_ID
            ).on(self._txn)

            # add to foreign member table row by UID
            memberAddress = "urn:uuid:" + self._uid
            for groupID in [groupIDRow[0] for groupIDRow in groupIDRows]:
                if groupID != self._ownerAddressBookResourceID: # no aboForeignMembers on address books
                    yield Insert(
                            {aboForeignMembers.GROUP_ID: groupID,
                             aboForeignMembers.ADDRESSBOOK_ID: self._ownerAddressBookResourceID,
                             aboForeignMembers.MEMBER_ADDRESS: memberAddress, }
                        ).on(self._txn)

            yield super(AddressBookObject, self).remove()
            self._kind = None
            self._ownerAddressBookResourceID = None
            self._component = None

    @classmethod
    def _allWithResourceIDAnd(cls, resourceIDs, column, paramName):
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
    def _allWithResourceIDAndName(cls, resourceIDs): #@NoSelf
        return cls._allWithResourceIDAnd(resourceIDs, cls._objectSchema.RESOURCE_NAME, "name")


    @classmethod
    def _allWithResourceIDAndUID(cls, resourceIDs): #@NoSelf
        return cls._allWithResourceIDAnd(resourceIDs, cls._objectSchema.UID, "uid")


    @classproperty
    def _allWithResourceID(cls): #@NoSelf
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
        ownerGroup = yield self._addressbook.ownerGroup()
        if ownerGroup:

            objectIDs = yield ownerGroup._allGroupObjectIDs()
            if self._name:
                rows = (yield self._allWithResourceIDAndName(objectIDs).on(
                    self._txn, name=self._name,
                    resourceIDs=objectIDs,)) if objectIDs else []
            elif self._uid:
                rows = (yield self._allWithResourceIDAndUID(objectIDs).on(
                    self._txn, uid=self._uid,
                    resourceIDs=objectIDs,)) if objectIDs else []
            elif self._resourceID:
                rows = (yield self._allWithResourceID.on(
                    self._txn, resourceID=self._resourceID,)) if (self._resourceID in objectIDs) else []

        else:
            if self._name:
                rows = yield self._allWithParentAndName.on(
                    self._txn, name=self._name,
                    parentID=self._parentCollection._resourceID)
            elif self._uid:
                rows = yield self._allWithParentAndUID.on(
                    self._txn, uid=self._uid,
                    parentID=self._parentCollection._resourceID)
            elif self._resourceID:
                rows = yield self._allWithParentAndID.on(
                    self._txn, resourceID=self._resourceID,
                    parentID=self._parentCollection._resourceID)


        # get special group vCard
        if not rows and not self._addressbook.owned():
            if self._name:
                if self._name == (yield self._addressbook._groupForSharedAddressBookName()):
                    rows = [(yield self._addressbook._groupForSharedAddressBookRow())]
            elif self._uid:
                if self._uid == (yield self._addressbook._groupForSharedAddressBookUID()):
                    rows = [(yield self._addressbook._groupForSharedAddressBookRow())]
            elif self._resourceID:
                if self._resourceID == self._addressbook._resourceID:
                    rows = [(yield self._addressbook._groupForSharedAddressBookRow())]

        if rows:
            self._initFromRow(tuple(rows[0]))

            if self._kind == _ABO_KIND_GROUP:
                # generate "X-ADDRESSBOOKSERVER-MEMBER" properties
                # calc md5 and set size
                componentText = str((yield self.component()))
                self._md5 = hashlib.md5(componentText).hexdigest()
                self._size = len(componentText)

            yield self._loadPropertyStore()

            returnValue(self)
        else:
            returnValue(None)


    @classmethod
    def _memberIDsWithGroupIDsQuery(cls, groupIDs): #@NoSelf
        """
        DAL query to load all object resource names for a home child.
        """
        aboMembers = schema.ABO_MEMBERS
        return Select([aboMembers.MEMBER_ID], From=aboMembers,
                      Where=aboMembers.GROUP_ID.In(Parameter("groupIDs", len(groupIDs))),
                      )

    @inlineCallbacks
    def _allGroupObjectIDs(self):
        """
        Get all addressbookobject resource IDs in this address book
        """

        objectIDs = set() if self.owned() else set([self._resourceID, ])
        examinedIDs = set()
        remainingIDs = set([self._resourceID, ])
        while remainingIDs:
            memberRows = yield self._memberIDsWithGroupIDsQuery(remainingIDs).on(self._txn, groupIDs=remainingIDs)
            objectIDs |= set([memberRow[0] for memberRow in memberRows])
            examinedIDs |= remainingIDs
            remainingIDs = objectIDs - examinedIDs

        returnValue(tuple(objectIDs))


    @classproperty
    def _allColumns(cls): #@NoSelf
        """
        Full set of columns in the object table that need to be loaded to
        initialize the object resource state.
        """
        obj = cls._objectSchema
        return [
            obj.ADDRESSBOOK_RESOURCE_ID,
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
    def _abObjectColumnsWithResourceIDsQuery(cls, columns, resourceIDs): #@NoSelf
        """
        DAL statement to retrieve addressbook object rows with given columns.
        """
        obj = cls._objectSchema
        return Select(columns, From=obj,
                      Where=obj.RESOURCE_ID.In(Parameter("resourceIDs", len(resourceIDs))),)


    @classmethod
    @inlineCallbacks
    def _allColumnsWithParent(cls, parent): #@NoSelf

        ownerGroup = yield parent.ownerGroup()
        if ownerGroup:
            objectIDs = yield ownerGroup._allGroupObjectIDs()
            rows = (yield cls._abObjectColumnsWithResourceIDsQuery(cls._allColumns, objectIDs).on(
                parent._txn, resourceIDs=objectIDs)) if objectIDs else []
        else:
            rows = yield super(AddressBookObject, cls)._allColumnsWithParent(parent)
            # add group vCard for shared address books
            if not parent.owned():
                rows.append((yield parent._groupForSharedAddressBookRow()))

        returnValue(rows)


    @classmethod
    def _allColumnsWithResourceIDsAndNamesQuery(cls, resourceIDs, names): #@NoSelf
        obj = cls._objectSchema
        return Select(cls._allColumns, From=obj,
                      Where=(obj.RESOURCE_ID.In(Parameter("resourceIDs", len(resourceIDs))).And(
                          obj.RESOURCE_NAME.In(Parameter("names", len(names))))),)


    @classmethod
    @inlineCallbacks
    def _allColumnsWithParentAndNames(cls, parent, names): #@NoSelf

        ownerGroup = yield parent.ownerGroup()
        if ownerGroup:
            objectIDs = yield parent._allAddressBookObjectIDs()
            rows = (yield cls._allColumnsWithResourceIDsAndNamesQuery(objectIDs, names).on(
                parent._txn, resourceIDs=objectIDs, names=names)) if objectIDs else []
        else:
            rows = yield super(AddressBookObject, cls)._allColumnsWithParentAndNames(parent, names)

            # add group vCard for shared address books
            if not parent.owned() and (yield parent._groupForSharedAddressBookName()) in names:
                rows.append((yield parent._groupForSharedAddressBookRow(parent)))

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

        validateAddressBookComponent(self, self._addressbook, component, inserting)
        yield self.updateDatabase(component, inserting=inserting)
        yield self._changeAddressBookRevision(self._addressbook, inserting)

        if self._addressbook.owned():
            # update revision table of the sharee group address book
            if self._kind == _ABO_KIND_GROUP:  # optimization
                for shareeAddressBook in (yield self.asShared()):
                    yield self._changeAddressBookRevision(shareeAddressBook, inserting)
                    # one is enough because all have the same resourceID
                    break
        else:
            if self._addressbook._resourceID != self._ownerAddressBookResourceID:
                # update revisions table of shared group's containing address book
                ownerAddressBook = yield self._addressbook.ownerAddressBook()
                yield self._changeAddressBookRevision(ownerAddressBook, inserting)

        self._component = component


    @classmethod
    def _resourceIDAndUIDForUIDsAndAddressBookResourceIDQuery(cls, uids): #@NoSelf
        abo = schema.ADDRESSBOOK_OBJECT
        return Select([abo.RESOURCE_ID, abo.VCARD_UID],
                      From=abo,
                      Where=((abo.ADDRESSBOOK_RESOURCE_ID == Parameter("addressbookResourceID")
                              ).And(
                                    abo.VCARD_UID.In(Parameter("uids", len(uids))))),
                      )


    @classmethod
    def _deleteMembersWithGroupIDAndMemberIDsQuery(cls, groupID, memberIDs): #@NoSelf
        aboMembers = schema.ABO_MEMBERS
        return Delete(
            aboMembers,
            Where=(aboMembers.GROUP_ID == groupID).And(
                    aboMembers.MEMBER_ID.In(Parameter("memberIDs", len(memberIDs)))))


    @classmethod
    def _deleteForeignMembersWithGroupIDAndMembeAddrsQuery(cls, groupID, memberAddrs): #@NoSelf
        aboForeignMembers = schema.ABO_FOREIGN_MEMBERS
        return Delete(
            aboForeignMembers,
            Where=(aboForeignMembers.GROUP_ID == groupID).And(
                    aboForeignMembers.MEMBER_ADDRESS.In(Parameter("memberAddrs", len(memberAddrs)))))


    @classproperty
    def _insertABObject(cls): #@NoSelf
        """
        DAL statement to create an addressbook object with all default values.
        """
        abo = schema.ADDRESSBOOK_OBJECT
        return Insert(
            {abo.RESOURCE_ID: schema.RESOURCE_ID_SEQ,
             abo.ADDRESSBOOK_RESOURCE_ID: Parameter("addressbookResourceID"),
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
    def updateDatabase(self, component, expand_until=None, reCreate=False,
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
            ownerAddressBook = yield self._addressbook.ownerAddressBook()
            self._ownerAddressBookResourceID = ownerAddressBook._resourceID

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
                                self._txn, addressbookResourceID=self._ownerAddressBookResourceID, uids=memberUIDs) if memberUIDs else []
            memberIDs = [memberRow[0] for memberRow in memberRows]
            foundUIDs = [memberRow[1] for memberRow in memberRows]
            foreignMemberAddrs.extend(["urn:uuid:" + missingUID for missingUID in set(memberUIDs) - set(foundUIDs)])

            #in shared group, all members must be inside the shared group
            ownerGroup = yield self._addressbook.ownerGroup()
            if ownerGroup:
                if foreignMemberAddrs or \
                    set(memberIDs) - set((yield ownerGroup._allGroupObjectIDs())):
                    raise GroupWithUnsharedAddressNotAllowedError

            # don't store group members in object text

            # sort addreses in component text
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
        assert inserting or self._uid == uid # can't change UID. Should be checked in upper layers
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
                    ))[0]

            # delete foreign members table row for this object
            groupIDRows = yield Delete(
                aboForeignMembers,
                # should this be scoped to the owner address book?
                Where=aboForeignMembers.MEMBER_ADDRESS == "urn:uuid:" + self._uid,
                Return=aboForeignMembers.GROUP_ID
            ).on(self._txn)
            groupIDs = [groupIDRow[0] for groupIDRow in groupIDRows]

            # add group if of this owner address book
            # groupIDs.append(self._ownerAddressBookResourceID)

            # add owner group if there is one
            ownerGroup = yield self._addressbook.ownerGroup()
            if ownerGroup:
                groupIDs.append(ownerGroup._resourceID)

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
                    self._txn, memberIDs=memberIDsToDelete)

            for memberIDToAdd in memberIDsToAdd:
                yield Insert(
                    {aboMembers.GROUP_ID: self._resourceID,
                     aboMembers.ADDRESSBOOK_ID: self._ownerAddressBookResourceID,
                     aboMembers.MEMBER_ID: memberIDToAdd, }
                ).on(self._txn)

            # don't bother with aboForeignMembers on address books
            if self._resourceID != self._ownerAddressBookResourceID:

                #get current foreign members 
                currentForeignMemberRows = yield Select([aboForeignMembers.MEMBER_ADDRESS],
                                                     From=aboForeignMembers,
                                                     Where=aboForeignMembers.GROUP_ID == self._resourceID,).on(self._txn)
                currentForeignMemberAddrs = [currentForeignMemberRow[0] for currentForeignMemberRow in currentForeignMemberRows]

                foreignMemberAddrsToDelete = set(currentForeignMemberAddrs) - set(foreignMemberAddrs)
                foreignMemberAddrsToAdd = set(foreignMemberAddrs) - set(currentForeignMemberAddrs)

                if foreignMemberAddrsToDelete:
                    yield self._deleteForeignMembersWithGroupIDAndMembeAddrsQuery(self._resourceID, foreignMemberAddrsToDelete).on(
                        self._txn, memberAddrs=foreignMemberAddrsToDelete)

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

            if not self._addressbook.owned() and  self._resourceID == self._addressbook._resourceID:

                component = yield self._addressbook._groupForSharedAddressBookComponent()

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
                    memberRows = yield Select([aboMembers.MEMBER_ID],
                                         From=aboMembers,
                                         Where=aboMembers.GROUP_ID == self._resourceID,).on(self._txn)
                    memberIDs = [memberRow[0] for memberRow in memberRows]

                    # then get member UIDs
                    abo = schema.ADDRESSBOOK_OBJECT
                    memberUIDRows = (yield self._abObjectColumnsWithResourceIDsQuery(
                                     [abo.VCARD_UID],
                                     memberIDs).on(
                                        self._txn, resourceIDs=memberIDs)
                                    ) if memberIDs else []
                    memberUIDs = [memberUIDRow[0] for memberUIDRow in memberUIDRows]

                    # add prefix to get property string
                    memberAddresses = ["urn:uuid:" + memberUID for memberUID in memberUIDs]

                    # get foreign members
                    aboForeignMembers = schema.ABO_FOREIGN_MEMBERS
                    foreignMemberRows = yield Select([aboForeignMembers.MEMBER_ADDRESS],
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
        return True


    def ownerHome(self):
        return self._addressbook.ownerHome()


    def notifyChanged(self):
        self._addressbook.notifyChanged()


AddressBook._objectResourceClass = AddressBookObject
