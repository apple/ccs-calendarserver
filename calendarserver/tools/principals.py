#!/usr/bin/env python

##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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

import sys
import os
import operator
import signal
from getopt import getopt, GetoptError
from uuid import UUID

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from txdav.xml import element as davxml

from txdav.xml.base import decodeXMLName, encodeXMLName

from twistedcaldav.config import config
from twistedcaldav.directory.directory import UnknownRecordTypeError, DirectoryError

from calendarserver.tools.util import booleanArgument 
from twistedcaldav.directory.augment import allowedAutoScheduleModes
from calendarserver.tools.cmdline import utilityMain

# FIXME: Move WorkerService to a util module?
from calendarserver.tools.purge import WorkerService

__all__ = [
    "principalForPrincipalID", "proxySubprincipal", "addProxy", "removeProxy",
    "ProxyError", "ProxyWarning", "updateRecord"
]

def usage(e=None):
    if e:
        if isinstance(e, UnknownRecordTypeError):
            print("Valid record types:")
            for recordType in config.directory.recordTypes():
                print("    %s" % (recordType,))

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
    #print("    A principal path (eg.: /principals/users/wsanchez/)")
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
    print("  --read-property=property: read DAV property (eg.: {DAV:}group-member-set)")
    print("  --list-read-proxies: list proxies with read-only access")
    print("  --list-write-proxies: list proxies with read-write access")
    print("  --list-proxies: list all proxies")
    print("  --add-read-proxy=principal: add a read-only proxy")
    print("  --add-write-proxy=principal: add a read-write proxy")
    print("  --remove-proxy=principal: remove a proxy")
    print("  --set-auto-schedule={true|false}: set auto-accept state")
    print("  --get-auto-schedule: read auto-schedule state")
    print("  --set-auto-schedule-mode={default|none|accept-always|decline-always|accept-if-free|decline-if-busy|automatic}: set auto-schedule mode")
    print("  --get-auto-schedule-mode: read auto-schedule mode")
    print("  --set-auto-accept-group=principal: set auto-accept-group")
    print("  --get-auto-accept-group: read auto-accept-group")
    print("  --add {locations|resources} 'full name' [record name] [GUID]: add a principal")
    print("  --remove: remove a principal")

    if e:
        sys.exit(64)
    else:
        sys.exit(0)


