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

from twext.who.idirectory import (
    RecordType,
    NoSuchRecordError
)
from twext.who.index import (
    DirectoryService as IndexDirectoryService,
    DirectoryRecord as IndexedDirectoryRecord
)
from twext.who.util import ConstantsContainer
from twisted.internet.defer import succeed, inlineCallbacks
from txdav.who.directory import (
    CalendarDirectoryRecordMixin, CalendarDirectoryServiceMixin
)
from txdav.who.idirectory import (
    RecordType as CalRecordType
)


class TestRecord(IndexedDirectoryRecord, CalendarDirectoryRecordMixin):
    pass



class InMemoryDirectoryService(IndexDirectoryService):
    """
    An in-memory IDirectoryService.  You must call updateRecords( ) if you want
    to populate this service.
    """

    recordType = ConstantsContainer(
        (
            RecordType.user,
            RecordType.group,
            CalRecordType.location,
            CalRecordType.resource,
            CalRecordType.address
        )
    )


    def loadRecords(self):
        pass


    @inlineCallbacks
    def updateRecords(self, records, create=False):
        recordsByUID = dict(((record.uid, record) for record in records))
        if not create:
            # Make sure all the records already exist
            for uid, _ignore_record in recordsByUID.items():
                if uid not in self._index[self.fieldName.uid]:
                    raise NoSuchRecordError(uid)

        yield self.removeRecords(recordsByUID.keys())
        self.indexRecords(records)


    def removeRecords(self, uids):
        index = self._index
        for fieldName in self.indexedFields:
            for recordSet in index[fieldName].itervalues():
                for record in list(recordSet):
                    if record.uid in uids:
                        recordSet.remove(record)
        return succeed(None)



class CalendarInMemoryDirectoryService(
    InMemoryDirectoryService,
    CalendarDirectoryServiceMixin
):
    pass
