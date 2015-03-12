#!/usr/bin/env python
# -*- test-case-name: calendarserver.tools.test.test_trash -*-
##
# Copyright (c) 2015 Apple Inc. All rights reserved.
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
from __future__ import print_function

from argparse import ArgumentParser
import datetime

from calendarserver.tools.cmdline import utilityMain, WorkerService
from calendarserver.tools.util import prettyRecord
from pycalendar.datetime import DateTime, Timezone
from twext.python.log import Logger
from twisted.internet.defer import inlineCallbacks, returnValue
from txdav.base.propertystore.base import PropertyName
from txdav.xml import element

log = Logger()



class TrashRestorationService(WorkerService):

    operation = None
    operationArgs = []

    def doWork(self):
        return self.operation(self.store, *self.operationArgs)



def main():

    parser = ArgumentParser(description='Restore events from trash')
    parser.add_argument('-f', '--config', dest='configFileName', metavar='CONFIGFILE', help='caldavd.plist configuration file path')
    parser.add_argument('-d', '--debug', action='store_true', help='show debug logging')
    parser.add_argument('-p', '--principal', dest='principal', help='the principal to use (uid)')
    parser.add_argument('-e', '--events', action='store_true', help='list trashed events')
    parser.add_argument('-c', '--collections', action='store_true', help='list trashed collections for principal (uid)')
    parser.add_argument('-r', '--recover', dest='resourceID', type=int, help='recover trashed collection or event (by resource ID)')
    parser.add_argument('--empty', action='store_true', help='empty the principal\'s trash')
    parser.add_argument('--days', type=int, default=0, help='number of past days to retain')

    args = parser.parse_args()

    if not args.principal:
        print("--principal missing")
        return

    if args.empty:
        operation = emptyTrashForPrincipal
        operationArgs = [args.principal, args.days]
    elif args.collections:
        if args.resourceID:
            operation = restoreTrashedCollection
            operationArgs = [args.principal, args.resourceID]
        else:
            operation = listTrashedCollectionsForPrincipal
            operationArgs = [args.principal]
    elif args.events:
        if args.resourceID:
            operation = restoreTrashedEvent
            operationArgs = [args.principal, args.resourceID]
        else:
            operation = listTrashedEventsForPrincipal
            operationArgs = [args.principal]
    else:
        operation = listTrashedCollectionsForPrincipal
        operationArgs = [args.principal]

    TrashRestorationService.operation = operation
    TrashRestorationService.operationArgs = operationArgs

    utilityMain(
        args.configFileName,
        TrashRestorationService,
        verbose=args.debug,
        loadTimezones=True
    )



@inlineCallbacks
def listTrashedCollectionsForPrincipal(service, store, principalUID):
    directory = store.directoryService()
    record = yield directory.recordWithUID(principalUID)
    if record is None:
        print("No record found for:", principalUID)
        returnValue(None)


    @inlineCallbacks
    def doIt(txn):
        home = yield txn.calendarHomeWithUID(principalUID)
        if home is None:
            print("No home for principal")
            returnValue(None)

        trash = yield home.getTrash()
        if trash is None:
            print("No trash available")
            returnValue(None)

        trashedCollections = yield home.children(onlyInTrash=True)
        if len(trashedCollections) == 0:
            print("No trashed collections for:", prettyRecord(record))
            returnValue(None)

        print("Listing trashed collections for:", prettyRecord(record))
        for collection in trashedCollections:
            displayName = displayNameForCollection(collection)
            print(
                "Collection = \"{}\", trashed = {}, id = {}".format(
                    displayName.encode("utf-8"), collection.whenTrashed(),
                    collection._resourceID
                )
            )
            startTime = collection.whenTrashed() - datetime.timedelta(minutes=5)
            children = yield trash.trashForCollection(
                collection._resourceID, start=startTime
            )
            print(" ...containing events:")
            for child in children:
                component = yield child.component()
                summary = component.mainComponent().propertyValue("SUMMARY", "<no title>")
                whenTrashed = yield child.whenTrashed()
                print(" \"{}\", trashed = {}".format(summary.encode("utf-8"), whenTrashed))

    yield store.inTransaction(label="List trashed collections", operation=doIt)


