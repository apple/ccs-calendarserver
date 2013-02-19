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

from getopt import getopt, GetoptError
import os
import sys
import xml

from twext.python.plistlib import readPlistFromString, writePlistToString

from twisted.internet.defer import inlineCallbacks
from twistedcaldav.directory.directory import DirectoryError
from txdav.xml import element as davxml

from calendarserver.tools.principals import (
    principalForPrincipalID, proxySubprincipal, addProxy, removeProxy,
    getProxies, setProxies, ProxyError, ProxyWarning, updateRecord
)
from calendarserver.tools.purge import WorkerService, PurgeOldEventsService, DEFAULT_BATCH_SIZE, DEFAULT_RETAIN_DAYS
from calendarserver.tools.cmdline import utilityMain

from pycalendar.datetime import PyCalendarDateTime


def usage(e=None):

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options]" % (name,)
    print ""
    print "  TODO: describe usage"
    print ""
    print "options:"
    print "  -h --help: print this help and exit"
    print "  -e --error: send stderr to stdout"
    print "  -f --config <path>: Specify caldavd.plist configuration path"
    print ""

    if e:
        sys.exit(64)
    else:
        sys.exit(0)



class RunnerService(WorkerService):
    """
    A wrapper around Runner which uses utilityMain to get the store
    """

    commands = None

    @inlineCallbacks
    def doWork(self):
        """
        Create/run a Runner to execute the commands
        """
        rootResource = self.rootResource()
        directory = rootResource.getDirectory()
        runner = Runner(rootResource, directory, self._store, self.commands)
        if runner.validate():
            yield runner.run()



def main():

    try:
        (optargs, _ignore_args) = getopt(
            sys.argv[1:], "hef:", [
                "help",
                "error",
                "config=",
            ],
        )
    except GetoptError, e:
        usage(e)

    #
    # Get configuration
    #
    configFileName = None
    debug = False

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        if opt in ("-e", "--error"):
            debug = True

        elif opt in ("-f", "--config"):
            configFileName = arg

        else:
            raise NotImplementedError(opt)

    #
    # Read commands from stdin
    #
    rawInput = sys.stdin.read()
    try:
        plist = readPlistFromString(rawInput)
    except xml.parsers.expat.ExpatError, e:
        respondWithError(str(e))
        return

    # If the plist is an array, each element of the array is a separate
    # command dictionary.
    if isinstance(plist, list):
        commands = plist
    else:
        commands = [plist]

    RunnerService.commands = commands
    utilityMain(configFileName, RunnerService, verbose=debug)


attrMap = {
    'GeneratedUID' : { 'attr' : 'guid', },
    'RealName' : { 'attr' : 'fullName', },
    'RecordName' : { 'attr' : 'shortNames', },
    'Comment' : { 'extras' : True, 'attr' : 'comment', },
    'Description' : { 'extras' : True, 'attr' : 'description', },
    'Type' : { 'extras' : True, 'attr' : 'type', },
    'Capacity' : { 'extras' : True, 'attr' : 'capacity', },
    'Building' : { 'extras' : True, 'attr' : 'building', },
    'Floor' : { 'extras' : True, 'attr' : 'floor', },
    'Street' : { 'extras' : True, 'attr' : 'street', },
    'City' : { 'extras' : True, 'attr' : 'city', },
    'State' : { 'extras' : True, 'attr' : 'state', },
    'ZIP' : { 'extras' : True, 'attr' : 'zip', },
    'Country' : { 'extras' : True, 'attr' : 'country', },
    'Phone' : { 'extras' : True, 'attr' : 'phone', },
    'AutoSchedule' : { 'attr' : 'autoSchedule', },
    'AutoAcceptGroup' : { 'attr' : 'autoAcceptGroup', },
}