class PrincipalService(WorkerService):
    """
    """

    params = []

    @inlineCallbacks
    def doWork(self):
        """
        """
        rootResource = self.rootResource()
        directory = rootResource.getDirectory()
        yield self.command(rootResource, directory, self._store, *self.params) 


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
                "list-principals=",
                "read-property=",
                "list-read-proxies",
                "list-write-proxies",
                "list-proxies",
                "add-read-proxy=",
                "add-write-proxy=",
                "remove-proxy=",
                "set-auto-schedule=",
                "get-auto-schedule",
                "set-auto-schedule-mode=",
                "get-auto-schedule-mode",
                "set-auto-accept-group=",
                "get-auto-accept-group",
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
    principalActions = []
    verbose = False

    for opt, arg in optargs:
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

        elif opt in ("", "--list-principals"):
            listPrincipals = arg

        elif opt in ("", "--search"):
            searchPrincipals = arg

        elif opt in ("", "--read-property"):
            try:
                qname = decodeXMLName(arg)
            except ValueError, e:
                abort(e)
            principalActions.append((action_readProperty, qname))

        elif opt in ("", "--list-read-proxies"):
            principalActions.append((action_listProxies, "read"))

        elif opt in ("", "--list-write-proxies"):
            principalActions.append((action_listProxies, "write"))

        elif opt in ("-L", "--list-proxies"):
            principalActions.append((action_listProxies, "read", "write"))

        elif opt in ("--add-read-proxy", "--add-write-proxy"):
            if "read" in opt:
                proxyType = "read"
            elif "write" in opt:
                proxyType = "write"
            else:
                raise AssertionError("Unknown proxy type")

            try:
                principalForPrincipalID(arg, checkOnly=True)
            except ValueError, e:
                abort(e)

            principalActions.append((action_addProxy, proxyType, arg))

        elif opt in ("", "--remove-proxy"):
            try:
                principalForPrincipalID(arg, checkOnly=True)
            except ValueError, e:
                abort(e)

            principalActions.append((action_removeProxy, arg))

        elif opt in ("", "--set-auto-schedule"):
            try:
                autoSchedule = booleanArgument(arg)
            except ValueError, e:
                abort(e)

            principalActions.append((action_setAutoSchedule, autoSchedule))

        elif opt in ("", "--get-auto-schedule"):
            principalActions.append((action_getAutoSchedule,))

        elif opt in ("", "--set-auto-schedule-mode"):
            try:
                if arg not in allowedAutoScheduleModes:
                    raise ValueError("Unknown auto-schedule mode: %s" % (arg,))
                autoScheduleMode = arg
            except ValueError, e:
                abort(e)

            principalActions.append((action_setAutoScheduleMode, autoScheduleMode))

        elif opt in ("", "--get-auto-schedule-mode"):
            principalActions.append((action_getAutoScheduleMode,))

        elif opt in ("", "--set-auto-accept-group"):
            try:
                principalForPrincipalID(arg, checkOnly=True)
            except ValueError, e:
                abort(e)

            principalActions.append((action_setAutoAcceptGroup, arg))

        elif opt in ("", "--get-auto-accept-group"):
            principalActions.append((action_getAutoAcceptGroup,))


        else:
            raise NotImplementedError(opt)


    #
    # List principals
    #
    if listPrincipalTypes:
        if args:
            usage("Too many arguments")

        for recordType in config.directory.recordTypes():
            print(recordType)

        return

    elif addType:

        try:
            addType = matchStrings(addType, ["locations", "resources"])
        except ValueError, e:
            print(e)
            return

        try:
            fullName, shortName, guid = parseCreationArgs(args)
        except ValueError, e:
            print(e)
            return

        if shortName is not None:
            shortNames = [shortName]
        else:
            shortNames = ()

        params = (runAddPrincipal, addType, guid, shortNames, fullName)


    elif listPrincipals:
        try:
            listPrincipals = matchStrings(listPrincipals, ["users", "groups",
                "locations", "resources"])
        except ValueError, e:
            print(e)
            return

        if args:
            usage("Too many arguments")

        try:
            records = list(config.directory.listRecords(listPrincipals))
            if records:
                printRecordList(records)
            else:
                print("No records of type %s" % (listPrincipals,))
        except UnknownRecordTypeError, e:
            usage(e)

        return

    elif searchPrincipals:
        params = (runSearch, searchPrincipals)

    else:
        #
        # Do a quick sanity check that arguments look like principal
        # identifiers.
        #
        if not args:
            usage("No principals specified.")

        for arg in args:
            try:
                principalForPrincipalID(arg, checkOnly=True)
            except ValueError, e:
                abort(e)

        params = (runPrincipalActions, args, principalActions)


    PrincipalService.params = params
    utilityMain(configFileName, PrincipalService, verbose=verbose)


@inlineCallbacks
def runPrincipalActions(rootResource, directory, store, principalIDs, actions):
    try:
        for principalID in principalIDs:
            # Resolve the given principal IDs to principals
            try:
                principal = principalForPrincipalID(principalID)
            except ValueError:
                principal = None

            if principal is None:
                sys.stderr.write("Invalid principal ID: %s\n" % (principalID,))
                continue

            # Performs requested actions
            for action in actions:
                (yield action[0](rootResource, directory, store, principal,
                    *action[1:]))
                print("")

    finally:
        #
        # Stop the reactor
        #
        reactor.stop()

