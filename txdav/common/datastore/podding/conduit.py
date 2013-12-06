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

from twisted.internet.defer import inlineCallbacks, returnValue

from txdav.common.datastore.podding.request import ConduitRequest
from txdav.common.idirectoryservice import DirectoryRecordNotFoundError
from txdav.common.icommondatastore import ExternalShareFailed


__all__ = [
    "PoddingConduitResource",
]

class BadMessageError(Exception):
    pass



class InvalidCrossPodRequestError(Exception):
    pass



class FailedCrossPodRequestError(Exception):
    pass



class PoddingConduit(object):
    """
    This class is the API/RPC bridge between cross-pod requests and the store.

    Each cross-pod request/response is described by a Python C{dict} that is serialized
    to JSON for the HTTP request/response.

    Each request C{dict} has an "action" key that indicates what call is being made, and
    the other keys are arguments to that call.

    Each response C{dict} has a "result" key that indicates the call result, and other
    optional keys for any parameters returned by the call.

    The conduit provides two methods for each action: one for the sending side and one for
    the receiving side, called "send_{action}" and "recv_{action}", respectively, where
    {action} is the action value.

    The "send_{action}" calls each have a set of arguments specific to the call itself. The
    code takes care of packing that into a C{dict} and sending to the appropriate pod.

    The "recv_{action}" calls take a single C{dict} argument that is the deserialized JSON
    data from the incoming request. The return value is a C{dict} with the result.

    Right now this conduit is used for cross-pod sharing operations. In the future we will
    likely use it for cross-pod migration.
    """

    def __init__(self, store):
        """
        @param store: the L{CommonDataStore} in use.
        """
        self.store = store


    def validRequst(self, source_guid, destination_guid):
        """
        Verify that the specified GUIDs are valid for the request and return the
        matching directory records.

        @param source_guid: GUID for the user on whose behalf the request is being made
        @type source_guid: C{str}
        @param destination_guid: GUID for the user to whom the request is being sent
        @type destination_guid: C{str}

        @return: C{tuple} of L{IStoreDirectoryRecord}
        """

        source = self.store.directoryService().recordWithUID(source_guid)
        if source is None:
            raise DirectoryRecordNotFoundError("Cross-pod source: {}".format(source_guid))
        if not source.thisServer():
            raise InvalidCrossPodRequestError("Cross-pod source not on this server: {}".format(source_guid))

        destination = self.store.directoryService().recordWithUID(destination_guid)
        if destination is None:
            raise DirectoryRecordNotFoundError("Cross-pod destination: {}".format(destination_guid))
        if destination.thisServer():
            raise InvalidCrossPodRequestError("Cross-pod destination on this server: {}".format(destination_guid))

        return (source, destination,)


    @inlineCallbacks
    def send_shareinvite(self, txn, homeType, ownerUID, ownerID, ownerName, shareeUID, shareUID, bindMode, summary, supported_components):
        """
        Send a sharing invite cross-pod message.

        @param homeType: Type of home being shared.
        @type homeType: C{int}
        @param ownerUID: GUID of the sharer.
        @type ownerUID: C{str}
        @param ownerID: resource ID of the sharer calendar
        @type ownerID: C{int}
        @param ownerName: owner's name of the sharer calendar
        @type ownerName: C{str}
        @param shareeUID: GUID of the sharee
        @type shareeUID: C{str}
        @param shareUID: Resource/invite ID for sharee
        @type shareUID: C{str}
        @param bindMode: bind mode for the share
        @type bindMode: C{str}
        @param summary: sharing message
        @type summary: C{str}
        @param supported_components: supproted components, may be C{None}
        @type supported_components: C{str}
        """

        _ignore_owner, sharee = self.validRequst(ownerUID, shareeUID)

        action = {
            "action": "shareinvite",
            "type": homeType,
            "owner": ownerUID,
            "owner_id": ownerID,
            "owner_name": ownerName,
            "sharee": shareeUID,
            "share_id": shareUID,
            "mode": bindMode,
            "summary": summary,
        }
        if supported_components is not None:
            action["supported-components"] = supported_components

        request = ConduitRequest(sharee.server(), action)
        response = (yield request.doRequest(txn))
        if response["result"] != "ok":
            raise FailedCrossPodRequestError(response["description"])


    @inlineCallbacks
    def recv_shareinvite(self, txn, message):
        """
        Process a sharing invite cross-pod message. Message arguments as per L{send_shareinvite}.

        @param message: message arguments
        @type message: C{dict}
        """

        if message["action"] != "shareinvite":
            raise BadMessageError("Wrong action '{}' for recv_shareinvite".format(message["action"]))

        # Create a share
        shareeHome = yield txn.homeWithUID(message["type"], message["sharee"], create=True)
        if shareeHome is None or shareeHome.external():
            returnValue({
                "result": "bad",
                "description": "Invalid sharee UID specified",
            })

        try:
            yield shareeHome.processExternalInvite(
                message["owner"],
                message["owner_id"],
                message["owner_name"],
                message["share_id"],
                message["mode"],
                message["summary"],
                supported_components=message.get("supported-components")
            )
        except ExternalShareFailed as e:
            returnValue({
                "result": "bad",
                "description": str(e),
            })

        returnValue({
            "result": "ok",
            "description": "Success"
        })


    @inlineCallbacks
    def send_shareuninvite(self, txn, homeType, ownerUID, ownerID, shareeUID, shareUID):
        """
        Send a sharing uninvite cross-pod message.

        @param homeType: Type of home being shared.
        @type homeType: C{int}
        @param ownerUID: GUID of the sharer.
        @type ownerUID: C{str}
        @param ownerID: resource ID of the sharer calendar
        @type ownerID: C{int}
        @param shareeUID: GUID of the sharee
        @type shareeUID: C{str}
        @param shareUID: Resource/invite ID for sharee
        @type shareUID: C{str}
        """

        _ignore_owner, sharee = self.validRequst(ownerUID, shareeUID)

        action = {
            "action": "shareuninvite",
            "type": homeType,
            "owner": ownerUID,
            "owner_id": ownerID,
            "sharee": shareeUID,
            "share_id": shareUID,
        }

        request = ConduitRequest(sharee.server(), action)
        response = (yield request.doRequest(txn))
        if response["result"] != "ok":
            raise FailedCrossPodRequestError(response["description"])


    @inlineCallbacks
    def recv_shareuninvite(self, txn, message):
        """
        Process a sharing uninvite cross-pod message. Message arguments as per L{send_shareuninvite}.

        @param message: message arguments
        @type message: C{dict}
        """

        if message["action"] != "shareuninvite":
            raise BadMessageError("Wrong action '{}' for recv_shareuninvite".format(message["action"]))

        # Create a share
        shareeHome = yield txn.homeWithUID(message["type"], message["sharee"], create=True)
        if shareeHome is None or shareeHome.external():
            returnValue({
                "result": "bad",
                "description": "Invalid sharee UID specified",
            })

        try:
            yield shareeHome.processExternalUninvite(
                message["owner"],
                message["owner_id"],
                message["share_id"],
            )
        except ExternalShareFailed as e:
            returnValue({
                "result": "bad",
                "description": str(e),
            })

        returnValue({
            "result": "ok",
            "description": "Success"
        })


    @inlineCallbacks
    def send_sharereply(self, txn, homeType, ownerUID, shareeUID, shareUID, bindStatus, summary=None):
        """
        Send a sharing reply cross-pod message.

        @param homeType: Type of home being shared.
        @type homeType: C{int}
        @param ownerUID: GUID of the sharer.
        @type ownerUID: C{str}
        @param shareeUID: GUID of the sharee
        @type shareeUID: C{str}
        @param shareUID: Resource/invite ID for sharee
        @type shareUID: C{str}
        @param bindStatus: bind mode for the share
        @type bindStatus: C{str}
        @param summary: sharing message
        @type summary: C{str}
        """

        _ignore_owner, sharee = self.validRequst(shareeUID, ownerUID)

        action = {
            "action": "sharereply",
            "type": homeType,
            "owner": ownerUID,
            "sharee": shareeUID,
            "share_id": shareUID,
            "status": bindStatus,
        }
        if summary is not None:
            action["summary"] = summary

        request = ConduitRequest(sharee.server(), action)
        response = (yield request.doRequest(txn))
        if response["result"] != "ok":
            raise FailedCrossPodRequestError(response["description"])


    @inlineCallbacks
    def recv_sharereply(self, txn, message):
        """
        Process a sharing reply cross-pod message. Message arguments as per L{send_sharereply}.

        @param message: message arguments
        @type message: C{dict}
        """

        if message["action"] != "sharereply":
            raise BadMessageError("Wrong action '{}' for recv_sharereply".format(message["action"]))

        # Create a share
        ownerHome = yield txn.homeWithUID(message["type"], message["owner"])
        if ownerHome is None or ownerHome.external():
            returnValue({
                "result": "bad",
                "description": "Invalid owner UID specified",
            })

        try:
            yield ownerHome.processExternalReply(
                message["owner"],
                message["sharee"],
                message["share_id"],
                message["status"],
                summary=message.get("summary")
            )
        except ExternalShareFailed as e:
            returnValue({
                "result": "bad",
                "description": str(e),
            })

        returnValue({
            "result": "ok",
            "description": "Success"
        })
