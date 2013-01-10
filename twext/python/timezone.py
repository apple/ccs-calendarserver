##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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


from twistedcaldav.config import config
import twistedcaldav.timezones

DEFAULT_TIMEZONE = "America/Los_Angeles"

try:
    from Foundation import NSTimeZone
    def lookupSystemTimezone():
        return NSTimeZone.localTimeZone().name().encode("utf-8")

except:
    def lookupSystemTimezone():
        return ""


def getLocalTimezone():
    """
    Returns the default timezone for the server.  The order of precedence is:
    config.DefaultTimezone, lookupSystemTimezone( ), DEFAULT_TIMEZONE.
    Also, if neither of the first two values in that list are in the timezone
    database, DEFAULT_TIMEZONE is returned.

    @return: The server's local timezone name
    @rtype: C{str}
    """
    if config.DefaultTimezone:
        if twistedcaldav.timezones.hasTZ(config.DefaultTimezone):
            return config.DefaultTimezone

    systemTimezone = lookupSystemTimezone()
    if twistedcaldav.timezones.hasTZ(systemTimezone):
        return systemTimezone

    return DEFAULT_TIMEZONE
