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

from twext.enterprise.dal.syntax import \
    Delete, Insert, Len, Parameter, Update, Select, utcNowSQL

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
    IAddressBookObject
from txdav.common.datastore.sql import CommonHome, CommonHomeChild, \
    CommonObjectResource, EADDRESSBOOKTYPE, SharingMixIn
from txdav.common.datastore.sql_legacy import PostgresLegacyABIndexEmulator
from txdav.common.datastore.sql_tables import ADDRESSBOOK_TABLE, \
    ADDRESSBOOK_BIND_TABLE, ADDRESSBOOK_OBJECT_REVISIONS_TABLE, \
    ADDRESSBOOK_OBJECT_TABLE, ADDRESSBOOK_HOME_TABLE, \
    ADDRESSBOOK_HOME_METADATA_TABLE, ADDRESSBOOK_AND_ADDRESSBOOK_BIND, \
    ADDRESSBOOK_OBJECT_AND_BIND_TABLE, \
    ADDRESSBOOK_OBJECT_REVISIONS_AND_BIND_TABLE, \
    _ABO_KIND_PERSON, _ABO_KIND_GROUP, _ABO_KIND_RESOURCE, _ABO_KIND_LOCATION, \
    schema
from txdav.xml.rfc2518 import ResourceType

from uuid import uuid4

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

class AddressBookSharingMixIn(SharingMixIn):

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


class AddressBook(CommonHomeChild, AddressBookSharingMixIn):
    """
    SQL-based implementation of L{IAddressBook}.
    """
    implements(IAddressBook)

    # structured tables.  (new, preferred)
    _homeSchema = schema.ADDRESSBOOK_HOME
    _bindSchema = schema.ADDRESSBOOK_BIND
    _homeChildSchema = schema.ADDRESSBOOK_OBJECT
    _homeChildMetaDataSchema = schema.ADDRESSBOOK_OBJECT
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


    @classmethod
    @inlineCallbacks
    def _createChild(cls, home, name):  #@NoSelf
        # Create this object

        # TODO:  N, FN, set to resource name for now,
        #        but "may" have to change when shared
        #        and perhaps will need to reflect a per-user property
        uid = str(uuid4())
        component = VCard.fromString(
            """BEGIN:VCARD
VERSION:3.0
PRODID:%s
UID:%s
FN:%s
N:%s;;;;
X-ADDRESSBOOKSERVER-KIND:group
END:VCARD
""".replace("\n", "\r\n") % (vCardProductID, uid, name, name)
            )

        componentText = str(component)
        md5 = hashlib.md5(componentText).hexdigest()

        resourceID, created, modified = (#@UnusedVariable
            yield cls._insertABObject.on(
                home._txn,
                addressbookResourceID=None,
                name=name,
                text=componentText,
                uid=component.resourceUID(),
                md5=md5,
                kind=_ABO_KIND_GROUP,
                ))[0]

        returnValue((resourceID, created, modified))




    @classmethod
    def _memberIDsWithGroupIDsQuery(cls, groupIDs): #@NoSelf
        """
        DAL query to load all object resource names for a home child.
        """
        aboMembers = schema.ABO_MEMBERS
        return Select([aboMembers.MEMBER_ID], From=aboMembers,
                      Where=aboMembers.GROUP_ID.In(Parameter("groupIDs", len(groupIDs)))
                      )

    @inlineCallbacks
    def _addressBookObjectIDs(self):
        """
        Get all addressbookobject resource IDs in this address book
        
        TODO: optimize
        """
        # TODO: if shared, self is a member
        # allMemberIDs = set() if self.owned() else set([self._resourceID])
        allMemberIDs = set()
        examinedIDs = set()
        remainingIDs = set([self._resourceID])
        while remainingIDs:
            memberRows = yield self._memberIDsWithGroupIDsQuery(remainingIDs).on(self._txn, groupIDs=remainingIDs)
            allMemberIDs |= set([memberRow[0] for memberRow in memberRows])
            examinedIDs |= remainingIDs
            remainingIDs = allMemberIDs - examinedIDs
            print("_addressBookObjectIDs:self=%s, examinedIDs=%s, remainingIDs=%s, allMemberIDs=%s" % (self, examinedIDs, remainingIDs, allMemberIDs,))

        returnValue(tuple(allMemberIDs))


    @classmethod
    def _objectResourceNamesWithResourceIDsQuery(cls, resourceIDs): #@NoSelf
        """
        DAL query to load all object resource names for a home child.
        """
        abo = schema.ADDRESSBOOK_OBJECT
        return Select([abo.RESOURCE_NAME], From=abo,
                      Where=abo.RESOURCE_ID.In(Parameter("resourceIDs", len(resourceIDs)))
                      )


    @inlineCallbacks
    def listObjectResources(self):
        if self._objectNames is None:
            memberIDs = yield self._addressBookObjectIDs()
            rows = (yield self._objectResourceNamesWithResourceIDsQuery(memberIDs).on(
                self._txn, resourceIDs=memberIDs)) if memberIDs else []
            self._objectNames = sorted([row[0] for row in rows])

        returnValue(self._objectNames)


    @inlineCallbacks
    def countObjectResources(self):
        returnValue(len((yield self._addressBookObjectIDs())))


