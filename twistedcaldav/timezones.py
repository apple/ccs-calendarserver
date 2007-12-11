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

from twistedcaldav.ical import Component

from vobject.icalendar import getTzid
from vobject.icalendar import registerTzid

import os
import vobject

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

class TimezoneException(Exception):
    pass

class TimezoneCache(object):
    
    def __init__(self, dirname):
        """
        
        @param dirname: the directory that is the root of the Olson data.
        @type dirname: str
        """
        
        assert os.path.exists(dirname), "Timezone directory %s does not exist." % (dirname,)
        assert os.path.isdir(dirname), "%s is not a directory." % (dirname,)
        assert os.path.exists(os.path.join(dirname, "America/New_York.ics")), "Timezone directory %s does not seem to contain timezones" % (dirname,)
        self.dirname = dirname

        self.caching = False
        self.register()

    def register(self):
        self.vobjectRegisterTzid = registerTzid
        vobject.icalendar.registerTzid = self.registerTzidFromCache
    
    def unregister(self):
        vobject.icalendar.registerTzid = self.vobjectRegisterTzid

    def loadTimezone(self, tzid):
        
        # Make sure it is not already loaded
        if getTzid(tzid) != None:
            return False

        tzpath = os.path.join(self.dirname, tzid) + ".ics"
        if not os.path.exists(tzpath):
            raise TimezoneException("Timezone path %s missing" % (tzpath,))
        
        calendar = Component.fromStream(file(tzpath))
        if calendar.name() != "VCALENDAR":
            raise TimezoneException("%s does not contain valid iCalendar data." % (tzpath,))

        # Check that we now have it cached
        if getTzid(tzid) == None:
            raise TimezoneException("Could not read timezone %s from %s." % (tzid, tzpath,))
        
        return True

    def registerTzidFromCache(self, tzid, tzinfo):
        
        if not self.caching:
            self.caching = True
            self.loadTimezone(tzid)
            self.caching = False
        else:
            self.vobjectRegisterTzid(tzid, tzinfo)
