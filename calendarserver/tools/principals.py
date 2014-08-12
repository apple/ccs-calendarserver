#!/usr/bin/env python

##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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

from getopt import getopt, GetoptError
import operator
import os
import sys
import uuid

from calendarserver.tools.cmdline import utilityMain, WorkerService
from calendarserver.tools.util import (
    recordForPrincipalID, prettyRecord
)
from twext.who.directory import DirectoryRecord
from twext.who.idirectory import RecordType, InvalidDirectoryRecordError
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twistedcaldav.config import config
from txdav.who.delegates import (
    addDelegate, removeDelegate, RecordType as DelegateRecordType
)
from txdav.who.idirectory import AutoScheduleMode


allowedAutoScheduleModes = {
    "default": None,
    "none": AutoScheduleMode.none,
    "accept-always": AutoScheduleMode.accept,
    "decline-always": AutoScheduleMode.decline,
    "accept-if-free": AutoScheduleMode.acceptIfFree,
    "decline-if-busy": AutoScheduleMode.declineIfBusy,
    "automatic": AutoScheduleMode.acceptIfFreeDeclineIfBusy,
}


def usage(e=None):
    if e:
        print(e)
        print("")

    name = os.path.basename(sys.argv[0])
    print("usage: %s [options] action_flags principal [principal ...]" % (name,))
    print("       %s [options] --list-principal-types" % (name,))
    print("       %s [options] --list-principals type" % (name,))
    print("")
    print("  Performs the given actions against the giving principals.")
    print("")
    print("  Principals are identified by one of the following:")
    print("    Type and shortname (eg.: users:wsanchez)")
    # print("    A principal path (eg.: /principals/users/wsanchez/)")
    print("    A GUID (eg.: E415DBA7-40B5-49F5-A7CC-ACC81E4DEC79)")
    print("")
    print("options:")
    print("  -h --help: print this help and exit")
    print("  -f --config <path>: Specify caldavd.plist configuration path")
    print("  -v --verbose: print debugging information")
    print("")
    print("actions:")
    print("  --search <search-string>: search for matching principals")
    print("  --list-principal-types: list all of the known principal types")
    print("  --list-principals type: list all principals of the given type")
    print("  --list-read-proxies: list proxies with read-only access")
    print("  --list-write-proxies: list proxies with read-write access")
    print("  --list-proxies: list all proxies")
    print("  --list-proxy-for: principals this principal is a proxy for")
    print("  --add-read-proxy=principal: add a read-only proxy")
    print("  --add-write-proxy=principal: add a read-write proxy")
    print("  --remove-proxy=principal: remove a proxy")
    print("  --set-auto-schedule-mode={default|none|accept-always|decline-always|accept-if-free|decline-if-busy|automatic}: set auto-schedule mode")
    print("  --get-auto-schedule-mode: read auto-schedule mode")
    print("  --set-auto-accept-group=principal: set auto-accept-group")
    print("  --get-auto-accept-group: read auto-accept-group")
    print("  --add {locations|resources|addresses} full-name record-name UID: add a principal")
    print("  --remove: remove a principal")
    print("  --set-geo=url: set the geo: url for an address (e.g. geo:37.331741,-122.030333)")
    print("  --get-geo: get the geo: url for an address")
    print("  --set-street-address=streetaddress: set the street address string for an address")
    print("  --get-street-address: get the street address string for an address")
    print("  --set-address=guid: associate principal with an address (by guid)")
    print("  --get-address: get the associated address's guid")

    if e:
        sys.exit(64)
    else:
        sys.exit(0)



class PrincipalService(WorkerService):
    """
    Executes principals-related functions in a context which has access to the store
    """

    function = None
    params = []

    @inlineCallbacks
    def doWork(self):
        """
        Calls the function that's been assigned to "function" and passes the root
        resource, directory, store, and whatever has been assigned to "params".
        """
        if self.function is not None:
            yield self.function(self.store, *self.params)