def agoString(delta):
    if delta.days:
        agoString = "{} days ago".format(delta.days)
    elif delta.seconds:
        if delta.seconds < 60:
            agoString = "{} second{} ago".format(delta.seconds, "s" if delta.seconds > 1 else "")
        else:
            minutesAgo = delta.seconds / 60
            if minutesAgo < 60:
                agoString = "{} minute{} ago".format(minutesAgo, "s" if minutesAgo > 1 else "")
            else:
                hoursAgo = minutesAgo / 60
                agoString = "{} hour{} ago".format(hoursAgo, "s" if hoursAgo > 1 else "")
    return agoString


def startString(pydt):
    return pydt.getLocaleDateTime(DateTime.FULLDATE, False, True, pydt.getTimezoneID())


def locationString(component):
    locationProps = component.properties("LOCATION")
    if locationProps is not None:
        locations = []
        for locationProp in locationProps:
            locations.append(locationProp.value())
        locationString = ", ".join(locations)
    else:
        locationString = ""
    return locationString


@inlineCallbacks
def listTrashedEventsForPrincipal(service, store, principalUID):
    directory = store.directoryService()
    record = yield directory.recordWithUID(principalUID)
    if record is None:
        print("No record found for:", principalUID)
        returnValue(None)


    @inlineCallbacks
    def doIt(txn):
        home = yield txn.calendarHomeWithUID(principalUID)
        if home is None:
            print("No home for principal")
            returnValue(None)

        trash = yield home.getTrash()
        if trash is None:
            print("No trash available")
            returnValue(None)

        untrashedCollections = yield home.children(onlyInTrash=False)
        if len(untrashedCollections) == 0:
            print("No untrashed collections for:", prettyRecord(record))
            returnValue(None)

        oneYearInFuture = DateTime.getNowUTC()
        oneYearInFuture.offsetDay(365)

        nowPyDT = DateTime.getNowUTC()

        nowDT = datetime.datetime.utcnow()

        for collection in untrashedCollections:
            displayName = displayNameForCollection(collection)
            children = yield trash.trashForCollection(collection._resourceID)
            if len(children) == 0:
                continue

            print("Trashed events in calendar \"{}\":".format(displayName.encode("utf-8")))
            for child in children:
                print()
                component = yield child.component()

                mainSummary = component.mainComponent().propertyValue("SUMMARY", u"<no title>")
                whenTrashed = yield child.whenTrashed()
                ago = nowDT - whenTrashed
                print("   Trashed {}:".format(agoString(ago)))

                if component.isRecurring():
                    print(
                        "      \"{}\" (repeating)  Recovery ID = {}".format(
                            mainSummary, child._resourceID
                        )
                    )
                    print("         ...upcoming instances:")
                    instances = component.cacheExpandedTimeRanges(oneYearInFuture)
                    instances = sorted(instances.instances.values(), key=lambda x: x.start)
                    limit = 3
                    count = 0
                    for instance in instances:
                        if instance.start >= nowPyDT:
                            summary = instance.component.propertyValue("SUMMARY", u"<no title>")
                            location = locationString(instance.component)
                            tzid = instance.component.getProperty("DTSTART").parameterValue("TZID", None)
                            dtstart = instance.start
                            if tzid is not None:
                                timezone = Timezone(tzid=tzid)
                                dtstart.adjustTimezone(timezone)
                            print("            \"{}\" {} {}".format(summary, startString(dtstart), location))
                            count += 1
                            limit -= 1
                        if limit == 0:
                            break
                    if not count:
                        print("            (none)")

                else:
                    print(
                        "      \"{}\" (non-repeating)  Recovery ID = {}".format(
                            mainSummary, child._resourceID
                        )
                    )
                    dtstart = component.mainComponent().propertyValue("DTSTART")
                    location = locationString(component.mainComponent())
                    print("         {} {}".format(startString(dtstart), location))


    yield store.inTransaction(label="List trashed events", operation=doIt)



