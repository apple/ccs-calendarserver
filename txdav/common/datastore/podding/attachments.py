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


class AttachmentsConduitMixin(object):
    """
    Defines the cross-pod API for managed attachments that will be mixed into the
    L{PoddingConduit} class.
    """

    @inlineCallbacks
    def send_add_attachment(self, objectResource, rids, content_type, filename, stream):
        """
        Managed attachment addAttachment call.

        @param objectResource: child resource having an attachment added
        @type objectResource: L{CalendarObject}
        @param rids: list of recurrence ids
        @type rids: C{list}
        @param content_type: content type of attachment data
        @type content_type: L{MimeType}
        @param filename: name of attachment
        @type filename: C{str}
        @param stream: attachment data stream
        @type stream: L{IStream}
        """

        actionName = "add-attachment"
        txn, request, server = yield self._getRequestForStoreObject(actionName, objectResource, False)
        request["rids"] = rids
        request["filename"] = filename

        response = yield self.sendRequestToServer(txn, server, request, stream, content_type)
        returnValue(response)


    @inlineCallbacks
    def recv_add_attachment(self, txn, request):
        """
        Process an addAttachment cross-pod request. Request arguments as per L{send_add_attachment}.

        @param request: request arguments
        @type request: C{dict}
        """

        objectResource, _ignore = yield self._getStoreObjectForRequest(txn, request)
        attachment, location = yield objectResource.addAttachment(
            request["rids"],
            request["streamType"],
            request["filename"],
            request["stream"],
        )

        returnValue((attachment.managedID(), location,))


    @inlineCallbacks
    def send_update_attachment(self, objectResource, managed_id, content_type, filename, stream):
        """
        Managed attachment updateAttachment call.

        @param objectResource: child resource having an attachment added
        @type objectResource: L{CalendarObject}
        @param managed_id: managed-id to update
        @type managed_id: C{str}
        @param content_type: content type of attachment data
        @type content_type: L{MimeType}
        @param filename: name of attachment
        @type filename: C{str}
        @param stream: attachment data stream
        @type stream: L{IStream}
        """

        actionName = "update-attachment"
        txn, request, server = yield self._getRequestForStoreObject(actionName, objectResource, False)
        request["managedID"] = managed_id
        request["filename"] = filename

        response = yield self.sendRequestToServer(txn, server, request, stream, content_type)
        returnValue(response)


    @inlineCallbacks
    def recv_update_attachment(self, txn, request):
        """
        Process an updateAttachment cross-pod request. Request arguments as per L{send_update_attachment}.

        @param request: request arguments
        @type request: C{dict}
        """

        objectResource, _ignore = yield self._getStoreObjectForRequest(txn, request)
        attachment, location = yield objectResource.updateAttachment(
            request["managedID"],
            request["streamType"],
            request["filename"],
            request["stream"],
        )

        returnValue((attachment.managedID(), location,))


    @inlineCallbacks
    def send_remove_attachment(self, objectResource, rids, managed_id):
        """
        Managed attachment removeAttachment call.

        @param objectResource: child resource having an attachment added
        @type objectResource: L{CalendarObject}
        @param rids: list of recurrence ids
        @type rids: C{list}
        @param managed_id: managed-id to update
        @type managed_id: C{str}
        """

        actionName = "remove-attachment"
        txn, request, server = yield self._getRequestForStoreObject(actionName, objectResource, False)
        request["rids"] = rids
        request["managedID"] = managed_id

        yield self.sendRequestToServer(txn, server, request)


    @inlineCallbacks
    def recv_remove_attachment(self, txn, request):
        """
        Process an removeAttachment cross-pod request. Request arguments as per L{send_remove_attachment}.

        @param request: request arguments
        @type request: C{dict}
        """

        objectResource, _ignore = yield self._getStoreObjectForRequest(txn, request)
        yield objectResource.removeAttachment(
            request["rids"],
            request["managedID"],
        )
