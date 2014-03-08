# -*- test-case-name: txdav.carddav.datastore.test -*-
##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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
from twisted.trial.unittest import TestCase
from twext.python.clsprop import classproperty
from twisted.internet.defer import inlineCallbacks, succeed

"""
Store test utility functions
"""

from twistedcaldav.config import config
from txdav.caldav.icalendardirectoryservice import ICalendarStoreDirectoryService, \
    ICalendarStoreDirectoryRecord
from txdav.common.datastore.test.util import TestStoreDirectoryService, \
    TestStoreDirectoryRecord, theStoreBuilder, CommonCommonTests, \
    populateCalendarsFrom
from zope.interface.declarations import implements

class TestCalendarStoreDirectoryService(TestStoreDirectoryService):

    implements(ICalendarStoreDirectoryService)

    def __init__(self):
        super(TestCalendarStoreDirectoryService, self).__init__()
        self.recordsByCUA = {}


    def recordWithCalendarUserAddress(self, cuaddr):
        return succeed(self.recordsByCUA.get(cuaddr))


    def addRecord(self, record):
        super(TestCalendarStoreDirectoryService, self).addRecord(record)
        for cuaddr in record.calendarUserAddresses:
            self.recordsByCUA[cuaddr] = record



class TestCalendarStoreDirectoryRecord(TestStoreDirectoryRecord):

    implements(ICalendarStoreDirectoryRecord)

    def __init__(
        self,
        uid,
        shortNames,
        fullName,
        calendarUserAddresses,
        cutype="INDIVIDUAL",
        thisServer=True,
        server=None,
        extras={},
    ):

        super(TestCalendarStoreDirectoryRecord, self).__init__(uid, shortNames, fullName, thisServer, server, extras=extras)
        self.calendarUserAddresses = calendarUserAddresses
        self.cutype = cutype


    def canonicalCalendarUserAddress(self):
        cua = ""
        for candidate in self.calendarUserAddresses:
            # Pick the first one, but urn:uuid: and mailto: can override
            if not cua:
                cua = candidate
            # But always immediately choose the urn:uuid: form
            if candidate.startswith("urn:uuid:"):
                cua = candidate
                break
            # Prefer mailto: if no urn:uuid:
            elif candidate.startswith("mailto:"):
                cua = candidate
        return cua


    def calendarsEnabled(self):
        return True


    def enabledAsOrganizer(self):
        if self.cutype == "INDIVIDUAL":
            return True
        elif self.recordType == "GROUP":
            return config.Scheduling.Options.AllowGroupAsOrganizer
        elif self.recordType == "ROOM":
            return config.Scheduling.Options.AllowLocationAsOrganizer
        elif self.recordType == "RESOURCE":
            return config.Scheduling.Options.AllowResourceAsOrganizer
        else:
            return False


    def getCUType(self):
        return self.cutype


    def canAutoSchedule(self, organizer):
        return False


    def getAutoScheduleMode(self, organizer):
        return "automatic"


    def isProxyFor(self, other):
        return succeed(False)



def buildDirectory(homes=None):

    directory = TestCalendarStoreDirectoryService()

    # User accounts
    for ctr in range(1, 100):
        directory.addRecord(TestCalendarStoreDirectoryRecord(
            "user%02d" % (ctr,),
            ("user%02d" % (ctr,),),
            "User %02d" % (ctr,),
            frozenset((
                "urn:uuid:user%02d" % (ctr,),
                "mailto:user%02d@example.com" % (ctr,),
            )),
        ))

    homes = set(homes) if homes is not None else set()
    homes.update((
        "home1",
        "home2",
        "home3",
        "home_attachments",
        "home_bad",
        "home_defaults",
        "home_no_splits",
        "home_provision1",
        "home_provision2",
        "home_splits",
        "home_splits_shared",
        "uid1",
        "uid2",
        "new-home",
        "xyzzy",
    ))
    for uid in homes:
        directory.addRecord(buildDirectoryRecord(uid))

    # Structured Locations
    directory.addRecord(TestCalendarStoreDirectoryRecord(
        "il1", ("il1",), "1 Infinite Loop", [],
        extras={
            "geo" : "37.331741,-122.030333",
            "streetAddress" : "1 Infinite Loop, Cupertino, CA 95014",
        }
    ))
    directory.addRecord(TestCalendarStoreDirectoryRecord(
        "il2", ("il2",), "2 Infinite Loop", [],
        extras={
            "geo" : "37.332633,-122.030502",
            "streetAddress" : "2 Infinite Loop, Cupertino, CA 95014",
        }
    ))
    directory.addRecord(TestCalendarStoreDirectoryRecord(
        "room1", ("room1",), "Conference Room One",
        frozenset(("urn:uuid:room1",)),
        extras={
            "associatedAddress" : "il1",
        }
    ))
    directory.addRecord(TestCalendarStoreDirectoryRecord(
        "room2", ("room2",), "Conference Room Two",
        frozenset(("urn:uuid:room2",)),
        extras={
            "associatedAddress" : "il2",
        }
    ))

    return directory



def buildDirectoryRecord(uid):
    return TestCalendarStoreDirectoryRecord(
        uid,
        (uid,),
        uid.capitalize(),
        frozenset((
            "urn:uuid:%s" % (uid,),
            "mailto:%s@example.com" % (uid,),
        )),
    )



def buildCalendarStore(testCase, notifierFactory, directoryService=None, homes=None):
    if directoryService is None:
        directoryService = buildDirectory(homes=homes)
    return theStoreBuilder.buildStore(testCase, notifierFactory, directoryService)



class CommonStoreTests(CommonCommonTests, TestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(CommonStoreTests, self).setUp()
        self._sqlCalendarStore = yield buildCalendarStore(self, self.notifierFactory)
        yield self.populate()


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()


    @classproperty(cache=False)
    def requirements(cls): #@NoSelf
        return {
        "user01": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
        "user02": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
        "user03": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
        "user04": {
            "calendar_1": {
            },
            "inbox": {
            },
        },
    }


    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        return self._sqlCalendarStore