@inlineCallbacks
def restoreTrashedCollection(service, store, principalUID, resourceID):
    directory = store.directoryService()
    record = yield directory.recordWithUID(principalUID)
    if record is None:
        print("No record found for:", principalUID)
        returnValue(None)


    @inlineCallbacks
    def doIt(txn):
        home = yield txn.calendarHomeWithUID(principalUID)
        if home is None:
            print("No home for principal")
            returnValue(None)

        collection = yield home.childWithID(resourceID, onlyInTrash=True)
        if collection is None:
            print("Collection {} is not in the trash".format(resourceID))
            returnValue(None)

        yield collection.fromTrash(
            restoreChildren=True, delta=datetime.timedelta(minutes=5), verbose=True
        )

    yield store.inTransaction(label="Restore trashed collection", operation=doIt)



@inlineCallbacks
def restoreTrashedEvent(service, store, principalUID, resourceID):
    directory = store.directoryService()
    record = yield directory.recordWithUID(principalUID)
    if record is None:
        print("No record found for:", principalUID)
        returnValue(None)


    @inlineCallbacks
    def doIt(txn):
        home = yield txn.calendarHomeWithUID(principalUID)
        if home is None:
            print("No home for principal")
            returnValue(None)

        trash = yield home.getTrash()
        if trash is None:
            print("No trash available")
            returnValue(None)

        child = yield trash.objectResourceWithID(resourceID)
        if child is None:
            print("Event not found")
            returnValue(None)

        component = yield child.component()
        summary = component.mainComponent().propertyValue("SUMMARY", "<no title>")
        print("Restoring \"{}\"".format(summary.encode("utf-8")))
        yield child.fromTrash()

    yield store.inTransaction(label="Restore trashed event", operation=doIt)



@inlineCallbacks
def emptyTrashForPrincipal(service, store, principalUID, days, txn=None, verbose=True):
    directory = store.directoryService()
    record = yield directory.recordWithUID(principalUID)
    if record is None:
        if verbose:
            print("No record found for:", principalUID)
        returnValue(None)


    @inlineCallbacks
    def doIt(txn):
        home = yield txn.calendarHomeWithUID(principalUID)
        if home is None:
            if verbose:
                print("No home for principal")
            returnValue(None)

        trash = yield home.getTrash()
        if trash is None:
            if verbose:
                print("No trash available")
            returnValue(None)

        untrashedCollections = yield home.children(onlyInTrash=False)
        if len(untrashedCollections) == 0:
            if verbose:
                print("No untrashed collections for:", prettyRecord(record))
            returnValue(None)

        endTime = datetime.datetime.utcnow() - datetime.timedelta(days=-days)
        for collection in untrashedCollections:
            displayName = displayNameForCollection(collection)
            children = yield trash.trashForCollection(
                collection._resourceID, end=endTime
            )
            if len(children) == 0:
                continue

            if verbose:
                print("Collection = \"{}\"".format(displayName.encode("utf-8")))
            for child in children:
                component = yield child.component()
                summary = component.mainComponent().propertyValue("SUMMARY", "<no title>")
                whenTrashed = yield child.whenTrashed()
                if verbose:
                    print(
                        " \"{}\", trashed = {}, id = {}".format(
                            summary.encode("utf-8"), whenTrashed, child._resourceID
                        )
                    )
                    print("Removing...")
                yield child.reallyRemove()

    if txn is None:
        yield store.inTransaction(label="Empty trash", operation=doIt)
    else:
        yield doIt(txn)



def displayNameForCollection(collection):
    try:
        displayName = collection.properties()[
            PropertyName.fromElement(element.DisplayName)
        ]
        displayName = displayName.toString()
    except:
        displayName = collection.name()

    return displayName


if __name__ == "__main__":
    main()
