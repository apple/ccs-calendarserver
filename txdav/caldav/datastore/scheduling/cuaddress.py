##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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

from twext.python.log import Logger
from twext.who.directory import DirectoryRecord as BaseDirectoryRecord
from twext.who.idirectory import FieldName as BaseFieldName
from twext.who.idirectory import RecordType as BaseRecordType

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.constants import Names, NamedConstant

from txdav.caldav.datastore.scheduling.utils import extractEmailDomain, \
    uidFromCalendarUserAddress
from txdav.caldav.icalendardirectoryservice import ICalendarStoreDirectoryRecord
from txdav.who.directory import CalendarDirectoryRecordMixin
from txdav.who.idirectory import FieldName

from zope.interface.declarations import implementer

__all__ = [
    "LocalCalendarUser",
    "OtherServerCalendarUser",
    "RemoteCalendarUser",
    "EmailCalendarUser",
    "InvalidCalendarUser",
]

log = Logger()

class CalendarUser(object):

    def __init__(self, cuaddr):
        self.cuaddr = cuaddr


    def hosted(self):
        """
        Is this user hosted on this service (this pod or any other)
        """
        return False


    def validOriginator(self):
        """
        Is this user able to originate scheduling messages.
        """
        return True


    def validRecipient(self):
        """
        Is this user able to receive scheduling messages.
        """
        return True



class HostedCalendarUser(CalendarUser):
    """
    User hosted on any pod of this service. This is derived from an L{DirectoryRecord}
    in most cases. However, we need to cope with the situation where a user has been
    removed from the directory but still has calendar data that needs to be managed
    (typically purged). In that case we there is no directory record, but we can confirm
    from the cu-address that corresponding data for their UID exists, and thus can
    determine the valid UID to use.
    """

    def __init__(self, cuaddr, record):
        self.cuaddr = cuaddr
        self.record = record


    def hosted(self):
        """
        Is this user hosted on this service (this pod or any other)
        """
        return True


    def validOriginator(self):
        """
        Is this user able to originate scheduling messages.
        A user with a temporary directory record can be schedule, but that will
        only be for purposes of automatic purge.
        """
        return self.record.calendarsEnabled()


    def validRecipient(self):
        """
        Is this user able to receive scheduling messages.
        A user with a temporary directory record cannot be scheduled with.
        """
        return self.record.calendarsEnabled() and not isinstance(self.record, TemporaryDirectoryRecord)



class LocalCalendarUser(HostedCalendarUser):
    """
    User hosted on the current pod.
    """

    def __init__(self, cuaddr, record):
        super(LocalCalendarUser, self).__init__(cuaddr, record)


    def __str__(self):
        return "Local calendar user: {}".format(self.cuaddr)



class OtherServerCalendarUser(HostedCalendarUser):
    """
    User hosted on another pod.
    """

    def __init__(self, cuaddr, record):
        super(OtherServerCalendarUser, self).__init__(cuaddr, record)


    def __str__(self):
        return "Other server calendar user: {}".format(self.cuaddr)



class RemoteCalendarUser(CalendarUser):
    """
    User external to the entire system (set of pods). Used for iSchedule.
    """

    def __init__(self, cuaddr):
        super(RemoteCalendarUser, self).__init__(cuaddr)
        self.extractDomain()


    def __str__(self):
        return "Remote calendar user: {}".format(self.cuaddr)


    def extractDomain(self):
        if self.cuaddr.startswith("mailto:"):
            self.domain = extractEmailDomain(self.cuaddr)
        elif self.cuaddr.startswith("http://") or self.cuaddr.startswith("https://"):
            splits = self.cuaddr.split(":")[1][2:].split("/")
            self.domain = splits[0]
        else:
            self.domain = ""



class EmailCalendarUser(CalendarUser):
    """
    User external to the entire system (set of pods). Used for iMIP.
    """

    def __init__(self, cuaddr):
        super(EmailCalendarUser, self).__init__(cuaddr)


    def __str__(self):
        return "Email/iMIP calendar user: {}".format(self.cuaddr)