@inlineCallbacks
def runSearch(rootResource, directory, store, searchTerm):

    try:
        fields = []
        for fieldName in ("fullName", "firstName", "lastName", "emailAddresses"):
            fields.append((fieldName, searchTerm, True, "contains"))

        records = list((yield directory.recordsMatchingTokens(searchTerm.strip().split())))
        if records:
            records.sort(key=operator.attrgetter('fullName'))
            print("%d matches found:" % (len(records),))
            for record in records:
                print("\n%s (%s)" % (record.fullName,
                    { "users"     : "User",
                      "groups"    : "Group",
                      "locations" : "Place",
                      "resources" : "Resource",
                    }.get(record.recordType),
                ))
                print("   GUID: %s" % (record.guid,))
                print("   Record name(s): %s" % (", ".join(record.shortNames),))
                if record.authIDs:
                    print("   Auth ID(s): %s" % (", ".join(record.authIDs),))
                if record.emailAddresses:
                    print("   Email(s): %s" % (", ".join(record.emailAddresses),))
        else:
            print("No matches found")

        print("")

    finally:
        #
        # Stop the reactor
        #
        reactor.stop()

@inlineCallbacks
def runAddPrincipal(addType, guid, shortNames, fullName):
    try:
        try:
            yield updateRecord(True, config.directory, addType, guid=guid,
                shortNames=shortNames, fullName=fullName)
            print("Added '%s'" % (fullName,))
        except DirectoryError, e:
            print(e)

    finally:
        #
        # Stop the reactor
        #
        reactor.stop()


def principalForPrincipalID(principalID, checkOnly=False, directory=None):
    
    # Allow a directory parameter to be passed in, but default to config.directory
    # But config.directory isn't set right away, so only use it when we're doing more 
    # than checking.
    if not checkOnly and not directory:
        directory = config.directory

    if principalID.startswith("/"):
        segments = principalID.strip("/").split("/")
        if (len(segments) == 3 and
            segments[0] == "principals" and segments[1] == "__uids__"):
            uid = segments[2]
        else:
            raise ValueError("Can't resolve all paths yet")

        if checkOnly:
            return None

        return directory.principalCollection.principalForUID(uid)


    if principalID.startswith("("):
        try:
            i = principalID.index(")")

            if checkOnly:
                return None

            recordType = principalID[1:i]
            shortName = principalID[i+1:]

            if not recordType or not shortName or "(" in recordType:
                raise ValueError()

            return directory.principalCollection.principalForShortName(recordType, shortName)

        except ValueError:
            pass

    if ":" in principalID:
        if checkOnly:
            return None

        recordType, shortName = principalID.split(":", 1)

        return directory.principalCollection.principalForShortName(recordType, shortName)

    try:
        UUID(principalID)

        if checkOnly:
            return None

        x = directory.principalCollection.principalForUID(principalID)
        return x
    except ValueError:
        pass

    raise ValueError("Invalid principal identifier: %s" % (principalID,))

def proxySubprincipal(principal, proxyType):
    return principal.getChild("calendar-proxy-" + proxyType)

def action_removePrincipal(rootResource, directory, store, principal):
    record = principal.record
    fullName = record.fullName
    shortName = record.shortNames[0]
    guid = record.guid

    directory.destroyRecord(record.recordType, guid=guid)
    print("Removed '%s' %s %s" % (fullName, shortName, guid))


@inlineCallbacks
def action_readProperty(rootResource, directory, store, resource, qname):
    property = (yield resource.readProperty(qname, None))
    print("%r on %s:" % (encodeXMLName(*qname), resource))
    print("")
    print(property.toxml())