def main():
    try:
        (optargs, args) = getopt(
            sys.argv[1:], "a:hf:P:v", [
                "help",
                "config=",
                "add=",
                "remove",
                "search=",
                "list-principal-types",
                "print-group-info",
                "list-principals=",
                "list-read-proxies",
                "list-write-proxies",
                "list-proxies",
                "list-proxy-for",
                "add-read-proxy=",
                "add-write-proxy=",
                "remove-proxy=",
                "set-auto-schedule-mode=",
                "get-auto-schedule-mode",
                "set-auto-accept-group=",
                "get-auto-accept-group",
                "set-geo=",
                "get-geo",
                "set-address=",
                "get-address",
                "set-street-address=",
                "get-street-address",
                "verbose",
            ],
        )
    except GetoptError, e:
        usage(e)

    #
    # Get configuration
    #
    configFileName = None
    addType = None
    listPrincipalTypes = False
    listPrincipals = None
    searchPrincipals = None
    printGroupInfo = False
    principalActions = []
    verbose = False

    for opt, arg in optargs:

        # Args come in as encoded bytes
        arg = arg.decode("utf-8")

        if opt in ("-h", "--help"):
            usage()

        elif opt in ("-v", "--verbose"):
            verbose = True

        elif opt in ("-f", "--config"):
            configFileName = arg

        elif opt in ("-a", "--add"):
            addType = arg

        elif opt in ("-r", "--remove"):
            principalActions.append((action_removePrincipal,))

        elif opt in ("", "--list-principal-types"):
            listPrincipalTypes = True

        elif opt in ("", "--print-group-info"):
            printGroupInfo = True

        elif opt in ("", "--list-principals"):
            listPrincipals = arg

        elif opt in ("", "--search"):
            searchPrincipals = arg

        elif opt in ("", "--list-read-proxies"):
            principalActions.append((action_listProxies, "read"))

        elif opt in ("", "--list-write-proxies"):
            principalActions.append((action_listProxies, "write"))

        elif opt in ("-L", "--list-proxies"):
            principalActions.append((action_listProxies, "read", "write"))

        elif opt in ("--list-proxy-for"):
            principalActions.append((action_listProxyFor, "read", "write"))

        elif opt in ("--add-read-proxy", "--add-write-proxy"):
            if "read" in opt:
                proxyType = "read"
            elif "write" in opt:
                proxyType = "write"
            else:
                raise AssertionError("Unknown proxy type")
            principalActions.append((action_addProxy, proxyType, arg))

        elif opt in ("", "--remove-proxy"):
            principalActions.append((action_removeProxy, arg))

        elif opt in ("", "--set-auto-schedule-mode"):
            try:
                if arg not in allowedAutoScheduleModes:
                    raise ValueError("Unknown auto-schedule mode: {mode}".format(
                        mode=arg))
                autoScheduleMode = allowedAutoScheduleModes[arg]
            except ValueError, e:
                abort(e)

            principalActions.append((action_setAutoScheduleMode, autoScheduleMode))

        elif opt in ("", "--get-auto-schedule-mode"):
            principalActions.append((action_getAutoScheduleMode,))

        elif opt in ("", "--set-auto-accept-group"):
            principalActions.append((action_setAutoAcceptGroup, arg))

        elif opt in ("", "--get-auto-accept-group"):
            principalActions.append((action_getAutoAcceptGroup,))

        elif opt in ("", "--set-geo"):
            principalActions.append((action_setValue, u"geographicLocation", arg))

        elif opt in ("", "--get-geo"):
            principalActions.append((action_getValue, u"geographicLocation"))

        elif opt in ("", "--set-street-address"):
            principalActions.append((action_setValue, u"streetAddress", arg))

        elif opt in ("", "--get-street-address"):
            principalActions.append((action_getValue, u"streetAddress"))

        elif opt in ("", "--set-address"):
            principalActions.append((action_setValue, u"associatedAddress", arg))

        elif opt in ("", "--get-address"):
            principalActions.append((action_getValue, u"associatedAddress"))

        else:
            raise NotImplementedError(opt)

    #
    # List principals
    #
    if listPrincipalTypes:
        if args:
            usage("Too many arguments")

        function = runListPrincipalTypes
        params = ()

    elif printGroupInfo:
        function = printGroupCacherInfo
        params = ()

    elif addType:

        try:
            addType = matchStrings(
                addType,
                [
                    "locations", "resources", "addresses", "users", "groups"
                ]
            )
        except ValueError, e:
            print(e)
            return

        try:
            fullName, shortName, uid = parseCreationArgs(args)
        except ValueError, e:
            print(e)
            return

        if fullName is not None:
            fullNames = [fullName]
        else:
            fullNames = ()

        if shortName is not None:
            shortNames = [shortName]
        else:
            shortNames = ()

        function = runAddPrincipal
        params = (addType, uid, shortNames, fullNames)

    elif listPrincipals:
        try:
            listPrincipals = matchStrings(
                listPrincipals,
                ["users", "groups", "locations", "resources", "addresses"]
            )
        except ValueError, e:
            print(e)
            return

        if args:
            usage("Too many arguments")

        function = runListPrincipals
        params = (listPrincipals,)

    elif searchPrincipals:
        function = runSearch
        params = (searchPrincipals,)

    else:
        if not args:
            usage("No principals specified.")

        unicodeArgs = [a.decode("utf-8") for a in args]
        function = runPrincipalActions
        params = (unicodeArgs, principalActions)

    PrincipalService.function = function
    PrincipalService.params = params
    utilityMain(configFileName, PrincipalService, verbose=verbose)



