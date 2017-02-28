# coding=utf-8
##
# Copyright (c) 2005-2017 Apple Inc. All rights reserved.
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

from calendarserver.tools.trash import listTrashedEventsForPrincipal, listTrashedCollectionsForPrincipal, restoreTrashedEvent

from twistedcaldav.config import config
from txdav.xml import element
from txdav.base.propertystore.base import PropertyName
from txdav.common.datastore.test.test_trash import TrashTestsBase
from twistedcaldav.ical import Component


class TrashTool(TrashTestsBase):
    """
    Test trash tool.
    """

    @inlineCallbacks
    def setUp(self):
        yield super(TrashTool, self).setUp()
        self.patch(config, "EnableTrashCollection", True)

    @inlineCallbacks
    def test_trashEventWithNonAsciiSummary(self):
        """
        Test that non-ascii summary does not cause any problems.
        """

        data1 = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//CALENDARSERVER.ORG//NONSGML Version 1//EN
BEGIN:VEVENT
UID:5CE3B280-DBC9-4E8E-B0B2-996754020E5F
DTSTART;TZID=America/Los_Angeles:20141108T093000
DTEND;TZID=America/Los_Angeles:20141108T103000
CREATED:20141106T192546Z
DTSTAMP:20141106T192546Z
RRULE:FREQ=DAILY
SEQUENCE:0
SUMMARY:repeating évent
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
"""

        txn = self.store.newTransaction()
        calendar = yield self._collectionForUser(txn, "user01", "tést-calendar", create=True)
        calendar.properties()[PropertyName.fromElement(element.DisplayName)] = element.DisplayName.fromString("tést-calendar-name")

        yield calendar.createObjectResourceWithName(
            "tést-resource.ics",
            Component.allFromString(data1)
        )
        yield txn.commit()

        txn = self.store.newTransaction()
        resource = yield self._getResource(txn, "user01", "tést-calendar", "tést-resource.ics")
        objID = resource._resourceID
        yield resource.remove()
        names = yield self._getTrashNames(txn, "user01")
        self.assertEquals(len(names), 1)
        yield txn.commit()

        yield listTrashedCollectionsForPrincipal(None, self.store, "user01")
        yield listTrashedEventsForPrincipal(None, self.store, "user01")
        yield restoreTrashedEvent(None, self.store, "user01", objID)
