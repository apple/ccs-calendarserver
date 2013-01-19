##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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
Tests for L{txdav.caldav.datastore.scheduling}.

The aforementioned module is intended to eventually support implicit
scheduling; however, it does not currently.  The interim purpose of this module
and accompanying tests is to effectively test the interface specifications to
make sure that the common tests don't require anything I{not} specified in the
interface, so that dynamic proxies specified with a tool like
C{proxyForInterface} can be used to implement features such as implicit
scheduling or data caching as middleware in the data-store layer.
"""

from twisted.trial.unittest import TestCase, SkipTest
from txdav.caldav.datastore.test.test_file import FileStorageTests
from txdav.caldav.datastore.scheduling import ImplicitStore

simpleEvent = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:12345-67890
DTSTART:20080601T120000Z
DTEND:20080601T130000Z
ORGANIZER:mailto:user1@example.com
ATTENDEE:mailto:user1@example.com
ATTENDEE:mailto:user2@example.com
END:VEVENT
END:VCALENDAR
"""

class ImplicitStoreTests(FileStorageTests, TestCase):
    """
    Tests for L{ImplicitSchedulingStore}.
    """

    implicitStore = None

    def storeUnderTest(self):
        if self.implicitStore is None:
            sut = super(ImplicitStoreTests, self).storeUnderTest()
            self.implicitStore = ImplicitStore(sut)
        return self.implicitStore

    def skipit(self):
        raise SkipTest("No private attribute tests.")

    test_calendarObjectsWithDotFile = skipit
    test_countComponentTypes = skipit
    test_init = skipit
    test_calendarObjectsWithDirectory = skipit
    test_hasCalendarResourceUIDSomewhereElse = skipit

del FileStorageTests
