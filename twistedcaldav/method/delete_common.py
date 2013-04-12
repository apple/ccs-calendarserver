##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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


"""
CalDAV DELETE behaviors.
"""

__all__ = ["DeleteResource"]

from twisted.internet.defer import inlineCallbacks, returnValue

from twext.python.log import Logger

log = Logger()

class DeleteResource(object):

    def __init__(self, request, resource, resource_uri, parent, depth,
        internal_request=False, allowImplicitSchedule=True):

        raise AssertionError("Never use this")

        self.request = request
        self.resource = resource
        self.resource_uri = resource_uri
        self.parent = parent
        self.depth = depth
        self.internal_request = internal_request
        self.allowImplicitSchedule = allowImplicitSchedule


    @inlineCallbacks
    def run(self):
        # FIXME: this code-path shouldn't actually be used, as the things
        # with storeRemove on them also have their own http_DELETEs.
        response = (
            yield self.resource.storeRemove(
                self.request,
                not self.internal_request and self.allowImplicitSchedule,
                self.resource_uri
            )
        )

        returnValue(response)