class Runner(object):

    def __init__(self, root, directory, store, commands):
        self.root = root
        self.dir = directory
        self.store = store
        self.commands = commands


    def validate(self):
        # Make sure commands are valid
        for command in self.commands:
            if 'command' not in command:
                respondWithError("'command' missing from plist")
                return False
            commandName = command['command']
            methodName = "command_%s" % (commandName,)
            if not hasattr(self, methodName):
                respondWithError("Unknown command '%s'" % (commandName,))
                return False
        return True


    @inlineCallbacks
    def run(self):
        try:
            for command in self.commands:
                commandName = command['command']
                methodName = "command_%s" % (commandName,)
                if hasattr(self, methodName):
                    (yield getattr(self, methodName)(command))
                else:
                    respondWithError("Unknown command '%s'" % (commandName,))

        except Exception, e:
            respondWithError("Command failed: '%s'" % (str(e),))
            raise

    # Locations


    def command_getLocationList(self, command):
        respondWithRecordsOfType(self.dir, command, "locations")


    @inlineCallbacks
    def command_createLocation(self, command):
        kwargs = {}
        for key, info in attrMap.iteritems():
            if key in command:
                kwargs[info['attr']] = command[key]

        try:
            record = (yield updateRecord(True, self.dir, "locations", **kwargs))
        except DirectoryError, e:
            respondWithError(str(e))
            return

        readProxies = command.get("ReadProxies", None)
        writeProxies = command.get("WriteProxies", None)
        principal = principalForPrincipalID(record.guid, directory=self.dir)
        (yield setProxies(principal, readProxies, writeProxies, directory=self.dir))

        respondWithRecordsOfType(self.dir, command, "locations")


    @inlineCallbacks
    def command_getLocationAttributes(self, command):
        guid = command['GeneratedUID']
        record = self.dir.recordWithGUID(guid)
        if record is None:
            respondWithError("Principal not found: %s" % (guid,))
            return
        recordDict = recordToDict(record)
        principal = principalForPrincipalID(guid, directory=self.dir)
        if principal is None:
            respondWithError("Principal not found: %s" % (guid,))
            return
        recordDict['AutoSchedule'] = principal.getAutoSchedule()
        recordDict['AutoAcceptGroup'] = principal.getAutoAcceptGroup()
        recordDict['ReadProxies'], recordDict['WriteProxies'] = (yield getProxies(principal,
            directory=self.dir))
        respond(command, recordDict)

    command_getResourceAttributes = command_getLocationAttributes

    @inlineCallbacks
    def command_setLocationAttributes(self, command):

        # Set autoSchedule prior to the updateRecord so that the right
        # value ends up in memcached
        principal = principalForPrincipalID(command['GeneratedUID'],
            directory=self.dir)
        (yield principal.setAutoSchedule(command.get('AutoSchedule', False)))
        (yield principal.setAutoAcceptGroup(command.get('AutoAcceptGroup', "")))

        kwargs = {}
        for key, info in attrMap.iteritems():
            if key in command:
                kwargs[info['attr']] = command[key]
        try:
            record = (yield updateRecord(False, self.dir, "locations", **kwargs))
        except DirectoryError, e:
            respondWithError(str(e))
            return

        readProxies = command.get("ReadProxies", None)
        writeProxies = command.get("WriteProxies", None)
        principal = principalForPrincipalID(record.guid, directory=self.dir)
        (yield setProxies(principal, readProxies, writeProxies, directory=self.dir))

        yield self.command_getLocationAttributes(command)


    def command_deleteLocation(self, command):
        kwargs = {}
        for key, info in attrMap.iteritems():
            if key in command:
                kwargs[info['attr']] = command[key]
        try:
            self.dir.destroyRecord("locations", **kwargs)
        except DirectoryError, e:
            respondWithError(str(e))
            return
        respondWithRecordsOfType(self.dir, command, "locations")

    # Resources


    def command_getResourceList(self, command):
        respondWithRecordsOfType(self.dir, command, "resources")


    @inlineCallbacks
    def command_createResource(self, command):
        kwargs = {}
        for key, info in attrMap.iteritems():
            if key in command:
                kwargs[info['attr']] = command[key]

        try:
            record = (yield updateRecord(True, self.dir, "resources", **kwargs))
        except DirectoryError, e:
            respondWithError(str(e))
            return

        readProxies = command.get("ReadProxies", None)
        writeProxies = command.get("WriteProxies", None)
        principal = principalForPrincipalID(record.guid, directory=self.dir)
        (yield setProxies(principal, readProxies, writeProxies, directory=self.dir))

        respondWithRecordsOfType(self.dir, command, "resources")


    @inlineCallbacks
    def command_setResourceAttributes(self, command):

        # Set autoSchedule prior to the updateRecord so that the right
        # value ends up in memcached
        principal = principalForPrincipalID(command['GeneratedUID'],
            directory=self.dir)
        (yield principal.setAutoSchedule(command.get('AutoSchedule', False)))
        (yield principal.setAutoAcceptGroup(command.get('AutoAcceptGroup', "")))

        kwargs = {}
        for key, info in attrMap.iteritems():
            if key in command:
                kwargs[info['attr']] = command[key]
        try:
            record = (yield updateRecord(False, self.dir, "resources", **kwargs))
        except DirectoryError, e:
            respondWithError(str(e))
            return

        readProxies = command.get("ReadProxies", None)
        writeProxies = command.get("WriteProxies", None)
        principal = principalForPrincipalID(record.guid, directory=self.dir)
        (yield setProxies(principal, readProxies, writeProxies, directory=self.dir))

        yield self.command_getResourceAttributes(command)


    def command_deleteResource(self, command):
        kwargs = {}
        for key, info in attrMap.iteritems():
            if key in command:
                kwargs[info['attr']] = command[key]
        try:
            self.dir.destroyRecord("resources", **kwargs)
        except DirectoryError, e:
            respondWithError(str(e))
            return
        respondWithRecordsOfType(self.dir, command, "resources")

    # Proxies


    @inlineCallbacks
    def command_listWriteProxies(self, command):
        principal = principalForPrincipalID(command['Principal'], directory=self.dir)
        if principal is None:
            respondWithError("Principal not found: %s" % (command['Principal'],))
            return
        (yield respondWithProxies(self.dir, command, principal, "write"))


    @inlineCallbacks
    def command_addWriteProxy(self, command):
        principal = principalForPrincipalID(command['Principal'],
            directory=self.dir)
        if principal is None:
            respondWithError("Principal not found: %s" % (command['Principal'],))
            return

        proxy = principalForPrincipalID(command['Proxy'], directory=self.dir)
        if proxy is None:
            respondWithError("Proxy not found: %s" % (command['Proxy'],))
            return
        try:
            (yield addProxy(principal, "write", proxy))
        except ProxyError, e:
            respondWithError(str(e))
            return
        except ProxyWarning, e:
            pass
        (yield respondWithProxies(self.dir, command, principal, "write"))


    @inlineCallbacks
    def command_removeWriteProxy(self, command):
        principal = principalForPrincipalID(command['Principal'], directory=self.dir)
        if principal is None:
            respondWithError("Principal not found: %s" % (command['Principal'],))
            return
        proxy = principalForPrincipalID(command['Proxy'], directory=self.dir)
        if proxy is None:
            respondWithError("Proxy not found: %s" % (command['Proxy'],))
            return
        try:
            (yield removeProxy(principal, proxy, proxyTypes=("write",)))
        except ProxyError, e:
            respondWithError(str(e))
            return
        except ProxyWarning, e:
            pass
        (yield respondWithProxies(self.dir, command, principal, "write"))


    @inlineCallbacks
    def command_listReadProxies(self, command):
        principal = principalForPrincipalID(command['Principal'], directory=self.dir)
        if principal is None:
            respondWithError("Principal not found: %s" % (command['Principal'],))
            return
        (yield respondWithProxies(self.dir, command, principal, "read"))


    @inlineCallbacks
    def command_addReadProxy(self, command):
        principal = principalForPrincipalID(command['Principal'], directory=self.dir)
        if principal is None:
            respondWithError("Principal not found: %s" % (command['Principal'],))
            return
        proxy = principalForPrincipalID(command['Proxy'], directory=self.dir)
        if proxy is None:
            respondWithError("Proxy not found: %s" % (command['Proxy'],))
            return
        try:
            (yield addProxy(principal, "read", proxy))
        except ProxyError, e:
            respondWithError(str(e))
            return
        except ProxyWarning, e:
            pass
        (yield respondWithProxies(self.dir, command, principal, "read"))


    @inlineCallbacks
    def command_removeReadProxy(self, command):
        principal = principalForPrincipalID(command['Principal'], directory=self.dir)
        if principal is None:
            respondWithError("Principal not found: %s" % (command['Principal'],))
            return
        proxy = principalForPrincipalID(command['Proxy'], directory=self.dir)
        if proxy is None:
            respondWithError("Proxy not found: %s" % (command['Proxy'],))
            return
        try:
            (yield removeProxy(principal, proxy, proxyTypes=("read",)))
        except ProxyError, e:
            respondWithError(str(e))
            return
        except ProxyWarning, e:
            pass
        (yield respondWithProxies(self.dir, command, principal, "read"))


    @inlineCallbacks
    def command_purgeOldEvents(self, command):
        """
        Convert RetainDays from the command dictionary into a date, then purge
        events older than that date.

        @param command: the dictionary parsed from the plist read from stdin
        @type command: C{dict}
        """
        retainDays = command.get("RetainDays", DEFAULT_RETAIN_DAYS)
        cutoff = PyCalendarDateTime.getToday()
        cutoff.setDateOnly(False)
        cutoff.offsetDay(-retainDays)
        eventCount = (yield PurgeOldEventsService.purgeOldEvents(self.store, cutoff, DEFAULT_BATCH_SIZE))
        respond(command, {'EventsRemoved' : eventCount, "RetainDays" : retainDays})