class AddressBookObject(CommonObjectResource, AddressBookSharingMixIn):

    implements(IAddressBookObject)

    _objectTable = ADDRESSBOOK_OBJECT_TABLE
    _objectSchema = schema.ADDRESSBOOK_OBJECT
    _bindSchema = schema.ADDRESSBOOK_BIND


    def __init__(self, addressbook, name, uid, resourceID=None, metadata=None):

        self._kind = None
        self._ownerAddressBookResourceID = None
        super(AddressBookObject, self).__init__(addressbook, name, uid, resourceID)


    @property
    def _addressbook(self):
        return self._parentCollection


    def addressbook(self):
        return self._addressbook

    def kind(self):
        return self._kind

    @inlineCallbacks
    def remove(self):

        aboForeignMembers = schema.ABO_FOREIGN_MEMBERS
        aboMembers = schema.ABO_MEMBERS

        print("remove:%s, name=%s" % (self, self._name))

        if not self._addressbook.owned():
            ownerGroup, ownerAddressBook = yield self._ownerGroupAndAddressBook()  #@UnusedVariable 
            if ownerGroup:
                ownerGroupComponent = yield ownerGroup.component()
                member = "urn:uuid:" + self._uid
                if member in ownerGroupComponent.resourceMembers():
                    ownerGroupComponent.removeProperty(Property("X-ADDRESSBOOKSERVER-MEMBER", member))
                    ownerGroup.updateDatabase(ownerGroupComponent)

        elif self._kind == _ABO_KIND_GROUP:
            # need to invalidate queryCacher
            queryCacher = self._txn._queryCacher
            if queryCacher:
                for shareeAddressBook in (yield self.asShared()):
                    cacheKey = queryCacher.keyForObjectWithName(shareeAddressBook._home._resourceID, shareeAddressBook._name)
                    yield queryCacher.invalidateAfterCommit(self._txn, cacheKey)

        # delete members table row for this object
        groupIDs = yield Delete(
            aboMembers,
            Where=aboMembers.MEMBER_ID == self._resourceID,
            Return=aboMembers.GROUP_ID
        ).on(self._txn)

        print("remove:self=%s, deleted from groupIDs=%s" % (self, groupIDs,))

        # add to foreign member table row by UID
        assert self._ownerAddressBookResourceID
        for groupID in groupIDs:
            if groupID[0] != self._ownerAddressBookResourceID:
                # remove on address book, add aboForeignMembers row to local groups only
                yield Insert(
                        {aboForeignMembers.GROUP_ID: groupID[0],
                         aboForeignMembers.ADDRESSBOOK_ID: self._ownerAddressBookResourceID,
                         aboForeignMembers.MEMBER_ADDRESS: "urn:uuid:" + self._uid, }
                    ).on(self._txn)

        yield super(AddressBookObject, self).remove()
        self._kind = None
        self._ownerAddressBookResourceID = None

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
                obj.RESOURCE_ID.In(Parameter("resourceIDs", len(resourceIDs))))
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
            Where=(obj.RESOURCE_ID == Parameter("resourceID")))


    @inlineCallbacks
    def initFromStore(self):
        """
        Initialise this object from the store. We read in and cache all the
        extra metadata from the DB to avoid having to do DB queries for those
        individually later. Either the name or uid is present, so we have to
        tweak the query accordingly.

        @return: L{self} if object exists in the DB, else C{None}
        """
        memberIDs = yield self._addressbook._addressBookObjectIDs()
        if self._name:
            rows = (yield self._allWithResourceIDAndName(memberIDs).on(
                self._txn, name=self._name,
                resourceIDs=memberIDs,)) if memberIDs else []
        elif self._uid:
            rows = (yield self._allWithResourceIDAndUID(memberIDs).on(
                self._txn, uid=self._uid,
                resourceIDs=memberIDs,)) if memberIDs else []
        elif self._resourceID:
            rows = (yield self._allWithResourceID(memberIDs).on(
                self._txn, resourceID=self._resourceID,)) if self._resourceID in memberIDs else []
        print("initFromStore:self=%s, self._name=%s, self._uid=%s, self._resourceID=%s, self._parentCollection._resourceID=%s rows=%s" %
              (self, self._name, self._uid, self._resourceID, self._parentCollection._resourceID, rows))

        if rows:
            self._initFromRow(tuple(rows[0]))
            yield self._loadPropertyStore()
            returnValue(self)
        else:
            returnValue(None)


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
            obj.MODIFIED
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

        print("_initFromRow:self=%s, row=%s, self._ownerAddressBookResourceID=%s, self._addressbook=%s" % (self, row, self._ownerAddressBookResourceID, self._addressbook))

    @classmethod
    def _allColumnsWithResourceIDsQuery(cls, resourceIDs): #@NoSelf
        obj = cls._objectSchema
        return Select(cls._allColumns, From=obj,
                      Where=obj.RESOURCE_ID.In(Parameter("resourceIDs", len(resourceIDs))))

    @classmethod
    @inlineCallbacks
    def _allColumnsWithParent(cls, parent): #@NoSelf

        memberIDs = yield parent._addressBookObjectIDs()
        print("_allColumnsWithParent:cls=%s, parent=%s, memberIDs=%s" % (cls, parent, memberIDs,))

        rows = (yield cls._allColumnsWithResourceIDsQuery(memberIDs).on(
            parent._txn, resourceIDs=memberIDs)) if memberIDs else []

        print("_allColumnsWithParent:cls=%s, parent=%s, rows=%s" % (cls, parent, rows,))
        returnValue(rows)


    @classmethod
    def _allColumnsWithResourceIDsAndNamesQuery(cls, resourceIDs, names): #@NoSelf
        obj = cls._objectSchema
        return Select(cls._allColumns, From=obj,
                      Where=(obj.RESOURCE_ID.In(Parameter("resourceIDs", len(resourceIDs))).And(
                          obj.RESOURCE_NAME.In(Parameter("names", len(names))))))


    @classmethod
    @inlineCallbacks
    def _allColumnsWithParentAndNames(cls, parent, names): #@NoSelf
        memberIDs = yield parent._addressBookObjectIDs()

        rows = (yield cls._allColumnsWithResourceIDsAndNamesQuery(memberIDs, names).on(
            parent._txn, resourceIDs=memberIDs, names=names)) if memberIDs else []

        returnValue(rows)


    @inlineCallbacks
    def setComponent(self, component, inserting=False):

        validateAddressBookComponent(self, self._addressbook, component, inserting)

        yield self.updateDatabase(component, inserting=inserting)
        if inserting:
            yield self._addressbook._insertRevision(self._name)
        else:
            yield self._addressbook._updateRevision(self._name)

        yield self._addressbook.notifyChanged()


    @inlineCallbacks
    def _ownerGroupAndAddressBook(self):
        # find the owning address book
        ownerGroup = None
        ownerAddressBook = None
        if self._addressbook.owned():
            ownerAddressBook = self._addressbook
        else:
            ownerAddressBook = yield self._addressbook.ownerHome().childWithID(self._addressbook._resourceID)
            if not ownerAddressBook:
                for addressbook in (yield self._addressbook.ownerHome().children()):
                    for addressBookObject in (yield addressbook.objectResources()):
                        if addressBookObject._resourceID == self._addressbook._resourceID:
                            ownerGroup = addressBookObject
                            ownerAddressBook = addressbook
                            break
        returnValue((ownerGroup, ownerAddressBook))

    @inlineCallbacks
    def updateDatabase(self, component, expand_until=None, reCreate=False,
                       inserting=False):
        """
        Update the database tables for the new data being written.

        @param component: addressbook data to store
        @type component: L{Component}
        """

        abo = schema.ADDRESSBOOK_OBJECT
        aboForeignMembers = schema.ABO_FOREIGN_MEMBERS
        aboMembers = schema.ABO_MEMBERS

        componentText = str(component)
        self._objectText = componentText

        # ADDRESSBOOK_OBJECT table update
        uid = component.resourceUID()
        assert inserting or self._uid == uid # can't change UID. Should be checked in upper layers
        self._uid = uid
        self._md5 = hashlib.md5(componentText).hexdigest()
        self._size = len(componentText)

        # Special - if migrating we need to preserve the original md5    
        if self._txn._migrating and hasattr(component, "md5"):
            self._md5 = component.md5

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

        ''' FIXME: 
            SECURITY HOLE on for shared groups:  Non owner may NOT add group members not currently in group!
            (Or it would be possible to troll for unshared vCard UIDs and make them shared.)
            Fixes: just prevent it, but may make some clients fail when sharee adds groups + members to shared group.
        '''

        print("updateDatabase:self=%s self._addressbook.=%s self._ownerAddressBookResourceID=%s" % (self, self._addressbook, self._ownerAddressBookResourceID,))
        print("updateDatabase:self=%s insert=%s, component=%s" % (self, inserting, component))
        if inserting:

            ownerGroup, ownerAddressBook = yield self._ownerGroupAndAddressBook()
            assert ownerAddressBook
            self._ownerAddressBookResourceID = ownerAddressBook._resourceID

            self._resourceID, self._created, self._modified = (
                yield self._insertABObject.on(
                    self._txn,
                    addressbookResourceID=self._ownerAddressBookResourceID,
                    name=self._name,
                    text=componentText,
                    uid=self._uid,
                    md5=self._md5,
                    kind=self._kind,
                    ))[0]

            if ownerGroup:
                ownerGroupComponent = yield ownerGroup.component()
                member = "urn:uuid:" + self._uid
                if not member in ownerGroupComponent.resourceMembers():
                    ownerGroupComponent.addProperty(Property("X-ADDRESSBOOKSERVER-MEMBER", member))
                    ownerGroup.updateDatabase(ownerGroupComponent)

            # add row on this address book group table
            print("updateDatabase1:self=%s Insert(aboMembers.GROUP_ID:%s,  aboMembers.ADDRESSBOOK_ID:%s, aboMembers.MEMBER_ID:%s" % (
                self, self._ownerAddressBookResourceID, self._ownerAddressBookResourceID, self._resourceID))
            yield Insert(
                {aboMembers.GROUP_ID: self._ownerAddressBookResourceID,
                 aboMembers.ADDRESSBOOK_ID: self._ownerAddressBookResourceID,
                 aboMembers.MEMBER_ID: self._resourceID, }
            ).on(self._txn)

            # update existing group member tables for this new object
            # delete foreign members table row for this object
            groupIDs = yield Delete(
                aboForeignMembers,
                Where=aboForeignMembers.MEMBER_ADDRESS == "urn:uuid:" + self._uid,
                Return=aboForeignMembers.GROUP_ID
            ).on(self._txn)

            # add to member table row by resourceID
            for groupID in groupIDs:
                print("updateDatabase2:self=%s Insert(aboMembers.GROUP_ID:%s,  aboMembers.ADDRESSBOOK_ID:%s, aboMembers.MEMBER_ID:%s" % (
                    self, groupID[0], self._ownerAddressBookResourceID, self._resourceID))
                yield Insert(
                    {aboMembers.GROUP_ID: groupID[0],
                     aboMembers.ADDRESSBOOK_ID: self._ownerAddressBookResourceID,
                     aboMembers.MEMBER_ID: self._resourceID, }
                ).on(self._txn)

        else:
            self._modified = (yield Update(
                {abo.VCARD_TEXT: componentText,
                 abo.MD5: self._md5,
                 abo.MODIFIED: utcNowSQL},
                Where=abo.RESOURCE_ID == self._resourceID,
                Return=abo.MODIFIED).on(self._txn))[0][0]

        if self._kind == _ABO_KIND_GROUP:

            assert self._ownerAddressBookResourceID
            # get member resource ID for each member string, or keep as string
            memberIDs = []
            foreignMemberAddrs = []
            for memberAddr in component.resourceMembers():
                memberRow = []
                if len(memberAddr) > len("urn:uuid:") and memberAddr.startswith("urn:uuid:"):
                    memberUID = memberAddr[len("urn:uuid:"):]
                    memberRow = yield Select([abo.RESOURCE_ID],
                                     From=abo,
                                     Where=((abo.ADDRESSBOOK_RESOURCE_ID == self._ownerAddressBookResourceID)
                                            ).And(abo.VCARD_UID == memberUID)).on(self._txn)
                if memberRow:
                    memberIDs.append(memberRow[0][0])
                else:
                    foreignMemberAddrs.append(memberAddr)

            #get current members
            currentMemberRows = yield Select([aboMembers.MEMBER_ID],
                                 From=aboMembers,
                                 Where=(aboMembers.GROUP_ID == self._resourceID)).on(self._txn)
            currentMemberIDs = [currentMemberRow[0] for currentMemberRow in currentMemberRows]

            memberIDsToDelete = set(currentMemberIDs) - set(memberIDs)
            memberIDsToAdd = set(memberIDs) - set(currentMemberIDs)
            print("updateDatabase3:self=%s component.resourceMembers()=%s, currentMemberIDs:%s,  memberIDsToAdd:%s, memberIDsToDelete:%s" % (self, component.resourceMembers(), currentMemberIDs, memberIDsToAdd, memberIDsToDelete,))

            for memberIDToDelete in memberIDsToDelete:
                yield Delete(
                    aboMembers,
                    Where=((aboMembers.GROUP_ID == self._resourceID).And(aboMembers.MEMBER_ID == memberIDToDelete))
                ).on(self._txn)

            for memberIDToAdd in memberIDsToAdd:
                print("updateDatabase3.1:self=%s Insert(aboMembers.GROUP_ID:%s,  aboMembers.ADDRESSBOOK_ID:%s, aboMembers.MEMBER_ID:%s" % (
                    self, self._resourceID, self._ownerAddressBookResourceID, memberIDToAdd))
                yield Insert(
                    {aboMembers.GROUP_ID: self._resourceID,
                     aboMembers.ADDRESSBOOK_ID: self._ownerAddressBookResourceID,
                     aboMembers.MEMBER_ID: memberIDToAdd, }
                ).on(self._txn)

            #get current foreign members 
            currentForeignMemberAddrs = yield Select([aboForeignMembers.MEMBER_ADDRESS],
                                                 From=aboForeignMembers,
                                                 Where=(aboForeignMembers.GROUP_ID == self._resourceID)).on(self._txn)

            foreignMemberAddrsToDelete = set(currentForeignMemberAddrs) - set(foreignMemberAddrs)
            foreignMemberAddrsToAdd = set(foreignMemberAddrs) - set(currentForeignMemberAddrs)

            for foreignMemberAddrToDelete in foreignMemberAddrsToDelete:
                yield Delete(
                    aboForeignMembers,
                    Where=((aboMembers.GROUP_ID == self._resourceID).And(aboForeignMembers.MEMBER_ADDRESS == foreignMemberAddrToDelete))
                ).on(self._txn)

            for foreignMemberAddrToAdd in foreignMemberAddrsToAdd:
                print("updateDatabase4:self=%s Insert(foreignMemberAddrToAdd.GROUP_ID:%s,  foreignMemberAddrToAdd.ADDRESSBOOK_ID:%s, foreignMemberAddrToAdd.MEMBER_ID:%s" % (
                    self, self._resourceID, self._ownerAddressBookResourceID, foreignMemberAddrToAdd))
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

        returnValue(component)


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