@inlineCallbacks
def action_listProxies(rootResource, directory, store, principal, *proxyTypes):
    for proxyType in proxyTypes:
        subPrincipal = proxySubprincipal(principal, proxyType)
        if subPrincipal is None:
            print("No %s proxies for %s" % (proxyType,
                prettyPrincipal(principal)))
            continue

        membersProperty = (yield subPrincipal.readProperty(davxml.GroupMemberSet, None))

        if membersProperty.children:
            print("%s proxies for %s:" % (
                {"read": "Read-only", "write": "Read/write"}[proxyType],
                prettyPrincipal(principal)
            ))
            records = []
            for member in membersProperty.children:
                proxyPrincipal = principalForPrincipalID(str(member),
                    directory=directory)
                records.append(proxyPrincipal.record)

            printRecordList(records)
            print
        else:
            print("No %s proxies for %s" % (proxyType,
                prettyPrincipal(principal)))

@inlineCallbacks
def action_addProxy(rootResource, directory, store, principal, proxyType, *proxyIDs):
    for proxyID in proxyIDs:
        proxyPrincipal = principalForPrincipalID(proxyID)
        if proxyPrincipal is None:
            print("Invalid principal ID: %s" % (proxyID,))
        else:
            (yield action_addProxyPrincipal(principal, proxyType, proxyPrincipal))

@inlineCallbacks
def action_addProxyPrincipal(rootResource, directory, store, principal, proxyType, proxyPrincipal):
    try:
        (yield addProxy(principal, proxyType, proxyPrincipal))
        print("Added %s as a %s proxy for %s" % (
            prettyPrincipal(proxyPrincipal), proxyType,
            prettyPrincipal(principal)))
    except ProxyError, e:
        print("Error:", e)
    except ProxyWarning, e:
        print(e)

@inlineCallbacks
def addProxy(principal, proxyType, proxyPrincipal):
    proxyURL = proxyPrincipal.url()

    subPrincipal = proxySubprincipal(principal, proxyType)
    if subPrincipal is None:
        raise ProxyError("Unable to edit %s proxies for %s\n" % (proxyType,
            prettyPrincipal(principal)))

    membersProperty = (yield subPrincipal.readProperty(davxml.GroupMemberSet, None))

    for memberURL in membersProperty.children:
        if str(memberURL) == proxyURL:
            raise ProxyWarning("%s is already a %s proxy for %s" % (
                prettyPrincipal(proxyPrincipal), proxyType,
                prettyPrincipal(principal)))

    else:
        memberURLs = list(membersProperty.children)
        memberURLs.append(davxml.HRef(proxyURL))
        membersProperty = davxml.GroupMemberSet(*memberURLs)
        (yield subPrincipal.writeProperty(membersProperty, None))

    proxyTypes = ["read", "write"]
    proxyTypes.remove(proxyType)

    (yield action_removeProxyPrincipal(principal, proxyPrincipal, proxyTypes=proxyTypes))

    triggerGroupCacherUpdate(config)


@inlineCallbacks
def setProxies(principal, readProxyPrincipals, writeProxyPrincipals, directory=None):
    """
    Set read/write proxies en masse for a principal
    @param principal: DirectoryPrincipalResource
    @param readProxyPrincipals: a list of principal IDs (see principalForPrincipalID)
    @param writeProxyPrincipals: a list of principal IDs (see principalForPrincipalID)
    """

    proxyTypes = [
        ("read", readProxyPrincipals),
        ("write", writeProxyPrincipals),
    ]
    for proxyType, proxyIDs in proxyTypes:
        if proxyIDs is None:
            continue
        subPrincipal = proxySubprincipal(principal, proxyType)
        if subPrincipal is None:
            raise ProxyError("Unable to edit %s proxies for %s\n" % (proxyType,
                prettyPrincipal(principal)))
        memberURLs = []
        for proxyID in proxyIDs:
            proxyPrincipal = principalForPrincipalID(proxyID, directory=directory)
            proxyURL = proxyPrincipal.url()
            memberURLs.append(davxml.HRef(proxyURL))
        membersProperty = davxml.GroupMemberSet(*memberURLs)
        (yield subPrincipal.writeProperty(membersProperty, None))
        triggerGroupCacherUpdate(config)