@inlineCallbacks
def respondWithProxies(directory, command, principal, proxyType):
    proxies = []
    subPrincipal = proxySubprincipal(principal, proxyType)
    if subPrincipal is not None:
        membersProperty = (yield subPrincipal.readProperty(davxml.GroupMemberSet, None))
        if membersProperty.children:
            for member in membersProperty.children:
                proxyPrincipal = principalForPrincipalID(str(member), directory=directory)
                proxies.append(proxyPrincipal.record.guid)

    respond(command, {
        'Principal' : principal.record.guid, 'Proxies' : proxies
    })



def recordToDict(record):
    recordDict = {}
    for key, info in attrMap.iteritems():
        try:
            if info.get('extras', False):
                value = record.extras[info['attr']]
            else:
                value = getattr(record, info['attr'])
            if isinstance(value, str):
                value = value.decode("utf-8")
            recordDict[key] = value
        except KeyError:
            pass
    return recordDict



def respondWithRecordsOfType(directory, command, recordType):
    result = []
    for record in directory.listRecords(recordType):
        recordDict = recordToDict(record)
        result.append(recordDict)
    respond(command, result)



def respond(command, result):
    sys.stdout.write(writePlistToString({'command' : command['command'], 'result' : result}))



def respondWithError(msg, status=1):
    sys.stdout.write(writePlistToString({'error' : msg, }))
    """
    try:
        reactor.stop()
    except RuntimeError:
        pass
    sys.exit(status)
    """

if __name__ == "__main__":
    main()
