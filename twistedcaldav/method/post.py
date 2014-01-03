# #
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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
# #


"""
CalDAV POST method.
"""

__all__ = ["http_POST"]

from txweb2 import responsecode
from txweb2.http import StatusResponse

from twisted.internet.defer import inlineCallbacks, returnValue

from twistedcaldav.config import config

@inlineCallbacks
def http_POST(self, request):

    # POST can support many different APIs

    # First look at query params
    if request.params:
        if request.params == "add-member":
            if config.EnableAddMember and hasattr(self, "POST_handler_add_member"):
                result = (yield self.POST_handler_add_member(request))
                returnValue(result)

    # Look for query arguments
    if request.args:
        action = request.args.get("action", ("",))
        if len(action) == 1:
            action = action[0]
            if action in ("attachment-add", "attachment-update", "attachment-remove") and \
                hasattr(self, "POST_handler_attachment"):
                if config.EnableManagedAttachments:
                    result = (yield self.POST_handler_attachment(request, action))
                    returnValue(result)
                else:
                    returnValue(StatusResponse(responsecode.FORBIDDEN, "Managed Attachments not supported."))

    # Content-type handlers
    contentType = request.headers.getHeader("content-type")
    if contentType:
        if hasattr(self, "POST_handler_content_type"):
            result = (yield self.POST_handler_content_type(request, (contentType.mediaType, contentType.mediaSubtype)))
            returnValue(result)

    returnValue(responsecode.FORBIDDEN)