@inlineCallbacks
def getProxies(principal, directory=None):
    """
    Returns a tuple containing the GUIDs for read proxies and write proxies
    of the given principal
    """

    proxies = {
        "read" : [],
        "write" : [],
    }
    for proxyType in proxies.iterkeys():
        subPrincipal = proxySubprincipal(principal, proxyType)
        if subPrincipal is not None:
            membersProperty = (yield subPrincipal.readProperty(davxml.GroupMemberSet, None))
            if membersProperty.children:
                for member in membersProperty.children:
                    proxyPrincipal = principalForPrincipalID(str(member), directory=directory)
                    proxies[proxyType].append(proxyPrincipal.record.guid)

    returnValue((proxies['read'], proxies['write']))


@inlineCallbacks
def action_removeProxy(rootResource, directory, store, principal, *proxyIDs, **kwargs):
    for proxyID in proxyIDs:
        proxyPrincipal = principalForPrincipalID(proxyID)
        if proxyPrincipal is None:
            print("Invalid principal ID: %s" % (proxyID,))
        else:
            (yield action_removeProxyPrincipal(principal, proxyPrincipal, **kwargs))

@inlineCallbacks
def action_removeProxyPrincipal(rootResource, directory, store, principal, proxyPrincipal, **kwargs):
    try:
        removed = (yield removeProxy(principal, proxyPrincipal, **kwargs))
        if removed:
            print("Removed %s as a proxy for %s" % (
                prettyPrincipal(proxyPrincipal),
                prettyPrincipal(principal)))
    except ProxyError, e:
        print("Error:", e)
    except ProxyWarning, e:
        print(e)


@inlineCallbacks
def removeProxy(principal, proxyPrincipal, **kwargs):
    removed = False
    proxyTypes = kwargs.get("proxyTypes", ("read", "write"))
    for proxyType in proxyTypes:
        proxyURL = proxyPrincipal.url()

        subPrincipal = proxySubprincipal(principal, proxyType)
        if subPrincipal is None:
            raise ProxyError("Unable to edit %s proxies for %s\n" % (proxyType,
                prettyPrincipal(principal)))

        membersProperty = (yield subPrincipal.readProperty(davxml.GroupMemberSet, None))

        memberURLs = [
            m for m in membersProperty.children
            if str(m) != proxyURL
        ]

        if len(memberURLs) == len(membersProperty.children):
            # No change
            continue
        else:
            removed = True

        membersProperty = davxml.GroupMemberSet(*memberURLs)
        (yield subPrincipal.writeProperty(membersProperty, None))

    if removed:
        triggerGroupCacherUpdate(config)
    returnValue(removed)


@inlineCallbacks
def action_setAutoSchedule(rootResource, directory, store, principal, autoSchedule):
    if principal.record.recordType == "groups":
        print("Enabling auto-schedule for %s is not allowed." % (principal,))

    elif principal.record.recordType == "users" and not config.Scheduling.Options.AutoSchedule.AllowUsers:
        print("Enabling auto-schedule for %s is not allowed." % (principal,))

    else:
        print("Setting auto-schedule to %s for %s" % (
            { True: "true", False: "false" }[autoSchedule],
            prettyPrincipal(principal),
        ))

        (yield updateRecord(False, directory,
            principal.record.recordType,
            guid=principal.record.guid,
            shortNames=principal.record.shortNames,
            fullName=principal.record.fullName,
            autoSchedule=autoSchedule,
            **principal.record.extras
        ))

def action_getAutoSchedule(rootResource, directory, store, principal):
    autoSchedule = principal.getAutoSchedule()
    print("Auto-schedule for %s is %s" % (
        prettyPrincipal(principal),
        { True: "true", False: "false" }[autoSchedule],
    ))

