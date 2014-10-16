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

from txdav.common.datastore.podding.base import FailedCrossPodRequestError


class SharingCommonPoddingConduit(object):
    """
    Defines common cross-pod API for sharing that will be mixed into the L{PoddingConduit} class.
    """

    #
    # Sharer data access related apis
    #

    @inlineCallbacks
    def _getRequestForResource(self, action, parent, child=None):
        """
        Create a request for an operation on a L{CommonHomeChild}. This is used when building the JSON
        request object prior to sending it.

        @param shareeView: sharee resource being operated on.
        @type shareeView: L{CommonHomeChildExternal}
        """

        homeType = parent.ownerHome()._homeType
        ownerUID = parent.ownerHome().uid()
        ownerID = parent.external_id()
        shareeUID = parent.viewerHome().uid()

        _ignore_sender, recipient = yield self.validRequest(shareeUID, ownerUID)

        result = {
            "action": action,
            "type": homeType,
            "owner": ownerUID,
            "owner_id": ownerID,
            "sharee": shareeUID,
        }
        if child is not None:
            result["resource_id"] = child.id()
        returnValue((result, recipient))


    @inlineCallbacks
    def _getResourcesForRequest(self, txn, request, expected_action):
        """
        Find the resources associated with the request. This is used when a JSON request has been received
        and the underlying store objects the request refers to need to be found.

        @param request: request arguments
        @type request: C{dict}
        """

        if request["action"] != expected_action:
            raise FailedCrossPodRequestError("Wrong action '{}' for recv_{}".format(request["action"], expected_action))

        # Get a share
        ownerHome = yield txn.homeWithUID(request["type"], request["owner"])
        if ownerHome is None or ownerHome.external():
            FailedCrossPodRequestError("Invalid owner UID specified")

        shareeHome = yield txn.homeWithUID(request["type"], request["sharee"])
        if shareeHome is None or not shareeHome.external():
            FailedCrossPodRequestError("Invalid sharee UID specified")

        shareeView = yield shareeHome.childWithID(request["owner_id"])
        if shareeView is None:
            FailedCrossPodRequestError("Invalid shared resource specified")

        resourceID = request.get("resource_id", None)
        if resourceID is not None:
            objectResource = yield shareeView.objectResourceWithID(resourceID)
            if objectResource is None:
                FailedCrossPodRequestError("Invalid owner shared object resource specified")
        else:
            objectResource = None

        returnValue((shareeView, objectResource,))
