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
Implements a directory-backed principal hierarchy.
"""

from txweb2.dav.util import joinURL

from twistedcaldav.client.reverseproxy import ReverseProxyResource

__all__ = ["DirectoryReverseProxyResource"]

class DirectoryReverseProxyResource(ReverseProxyResource):

    def __init__(self, parent, record):
        self.parent = parent
        self.record = record

        super(DirectoryReverseProxyResource, self).__init__(self.record.serverID)


    def url(self):
        return joinURL(self.parent.url(), self.record.uid)