def runListPrincipalTypes(service, store):
    directory = store.directoryService()
    for recordType in directory.recordTypes():
        print(directory.recordTypeToOldName(recordType))
    return succeed(None)



@inlineCallbacks
def runListPrincipals(service, store, listPrincipals):
    directory = store.directoryService()
    recordType = directory.oldNameToRecordType(listPrincipals)
    try:
        records = list((yield directory.recordsWithRecordType(recordType)))
        if records:
            printRecordList(records)
        else:
            print("No records of type %s" % (listPrincipals,))
    except InvalidDirectoryRecordError, e:
        usage(e)
    returnValue(None)



@inlineCallbacks
def runPrincipalActions(service, store, principalIDs, actions):
    directory = store.directoryService()
    for principalID in principalIDs:
        # Resolve the given principal IDs to records
        try:
            record = yield recordForPrincipalID(directory, principalID)
        except ValueError:
            record = None

        if record is None:
            sys.stderr.write("Invalid principal ID: %s\n" % (principalID,))
            continue

        # Performs requested actions
        for action in actions:
            (yield action[0](store, record, *action[1:]))
            print("")



@inlineCallbacks
def runSearch(service, store, searchTerm):
    directory = store.directoryService()
    fields = []
    for fieldName in ("fullNames", "emailAddresses"):
        fields.append((fieldName, searchTerm, True, "contains"))

    records = list((yield directory.recordsMatchingTokens(searchTerm.strip().split())))
    if records:
        records.sort(key=operator.attrgetter('fullNames'))
        print("{n} matches found:".format(n=len(records)))
        for record in records:
            print(
                "\n{d} ({rt})".format(
                    d=record.displayName,
                    rt=record.recordType.name
                )
            )
            print("   UID: {u}".format(u=record.uid,))
            try:
                print(
                    "   Record name{plural}: {names}".format(
                        plural=("s" if len(record.shortNames) > 1 else ""),
                        names=(", ".join(record.shortNames))
                    )
                )
            except AttributeError:
                pass
            try:
                if record.emailAddresses:
                    print(
                        "   Email{plural}: {emails}".format(
                            plural=("s" if len(record.emailAddresses) > 1 else ""),
                            emails=(", ".join(record.emailAddresses))
                        )
                    )
            except AttributeError:
                pass
    else:
        print("No matches found")

    print("")



