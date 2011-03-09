##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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

import os

from twext.python.log import Logger

from pycalendar.timezonedb import PyCalendarTimezoneDatabase

log = Logger()

"""
Timezone caching.

We need to use our own full definitions of iCalendar VTIMEZONEs as some clients only
send partial VTIMEZONE objects. Since vObject caches the first VTIMEZONE TZID it sees,
if the cached one is partial that will result in incorrect UTC offsets for events outside
of the time range covered by that partial VTIMEZONE.

What we will do is take VTIMEZONE data derived from the Olson database and use an on-demand
cache mechanism to use those timezone definitions instead of ones from client supplied
calendar data.
"""

__all__ = [
    "TimezoneException",
    "TimezoneCache",
    "readTZ",
    "listTZs",
]

class TimezoneException(Exception):
    pass

class TimezoneCache(object):
    
    dirName = None

    @staticmethod
    def _getDBPath():
        if TimezoneCache.dirName is None:
            try:
                import pkg_resources
            except ImportError:
                TimezoneCache.dirName = os.path.join(os.path.dirname(__file__), "zoneinfo")
            else:
                TimezoneCache.dirName = pkg_resources.resource_filename("twistedcaldav", "zoneinfo")
        
        return TimezoneCache.dirName

    @staticmethod
    def create(dbpath=None):
        PyCalendarTimezoneDatabase.createTimezoneDatabase(TimezoneCache._getDBPath() if dbpath is None else dbpath)
    
    @staticmethod
    def clear():
        PyCalendarTimezoneDatabase.clearTimezoneDatabase()

# zoneinfo never changes in a running instance so cache all this data as we use it
cachedTZs = {}
cachedTZIDs = []

def readTZ(tzid):

    if tzid not in cachedTZs:
        
        tzcal = PyCalendarTimezoneDatabase.getTimezoneInCalendar(tzid)
        if tzcal:
            cachedTZs[tzid] = str(tzcal)
        else:
            raise TimezoneException("Unknown time zone: %s" % (tzid,))
        
    return cachedTZs[tzid]

def listTZs(path=""):
    if not path and cachedTZIDs:
        return cachedTZIDs

    result = []
    for item in os.listdir(os.path.join(TimezoneCache._getDBPath(), path)):
        if item.find('.') == -1:
            result.extend(listTZs(os.path.join(path, item)))
        elif item.endswith(".ics"):
            result.append(os.path.join(path, item[:-4]))
            
    if not path:
        cachedTZIDs.extend(result)
    return result
