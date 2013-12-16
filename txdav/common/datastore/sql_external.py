# -*- test-case-name: txdav.caldav.datastore.test.test_sql,txdav.carddav.datastore.test.test_sql -*-
##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
SQL data store.
"""

from twext.internet.decorate import memoizedKey
from twext.python.log import Logger

from twisted.internet.defer import inlineCallbacks, returnValue, succeed

from txdav.base.propertystore.sql import PropertyStore
from txdav.common.datastore.sql import CommonHome, CommonHomeChild, \
    CommonObjectResource
from txdav.common.datastore.sql_tables import _HOME_STATUS_EXTERNAL
from txdav.common.icommondatastore import NonExistentExternalShare, \
    ExternalShareFailed


log = Logger()

class CommonHomeExternal(CommonHome):
    """
    A CommonHome for a user not hosted on this system, but on another pod. This is needed to provide a
    "reference" to the external user so we can share with them. Actual operations to list child resources, etc
    are all stubbed out since no data for the user is actually hosted in this store.
    """

    def __init__(self, transaction, ownerUID, resourceID):
        super(CommonHomeExternal, self).__init__(transaction, ownerUID)
        self._resourceID = resourceID
        self._status = _HOME_STATUS_EXTERNAL


    def initFromStore(self, no_cache=False):
        """
        Never called - this should be done by CommonHome.initFromStore only.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def external(self):
        """
        Is this an external home.

        @return: a string.
        """
        return True


    def children(self):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def loadChildren(self):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def listChildren(self):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def objectWithShareUID(self, shareUID):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def invitedObjectWithShareUID(self, shareUID):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    @memoizedKey("name", "_children")
    @inlineCallbacks
    def createChildWithName(self, name, externalID=None):
        """
        No real children - only external ones.
        """
        if externalID is None:
            raise AssertionError("CommonHomeExternal: not supported")
        child = yield super(CommonHomeExternal, self).createChildWithName(name, externalID)
        returnValue(child)


    def removeChildWithName(self, name):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    @inlineCallbacks
    def removeExternalChild(self, child):
        """
        Remove an external child. Check that it is invalid or unused before calling this because if there
        are valid references to it, removing will break things.
        """
        if child._externalID is None:
            raise AssertionError("CommonHomeExternal: not supported")
        yield super(CommonHomeExternal, self).removeChildWithName(child.name())


    def syncToken(self):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def resourceNamesSinceRevision(self, revision, depth):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    @inlineCallbacks
    def _loadPropertyStore(self):
        """
        No property store - stub to a NonePropertyStore.
        """
        props = yield PropertyStore.load(
            self.uid(),
            self.uid(),
            self._txn,
            self._resourceID,
            notifyCallback=self.notifyChanged
        )
        self._propertyStore = props


    def properties(self):
        return self._propertyStore


    def objectResourcesWithUID(self, uid, ignore_children=[], allowShared=True):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def objectResourceWithID(self, rid):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def notifyChanged(self):
        """
        Notifications are not handled for external homes - make this a no-op.
        """
        return succeed(None)


    def bumpModified(self):
        """
        No changes recorded for external homes - make this a no-op.
        """
        return succeed(None)


    def removeUnacceptedShares(self):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


#    def ownerHomeAndChildNameForChildID(self, resourceID):
#        """
#        No children.
#        """
#        raise AssertionError("CommonHomeExternal: not supported")