@inlineCallbacks
def runAddPrincipal(service, store, addType, uid, shortNames, fullNames):
    directory = store.directoryService()
    recordType = directory.oldNameToRecordType(addType)

    # See if that UID is in use
    record = yield directory.recordWithUID(uid)
    if record is not None:
        print("UID already in use: {uid}".format(uid=uid))
        returnValue(None)

    # See if the shortnames are in use
    for shortName in shortNames:
        record = yield directory.recordWithShortName(recordType, shortName)
        if record is not None:
            print("Record name already in use: {name}".format(name=shortName))
            returnValue(None)

    fields = {
        directory.fieldName.recordType: recordType,
        directory.fieldName.uid: uid,
        directory.fieldName.shortNames: shortNames,
        directory.fieldName.fullNames: fullNames,
        directory.fieldName.hasCalendars: True,
        directory.fieldName.hasContacts: True,
    }
    record = DirectoryRecord(directory, fields)
    yield record.service.updateRecords([record], create=True)
    print("Added '{name}'".format(name=fullNames[0]))



@inlineCallbacks
def action_removePrincipal(store, record):
    directory = store.directoryService()
    fullName = record.displayName
    shortNames = ",".join(record.shortNames)

    yield directory.removeRecords([record.uid])
    print(
        "Removed '{full}' {shorts} {uid}".format(
            full=fullName, shorts=shortNames, uid=record.uid
        )
    )



@inlineCallbacks
def action_listProxies(store, record, *proxyTypes):
    directory = store.directoryService()
    for proxyType in proxyTypes:

        groupRecordType = {
            "read": directory.recordType.readDelegateGroup,
            "write": directory.recordType.writeDelegateGroup,
        }.get(proxyType)

        pseudoGroup = yield directory.recordWithShortName(
            groupRecordType,
            record.uid
        )
        proxies = yield pseudoGroup.members()
        if proxies:
            print("%s proxies for %s:" % (
                {"read": "Read-only", "write": "Read/write"}[proxyType],
                prettyRecord(record)
            ))
            printRecordList(proxies)
            print("")
        else:
            print("No %s proxies for %s" % (proxyType, prettyRecord(record)))



@inlineCallbacks
def action_listProxyFor(store, record, *proxyTypes):
    directory = store.directoryService()
    for proxyType in proxyTypes:

        groupRecordType = {
            "read": directory.recordType.readDelegatorGroup,
            "write": directory.recordType.writeDelegatorGroup,
        }.get(proxyType)

        pseudoGroup = yield directory.recordWithShortName(
            groupRecordType,
            record.uid
        )
        proxies = yield pseudoGroup.members()
        if proxies:
            print("%s is a %s proxy for:" % (
                prettyRecord(record),
                {"read": "Read-only", "write": "Read/write"}[proxyType]
            ))
            printRecordList(proxies)
            print("")
        else:
            print(
                "{r} is not a {t} proxy for anyone".format(
                    r=prettyRecord(record),
                    t={"read": "Read-only", "write": "Read/write"}[proxyType]
                )
            )



@inlineCallbacks
def _addRemoveProxy(msg, fn, store, record, proxyType, *proxyIDs):
    directory = store.directoryService()
    readWrite = (proxyType == "write")
    for proxyID in proxyIDs:
        proxyRecord = yield recordForPrincipalID(directory, proxyID)
        if proxyRecord is None:
            print("Invalid principal ID: %s" % (proxyID,))
        else:
            txn = store.newTransaction()
            yield fn(txn, record, proxyRecord, readWrite)
            yield txn.commit()
            print(
                "{msg} {proxy} as a {proxyType} proxy for {record}".format(
                    msg=msg, proxy=prettyRecord(proxyRecord),
                    proxyType=proxyType, record=prettyRecord(record)
                )
            )



@inlineCallbacks
def action_addProxy(store, record, proxyType, *proxyIDs):
    yield _addRemoveProxy("Added", addDelegate, store, record, proxyType, *proxyIDs)



@inlineCallbacks
def action_removeProxy(store, record, *proxyIDs):
    # Write
    yield _addRemoveProxy("Removed", removeDelegate, store, record, "write", *proxyIDs)
    # Read
    yield _addRemoveProxy("Removed", removeDelegate, store, record, "read", *proxyIDs)



