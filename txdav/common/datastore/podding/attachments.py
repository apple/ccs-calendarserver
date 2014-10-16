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


class AttachmentsPoddingConduitMixin(object):
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
        shareeView = objectResource._parentCollection
        request, recipient = yield self._getRequestForResource(actionName, shareeView, objectResource)
        request["rids"] = rids
        request["filename"] = filename

        response = yield self.sendRequest(shareeView._txn, recipient, request, stream, content_type)

        if response["result"] == "ok":
            returnValue(response["value"])
        elif response["result"] == "exception":
            raise namedClass(response["class"])(response["result"])


    @inlineCallbacks
    def recv_add_attachment(self, txn, request):
        """
        Process an addAttachment cross-pod request. Request arguments as per L{send_add_attachment}.

        @param request: request arguments
        @type request: C{dict}
        """

        actionName = "add-attachment"
        _ignore_shareeView, objectResource = yield self._getResourcesForRequest(txn, request, actionName)
        try:
            attachment, location = yield objectResource.addAttachment(
                request["rids"],
                request["streamType"],
                request["filename"],
                request["stream"],
            )
        except Exception as e:
            returnValue({
                "result": "exception",
                "class": ".".join((e.__class__.__module__, e.__class__.__name__,)),
                "request": str(e),
            })

        returnValue({
            "result": "ok",
            "value": (attachment.managedID(), location,),
        })


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
        shareeView = objectResource._parentCollection
        request, recipient = yield self._getRequestForResource(actionName, shareeView, objectResource)
        request["managedID"] = managed_id
        request["filename"] = filename

        response = yield self.sendRequest(shareeView._txn, recipient, request, stream, content_type)

        if response["result"] == "ok":
            returnValue(response["value"])
        elif response["result"] == "exception":
            raise namedClass(response["class"])(response["result"])


    @inlineCallbacks
    def recv_update_attachment(self, txn, request):
        """
        Process an updateAttachment cross-pod request. Request arguments as per L{send_update_attachment}.

        @param request: request arguments
        @type request: C{dict}
        """

        actionName = "update-attachment"
        _ignore_shareeView, objectResource = yield self._getResourcesForRequest(txn, request, actionName)
        try:
            attachment, location = yield objectResource.updateAttachment(
                request["managedID"],
                request["streamType"],
                request["filename"],
                request["stream"],
            )
        except Exception as e:
            returnValue({
                "result": "exception",
                "class": ".".join((e.__class__.__module__, e.__class__.__name__,)),
                "request": str(e),
            })

        returnValue({
            "result": "ok",
            "value": (attachment.managedID(), location,),
        })


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
        shareeView = objectResource._parentCollection
        request, recipient = yield self._getRequestForResource(actionName, shareeView, objectResource)
        request["rids"] = rids
        request["managedID"] = managed_id

        response = yield self.sendRequest(shareeView._txn, recipient, request)

        if response["result"] == "ok":
            returnValue(response["value"])
        elif response["result"] == "exception":
            raise namedClass(response["class"])(response["result"])


    @inlineCallbacks
    def recv_remove_attachment(self, txn, request):
        """
        Process an removeAttachment cross-pod request. Request arguments as per L{send_remove_attachment}.

        @param request: request arguments
        @type request: C{dict}
        """

        actionName = "remove-attachment"
        _ignore_shareeView, objectResource = yield self._getResourcesForRequest(txn, request, actionName)
        try:
            yield objectResource.removeAttachment(
                request["rids"],
                request["managedID"],
            )
        except Exception as e:
            returnValue({
                "result": "exception",
                "class": ".".join((e.__class__.__module__, e.__class__.__name__,)),
                "request": str(e),
            })

        returnValue({
            "result": "ok",
            "value": None,
        })
