# -*- test-case-name: txdav.caldav.datastore.test.test_sql -*-
##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
SQL backend for CalDAV storage when resources are external.
"""

from twisted.internet.defer import succeed

from twext.python.log import Logger

from txdav.caldav.datastore.sql import CalendarHome, Calendar, CalendarObject
from txdav.common.datastore.sql_external import CommonHomeExternal, CommonHomeChildExternal, \
    CommonObjectResourceExternal

log = Logger()

class CalendarHomeExternal(CommonHomeExternal, CalendarHome):
    """
    Wrapper for a CalendarHome that is external and only supports a limited set of operations.
    """

    def __init__(self, transaction, ownerUID, resourceID):

        CalendarHome.__init__(self, transaction, ownerUID)
        CommonHomeExternal.__init__(self, transaction, ownerUID, resourceID)


    def hasCalendarResourceUIDSomewhereElse(self, uid, ok_object, mode):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def getCalendarResourcesForUID(self, uid):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def calendarObjectWithDropboxID(self, dropboxID):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def getAllDropboxIDs(self):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def getAllAttachmentNames(self):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def getAllManagedIDs(self):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def createdHome(self):
        """
        No children - make this a no-op.
        """
        return succeed(None)


    def splitCalendars(self):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def ensureDefaultCalendarsExist(self):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def setDefaultCalendar(self, calendar, componentType):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def defaultCalendar(self, componentType, create=True):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def isDefaultCalendar(self, calendar):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def getDefaultAlarm(self, vevent, timed):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def setDefaultAlarm(self, alarm, vevent, timed):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def getAvailability(self):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def setAvailability(self, availability):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")



class CalendarExternal(CommonHomeChildExternal, Calendar):
    """
    SQL-based implementation of L{ICalendar}.
    """
    pass



class CalendarObjectExternal(CommonObjectResourceExternal, CalendarObject):
    """
    SQL-based implementation of L{ICalendar}.
    """
    pass
