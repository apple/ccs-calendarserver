##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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

from caldavclientlibrary.protocol.http.data.string import ResponseDataString
from caldavclientlibrary.protocol.webdav.definitions import davxml, statuscodes, \
    headers
from caldavclientlibrary.protocol.webdav.propfind import PropFind
from contrib.performance.sqlusage.requests.httpTests import HTTPTestBase

class PropfindTest(HTTPTestBase):
    """
    A propfind operation
    """

    def __init__(self, label, sessions, logFilePath, depth=1):
        super(PropfindTest, self).__init__(label, sessions, logFilePath)
        self.depth = headers.Depth1 if depth == 1 else headers.Depth0


    def doRequest(self):
        """
        Execute the actual HTTP request.
        """
        props = (
            davxml.getetag,
            davxml.getcontenttype,
        )

        # Create WebDAV propfind
        request = PropFind(self.sessions[0], self.sessions[0].calendarHref, self.depth, props)
        result = ResponseDataString()
        request.setOutput(result)

        # Process it
        self.sessions[0].runSession(request)

        # If its a 207 we want to parse the XML
        if request.getStatusCode() == statuscodes.MultiStatus:
            pass
        else:
            raise RuntimeError("Propfind request failed: %s" % (request.getStatusCode(),))
