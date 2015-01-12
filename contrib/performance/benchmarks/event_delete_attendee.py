##
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
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

from contrib.performance import _event_change

def measure(host, port, dtrace, attendeeCount, samples):
    def deleteAttendees(event, i):
        """
        Add C{i} new attendees to the given event.
        """
        for _ignore_n in range(attendeeCount):
            # Find the beginning of an ATTENDEE line
            attendee = event.find('ATTENDEE')
            # And the end of it
            eol = event.find('\n', attendee)
            # And remove it
            event = event[:attendee] + event[eol:]
        return event

    return _event_change.measure(
        host, port, dtrace, attendeeCount, samples, "delete-attendee",
        deleteAttendees, eventPerSample=True)
