##
# Copyright (c) 2006-2011 Apple Inc. All rights reserved.
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

from twistedcaldav.config import config

from pycalendar.timezonedb import PyCalendarTimezoneDatabase

log = Logger()

"""
Timezone caching.

We need to use our own full definitions of iCalendar VTIMEZONEs as some clients only
send partial VTIMEZONE objects. Since PyCalendar caches the first VTIMEZONE TZID it sees,
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
    def _getPackageDBPath():
        try:
            import pkg_resources
        except ImportError:
            return os.path.join(os.path.dirname(__file__), "zoneinfo")
        else:
            return pkg_resources.resource_filename("twistedcaldav", "zoneinfo") #@UndefinedVariable

    @staticmethod
    def getDBPath():
        if TimezoneCache.dirName is None:
            if config.TimezoneService.Enabled and config.TimezoneService.BasePath:
                TimezoneCache.dirName = config.TimezoneService.BasePath
            else:
                TimezoneCache.dirName = TimezoneCache._getPackageDBPath()
        
        return TimezoneCache.dirName

    @staticmethod
    def create(dbpath=None):
        TimezoneCache.dirName = dbpath
        PyCalendarTimezoneDatabase.createTimezoneDatabase(TimezoneCache.getDBPath())
    
    @staticmethod
    def clear():
        PyCalendarTimezoneDatabase.clearTimezoneDatabase()

# zoneinfo never changes in a running instance so cache all this data as we use it
cachedTZs = {}
cachedVTZs = {}
cachedTZIDs = []

def hasTZ(tzid):
    """
    Check if the specified TZID is available. Try to load it if not and raise if it
    cannot be found.
    """

    if tzid not in cachedVTZs:
        readVTZ(tzid)
    return True

def readVTZ(tzid):
    """
    Try to load the specified TZID as a calendar object from the database. Raise if not found.
    """

    if tzid not in cachedVTZs:
        
        tzcal = PyCalendarTimezoneDatabase.getTimezoneInCalendar(tzid)
        if tzcal:
            cachedVTZs[tzid] = tzcal
        else:
            raise TimezoneException("Unknown time zone: %s" % (tzid,))
        
    return cachedVTZs[tzid]

def readTZ(tzid):
    """
    Try to load the specified TZID as text from the database. Raise if not found.
    """

    if tzid not in cachedTZs:
        
        tzcal = readVTZ(tzid)
        if tzcal:
            cachedTZs[tzid] = str(tzcal)
        else:
            raise TimezoneException("Unknown time zone: %s" % (tzid,))
        
    return cachedTZs[tzid]

def listTZs(path=""):
    """
    List all timezones in the database.
    """

    if not path and cachedTZIDs:
        return cachedTZIDs

    result = []
    for item in os.listdir(os.path.join(TimezoneCache.getDBPath(), path)):
        if item.find('.') == -1:
            result.extend(listTZs(os.path.join(path, item)))
        elif item.endswith(".ics"):
            result.append(os.path.join(path, item[:-4]))
            
    if not path:
        cachedTZIDs.extend(result)
    return result
