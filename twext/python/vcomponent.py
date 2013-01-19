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
iCalendar utilities
"""

__all__ = [
    "VComponent",
    "VProperty",
    "InvalidICalendarDataError",
]

# FIXME: Move twistedcaldav.ical here, but that module needs some
# cleanup first.  Perhaps after porting to libical?

from twistedcaldav.ical import Component as VComponent
from twistedcaldav.ical import Property as VProperty
from twistedcaldav.ical import InvalidICalendarDataError
