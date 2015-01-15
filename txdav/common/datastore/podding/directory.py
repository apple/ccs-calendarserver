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
from txdav.who.delegates import Delegates


class DirectoryPoddingConduitMixin(object):
    """
    Defines the cross-pod API for common directory operations that will be mixed into the
    L{PoddingConduit} class.
    """

    @inlineCallbacks
    def send_all_group_delegates(self, txn, server):
        """
        Request all group delegates on another pod.

        @param txn: transaction to use
        @type txn: L{CommonStoreTransaction}
        @param server: server to query
        @type server: L{Server}
        """

        request = {
            "action": "all-group-delegates",
        }
        response = yield self.sendRequestToServer(txn, server, request)
        returnValue(set(response))


    @inlineCallbacks
    def recv_all_group_delegates(self, txn, request):
        """
        Process an all group delegates cross-pod request. Request arguments as per L{send_all_group_delegates}.

        @param request: request arguments
        @type request: C{dict}
        """

        delegatedUIDs = yield txn.allGroupDelegates()

        returnValue(list(delegatedUIDs))


    @inlineCallbacks
    def send_set_delegates(self, txn, delegator, delegates, readWrite):
        """
        Set delegates for delegator on another pod.

        @param txn: transaction to use
        @type txn: L{CommonStoreTransaction}
        @param delegator: delegator to set
        @type delegator: L{DirectoryRecord}
        @param delegates: delegates to set
        @type delegates: L{list} of L{DirectoryRecord}
        @param readWrite: if True, read and write access delegates are returned;
            read-only access otherwise
        """
        if delegator.thisServer():
            raise FailedCrossPodRequestError("Cross-pod destination on this server: {}".format(delegator.uid))

        request = {
            "action": "set-delegates",
            "uid": delegator.uid,
            "delegates": [delegate.uid for delegate in delegates],
            "read-write": readWrite,
        }
        yield self.sendRequestToServer(txn, delegator.server(), request)


    @inlineCallbacks
    def recv_set_delegates(self, txn, request):
        """
        Process a set delegates cross-pod request. Request arguments as per L{send_set_delegates}.

        @param request: request arguments
        @type request: C{dict}
        """

        delegator = yield txn.directoryService().recordWithUID(request["uid"])
        if delegator is None or not delegator.thisServer():
            raise FailedCrossPodRequestError("Cross-pod delegate not on this server: {}".format(delegator.uid))

        delegates = []
        for uid in request["delegates"]:
            delegate = yield txn.directoryService().recordWithUID(uid)
            if delegate is None:
                raise FailedCrossPodRequestError("Cross-pod delegate missing on this server: {}".format(uid))
            delegates.append(delegate)

        yield Delegates.setDelegates(txn, delegator, delegates, request["read-write"])


    @inlineCallbacks
    def send_get_delegates(self, txn, delegator, readWrite, expanded=False):
        """
        Get delegates from another pod.

        @param txn: transaction to use
        @type txn: L{CommonStoreTransaction}
        @param delegator: delegator to lookup
        @type delegator: L{DirectoryRecord}
        @param readWrite: if True, read and write access delegates are returned;
            read-only access otherwise
        """
        if delegator.thisServer():
            raise FailedCrossPodRequestError("Cross-pod destination on this server: {}".format(delegator.uid))

        request = {
            "action": "get-delegates",
            "uid": delegator.uid,
            "read-write": readWrite,
            "expanded": expanded,
        }
        response = yield self.sendRequestToServer(txn, delegator.server(), request)
        returnValue(set(response))


    @inlineCallbacks
    def recv_get_delegates(self, txn, request):
        """
        Process an delegates cross-pod request. Request arguments as per L{send_get_delegates}.

        @param request: request arguments
        @type request: C{dict}
        """

        delegator = yield txn.directoryService().recordWithUID(request["uid"])
        if delegator is None or not delegator.thisServer():
            raise FailedCrossPodRequestError("Cross-pod delegate not on this server: {}".format(delegator.uid))

        delegates = yield Delegates._delegatesOfUIDs(txn, delegator, request["read-write"], request["expanded"])

        returnValue(list(delegates))


    @inlineCallbacks
    def send_get_delegators(self, txn, server, delegate, readWrite):
        """
        Get delegators from another pod.

        @param txn: transaction to use
        @type txn: L{CommonStoreTransaction}
        @param server: server to query
        @type server: L{Server}
        @param delegate: delegate to lookup
        @type delegate: L{DirectoryRecord}
        @param readWrite: if True, read and write access delegates are returned;
            read-only access otherwise
        """
        if not delegate.thisServer():
            raise FailedCrossPodRequestError("Cross-pod destination on this server: {}".format(delegate.uid))

        request = {
            "action": "get-delegators",
            "uid": delegate.uid,
            "read-write": readWrite,
        }
        response = yield self.sendRequestToServer(txn, server, request)
        returnValue(set(response))


    @inlineCallbacks
    def recv_get_delegators(self, txn, request):
        """
        Process an delegators cross-pod request. Request arguments as per L{send_get_delegators}.

        @param request: request arguments
        @type request: C{dict}
        """

        delegate = yield txn.directoryService().recordWithUID(request["uid"])
        if delegate is None or delegate.thisServer():
            raise FailedCrossPodRequestError("Cross-pod delegate missing or on this server: {}".format(delegate.uid))

        delegators = yield Delegates._delegatedToUIDs(txn, delegate, request["read-write"], onlyThisServer=True)

        returnValue(list(delegators))
