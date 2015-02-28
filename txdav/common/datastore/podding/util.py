##
# Copyright (c) 2013-2015 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks, returnValue

from txdav.common.datastore.podding.base import FailedCrossPodRequestError
from txdav.common.datastore.sql_notification import NotificationCollection, \
    NotificationObject


class UtilityConduitMixin(object):
    """
    Defines utility methods for cross-pod API and mix-ins.
    """

    #
    # Utility methods to map from store objects to/from JSON
    #

    @inlineCallbacks
    def _getRequestForStoreObject(self, action, storeObject, classMethod):
        """
        Create the JSON data needed to identify the remote resource by type and ids, along with any parent resources.

        @param action: the conduit action name
        @type action: L{str}
        @param storeObject: the store object that is being operated on
        @type storeObject: L{object}
        @param classMethod: indicates whether the method being called is a classmethod
        @type classMethod: L{bool}

        @return: the transaction in use, the JSON dict to send in the request,
            the server where the request should be sent
        @rtype: L{tuple} of (L{CommonStoreTransaction}, L{dict}, L{str})
        """

        from txdav.common.datastore.sql import CommonObjectResource, CommonHomeChild, CommonHome
        result = {
            "action": action,
        }

        # Extract the relevant store objects
        txn = storeObject._txn
        owner_home = None
        viewer_home = None
        home_child = None
        object_resource = None
        notification = None
        if isinstance(storeObject, CommonObjectResource):
            owner_home = storeObject.ownerHome()
            viewer_home = storeObject.viewerHome()
            home_child = storeObject.parentCollection()
            object_resource = storeObject
        elif isinstance(storeObject, CommonHomeChild):
            owner_home = storeObject.ownerHome()
            viewer_home = storeObject.viewerHome()
            home_child = storeObject
            result["classMethod"] = classMethod
        elif isinstance(storeObject, CommonHome):
            owner_home = storeObject
            viewer_home = storeObject
            txn = storeObject._txn
            result["classMethod"] = classMethod
        elif isinstance(storeObject, NotificationCollection):
            notification = storeObject
            txn = storeObject._txn
            result["classMethod"] = classMethod

        # Add store object identities to JSON request
        if viewer_home:
            result["homeType"] = viewer_home._homeType
            result["homeUID"] = viewer_home.uid()
            if getattr(viewer_home, "_migratingHome", False):
                result["allowDisabledHome"] = True
            if home_child:
                if home_child.owned():
                    result["homeChildID"] = home_child.id()
                else:
                    result["homeChildSharedID"] = home_child.name()
            if object_resource:
                result["objectResourceID"] = object_resource.id()

            # Note that the owner_home is always the ownerHome() because in the sharing case
            # a viewer is accessing the owner's data on another pod.
            recipient = yield self.store.directoryService().recordWithUID(owner_home.uid())

        elif notification:
            result["notificationUID"] = notification.uid()
            if getattr(notification, "_migratingHome", False):
                result["allowDisabledHome"] = True
            recipient = yield self.store.directoryService().recordWithUID(notification.uid())

        returnValue((txn, result, recipient.server(),))


    @inlineCallbacks
    def _getStoreObjectForRequest(self, txn, request):
        """
        Resolve the supplied JSON data to get a store object to operate on.
        """

        returnObject = txn
        classObject = None

        if "allowDisabledHome" in request:
            txn._allowDisabled = True

        if "homeUID" in request:
            home = yield txn.homeWithUID(request["homeType"], request["homeUID"])
            if home is None:
                raise FailedCrossPodRequestError("Invalid owner UID specified")
            home._internalRequest = False
            returnObject = home
            if request.get("classMethod", False):
                classObject = home._childClass

        if "homeChildID" in request:
            homeChild = yield home.childWithID(request["homeChildID"])
            if homeChild is None:
                raise FailedCrossPodRequestError("Invalid home child specified")
            returnObject = homeChild
            if request.get("classMethod", False):
                classObject = homeChild._objectResourceClass
        elif "homeChildSharedID" in request:
            homeChild = yield home.childWithName(request["homeChildSharedID"])
            if homeChild is None:
                raise FailedCrossPodRequestError("Invalid home child specified")
            returnObject = homeChild
            if request.get("classMethod", False):
                classObject = homeChild._objectResourceClass

        if "objectResourceID" in request:
            objectResource = yield homeChild.objectResourceWithID(request["objectResourceID"])
            if objectResource is None:
                raise FailedCrossPodRequestError("Invalid object resource specified")
            returnObject = objectResource

        if "notificationUID" in request:
            notification = yield txn.notificationsWithUID(request["notificationUID"])
            if notification is None:
                raise FailedCrossPodRequestError("Invalid notification UID specified")
            notification._internalRequest = False
            returnObject = notification
            if request.get("classMethod", False):
                classObject = NotificationObject

        returnValue((returnObject, classObject,))


    #
    # We can simplify code generation for simple calls by dynamically generating the appropriate class methods.
    #

    @inlineCallbacks
    def _simple_object_send(self, actionName, storeObject, classMethod=False, transform=None, args=None, kwargs=None):
        """
        A simple send operation that returns a value.

        @param actionName: name of the action.
        @type actionName: C{str}
        @param shareeView: sharee resource being operated on.
        @type shareeView: L{CommonHomeChildExternal}
        @param objectResource: the resource being operated on, or C{None} for classmethod.
        @type objectResource: L{CommonObjectResourceExternal}
        @param transform: a function used to convert the JSON response into return values.
        @type transform: C{callable}
        @param args: list of optional arguments.
        @type args: C{list}
        @param kwargs: optional keyword arguments.
        @type kwargs: C{dict}
        """

        txn, request, server = yield self._getRequestForStoreObject(actionName, storeObject, classMethod)
        if args is not None:
            request["arguments"] = args
        if kwargs is not None:
            request["keywords"] = kwargs
        response = yield self.sendRequestToServer(txn, server, request)
        returnValue(transform(response) if transform is not None else response)


    @inlineCallbacks
    def _simple_object_recv(self, txn, actionName, request, method, transform=None):
        """
        A simple recv operation that returns a value. We also look for an optional set of arguments/keywords
        and include those only if present.

        @param actionName: name of the action.
        @type actionName: C{str}
        @param request: request arguments
        @type request: C{dict}
        @param method: name of the method to execute on the shared resource to get the result.
        @type method: C{str}
        @param transform: method to call on returned JSON value to convert it to something useful.
        @type transform: C{callable}
        """

        storeObject, classObject = yield self._getStoreObjectForRequest(txn, request)
        if classObject is not None:
            value = yield getattr(classObject, method)(storeObject, *request.get("arguments", ()), **request.get("keywords", {}))
        else:
            value = yield getattr(storeObject, method)(*request.get("arguments", ()), **request.get("keywords", {}))

        returnValue(transform(value) if transform is not None else value)


    #
    # Factory methods for binding actions to the conduit class
    #
    @staticmethod
    def _make_simple_action(bindcls, action, method, classMethod=False, transform_recv_result=None, transform_send_result=None):
        setattr(
            bindcls,
            "send_{}".format(action),
            lambda self, storeObject, *args, **kwargs:
                self._simple_object_send(action, storeObject, classMethod=classMethod, transform=transform_send_result, args=args, kwargs=kwargs)
        )
        setattr(
            bindcls,
            "recv_{}".format(action),
            lambda self, txn, message:
                self._simple_object_recv(txn, action, message, method, transform=transform_recv_result)
        )


    #
    # Transforms for returned data
    #
    @staticmethod
    def _to_serialize(value):
        """
        Convert the value to the external (JSON-based) representation.
        """
        return value.serialize() if value is not None else None


    @staticmethod
    def _to_serialize_list(value):
        """
        Convert the value to the external (JSON-based) representation.
        """
        return [v.serialize() for v in value]


    @staticmethod
    def _to_string(value):
        return str(value)


    @staticmethod
    def _to_tuple(value):
        return tuple(value)
