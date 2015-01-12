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

from twext.python.log import Logger

from twisted.internet.defer import inlineCallbacks, returnValue

from txdav.common.idirectoryservice import DirectoryRecordNotFoundError
from txdav.common.datastore.podding.attachments import AttachmentsPoddingConduitMixin
from txdav.common.datastore.podding.base import FailedCrossPodRequestError
from txdav.common.datastore.podding.directory import DirectoryPoddingConduitMixin
from txdav.common.datastore.podding.request import ConduitRequest
from txdav.common.datastore.podding.sharing_invites import SharingInvitesPoddingConduitMixin
from txdav.common.datastore.podding.sharing_store import SharingStorePoddingConduitMixin


log = Logger()


class PoddingConduit(
    AttachmentsPoddingConduitMixin,
    SharingInvitesPoddingConduitMixin,
    SharingStorePoddingConduitMixin,
    DirectoryPoddingConduitMixin,
):
    """
    This class is the API/RPC bridge between cross-pod requests and the store.

    Each cross-pod request/response is described by a Python C{dict} that is serialized
    to JSON for the HTTP request/response.

    Each request C{dict} has an "action" key that indicates what call is being made, and
    the other keys are arguments to that call.

    Each response C{dict} has a "result" key that indicates the call result, and other
    optional keys for any values returned by the call.

    The conduit provides two methods for each action: one for the sending side and one for
    the receiving side, called "send_{action}" and "recv_{action}", respectively, where
    {action} is the action value.

    The "send_{action}" calls each have a set of arguments specific to the call itself. The
    code takes care of packing that into a C{dict} and sending to the appropriate pod.

    The "recv_{action}" calls take a single C{dict} argument that is the deserialized JSON
    data from the incoming request. The return value is a C{dict} with the result.

    Some simple forms of send_/recv_ methods can be auto-generated to simplify coding.

    Actual implementations of this will be done via mix-ins for the different sub-systems using
    the conduit.
    """

    conduitRequestClass = ConduitRequest

    def __init__(self, store):
        """
        @param store: the L{CommonDataStore} in use.
        """
        self.store = store


    @inlineCallbacks
    def validRequest(self, source_uid, destination_uid):
        """
        Verify that the specified uids are valid for the request and return the
        matching directory records.

        @param source_uid: UID for the user on whose behalf the request is being made
        @type source_uid: C{str}
        @param destination_uid: UID for the user to whom the request is being sent
        @type destination_uid: C{str}

        @return: L{Deferred} resulting in C{tuple} of L{IStoreDirectoryRecord}
        """

        source = yield self.store.directoryService().recordWithUID(source_uid)
        if source is None:
            raise DirectoryRecordNotFoundError("Cross-pod source: {}".format(source_uid))
        if not source.thisServer():
            raise FailedCrossPodRequestError("Cross-pod source not on this server: {}".format(source_uid))

        destination = yield self.store.directoryService().recordWithUID(destination_uid)
        if destination is None:
            raise DirectoryRecordNotFoundError("Cross-pod destination: {}".format(destination_uid))
        if destination.thisServer():
            raise FailedCrossPodRequestError("Cross-pod destination on this server: {}".format(destination_uid))

        returnValue((source, destination,))


    def sendRequest(self, txn, recipient, data, stream=None, streamType=None):
        return self.sendRequestToServer(txn, recipient.server(), data, stream, streamType)


    @inlineCallbacks
    def sendRequestToServer(self, txn, server, data, stream=None, streamType=None):

        request = self.conduitRequestClass(server, data, stream, streamType)
        try:
            response = (yield request.doRequest(txn))
        except Exception as e:
            raise FailedCrossPodRequestError("Failed cross-pod request: {}".format(e))
        returnValue(response)


    @inlineCallbacks
    def processRequest(self, data):
        """
        Process the request.

        @param data: the JSON data to process
        @type data: C{dict}
        """
        # Must have a dict with an "action" key
        try:
            action = data["action"]
        except (KeyError, TypeError) as e:
            log.error("JSON data must have an object as its root with an 'action' attribute: {ex}\n{json}", ex=e, json=data)
            raise FailedCrossPodRequestError("JSON data must have an object as its root with an 'action' attribute: {}\n{}".format(e, data,))

        if action == "ping":
            result = {"result": "ok"}
            returnValue(result)

        method = "recv_{}".format(action.replace("-", "_"))
        if not hasattr(self, method):
            log.error("Unsupported action: {action}", action=action)
            raise FailedCrossPodRequestError("Unsupported action: {}".format(action))

        # Need a transaction to work with
        txn = self.store.newTransaction(repr("Conduit request"))

        # Do the actual request processing
        try:
            result = (yield getattr(self, method)(txn, data))
        except Exception as e:
            yield txn.abort()
            log.error("Failed action: {action}, {ex}", action=action, ex=e)
            raise FailedCrossPodRequestError("Failed action: {}, {}".format(action, e))

        yield txn.commit()

        returnValue(result)
