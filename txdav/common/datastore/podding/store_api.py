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
from txdav.caldav.datastore.scheduling.freebusy import generateFreeBusyInfo

from twistedcaldav.caldavxml import TimeRange


class StoreAPIConduitMixin(object):
    """
    Defines common cross-pod API for generic access to remote resources.
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

        # Add store object identities to JSON request
        result["homeType"] = viewer_home._homeType
        result["homeUID"] = viewer_home.uid()
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

        returnValue((txn, result, recipient.server(),))


    @inlineCallbacks
    def _getStoreObjectForRequest(self, txn, request):
        """
        Resolve the supplied JSON data to get a store object to operate on.
        """

        returnObject = txn
        classObject = None

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

        returnValue((returnObject, classObject,))


    @inlineCallbacks
    def send_home_resource_id(self, txn, recipient):
        """
        Lookup the remote resourceID matching the specified directory uid.

        @param ownerUID: directory record for user whose home is needed
        @type ownerUID: L{DirectroryRecord}
        """

        request = {
            "action": "home-resource_id",
            "ownerUID": recipient.uid,
        }

        response = yield self.sendRequest(txn, recipient, request)
        returnValue(response)


    @inlineCallbacks
    def recv_home_resource_id(self, txn, request):
        """
        Process an addAttachment cross-pod request. Request arguments as per L{send_add_attachment}.

        @param request: request arguments
        @type request: C{dict}
        """

        home = yield txn.calendarHomeWithUID(request["ownerUID"])
        returnValue(home.id() if home is not None else None)


    @inlineCallbacks
    def send_freebusy(
        self,
        calresource,
        timerange,
        matchtotal,
        excludeuid,
        organizer,
        organizerPrincipal,
        same_calendar_user,
        servertoserver,
        event_details,
    ):
        """
        Request free busy information for a shared calendar collection hosted on a different pod. See
        L{txdav.caldav.datastore.scheduling.freebusy} for the base free busy lookup behavior.
        """
        txn, request, server = yield self._getRequestForStoreObject("freebusy", calresource, False)

        request["timerange"] = [timerange.start.getText(), timerange.end.getText()]
        request["matchtotal"] = matchtotal
        request["excludeuid"] = excludeuid
        request["organizer"] = organizer
        request["organizerPrincipal"] = organizerPrincipal
        request["same_calendar_user"] = same_calendar_user
        request["servertoserver"] = servertoserver
        request["event_details"] = event_details

        response = yield self.sendRequestToServer(txn, server, request)
        returnValue((response["fbresults"], response["matchtotal"],))


    @inlineCallbacks
    def recv_freebusy(self, txn, request):
        """
        Process a freebusy cross-pod request. Message arguments as per L{send_freebusy}.

        @param request: request arguments
        @type request: C{dict}
        """

        # Operate on the L{CommonHomeChild}
        calresource, _ignore = yield self._getStoreObjectForRequest(txn, request)

        fbinfo = [[], [], []]
        matchtotal = yield generateFreeBusyInfo(
            calresource,
            fbinfo,
            TimeRange(start=request["timerange"][0], end=request["timerange"][1]),
            request["matchtotal"],
            request["excludeuid"],
            request["organizer"],
            request["organizerPrincipal"],
            request["same_calendar_user"],
            request["servertoserver"],
            request["event_details"],
            logItems=None
        )

        # Convert L{DateTime} objects to text for JSON response
        for i in range(3):
            for j in range(len(fbinfo[i])):
                fbinfo[i][j] = fbinfo[i][j].getText()

        returnValue({
            "fbresults": fbinfo,
            "matchtotal": matchtotal,
        })


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
    @classmethod
    def _make_simple_action(cls, action, method, classMethod=False, transform_recv_result=None, transform_send_result=None):
        setattr(
            cls,
            "send_{}".format(action),
            lambda self, storeObject, *args, **kwargs:
                self._simple_object_send(action, storeObject, classMethod=classMethod, transform=transform_send_result, args=args, kwargs=kwargs)
        )
        setattr(
            cls,
            "recv_{}".format(action),
            lambda self, txn, message:
                self._simple_object_recv(txn, action, message, method, transform=transform_recv_result)
        )


    #
    # Transforms for returned data
    #
    @staticmethod
    def _to_externalize(value):
        """
        Convert the value to the external (JSON-based) representation.
        """
        return value.externalize() if value is not None else None


    @staticmethod
    def _to_externalize_list(value):
        """
        Convert the value to the external (JSON-based) representation.
        """
        return [v.externalize() for v in value]


    @staticmethod
    def _to_string(value):
        return str(value)


    @staticmethod
    def _to_tuple(value):
        return tuple(value)

# These are the actions on store objects we need to expose via the conduit api

# Calls on L{CommonHome} objects

# Calls on L{CommonHomeChild} objects
StoreAPIConduitMixin._make_simple_action("homechild_listobjects", "listObjects", classMethod=True)
StoreAPIConduitMixin._make_simple_action("homechild_loadallobjects", "loadAllObjects", classMethod=True, transform_recv_result=StoreAPIConduitMixin._to_externalize_list)
StoreAPIConduitMixin._make_simple_action("homechild_objectwith", "objectWith", classMethod=True, transform_recv_result=StoreAPIConduitMixin._to_externalize)
StoreAPIConduitMixin._make_simple_action("homechild_movehere", "moveObjectResourceHere")
StoreAPIConduitMixin._make_simple_action("homechild_moveaway", "moveObjectResourceAway")
StoreAPIConduitMixin._make_simple_action("homechild_synctoken", "syncToken")
StoreAPIConduitMixin._make_simple_action("homechild_resourcenamessincerevision", "resourceNamesSinceRevision", transform_send_result=StoreAPIConduitMixin._to_tuple)
StoreAPIConduitMixin._make_simple_action("homechild_search", "search")

# Calls on L{CommonObjectResource} objects
StoreAPIConduitMixin._make_simple_action("objectresource_loadallobjects", "loadAllObjects", classMethod=True, transform_recv_result=StoreAPIConduitMixin._to_externalize_list)
StoreAPIConduitMixin._make_simple_action("objectresource_loadallobjectswithnames", "loadAllObjectsWithNames", classMethod=True, transform_recv_result=StoreAPIConduitMixin._to_externalize_list)
StoreAPIConduitMixin._make_simple_action("objectresource_listobjects", "listObjects", classMethod=True)
StoreAPIConduitMixin._make_simple_action("objectresource_countobjects", "countObjects", classMethod=True)
StoreAPIConduitMixin._make_simple_action("objectresource_objectwith", "objectWith", classMethod=True, transform_recv_result=StoreAPIConduitMixin._to_externalize)
StoreAPIConduitMixin._make_simple_action("objectresource_resourcenameforuid", "resourceNameForUID", classMethod=True)
StoreAPIConduitMixin._make_simple_action("objectresource_resourceuidforname", "resourceUIDForName", classMethod=True)
StoreAPIConduitMixin._make_simple_action("objectresource_create", "create", classMethod=True, transform_recv_result=StoreAPIConduitMixin._to_externalize)
StoreAPIConduitMixin._make_simple_action("objectresource_setcomponent", "setComponent")
StoreAPIConduitMixin._make_simple_action("objectresource_component", "component", transform_recv_result=StoreAPIConduitMixin._to_string)
StoreAPIConduitMixin._make_simple_action("objectresource_remove", "remove")
