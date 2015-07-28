# -*- test-case-name: txdav.caldav.datastore.test.test_sql -*-
##
# Copyright (c) 2013-2015 Apple Inc. All rights reserved.
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
from txdav.caldav.datastore.scheduling.work import ScheduleWork
"""
SQL backend for CalDAV storage when resources are external.
"""

from twisted.internet.defer import inlineCallbacks, returnValue

from twext.python.log import Logger

from txdav.caldav.datastore.scheduling.imip.token import iMIPTokenRecord
from txdav.caldav.datastore.sql import CalendarHome, Calendar, CalendarObject
from txdav.caldav.datastore.sql_attachment import Attachment, AttachmentLink
from txdav.caldav.datastore.sql_directory import GroupAttendeeRecord, GroupShareeRecord
from txdav.caldav.icalendarstore import ComponentUpdateState, ComponentRemoveState
from txdav.common.datastore.sql_directory import GroupsRecord
from txdav.common.datastore.sql_external import CommonHomeExternal, CommonHomeChildExternal, \
    CommonObjectResourceExternal

log = Logger()

class CalendarHomeExternal(CommonHomeExternal, CalendarHome):
    """
    Wrapper for a CalendarHome that is external and only supports a limited set of operations.
    """

    def __init__(self, transaction, homeData):

        CalendarHome.__init__(self, transaction, homeData)
        CommonHomeExternal.__init__(self, transaction, homeData)


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


    @inlineCallbacks
    def getAllAttachments(self):
        """
        Return all the L{Attachment} objects associated with this calendar home.
        Needed during migration.
        """
        raw_results = yield self._txn.store().conduit.send_home_get_all_attachments(self)
        returnValue([Attachment.deserialize(self._txn, attachment) for attachment in raw_results])


    @inlineCallbacks
    def readAttachmentData(self, remote_id, attachment):
        """
        Read the data associated with an attachment associated with this calendar home.
        Needed during migration only.
        """
        stream = attachment.store(attachment.contentType(), attachment.name(), migrating=True)
        yield self._txn.store().conduit.send_get_attachment_data(self, remote_id, stream)


    @inlineCallbacks
    def getAttachmentLinks(self):
        """
        Read the attachment<->calendar object mapping data associated with this calendar home.
        Needed during migration only.
        """
        raw_results = yield self._txn.store().conduit.send_home_get_attachment_links(self)
        returnValue([AttachmentLink.deserialize(self._txn, attachment) for attachment in raw_results])


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


    @inlineCallbacks
    def getAllGroupAttendees(self):
        """
        Return a list of L{GroupAttendeeRecord},L{GroupRecord} for each group attendee referenced in calendar data
        owned by this home.
        """

        raw_results = yield self._txn.store().conduit.send_home_get_all_group_attendees(self)
        returnValue([(GroupAttendeeRecord.deserialize(item[0]), GroupsRecord.deserialize(item[1]),) for item in raw_results])


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


    @inlineCallbacks
    def iMIPTokens(self):
        results = yield self._txn.store().conduit.send_home_imip_tokens(self)
        returnValue(map(iMIPTokenRecord.deserialize, results))


    def pauseWork(self):
        return self._txn.store().conduit.send_home_pause_work(self)


    def unpauseWork(self):
        return self._txn.store().conduit.send_home_unpause_work(self)


    @inlineCallbacks
    def workItems(self):
        results = yield self._txn.store().conduit.send_home_work_items(self)
        workItems = []
        for workType, records in results.items():
            workClass = ScheduleWork.classForWorkType(workType)
            if workClass is not None:
                for record in records:
                    workItems.append(workClass.deserialize(record))
        returnValue(workItems)



class CalendarExternal(CommonHomeChildExternal, Calendar):
    """
    SQL-based implementation of L{ICalendar}.
    """

    @inlineCallbacks
    def groupSharees(self):
        results = yield self._txn.store().conduit.send_homechild_group_sharees(self)
        results["groups"] = [GroupsRecord.deserialize(items) for items in results["groups"]]
        results["sharees"] = [GroupShareeRecord.deserialize(items) for items in results["sharees"]]
        returnValue(results)



class CalendarObjectExternal(CommonObjectResourceExternal, CalendarObject):
    """
    SQL-based implementation of L{ICalendarObject}.
    """

    @classmethod
    def _createInternal(cls, parent, name, component, internal_state, options=None, split_details=None):
        raise AssertionError("CalendarObjectExternal: not supported")


    def _setComponentInternal(self, component, inserting=False, internal_state=ComponentUpdateState.NORMAL, options=None, split_details=None):
        raise AssertionError("CalendarObjectExternal: not supported")


    def _removeInternal(
        self, internal_state=ComponentRemoveState.NORMAL, useTrash=False
    ):
        raise AssertionError("CalendarObjectExternal: not supported")


    @inlineCallbacks
    def addAttachment(self, rids, content_type, filename, stream):
        result = yield self._txn.store().conduit.send_add_attachment(self, rids, content_type, filename, stream)
        managedID, size, location = result
        returnValue((ManagedAttachmentExternal(str(managedID), size), str(location),))


    @inlineCallbacks
    def updateAttachment(self, managed_id, content_type, filename, stream):
        result = yield self._txn.store().conduit.send_update_attachment(self, managed_id, content_type, filename, stream)
        managedID, size, location = result
        returnValue((ManagedAttachmentExternal(str(managedID), size), str(location),))


    @inlineCallbacks
    def removeAttachment(self, rids, managed_id):
        yield self._txn.store().conduit.send_remove_attachment(self, rids, managed_id)
        returnValue(None)



class ManagedAttachmentExternal(object):
    """
    Fake managed attachment object returned from L{CalendarObjectExternal.addAttachment} and
    L{CalendarObjectExternal.updateAttachment}.
    """

    def __init__(self, managedID, size):
        self._managedID = managedID
        self._size = size


    def managedID(self):
        return self._managedID


    def size(self):
        return self._size


CalendarExternal._objectResourceClass = CalendarObjectExternal
