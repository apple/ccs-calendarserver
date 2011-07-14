##
# Copyright (c) 2011 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

"""
Benchmark a server's handling of event creation involving an
auto-accept resource.
"""

from itertools import count
from uuid import uuid4
from datetime import datetime, timedelta

from contrib.performance._event_create import (
    makeAttendees, makeVCalendar, measure as _measure)


def makeEvent(i, organizerSequence, attendeeCount):
    base = datetime(2010, 7, 30, 11, 15, 00)
    interval = timedelta(0, 5)
    duration = timedelta(0, 3)
    attendees = makeAttendees(attendeeCount)
    attendees.append(
        'ATTENDEE;CN="Resource 01";CUTYPE=INDIVIDUAL;PARTSTAT=NEEDS-ACTION;RSVP=T\n'
        ' RUE;SCHEDULE-STATUS="1.2":urn:uuid:resource01\n')
    return makeVCalendar(
        uuid4(), 
        base + i * interval,
        base + i * interval + duration,
        None,
        organizerSequence,
        attendees)


def measure(host, port, dtrace, attendeeCount, samples):
    calendar = "event-autoaccept-creation-benchmark"
    organizerSequence = 1

    # An infinite stream of VEVENTs to PUT to the server.
    events = ((i, makeEvent(i, organizerSequence, attendeeCount)) for i in count(2))

    return _measure(
        calendar, organizerSequence, events,
        host, port, dtrace, samples)
