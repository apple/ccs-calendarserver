##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
Extensions to web2.dav
"""

__all__ = [
    "DAVResource",
    "DAVFile",
    "ReadOnlyResourceMixIn",
]

from twisted.web2 import responsecode
from twisted.web2.http import HTTPError
from twisted.web2.dav.http import StatusResponse

import twisted.web2.dav.resource
import twisted.web2.dav.static

class DAVResource (twisted.web2.dav.resource.DAVResource):
    """
    Extended L{twisted.web2.dav.resource.DAVResource} implementation.
    """

class DAVFile (twisted.web2.dav.static.DAVFile):
    """
    Extended L{twisted.web2.dav.static.DAVFile} implementation.
    """

class ReadOnlyResourceMixIn (object):
    """
    Read only resource.
    """
    readOnlyResponse = StatusResponse(
        responsecode.FORBIDDEN,
        "Resource is read only."
    )

    def _forbidden(self, request):
        return self.readOnlyResponse

    http_DELETE    = _forbidden
    http_MOVE      = _forbidden
    http_PROPPATCH = _forbidden
    http_PUT       = _forbidden

    def writeProperty(self, property, request):
        raise HTTPError(self.readOnlyResponse)
