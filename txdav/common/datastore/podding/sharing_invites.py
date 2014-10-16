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

from txdav.common.icommondatastore import ExternalShareFailed
from txdav.common.datastore.podding.base import FailedCrossPodRequestError
from txdav.common.datastore.podding.sharing_base import SharingCommonPoddingConduit


class SharingInvitesPoddingConduitMixin(SharingCommonPoddingConduit):
    """
    Defines the cross-pod API for sharing invites that will be mixed into the
    L{PoddingConduit} class.
    """

    @inlineCallbacks
    def send_shareinvite(self, txn, homeType, ownerUID, ownerID, ownerName, shareeUID, shareUID, bindMode, summary, copy_properties, supported_components):
        """
        Send a sharing invite cross-pod message.

        @param homeType: Type of home being shared.
        @type homeType: C{int}
        @param ownerUID: UID of the sharer.
        @type ownerUID: C{str}
        @param ownerID: resource ID of the sharer calendar
        @type ownerID: C{int}
        @param ownerName: owner's name of the sharer calendar
        @type ownerName: C{str}
        @param shareeUID: UID of the sharee
        @type shareeUID: C{str}
        @param shareUID: Resource/invite ID for sharee
        @type shareUID: C{str}
        @param bindMode: bind mode for the share
        @type bindMode: C{str}
        @param summary: sharing message
        @type summary: C{str}
        @param copy_properties: C{str} name/value for properties to be copied
        @type copy_properties: C{dict}
        @param supported_components: supproted components, may be C{None}
        @type supported_components: C{str}
        """

        _ignore_sender, recipient = yield self.validRequest(ownerUID, shareeUID)

        request = {
            "action": "shareinvite",
            "type": homeType,
            "owner": ownerUID,
            "owner_id": ownerID,
            "owner_name": ownerName,
            "sharee": shareeUID,
            "share_id": shareUID,
            "mode": bindMode,
            "summary": summary,
            "properties": copy_properties,
        }
        if supported_components is not None:
            request["supported-components"] = supported_components

        result = yield self.sendRequest(txn, recipient, request)
        returnValue(result)


    @inlineCallbacks
    def recv_shareinvite(self, txn, request):
        """
        Process a sharing invite cross-pod request. Request arguments as per L{send_shareinvite}.

        @param request: request arguments
        @type request: C{dict}
        """

        if request["action"] != "shareinvite":
            raise FailedCrossPodRequestError("Wrong action '{}' for recv_shareinvite".format(request["action"]))

        # Sharee home on this pod must exist (create if needed)
        shareeHome = yield txn.homeWithUID(request["type"], request["sharee"], create=True)
        if shareeHome is None or shareeHome.external():
            raise FailedCrossPodRequestError("Invalid sharee UID specified")

        # Create a share
        try:
            yield shareeHome.processExternalInvite(
                request["owner"],
                request["owner_id"],
                request["owner_name"],
                request["share_id"],
                request["mode"],
                request["summary"],
                request["properties"],
                supported_components=request.get("supported-components")
            )
        except ExternalShareFailed as e:
            raise FailedCrossPodRequestError(str(e))

        returnValue({
            "result": "ok",
        })


    @inlineCallbacks
    def send_shareuninvite(self, txn, homeType, ownerUID, ownerID, shareeUID, shareUID):
        """
        Send a sharing uninvite cross-pod message.

        @param homeType: Type of home being shared.
        @type homeType: C{int}
        @param ownerUID: UID of the sharer.
        @type ownerUID: C{str}
        @param ownerID: resource ID of the sharer calendar
        @type ownerID: C{int}
        @param shareeUID: UID of the sharee
        @type shareeUID: C{str}
        @param shareUID: Resource/invite ID for sharee
        @type shareUID: C{str}
        """

        _ignore_sender, recipient = yield self.validRequest(ownerUID, shareeUID)

        request = {
            "action": "shareuninvite",
            "type": homeType,
            "owner": ownerUID,
            "owner_id": ownerID,
            "sharee": shareeUID,
            "share_id": shareUID,
        }

        result = yield self.sendRequest(txn, recipient, request)
        returnValue(result)


    @inlineCallbacks
    def recv_shareuninvite(self, txn, request):
        """
        Process a sharing uninvite cross-pod request. Request arguments as per L{send_shareuninvite}.

        @param request: request arguments
        @type request: C{dict}
        """

        if request["action"] != "shareuninvite":
            raise FailedCrossPodRequestError("Wrong action '{}' for recv_shareuninvite".format(request["action"]))

        # Sharee home on this pod must already exist
        shareeHome = yield txn.homeWithUID(request["type"], request["sharee"])
        if shareeHome is None or shareeHome.external():
            FailedCrossPodRequestError("Invalid sharee UID specified")

        # Remove a share
        try:
            yield shareeHome.processExternalUninvite(
                request["owner"],
                request["owner_id"],
                request["share_id"],
            )
        except ExternalShareFailed as e:
            FailedCrossPodRequestError(str(e))

        returnValue({
            "result": "ok",
        })


    @inlineCallbacks
    def send_sharereply(self, txn, homeType, ownerUID, shareeUID, shareUID, bindStatus, summary=None):
        """
        Send a sharing reply cross-pod message.

        @param homeType: Type of home being shared.
        @type homeType: C{int}
        @param ownerUID: UID of the sharer.
        @type ownerUID: C{str}
        @param shareeUID: UID of the recipient
        @type shareeUID: C{str}
        @param shareUID: Resource/invite ID for recipient
        @type shareUID: C{str}
        @param bindStatus: bind mode for the share
        @type bindStatus: C{str}
        @param summary: sharing message
        @type summary: C{str}
        """

        _ignore_sender, recipient = yield self.validRequest(shareeUID, ownerUID)

        request = {
            "action": "sharereply",
            "type": homeType,
            "owner": ownerUID,
            "sharee": shareeUID,
            "share_id": shareUID,
            "status": bindStatus,
        }
        if summary is not None:
            request["summary"] = summary

        result = yield self.sendRequest(txn, recipient, request)
        returnValue(result)


    @inlineCallbacks
    def recv_sharereply(self, txn, request):
        """
        Process a sharing reply cross-pod request. Request arguments as per L{send_sharereply}.

        @param request: request arguments
        @type request: C{dict}
        """

        if request["action"] != "sharereply":
            raise FailedCrossPodRequestError("Wrong action '{}' for recv_sharereply".format(request["action"]))

        # Sharer home on this pod must already exist
        ownerHome = yield txn.homeWithUID(request["type"], request["owner"])
        if ownerHome is None or ownerHome.external():
            FailedCrossPodRequestError("Invalid owner UID specified")

        # Process a reply
        try:
            yield ownerHome.processExternalReply(
                request["owner"],
                request["sharee"],
                request["share_id"],
                request["status"],
                summary=request.get("summary")
            )
        except ExternalShareFailed as e:
            FailedCrossPodRequestError(str(e))

        returnValue({
            "result": "ok",
        })