@inlineCallbacks
def setProxies(record, readProxyRecords, writeProxyRecords):
    """
    Set read/write proxies en masse for a record
    @param record: L{IDirectoryRecord}
    @param readProxyRecords: a list of records
    @param writeProxyRecords: a list of records
    """

    proxyTypes = [
        (DelegateRecordType.readDelegateGroup, readProxyRecords),
        (DelegateRecordType.writeDelegateGroup, writeProxyRecords),
    ]
    for recordType, proxyRecords in proxyTypes:
        if proxyRecords is None:
            continue
        proxyGroup = yield record.service.recordWithShortName(
            recordType, record.uid
        )
        yield proxyGroup.setMembers(proxyRecords)



@inlineCallbacks
def getProxies(record):
    """
    Returns a tuple containing the records for read proxies and write proxies
    of the given record
    """

    allProxies = {
        DelegateRecordType.readDelegateGroup: [],
        DelegateRecordType.writeDelegateGroup: [],
    }
    for recordType in allProxies.iterkeys():
        proxyGroup = yield record.service.recordWithShortName(
            recordType, record.uid
        )
        allProxies[recordType] = yield proxyGroup.members()

    returnValue(
        (
            allProxies[DelegateRecordType.readDelegateGroup],
            allProxies[DelegateRecordType.writeDelegateGroup]
        )
    )



def action_getAutoScheduleMode(store, record):
    print(
        "Auto-schedule mode for {record} is {mode}".format(
            record=prettyRecord(record),
            mode=(
                record.autoScheduleMode.description if record.autoScheduleMode
                else "Default"
            )
        )
    )



@inlineCallbacks
def action_setAutoScheduleMode(store, record, autoScheduleMode):
    if record.recordType == RecordType.group:
        print(
            "Setting auto-schedule-mode for {record} is not allowed.".format(
                record=prettyRecord(record)
            )
        )

    elif (
        record.recordType == RecordType.user and
        not config.Scheduling.Options.AutoSchedule.AllowUsers
    ):
        print(
            "Setting auto-schedule-mode for {record} is not allowed.".format(
                record=prettyRecord(record)
            )
        )

    else:
        print(
            "Setting auto-schedule-mode to {mode} for {record}".format(
                mode=autoScheduleMode.description,
                record=prettyRecord(record),
            )
        )

        # Get original fields
        newFields = record.fields.copy()

        # Set new values
        newFields[record.service.fieldName.autoScheduleMode] = autoScheduleMode

        updatedRecord = DirectoryRecord(record.service, newFields)
        yield record.service.updateRecords([updatedRecord], create=False)



@inlineCallbacks
def action_setAutoAcceptGroup(store, record, autoAcceptGroup):
    if record.recordType == RecordType.group:
        print(
            "Setting auto-accept-group for {record} is not allowed.".format(
                record=prettyRecord(record)
            )
        )

    elif (
        record.recordType == RecordType.user and
        not config.Scheduling.Options.AutoSchedule.AllowUsers
    ):
        print(
            "Setting auto-accept-group for {record} is not allowed.".format(
                record=prettyRecord(record)
            )
        )

    else:
        groupRecord = yield recordForPrincipalID(record.service, autoAcceptGroup)
        if groupRecord is None or groupRecord.recordType != RecordType.group:
            print("Invalid principal ID: {id}".format(id=autoAcceptGroup))
        else:
            print("Setting auto-accept-group to {group} for {record}".format(
                group=prettyRecord(groupRecord),
                record=prettyRecord(record),
            ))

            # Get original fields
            newFields = record.fields.copy()

            # Set new values
            newFields[record.service.fieldName.autoAcceptGroup] = groupRecord.uid

            updatedRecord = DirectoryRecord(record.service, newFields)
            yield record.service.updateRecords([updatedRecord], create=False)



@inlineCallbacks
def action_getAutoAcceptGroup(store, record):
    if record.autoAcceptGroup:
        groupRecord = yield record.service.recordWithUID(
            record.autoAcceptGroup
        )
        if groupRecord is not None:
            print(
                "Auto-accept-group for {record} is {group}".format(
                    record=prettyRecord(record),
                    group=prettyRecord(groupRecord),
                )
            )
        else:
            print(
                "Invalid auto-accept-group assigned: {uid}".format(
                    uid=record.autoAcceptGroup
                )
            )
    else:
        print(
            "No auto-accept-group assigned to {record}".format(
                record=prettyRecord(record)
            )
        )



