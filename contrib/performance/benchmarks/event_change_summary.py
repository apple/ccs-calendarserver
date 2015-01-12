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

from contrib.performance._event_create import SUMMARY
from contrib.performance._event_change import measure as _measure

def replaceSummary(event, i):
    return event.replace(SUMMARY, 'Replacement summary %d' % (i,))



def measure(host, port, dtrace, attendeeCount, samples):
    return _measure(
        host, port, dtrace, attendeeCount, samples, "change-summary",
        replaceSummary)
