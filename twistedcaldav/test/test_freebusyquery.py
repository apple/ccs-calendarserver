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

from twistedcaldav.ical import Component
from twisted.trial.unittest import SkipTest

import os

from twext.python.filepath import CachingFilePath as FilePath

from txweb2 import responsecode
from txweb2.iweb import IResponse
from txweb2.stream import MemoryStream

from txweb2.test.test_server import SimpleRequest

import twistedcaldav.test.util
from twistedcaldav import caldavxml

from twisted.internet.defer import inlineCallbacks, returnValue
from twistedcaldav.test.test_calendarquery import addEventsDir

class FreeBusyQuery (twistedcaldav.test.util.TestCase):
    """
    free-busy-query REPORT
    """
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    holidays_dir = os.path.join(data_dir, "Holidays")

    def test_free_busy_basic(self):
        """
        Free-busy on plain events.
        (CalDAV-access-09, section 7.8)
        """
        raise SkipTest("test unimplemented")


    def test_free_busy_recurring(self):
        """
        Free-busy on recurring events.
        (CalDAV-access-09, section 7.8)
        """
        raise SkipTest("test unimplemented")


    def test_free_busy_statustransp(self):
        """
        SFree-busy on events with different STATUS/TRANSP property values.
        (CalDAV-access-09, section 7.8)
        """
        raise SkipTest("test unimplemented")


    def test_free_busy_free_busy(self):
        """
        Free-busy on free busy components.
        (CalDAV-access-09, section 7.8)
        """
        raise SkipTest("test unimplemented")


    def simple_free_busy_query(self, cal_uri, start, end):

        query_timerange = caldavxml.TimeRange(
            start=start,
            end=end,
        )

        query = caldavxml.FreeBusyQuery(query_timerange,)

        def got_calendar(calendar):
            pass

        return self.free_busy_query(cal_uri, query, got_calendar)


    @inlineCallbacks
    def free_busy_query(self, calendar_uri, query, got_calendar):

        request = SimpleRequest(self.site, "MKCALENDAR", calendar_uri)
        response = yield self.send(request)
        response = IResponse(response)

        if response.code != responsecode.CREATED:
            self.fail("MKCALENDAR failed: %s" % (response.code,))

        yield addEventsDir(self, FilePath(self.holidays_dir), calendar_uri)

        request = SimpleRequest(self.site, "REPORT", calendar_uri)
        request.stream = MemoryStream(query.toxml())
        response = yield self.send(request)
        response = IResponse(response)

        if response.code != responsecode.OK:
            self.fail("REPORT failed: %s" % (response.code,))

        result = yield Component.fromIStream(response.stream).addCallback(
            got_calendar
        )
        returnValue(result)