@inlineCallbacks
def action_setAutoScheduleMode(rootResource, directory, store, principal, autoScheduleMode):
    if principal.record.recordType == "groups":
        print("Setting auto-schedule mode for %s is not allowed." % (principal,))

    elif principal.record.recordType == "users" and not config.Scheduling.Options.AutoSchedule.AllowUsers:
        print("Setting auto-schedule mode for %s is not allowed." % (principal,))

    else:
        print("Setting auto-schedule mode to %s for %s" % (
            autoScheduleMode,
            prettyPrincipal(principal),
        ))

        (yield updateRecord(False, directory,
            principal.record.recordType,
            guid=principal.record.guid,
            shortNames=principal.record.shortNames,
            fullName=principal.record.fullName,
            autoScheduleMode=autoScheduleMode,
            **principal.record.extras
        ))

def action_getAutoScheduleMode(rootResource, directory, store, principal):
    autoScheduleMode = principal.getAutoScheduleMode()
    if not autoScheduleMode:
        autoScheduleMode = "automatic"
    print("Auto-schedule mode for %s is %s" % (
        prettyPrincipal(principal),
        autoScheduleMode,
    ))

@inlineCallbacks
def action_setAutoAcceptGroup(rootResource, directory, store, principal, autoAcceptGroup):
    if principal.record.recordType == "groups":
        print("Setting auto-accept-group for %s is not allowed." % (principal,))

    elif principal.record.recordType == "users" and not config.Scheduling.Options.AutoSchedule.AllowUsers:
        print("Setting auto-accept-group for %s is not allowed." % (principal,))

    else:
        groupPrincipal = principalForPrincipalID(autoAcceptGroup)
        if groupPrincipal is None or groupPrincipal.record.recordType != "groups":
            print("Invalid principal ID: %s" % (autoAcceptGroup,))
        else:
            print("Setting auto-accept-group to %s for %s" % (
                prettyPrincipal(groupPrincipal),
                prettyPrincipal(principal),
            ))

            (yield updateRecord(False, directory,
                principal.record.recordType,
                guid=principal.record.guid,
                shortNames=principal.record.shortNames,
                fullName=principal.record.fullName,
                autoAcceptGroup=groupPrincipal.record.guid,
                **principal.record.extras
            ))

def action_getAutoAcceptGroup(rootResource, directory, store, principal):
    autoAcceptGroup = principal.getAutoAcceptGroup()
    if autoAcceptGroup:
        record = directory.recordWithGUID(autoAcceptGroup)
        if record is not None:
            groupPrincipal = directory.principalCollection.principalForUID(record.uid)
            if groupPrincipal is not None:
                print("Auto-accept-group for %s is %s" % (
                    prettyPrincipal(principal),
                    prettyPrincipal(groupPrincipal),
                ))
                return
        print("Invalid auto-accept-group assigned: %s" % (autoAcceptGroup,))
    else:
        print("No auto-accept-group assigned to %s" % (prettyPrincipal(principal),))


def abort(msg, status=1):
    sys.stdout.write("%s\n" % (msg,))
    try:
        reactor.stop()
    except RuntimeError:
        pass
    sys.exit(status)

class ProxyError(Exception):
    """
    Raised when proxy assignments cannot be performed
    """

class ProxyWarning(Exception):
    """
    Raised for harmless proxy assignment failures such as trying to add a
    duplicate or remove a non-existent assignment.
    """

def parseCreationArgs(args):
    """
    Look at the command line arguments for --add, and figure out which
    one is the shortName and which one is the guid by attempting to make a
    UUID object out of them.
    """

    fullName = args[0]
    shortName = None
    guid = None
    for arg in args[1:]:
        if isUUID(arg):
            if guid is not None:
                # Both the 2nd and 3rd args are UUIDs.  The first one
                # should be used for shortName.
                shortName = guid
            guid = arg
        else:
            shortName = arg

    if len(args) == 3 and guid is None:
        # both shortName and guid were specified but neither was a UUID
        raise ValueError("Invalid value for guid")

    return fullName, shortName, guid


def isUUID(value):
    try:
        UUID(value)
        return True
    except:
        return False

