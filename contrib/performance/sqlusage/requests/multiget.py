##
# Copyright (c) 2012-2015 Apple Inc. All rights reserved.
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

from caldavclientlibrary.protocol.caldav.definitions import caldavxml
from caldavclientlibrary.protocol.caldav.multiget import Multiget
from caldavclientlibrary.protocol.http.data.string import ResponseDataString
from caldavclientlibrary.protocol.webdav.definitions import davxml, statuscodes
from contrib.performance.sqlusage.requests.httpTests import HTTPTestBase
from txweb2.dav.util import joinURL

class MultigetTest(HTTPTestBase):
    """
    A multiget operation
    """

    def __init__(self, label, sessions, logFilePath, logFilePrefix, count):
        super(MultigetTest, self).__init__(label, sessions, logFilePath, logFilePrefix)
        self.count = count


    def doRequest(self):
        """
        Execute the actual HTTP request.
        """
        hrefs = [joinURL(self.sessions[0].calendarHref, "%d.ics" % (i + 1,)) for i in range(self.count)]
        props = (
            davxml.getetag,
            caldavxml.calendar_data,
            caldavxml.schedule_tag,
        )

        # Create CalDAV multiget
        request = Multiget(self.sessions[0], self.sessions[0].calendarHref, hrefs, props)
        result = ResponseDataString()
        request.setOutput(result)

        # Process it
        self.sessions[0].runSession(request)

        # If its a 207 we want to parse the XML
        if request.getStatusCode() == statuscodes.MultiStatus:
            pass
        else:
            raise RuntimeError("Muliget request failed: %s" % (request.getStatusCode(),))
