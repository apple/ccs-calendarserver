##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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

from twisted.internet.defer import succeed

__all__ = ["DirectoryReverseProxyResource"]

class DirectoryReverseProxyResource(ReverseProxyResource):

    def __init__(self, parent, record):
        self.parent = parent
        self.record = record

        super(DirectoryReverseProxyResource, self).__init__(self.record.serverID)


    def url(self):
        return joinURL(self.parent.url(), self.record.uid)


    def hasQuota(self, request):
        return succeed(False)


    def hasQuotaRoot(self, request):
        return succeed(False)


    def quotaRootResource(self, request):
        """
        Return the quota root for this resource.

        @return: L{DAVResource} or C{None}
        """

        return succeed(None)


    def checkPrivileges(
        self, request, privileges, recurse=False,
        principal=None, inherited_aces=None
    ):
        return succeed(None)


    def hasProperty(self, property, request):
        return succeed(False)