def matchStrings(value, validValues):
    for validValue in validValues:
        if validValue.startswith(value):
            return validValue

    raise ValueError("'%s' is not a recognized value" % (value,))


def printRecordList(records):
    results = [(record.fullName, record.shortNames[0], record.guid)
        for record in records]
    results.sort()
    format = "%-22s %-17s %s"
    print(format % ("Full name", "Record name", "UUID"))
    print(format % ("---------", "-----------", "----"))
    for fullName, shortName, guid in results:
        print(format % (fullName, shortName, guid))

def prettyPrincipal(principal):
    record = principal.record
    return "\"%s\" (%s:%s)" % (record.fullName, record.recordType,
        record.shortNames[0])


@inlineCallbacks
def updateRecord(create, directory, recordType, **kwargs):
    """
    Create/update a record, including the extra work required to set the
    autoSchedule bit in the augment record.

    If C{create} is true, the record is created, otherwise update the record
    matching the guid in kwargs.
    """

    assignAutoSchedule = False
    if kwargs.has_key("autoSchedule"):
        assignAutoSchedule = True
        autoSchedule = kwargs["autoSchedule"]
        del kwargs["autoSchedule"]
    elif create:
        assignAutoSchedule = True
        autoSchedule = recordType in ("locations", "resources")

    assignAutoScheduleMode = False
    if kwargs.has_key("autoScheduleMode"):
        assignAutoScheduleMode = True
        autoScheduleMode = kwargs["autoScheduleMode"]
        del kwargs["autoScheduleMode"]
    elif create:
        assignAutoScheduleMode = True
        autoScheduleMode = None

    assignAutoAcceptGroup = False
    if kwargs.has_key("autoAcceptGroup"):
        assignAutoAcceptGroup = True
        autoAcceptGroup = kwargs["autoAcceptGroup"]
        del kwargs["autoAcceptGroup"]
    elif create:
        assignAutoAcceptGroup = True
        autoAcceptGroup = None

    for key, value in kwargs.items():
        if isinstance(value, unicode):
            kwargs[key] = value.encode("utf-8")
        elif isinstance(value, list):
            newValue = [v.encode("utf-8") for v in value]
            kwargs[key] = newValue

    if create:
        record = directory.createRecord(recordType, **kwargs)
        kwargs['guid'] = record.guid
    else:
        try:
            record = directory.updateRecord(recordType, **kwargs)
        except NotImplementedError:
            # Updating of directory information is not supported by underlying
            # directory implementation, but allow augment information to be
            # updated
            record = directory.recordWithGUID(kwargs["guid"])
            pass

    augmentService = directory.serviceForRecordType(recordType).augmentService
    augmentRecord = (yield augmentService.getAugmentRecord(kwargs['guid'], recordType))

    if assignAutoSchedule:
        augmentRecord.autoSchedule = autoSchedule
    if assignAutoScheduleMode:
        augmentRecord.autoScheduleMode = autoScheduleMode
    if assignAutoAcceptGroup:
        augmentRecord.autoAcceptGroup = autoAcceptGroup
    (yield augmentService.addAugmentRecords([augmentRecord]))
    try:
        directory.updateRecord(recordType, **kwargs)
    except NotImplementedError:
        # Updating of directory information is not supported by underlying
        # directory implementation, but allow augment information to be
        # updated
        pass

    returnValue(record)


def triggerGroupCacherUpdate(config, killMethod=None):
    """
    Look up the pid of the group cacher sidecar and HUP it to trigger an update
    """
    if killMethod is None:
        killMethod = os.kill

    pidFilename = os.path.join(config.RunRoot, "groupcacher.pid")
    if os.path.exists(pidFilename):
        pidFile = open(pidFilename, "r")
        pid = pidFile.read().strip()
        pidFile.close()
        try:
            pid = int(pid)
        except ValueError:
            return
        try:
            killMethod(pid, signal.SIGHUP)
        except OSError:
            pass



if __name__ == "__main__":
    main()