class InvalidCalendarUser(CalendarUser):
    """
    A calendar user that ought to be hosted on the system, but does not have a valid
    directory entry.
    """

    def __str__(self):
        return "Invalid calendar user: {}".format(self.cuaddr)


    def validOriginator(self):
        """
        Is this user able to originate scheduling messages.
        """
        return False


    def validRecipient(self):
        """
        Is this user able to receive scheduling messages.
        """
        return False



@inlineCallbacks
def calendarUserFromCalendarUserAddress(cuaddr, txn):
    """
    Map a calendar user address into an L{CalendarUser} taking into account whether
    they are hosted in the directory or known to be locally hosted - or match
    address patterns for other services.

    @param cuaddr: the calendar user address to map
    @type cuaddr: L{str}
    @param txn: a transaction to use for store operations
    @type txn: L{ICommonStoreTransaction}
    """

    record = yield txn.directoryService().recordWithCalendarUserAddress(cuaddr)
    returnValue((yield _fromRecord(cuaddr, record, txn)))



@inlineCallbacks
def calendarUserFromCalendarUserUID(uid, txn):
    """
    Map a calendar user address into an L{CalendarUser} taking into account whether
    they are hosted in the directory or known to be locally hosted - or match
    address patterns for other services.

    @param uid: the calendar user UID to map
    @type uid: L{str}
    @param txn: a transaction to use for store operations
    @type txn: L{ICommonStoreTransaction}
    """

    record = yield txn.directoryService().recordWithUID(uid)
    cua = record.canonicalCalendarUserAddress() if record is not None else "urn:x-uid:{}".format(uid)
    returnValue((yield _fromRecord(cua, record, txn)))



class RecordType(Names):
    """
    Constants for temporary directory record type.

    @cvar unknown: Location record.
        Represents a calendar user of unknown type.
    """

    unknown = NamedConstant()
    unknown.description = u"unknown"



@implementer(ICalendarStoreDirectoryRecord)
class TemporaryDirectoryRecord(BaseDirectoryRecord, CalendarDirectoryRecordMixin):

    def __init__(self, service, uid, nodeUID):

        fields = {
            BaseFieldName.uid: uid.decode("utf-8"),
            BaseFieldName.recordType: BaseRecordType.user,
            FieldName.hasCalendars: True,
            FieldName.serviceNodeUID: nodeUID,
        }

        super(TemporaryDirectoryRecord, self).__init__(service, fields)
        self.fields[BaseFieldName.recordType] = RecordType.unknown
        self.fields[BaseFieldName.guid] = uid.decode("utf-8")



@inlineCallbacks
def _fromRecord(cuaddr, record, txn):
    """
    Map a calendar user record into an L{CalendarUser} taking into account whether
    they are hosted in the directory or known to be locally hosted - or match
    address patterns for other services.

    @param cuaddr: the calendar user address to map
    @type cuaddr: L{str}
    @param record: the calendar user record to map or L{None}
    @type record: L{IDirectoryRecord}
    @param txn: a transaction to use for store operations
    @type txn: L{ICommonStoreTransaction}
    """
    if record is not None:
        if not record.calendarsEnabled():
            returnValue(InvalidCalendarUser(cuaddr))
        elif record.thisServer():
            returnValue(LocalCalendarUser(cuaddr, record))
        else:
            returnValue(OtherServerCalendarUser(cuaddr, record))
    else:
        uid = uidFromCalendarUserAddress(cuaddr)
        if uid is not None:
            hosted, serviceNodeUID = yield txn.store().uidInStore(txn, uid)
            if hosted:
                record = TemporaryDirectoryRecord(txn.directoryService(), uid, serviceNodeUID)
                returnValue(LocalCalendarUser(cuaddr, record))

    from txdav.caldav.datastore.scheduling import addressmapping
    result = (yield addressmapping.mapper.getCalendarUser(cuaddr))
    returnValue(result)