@inlineCallbacks
def action_setValue(store, record, name, value):
    print(
        "Setting {name} to {value} for {record}".format(
            name=name, value=value, record=prettyRecord(record),
        )
    )
    # Get original fields
    newFields = record.fields.copy()

    # Set new value
    newFields[record.service.fieldName.lookupByName(name)] = value

    updatedRecord = DirectoryRecord(record.service, newFields)
    yield record.service.updateRecords([updatedRecord], create=False)



def action_getValue(store, record, name):
    try:
        value = record.fields[record.service.fieldName.lookupByName(name)]
        print(
            "{name} for {record} is {value}".format(
                name=name, record=prettyRecord(record), value=value
            )
        )
    except KeyError:
        print(
            "{name} is not set for {record}".format(
                name=name, record=prettyRecord(record),
            )
        )



@inlineCallbacks
def printGroupCacherInfo(service, store):
    """
    Print all groups that have been delegated to, their cached members, and
    who delegated to those groups.
    """
    directory = store.directoryService()
    txn = store.newTransaction()
    groupUIDs = yield txn.allGroupDelegates()
    for groupUID in groupUIDs:
        (
            groupID, name, _ignore_membershipHash, modified, _ignore_extant
        ) = yield txn.groupByUID(
            groupUID
        )
        print("Group: \"{name}\" ({uid})".format(name=name, uid=groupUID))

        for txt, readWrite in (("read-only", False), ("read-write", True)):
            delegatorUIDs = yield txn.delegatorsToGroup(groupID, readWrite)
            for delegatorUID in delegatorUIDs:
                delegator = yield directory.recordWithUID(delegatorUID)
                print(
                    "...has {rw} access to {rec}".format(
                        rw=txt, rec=prettyRecord(delegator)
                    )
                )

        print("Group members:")
        memberUIDs = yield txn.groupMemberUIDs(groupID)
        for memberUID in memberUIDs:
            record = yield directory.recordWithUID(memberUID)
            print(prettyRecord(record))

        print("Last cached: {} GMT".format(modified))
        print()

    yield txn.commit()



def abort(msg, status=1):
    sys.stdout.write("%s\n" % (msg,))
    try:
        reactor.stop()
    except RuntimeError:
        pass
    sys.exit(status)



def parseCreationArgs(args):
    """
    Look at the command line arguments for --add; the first arg is required
    and is the full name.   If only that one arg is provided, generate a UUID
    and use it for record name and uid.  If two args are provided, use the
    second arg as the record name and generate a UUID for the uid.  If three
    args are provided, the second arg is the record name and the third arg
    is the uid.
    """

    numArgs = len(args)
    if numArgs == 0:
        print(
            "When adding a principal, you must provide the full-name"
        )
        sys.exit(64)

    fullName = args[0].decode("utf-8")

    if numArgs == 1:
        shortName = uid = unicode(uuid.uuid4()).upper()

    elif numArgs == 2:
        shortName = args[1].decode("utf-8")
        uid = unicode(uuid.uuid4()).upper()

    else:
        shortName = args[1].decode("utf-8")
        uid = args[2].decode("utf-8")

    return fullName, shortName, uid



def isUUID(value):
    try:
        uuid.UUID(value)
        return True
    except:
        return False



def matchStrings(value, validValues):
    for validValue in validValues:
        if validValue.startswith(value):
            return validValue

    raise ValueError("'%s' is not a recognized value" % (value,))



def printRecordList(records):
    results = []
    for record in records:
        try:
            shortNames = record.shortNames
        except AttributeError:
            shortNames = []
        results.append(
            (record.displayName, record.recordType.name, record.uid, shortNames)
        )

    results.sort()
    format = "%-22s %-10s %-20s %s"
    print(format % ("Full name", "Type", "UID", "Short names"))
    print(format % ("---------", "----", "---", "-----------"))
    for fullName, recordType, uid, shortNames in results:
        print(format % (fullName, recordType, uid, u", ".join(shortNames)))



if __name__ == "__main__":
    main()
