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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

import os

import vobject
from vobject.icalendar import getTzid
from vobject.icalendar import registerTzid

from twistedcaldav.ical import Component
from twistedcaldav.log import Logger

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
]

class TimezoneException(Exception):
    pass

class TimezoneCache(object):
    
    activeCache = None

    @staticmethod
    def create():
        if TimezoneCache.activeCache is None:
            TimezoneCache.activeCache = TimezoneCache()
            TimezoneCache.activeCache.register()
        
    def __init__(self):
        self._caching = False

    def register(self):
        self.vobjectRegisterTzid = registerTzid
        vobject.icalendar.registerTzid = self.registerTzidFromCache
    
    def unregister(self):
        vobject.icalendar.registerTzid = self.vobjectRegisterTzid

    def loadTimezone(self, tzid):
        # Make sure it is not already loaded
        if getTzid(tzid) != None:
            return False

        tzData = readTZ(tzid)
        calendar = Component.fromString(tzData)

        if calendar.name() != "VCALENDAR":
            raise TimezoneException("%s does not contain valid iCalendar data." % (tzid,))

        # Check that we now have it cached
        if getTzid(tzid) == None:
            raise TimezoneException("Could not read timezone %s from timezone cache." % (tzid,))
        
        return True

    def registerTzidFromCache(self, tzid, tzinfo):
        if not self._caching:
            self._caching = True
            try:
                self.loadTimezone(tzid)
            except TimezoneException:
                # Fallback to vobject processing the actual tzdata
                log.err("Cannot load timezone data for %s from timezone cache" % (tzid,))
                self.vobjectRegisterTzid(tzid, tzinfo)
            self._caching = False
        else:
            self.vobjectRegisterTzid(tzid, tzinfo)

try:
    # zoneinfo never changes in a running instance so cache all this data as we use it
    cachedTZs = {}
    cachedTZIDs = []

    import pkg_resources
except ImportError:
    #
    # We don't have pkg_resources, so assume file paths work, since that's all we have
    #
    
    dirname = os.path.join(os.path.dirname(__file__), "zoneinfo")
    def readTZ(tzid):

        if tzid not in cachedTZs:
            tzpath = os.path.join(*tzid.split("/")) # Don't assume "/" from tzid is a path separator
            tzpath = os.path.join(dirname, tzpath + ".ics")
            try:
                cachedTZs[tzid] = file(tzpath).read()
            except IOError:
                raise TimezoneException("Unknown time zone: %s" % (tzid,))
            
        return cachedTZs[tzid]
        
    def listTZs(path=""):
        if not path and cachedTZIDs:
            return cachedTZIDs

        result = []
        for item in os.listdir(os.path.join(dirname, path)):
            if item.find('.') == -1:
                result.extend(listTZs(os.path.join(path, item)))
            elif item.endswith(".ics"):
                result.append(os.path.join(path, item[:-4]))
                
        if not path:
            cachedTZIDs.extend(result)
        return result
else:
    def readTZ(tzid):
        if tzid not in cachedTZs:
            # Here, "/" is always the path separator
            try:
                cachedTZs[tzid] = pkg_resources.resource_stream("twistedcaldav", "zoneinfo/%s.ics" % (tzid,)).read()
            except IOError:
                raise TimezoneException("Unknown time zone: %s" % (tzid,))
            
        return cachedTZs[tzid]

    def listTZs(path=""):  
        if not path and cachedTZIDs:
            return cachedTZIDs

        result = []
        for item in pkg_resources.resource_listdir("twistedcaldav", os.path.join("zoneinfo", path)):
            if item.find('.') == -1:
                result.extend(listTZs(os.path.join(path, item)))
            elif item.endswith(".ics"):
                result.append(os.path.join(path, item[:-4]))
                
        if not path:
            cachedTZIDs.extend(result)
        return result
