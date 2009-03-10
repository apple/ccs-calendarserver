##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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
Extensions to twisted.web2.http
"""

__all__ = [
    "XMLResponse",
]

from twisted.web2.http import Response
from twisted.web2.http_headers import MimeType


class XMLResponse (Response):
    """
    XML L{Response} object.
    Renders itself as an XML document.
    """
    def __init__(self, code, element):
        """
        @param xml_responses: an iterable of davxml.Response objects.
        """
        Response.__init__(self, code, stream=element.toxml())
        self.headers.setHeader("content-type", MimeType("text", "xml"))
