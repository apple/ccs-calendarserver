##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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
Benchmark a change in the date boundaries of an event.
"""


import datetime

from contrib.performance import _event_change

TIME_FORMAT = '%Y%m%dT%H%M%S'

def _increment(event, marker, amount):
    # Find the last occurrence of the marker
    dtstart = event.rfind(marker)
    # Find the end of that line
    eol = event.find('\n', dtstart)
    # Find the : preceding the date on that line
    colon = event.find(':', dtstart)
    # Replace the text between the colon and the eol with the new timestamp
    old = datetime.datetime.strptime(event[colon + 1:eol], TIME_FORMAT)
    new = old + amount
    return event[:colon + 1] + new.strftime(TIME_FORMAT) + event[eol:]



def replaceTimestamp(event, i):
    offset = datetime.timedelta(hours=i)
    return _increment(
        _increment(event, 'DTSTART', offset),
        'DTEND', offset)



def measure(host, port, dtrace, attendeeCount, samples):
    return _event_change.measure(
        host, port, dtrace, attendeeCount, samples, "change-date",
        replaceTimestamp)
