##
# Copyright (c) 2013-2014 Apple Inc. All rights reserved.
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
from twisted.python.reflect import namedClass

from txdav.common.datastore.podding.sharing_base import SharingCommonPoddingConduit
from txdav.caldav.datastore.scheduling.freebusy import generateFreeBusyInfo

from twistedcaldav.caldavxml import TimeRange


class SharingStorePoddingConduitMixin(SharingCommonPoddingConduit):
    """
    Defines the cross-pod API for access to shared resource data that will be mixed into the
    L{PoddingConduit} class.
    """

    #
    # Simple calls are ones where there is no argument and a single return value. We can simplify
    # code generation for these by dynamically generating the appropriate class methods.
    #

    @inlineCallbacks
    def _simple_send(self, actionName, shareeView, objectResource=None, transform=None, args=None, kwargs=None):
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

        request, recipient = yield self._getRequestForResource(actionName, shareeView, objectResource)
        if args is not None:
            request["arguments"] = args
        if kwargs is not None:
            request["keywords"] = kwargs
        response = yield self.sendRequest(shareeView._txn, recipient, request)
        if response["result"] == "ok":
            returnValue(response["value"] if transform is None else transform(response["value"], shareeView, objectResource))
        elif response["result"] == "exception":
            raise namedClass(response["class"])(response["result"])


    @inlineCallbacks
    def _simple_recv(self, txn, actionName, request, method, onHomeChild=True, transform=None):
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

        shareeView, objectResource = yield self._getResourcesForRequest(txn, request, actionName)
        try:
            if onHomeChild:
                # Operate on the L{CommonHomeChild}
                value = yield getattr(shareeView, method)(*request.get("arguments", ()), **request.get("keywords", {}))
            else:
                # Operate on the L{CommonObjectResource}
                if objectResource is not None:
                    value = yield getattr(objectResource, method)(*request.get("arguments", ()), **request.get("keywords", {}))
                else:
                    # classmethod call
                    value = yield getattr(shareeView._objectResourceClass, method)(shareeView, *request.get("arguments", ()), **request.get("keywords", {}))
        except Exception as e:
            returnValue({
                "result": "exception",
                "class": ".".join((e.__class__.__module__, e.__class__.__name__,)),
                "request": str(e),
            })

        returnValue({
            "result": "ok",
            "value": transform(value, shareeView, objectResource) if transform is not None else value,
        })


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
        action, recipient = yield self._getRequestForResource("freebusy", calresource)
        action["timerange"] = [timerange.start.getText(), timerange.end.getText()]
        action["matchtotal"] = matchtotal
        action["excludeuid"] = excludeuid
        action["organizer"] = organizer
        action["organizerPrincipal"] = organizerPrincipal
        action["same_calendar_user"] = same_calendar_user
        action["servertoserver"] = servertoserver
        action["event_details"] = event_details

        response = yield self.sendRequest(calresource._txn, recipient, action)

        if response["result"] == "ok":
            returnValue((response["fbresults"], response["matchtotal"],))
        elif response["result"] == "exception":
            raise namedClass(response["class"])(response["result"])


    @inlineCallbacks
    def recv_freebusy(self, txn, request):
        """
        Process a freebusy cross-pod request. Message arguments as per L{send_freebusy}.

        @param request: request arguments
        @type request: C{dict}
        """

        shareeView, _ignore_objectResource = yield self._getResourcesForRequest(txn, request, "freebusy")
        try:
            # Operate on the L{CommonHomeChild}
            fbinfo = [[], [], []]
            matchtotal = yield generateFreeBusyInfo(
                shareeView,
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
        except Exception as e:
            returnValue({
                "result": "exception",
                "class": ".".join((e.__class__.__module__, e.__class__.__name__,)),
                "request": str(e),
            })

        # Convert L{DateTime} objects to text for JSON response
        for i in range(3):
            for j in range(len(fbinfo[i])):
                fbinfo[i][j] = fbinfo[i][j].getText()

        returnValue({
            "result": "ok",
            "fbresults": fbinfo,
            "matchtotal": matchtotal,
        })


    #
    # Methods used to transform arguments to or results from a JSON request or response.
    #
    @staticmethod
    def _to_tuple(value, shareeView, objectResource):
        return tuple(value)


    @staticmethod
    def _to_string(value, shareeView, objectResource):
        return str(value)


    @staticmethod
    def _to_externalize(value, shareeView, objectResource):
        """
        Convert the value to the external (JSON-based) representation.
        """
        if isinstance(value, shareeView._objectResourceClass):
            value = value.externalize()
        elif value is not None:
            value = [v.externalize() for v in value]
        return value


    #
    # Factory methods for binding actions to the conduit class
    #
    @classmethod
    def _make_simple_homechild_action(cls, action, method, transform_recv=None, transform_send=None):
        setattr(
            cls,
            "send_{}".format(action),
            lambda self, shareeView, *args, **kwargs:
                self._simple_send(action, shareeView, transform=transform_send, args=args, kwargs=kwargs)
        )
        setattr(
            cls,
            "recv_{}".format(action),
            lambda self, txn, message:
                self._simple_recv(txn, action, message, method, transform=transform_recv)
        )


    @classmethod
    def _make_simple_object_action(cls, action, method, transform_recv=None, transform_send=None):
        setattr(
            cls,
            "send_{}".format(action),
            lambda self, shareeView, objectResource, *args, **kwargs:
                self._simple_send(action, shareeView, objectResource, transform=transform_send, args=args, kwargs=kwargs)
        )
        setattr(
            cls,
            "recv_{}".format(action),
            lambda self, txn, message:
                self._simple_recv(txn, action, message, method, onHomeChild=False, transform=transform_recv)
        )

# These are the actions on store objects we need to expose via the conduit api

# Calls on L{CommonHomeChild} objects
SharingStorePoddingConduitMixin._make_simple_homechild_action("countobjects", "countObjectResources")
SharingStorePoddingConduitMixin._make_simple_homechild_action("listobjects", "listObjectResources")
SharingStorePoddingConduitMixin._make_simple_homechild_action("resourceuidforname", "resourceUIDForName")
SharingStorePoddingConduitMixin._make_simple_homechild_action("resourcenameforuid", "resourceNameForUID")
SharingStorePoddingConduitMixin._make_simple_homechild_action("movehere", "moveObjectResourceHere")
SharingStorePoddingConduitMixin._make_simple_homechild_action("moveaway", "moveObjectResourceAway")
SharingStorePoddingConduitMixin._make_simple_homechild_action("synctoken", "syncToken")
SharingStorePoddingConduitMixin._make_simple_homechild_action("resourcenamessincerevision", "resourceNamesSinceRevision", transform_send=SharingStorePoddingConduitMixin._to_tuple)
SharingStorePoddingConduitMixin._make_simple_homechild_action("search", "search")

# Calls on L{CommonObjectResource} objects
SharingStorePoddingConduitMixin._make_simple_object_action("loadallobjects", "loadAllObjects", transform_recv=SharingStorePoddingConduitMixin._to_externalize)
SharingStorePoddingConduitMixin._make_simple_object_action("loadallobjectswithnames", "loadAllObjectsWithNames", transform_recv=SharingStorePoddingConduitMixin._to_externalize)
SharingStorePoddingConduitMixin._make_simple_object_action("objectwith", "objectWith", transform_recv=SharingStorePoddingConduitMixin._to_externalize)
SharingStorePoddingConduitMixin._make_simple_object_action("create", "create", transform_recv=SharingStorePoddingConduitMixin._to_externalize)
SharingStorePoddingConduitMixin._make_simple_object_action("setcomponent", "setComponent")
SharingStorePoddingConduitMixin._make_simple_object_action("component", "component", transform_recv=SharingStorePoddingConduitMixin._to_string)
SharingStorePoddingConduitMixin._make_simple_object_action("remove", "remove")