class CommonHomeChildExternal(CommonHomeChild):
    """
    A CommonHomeChild for a collection not hosted on this system, but on another pod. This will forward
    specific apis to the other pod using cross-pod requests.
    """

    def external(self):
        """
        Is this an external home.

        @return: a string.
        """
        return True


    def fixNonExistentExternalShare(self):
        """
        An external request has returned and indicates the external share no longer exists. That
        means this shared resource is an "orphan" and needs to be remove (uninvited) to clean things up.
        """
        log.error("Non-existent share detected and removed for {share}", share=self)
        ownerView = yield self.ownerView()
        yield ownerView.removeShare(self)


    @inlineCallbacks
    def remove(self):
        """
        External shares are never removed directly - instead they must be "uninvited". However,
        the owner's external calendar can be removed.
        """
        if self.owned():
            yield super(CommonHomeChildExternal, self).remove()
        else:
            raise AssertionError("CommonHomeChildExternal: not supported")


    @inlineCallbacks
    def listObjectResources(self):
        if self._objectNames is None:
            try:
                self._objectNames = yield self._txn.store().conduit.send_listobjects(self)
            except NonExistentExternalShare:
                yield self.fixNonExistentExternalShare()
                raise ExternalShareFailed("External share does not exist")

        returnValue(self._objectNames)


    @inlineCallbacks
    def countObjectResources(self):
        if self._objectNames is None:
            try:
                count = yield self._txn.store().conduit.send_countobjects(self)
            except NonExistentExternalShare:
                yield self.fixNonExistentExternalShare()
                raise ExternalShareFailed("External share does not exist")
            returnValue(count)
        returnValue(len(self._objectNames))


    @inlineCallbacks
    def resourceNameForUID(self, uid):
        try:
            resource = self._objects[uid]
            returnValue(resource.name() if resource else None)
        except KeyError:
            pass

        try:
            name = yield self._txn.store().conduit.send_resourcenameforuid(self, uid)
        except NonExistentExternalShare:
            yield self.fixNonExistentExternalShare()
            raise ExternalShareFailed("External share does not exist")

        if name:
            returnValue(name)
        else:
            self._objects[uid] = None
            returnValue(None)


    @inlineCallbacks
    def resourceUIDForName(self, name):
        try:
            resource = self._objects[name]
            returnValue(resource.uid() if resource else None)
        except KeyError:
            pass

        try:
            uid = yield self._txn.store().conduit.send_resourceuidforname(self, name)
        except NonExistentExternalShare:
            yield self.fixNonExistentExternalShare()
            raise ExternalShareFailed("External share does not exist")

        if uid:
            returnValue(uid)
        else:
            self._objects[name] = None
            returnValue(None)


    @inlineCallbacks
    def moveObjectResource(self, child, newparent, newname=None):
        """
        The base class does an optimization to avoid removing/re-creating
        the actual object resource data. That might not always be possible
        with external shares if the shared resource is moved to a collection
        that is not shared or shared by someone else on a different (third)
        pod. The best bet here is to treat the move as a delete/create.
        """
        raise NotImplementedError("TODO: external resource")


    @inlineCallbacks
    def syncToken(self):
        if self._syncTokenRevision is None:
            try:
                token = yield self._txn.store().conduit.send_synctoken(self)
                self._syncTokenRevision = self.revisionFromToken(token)
            except NonExistentExternalShare:
                yield self.fixNonExistentExternalShare()
                raise ExternalShareFailed("External share does not exist")
        returnValue(("%s_%s" % (self._externalID, self._syncTokenRevision,)))


    @inlineCallbacks
    def resourceNamesSinceRevision(self, revision):
        try:
            names = yield self._txn.store().conduit.send_resourcenamessincerevision(self, revision)
        except NonExistentExternalShare:
            yield self.fixNonExistentExternalShare()
            raise ExternalShareFailed("External share does not exist")

        returnValue(names)



class CommonObjectResourceExternal(CommonObjectResource):
    """
    A CommonObjectResource for a resource not hosted on this system, but on another pod. This will forward
    specific apis to the other pod using cross-pod requests.
    """

    @classmethod
    @inlineCallbacks
    def loadAllObjects(cls, parent):
        mapping_list = yield parent._txn.store().conduit.send_loadallobjects(parent, None)

        results = []
        if mapping_list:
            for mapping in mapping_list:
                child = yield cls.internalize(parent, mapping)
                results.append(child)
        returnValue(results)


    @classmethod
    @inlineCallbacks
    def loadAllObjectsWithNames(cls, parent, names):
        mapping_list = yield parent._txn.store().conduit.send_loadallobjectswithnames(parent, None, names)

        results = []
        if mapping_list:
            for mapping in mapping_list:
                child = yield cls.internalize(parent, mapping)
                results.append(child)
        returnValue(results)


    @classmethod
    @inlineCallbacks
    def objectWith(cls, parent, name=None, uid=None, resourceID=None):
        mapping = yield parent._txn.store().conduit.send_objectwith(parent, None, name, uid, resourceID)

        if mapping:
            child = yield cls.internalize(parent, mapping)
            returnValue(child)
        else:
            returnValue(None)


    @classmethod
    @inlineCallbacks
    def create(cls, parent, name, component, options=None):
        mapping = yield parent._txn.store().conduit.send_create(parent, None, name, str(component), options=options)

        if mapping:
            child = yield cls.internalize(parent, mapping)
            returnValue(child)
        else:
            returnValue(None)


    @inlineCallbacks
    def setComponent(self, component, **kwargs):
        self._componentChanged = yield self._txn.store().conduit.send_setcomponent(self.parentCollection(), self, str(component), **kwargs)
        self._cachedComponent = None
        returnValue(self._componentChanged)


    @inlineCallbacks
    def component(self):
        if self._cachedComponent is None:
            text = yield self._txn.store().conduit.send_component(self.parentCollection(), self)
            self._cachedComponent = self._componentClass.fromString(text)

        returnValue(self._cachedComponent)


    @inlineCallbacks
    def moveTo(self, destination, name=None):
        """
        Probably OK to leave this to the base implementation which calls up to the parent after some validation.
        """
        raise NotImplementedError


    @inlineCallbacks
    def remove(self):
        yield self._txn.store().conduit.send_remove(self.parentCollection(), self)
