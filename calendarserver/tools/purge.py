#!/usr/bin/env python

##
# Copyright (c) 2006-2010 Apple Inc. All rights reserved.
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
from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import TimeRange
from twistedcaldav.ical import Component as iComponent
from twistedcaldav.method.delete_common import DeleteResource
from twisted.internet.defer import inlineCallbacks, returnValue
from calendarserver.util import FakeRequest

log = Logger()

@inlineCallbacks
def purgeOldEvents(directory, root, date):

    calendars = root.getChild("calendars")
    uidsFPath = calendars.fp.child("__uids__")

    records = []
    if uidsFPath.exists():
        for firstFPath in uidsFPath.children():
            if len(firstFPath.basename()) == 2:
                for secondFPath in firstFPath.children():
                    if len(secondFPath.basename()) == 2:
                        for homeFPath in secondFPath.children():
                            uid = homeFPath.basename()
                            record = directory.recordWithUID(uid)
                            if record is not None:
                                records.append(record)

    log.info("Purging events from %d calendar homes" % (len(records),))

    filter =  caldavxml.Filter(
          caldavxml.ComponentFilter(
              caldavxml.ComponentFilter(
                  TimeRange(start=date,),
                  name=("VEVENT", "VFREEBUSY", "VAVAILABILITY"),
              ),
              name="VCALENDAR",
           )
      )

    eventCount = 0
    for record in records:
        # Get the calendar home
        principalCollection = directory.principalCollection
        principal = principalCollection.principalForRecord(record)
        calendarHome = principal.calendarHome()

        # For each collection in calendar home...
        for collName in calendarHome.listChildren():
            collection = calendarHome.getChild(collName)
            if collection.isCalendarCollection():
                # ...use their indexes to figure out which events to purge.

                # First, get the list of all child resources...
                resources = set(collection.listChildren())

                # ...and ignore those that appear *after* the given cutoff
                for name, uid, type in collection.index().indexedSearch(filter):
                    if name in resources:
                        resources.remove(name)

                for name in resources:
                    resource = collection.getChild(name)
                    uri = "/calendars/__uids__/%s/%s/%s" % (
                        record.uid,
                        collName,
                        name
                    )
                    try:
                        response = (yield deleteResource(root, collection,
                            resource, uri))
                        eventCount += 1
                    except Exception, e:
                        log.error("Failed to purge old event: %s (%s)" %
                            (uri, e))

    returnValue(eventCount)


def deleteResource(root, collection, resource, uri):
    request = FakeRequest(root, "DELETE", uri)

    # TODO: this seems hacky, even for a stub request:
    request._rememberResource(resource, uri)

    deleter = DeleteResource(request, resource, uri,
        collection, "infinity", allowImplicitSchedule=False)
    return deleter.run()
