##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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
Benchmark a server's handling of event creation.
"""

from itertools import count

from contrib.performance._event_create import makeEvent, measure as _measure

def measure(host, port, dtrace, attendeeCount, samples):
    calendar = "event-creation-benchmark"
    organizerSequence = 1

    # An infinite stream of VEVENTs to PUT to the server.
    events = ((i, makeEvent(i, organizerSequence, attendeeCount)) for i in count(2))

    return _measure(
        calendar, organizerSequence, events,
        host, port, dtrace, samples)
