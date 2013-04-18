##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks
from twext.python.filepath import CachingFilePath as FilePath
from twext.web2 import responsecode
from twext.web2.iweb import IResponse
from twext.web2.stream import MemoryStream, FileStream
from twext.web2.http_headers import MimeType

from twistedcaldav.ical import Component
from twistedcaldav.memcachelock import MemcacheLock
from twistedcaldav.memcacher import Memcacher
from twistedcaldav.method.put_common import StoreCalendarObjectResource


from twistedcaldav.test.util import StoreTestCase, SimpleStoreRequest
from twext.web2.dav.util import joinURL

class CollectionContents(StoreTestCase):
    """
    PUT request
    """

    dataPath = FilePath(__file__).sibling("data")

    def setUp(self):
        # Need to fake out memcache
        def _getFakeMemcacheProtocol(self):
            result = super(MemcacheLock, self)._getMemcacheProtocol()
            if isinstance(result, Memcacher.nullCacher):
                result = self._memcacheProtocol = Memcacher.memoryCacher()
            return result

        self.patch(MemcacheLock, "_getMemcacheProtocol",
                   _getFakeMemcacheProtocol)

        # Need to not do implicit behavior during these tests
        def _fakeDoImplicitScheduling(self):
            return False, False, False

        self.patch(StoreCalendarObjectResource , "doImplicitScheduling",
                   _fakeDoImplicitScheduling)

        # Tests in this suite assume that the root resource is a calendar home.
        # FIXME: there should be a centralized way of saying 'make this look
        # like a calendar home'
        return super(CollectionContents, self).setUp()


    def test_collection_in_calendar(self):
        """
        Make (regular) collection in calendar
        """
        calendar_uri = "/calendars/users/wsanchez/collection_in_calendar/"

        def mkcalendar_cb(response):
            response = IResponse(response)

            if response.code != responsecode.CREATED:
                self.fail("MKCALENDAR failed: %s" % (response.code,))

            def mkcol_cb(response):
                response = IResponse(response)

                if response.code != responsecode.FORBIDDEN:
                    self.fail("Incorrect response to nested MKCOL: %s" % (response.code,))

            nested_uri = joinURL(calendar_uri, "nested")

            request = SimpleStoreRequest(self, "MKCOL", nested_uri, authid="wsanchez")
            return self.send(request, mkcol_cb)

        request = SimpleStoreRequest(self, "MKCALENDAR", calendar_uri, authid="wsanchez")
        return self.send(request, mkcalendar_cb)


    def test_bogus_file(self):
        """
        Bogus file in calendar collection
        """

        # FIXME: Should FileStream be OK here?
        # FIXME: Should FileStream be OK here?
        dst_file = file(__file__)
        self.addCleanup(dst_file.close)
        stream = FileStream(dst_file)
        return self._test_file_in_calendar("bogus file in calendar", (stream, responsecode.FORBIDDEN))


    def openHolidays(self):
        """
        Open the 'Holidays.ics' calendar.

        @return: an open file pointing at the start of Holidays.ics

        @rtype: C{file}
        """
        f = self.dataPath.child("Holidays.ics").open()
        self.addCleanup(f.close)
        return f


    def test_monolithic_ical(self):
        """
        Monolithic iCalendar file in calendar collection
        """
        # FIXME: Should FileStream be OK here?
        dst_file = self.openHolidays()
        stream = FileStream(dst_file)
        return self._test_file_in_calendar("monolithic iCalendar file in calendar", (stream, responsecode.FORBIDDEN))


    def test_single_events(self):
        """
        Single events in calendar collection
        """
        work = []

        stream = self.openHolidays()
        calendar = Component.fromStream(stream)

        for subcomponent in calendar.subcomponents():
            if subcomponent.name() == "VEVENT":
                subcalendar = Component("VCALENDAR")
                subcalendar.addComponent(subcomponent)
                for property in calendar.properties():
                    subcalendar.addProperty(property)
                work.append((MemoryStream(str(subcalendar)), responsecode.CREATED))

        return self._test_file_in_calendar("single event in calendar", *work)


    def test_duplicate_uids(self):
        """
        Mutiple resources with the same UID.
        """
        stream = self.dataPath.child(
            "Holidays").child(
            "C318AA54-1ED0-11D9-A5E0-000A958A3252.ics").open()
        try:
            calendar = str(Component.fromStream(stream))
        finally:
            stream.close()

        return self._test_file_in_calendar(
            "mutiple resources with the same UID",
            (MemoryStream(calendar), responsecode.CREATED),
            (MemoryStream(calendar), responsecode.FORBIDDEN),
        )


    def _test_file_in_calendar(self, what, *work):
        """
        Creates a calendar collection, then PUTs a resource into that collection
        with the data from given stream and verifies that the response code from the
        PUT request matches the given response_code.
        """
        calendar_uri = "/calendars/users/wsanchez/testing_calendar/"


        @inlineCallbacks
        def mkcalendar_cb(response):
            response = IResponse(response)

            if response.code != responsecode.CREATED:
                self.fail("MKCALENDAR failed: %s" % (response.code,))

            c = 0

            for stream, response_code in work:

                dst_uri = joinURL(calendar_uri, "dst%d.ics" % (c,))
                request = SimpleStoreRequest(self, "PUT", dst_uri, authid="wsanchez")
                request.headers.setHeader("if-none-match", "*")
                request.headers.setHeader("content-type", MimeType("text", "calendar"))
                request.stream = stream
                response = yield self.send(request)
                response = IResponse(response)

                if response.code != response_code:
                    self.fail("Incorrect response to %s: %s (!= %s)" % (what, response.code, response_code))

                c += 1

        request = SimpleStoreRequest(self, "MKCALENDAR", calendar_uri, authid="wsanchez")
        return self.send(request, mkcalendar_cb)


    def test_fail_dot_file_put_in_calendar(self):
        """
        Make (regular) collection in calendar
        """
        calendar_uri = "/calendars/users/wsanchez/dot_file_in_calendar/"

        def mkcalendar_cb(response):
            response = IResponse(response)

            if response.code != responsecode.CREATED:
                self.fail("MKCALENDAR failed: %s" % (response.code,))

            def put_cb(response):
                response = IResponse(response)

                if response.code != responsecode.FORBIDDEN:
                    self.fail("Incorrect response to dot file PUT: %s" % (response.code,))

            stream = self.dataPath.child(
                "Holidays").child(
                "C318AA54-1ED0-11D9-A5E0-000A958A3252.ics"
            ).open()
            try:
                calendar = str(Component.fromStream(stream))
            finally:
                stream.close()

            event_uri = "/".join([calendar_uri, ".event.ics"])

            request = SimpleStoreRequest(self, "PUT", event_uri, authid="wsanchez")
            request.headers.setHeader("content-type", MimeType("text", "calendar"))
            request.stream = MemoryStream(calendar)
            return self.send(request, put_cb)

        request = SimpleStoreRequest(self, "MKCALENDAR", calendar_uri, authid="wsanchez")
        return self.send(request, mkcalendar_cb)
