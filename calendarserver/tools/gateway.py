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

from getopt import getopt, GetoptError
import os
import sys
import xml

from twext.python.plistlib import readPlistFromString, writePlistToString

from twisted.internet.defer import inlineCallbacks, succeed
from twistedcaldav.directory.directory import DirectoryError
from txdav.xml import element as davxml

from calendarserver.tools.util import (
    principalForPrincipalID, proxySubprincipal, addProxy, removeProxy,
    ProxyError, ProxyWarning, autoDisableMemcached
)
from calendarserver.tools.principals import getProxies, setProxies, updateRecord
from calendarserver.tools.purge import WorkerService, PurgeOldEventsService, DEFAULT_BATCH_SIZE, DEFAULT_RETAIN_DAYS
from calendarserver.tools.cmdline import utilityMain

from pycalendar.datetime import DateTime

from twistedcaldav.config import config, ConfigDict

from calendarserver.tools.config import WRITABLE_CONFIG_KEYS, setKeyPath, getKeyPath, flattenDictionary, WritableConfig

def usage(e=None):

    name = os.path.basename(sys.argv[0])
    print("usage: %s [options]" % (name,))
    print("")
    print("  TODO: describe usage")
    print("")
    print("options:")
    print("  -h --help: print this help and exit")
    print("  -e --error: send stderr to stdout")
    print("  -f --config <path>: Specify caldavd.plist configuration path")
    print("")

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
        runner = Runner(rootResource, directory, self.store, self.commands)
        if runner.validate():
            yield runner.run()


    def doWorkWithoutStore(self):
        respondWithError("Database is not available")
        return succeed(None)



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
    'Geo' : { 'extras' : True, 'attr' : 'geo', },
    'AutoSchedule' : { 'attr' : 'autoSchedule', },
    'AutoAcceptGroup' : { 'attr' : 'autoAcceptGroup', },
}

class Runner(object):

    def __init__(self, root, directory, store, commands, output=None):
        self.root = root
        self.dir = directory
        self.store = store
        self.commands = commands
        if output is None:
            output = sys.stdout
        self.output = output


    def validate(self):
        # Make sure commands are valid
        for command in self.commands:
            if 'command' not in command:
                self.respondWithError("'command' missing from plist")
                return False
            commandName = command['command']
            methodName = "command_%s" % (commandName,)
            if not hasattr(self, methodName):
                self.respondWithError("Unknown command '%s'" % (commandName,))
                return False
        return True


    @inlineCallbacks
    def run(self):

        # This method can be called as the result of an agent request.  We
        # check to see if memcached is there for each call because the server
        # could have stopped/started since the last time.

        for pool in config.Memcached.Pools.itervalues():
            pool.ClientEnabled = True
        autoDisableMemcached(config)

        from twistedcaldav.directory import calendaruserproxy
        if calendaruserproxy.ProxyDBService is not None:
            # Reset the proxy db memcacher because memcached may have come or
            # gone since the last time through here.
            # TODO: figure out a better way to do this
            calendaruserproxy.ProxyDBService._memcacher._memcacheProtocol = None

        try:
            for command in self.commands:
                commandName = command['command']
                methodName = "command_%s" % (commandName,)
                if hasattr(self, methodName):
                    (yield getattr(self, methodName)(command))
                else:
                    self.respondWithError("Unknown command '%s'" % (commandName,))

        except Exception, e:
            self.respondWithError("Command failed: '%s'" % (str(e),))
            raise

    # Locations


    def command_getLocationList(self, command):
        self.respondWithRecordsOfTypes(self.dir, command, ["locations"])


    @inlineCallbacks
    def command_createLocation(self, command):
        kwargs = {}
        for key, info in attrMap.iteritems():
            if key in command:
                kwargs[info['attr']] = command[key]

        try:
            record = (yield updateRecord(True, self.dir, "locations", **kwargs))
        except DirectoryError, e:
            self.respondWithError(str(e))
            return

        readProxies = command.get("ReadProxies", None)
        writeProxies = command.get("WriteProxies", None)
        principal = principalForPrincipalID(record.guid, directory=self.dir)
        (yield setProxies(self.store, principal, readProxies, writeProxies, directory=self.dir))

        self.respondWithRecordsOfTypes(self.dir, command, ["locations"])


    @inlineCallbacks
    def command_getLocationAttributes(self, command):
        guid = command['GeneratedUID']
        record = self.dir.recordWithGUID(guid)
        if record is None:
            self.respondWithError("Principal not found: %s" % (guid,))
            return
        recordDict = recordToDict(record)
        principal = principalForPrincipalID(guid, directory=self.dir)
        if principal is None:
            self.respondWithError("Principal not found: %s" % (guid,))
            return
        recordDict['AutoSchedule'] = principal.getAutoSchedule()
        recordDict['AutoAcceptGroup'] = principal.getAutoAcceptGroup()
        recordDict['ReadProxies'], recordDict['WriteProxies'] = (yield getProxies(principal,
            directory=self.dir))
        self.respond(command, recordDict)

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
            self.respondWithError(str(e))
            return

        readProxies = command.get("ReadProxies", None)
        writeProxies = command.get("WriteProxies", None)
        principal = principalForPrincipalID(record.guid, directory=self.dir)
        (yield setProxies(self.store, principal, readProxies, writeProxies, directory=self.dir))

        yield self.command_getLocationAttributes(command)


    def command_deleteLocation(self, command):
        kwargs = {}
        for key, info in attrMap.iteritems():
            if key in command:
                kwargs[info['attr']] = command[key]
        try:
            self.dir.destroyRecord("locations", **kwargs)
        except DirectoryError, e:
            self.respondWithError(str(e))
            return
        self.respondWithRecordsOfTypes(self.dir, command, ["locations"])

    # Resources


    def command_getResourceList(self, command):
        self.respondWithRecordsOfTypes(self.dir, command, ["resources"])


    @inlineCallbacks
    def command_createResource(self, command):
        kwargs = {}
        for key, info in attrMap.iteritems():
            if key in command:
                kwargs[info['attr']] = command[key]

        try:
            record = (yield updateRecord(True, self.dir, "resources", **kwargs))
        except DirectoryError, e:
            self.respondWithError(str(e))
            return

        readProxies = command.get("ReadProxies", None)
        writeProxies = command.get("WriteProxies", None)
        principal = principalForPrincipalID(record.guid, directory=self.dir)
        (yield setProxies(self.store, principal, readProxies, writeProxies, directory=self.dir))

        self.respondWithRecordsOfTypes(self.dir, command, ["resources"])


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
            self.respondWithError(str(e))
            return

        readProxies = command.get("ReadProxies", None)
        writeProxies = command.get("WriteProxies", None)
        principal = principalForPrincipalID(record.guid, directory=self.dir)
        (yield setProxies(self.store, principal, readProxies, writeProxies, directory=self.dir))

        yield self.command_getResourceAttributes(command)


    def command_deleteResource(self, command):
        kwargs = {}
        for key, info in attrMap.iteritems():
            if key in command:
                kwargs[info['attr']] = command[key]
        try:
            self.dir.destroyRecord("resources", **kwargs)
        except DirectoryError, e:
            self.respondWithError(str(e))
            return
        self.respondWithRecordsOfTypes(self.dir, command, ["resources"])


    def command_getLocationAndResourceList(self, command):
        self.respondWithRecordsOfTypes(self.dir, command, ["locations", "resources"])


    # Config

    def command_readConfig(self, command):
        """
        Return current configuration

        @param command: the dictionary parsed from the plist read from stdin
        @type command: C{dict}
        """
        config.reload()
        # config.Memcached.Pools.Default.ClientEnabled = False

        result = {}
        for keyPath in WRITABLE_CONFIG_KEYS:
            value = getKeyPath(config, keyPath)
            if value is not None:
                # Note: config contains utf-8 encoded strings, but plistlib
                # wants unicode, so decode here:
                if isinstance(value, str):
                    value = value.decode("utf-8")
                setKeyPath(result, keyPath, value)
        self.respond(command, result)


    def command_writeConfig(self, command):
        """
        Write config to secondary, writable plist

        @param command: the dictionary parsed from the plist read from stdin
        @type command: C{dict}
        """
        writable = WritableConfig(config, config.WritableConfigFile)
        writable.read()
        valuesToWrite = command.get("Values", {})
        # Note: values are unicode if they contain non-ascii
        for keyPath, value in flattenDictionary(valuesToWrite):
            if keyPath in WRITABLE_CONFIG_KEYS:
                writable.set(setKeyPath(ConfigDict(), keyPath, value))
        try:
            writable.save(restart=False)
        except Exception, e:
            self.respond(command, {"error": str(e)})
        else:
            self.command_readConfig(command)


    # Proxies

    @inlineCallbacks
    def command_listWriteProxies(self, command):
        principal = principalForPrincipalID(command['Principal'], directory=self.dir)
        if principal is None:
            self.respondWithError("Principal not found: %s" % (command['Principal'],))
            return
        (yield self.respondWithProxies(self.dir, command, principal, "write"))


    @inlineCallbacks
    def command_addWriteProxy(self, command):
        principal = principalForPrincipalID(command['Principal'],
            directory=self.dir)
        if principal is None:
            self.respondWithError("Principal not found: %s" % (command['Principal'],))
            return

        proxy = principalForPrincipalID(command['Proxy'], directory=self.dir)
        if proxy is None:
            self.respondWithError("Proxy not found: %s" % (command['Proxy'],))
            return
        try:
            (yield addProxy(self.root, self.dir, self.store, principal, "write", proxy))
        except ProxyError, e:
            self.respondWithError(str(e))
            return
        except ProxyWarning, e:
            pass
        (yield self.respondWithProxies(self.dir, command, principal, "write"))


    @inlineCallbacks
    def command_removeWriteProxy(self, command):
        principal = principalForPrincipalID(command['Principal'], directory=self.dir)
        if principal is None:
            self.respondWithError("Principal not found: %s" % (command['Principal'],))
            return
        proxy = principalForPrincipalID(command['Proxy'], directory=self.dir)
        if proxy is None:
            self.respondWithError("Proxy not found: %s" % (command['Proxy'],))
            return
        try:
            (yield removeProxy(self.root, self.dir, self.store, principal, proxy, proxyTypes=("write",)))
        except ProxyError, e:
            self.respondWithError(str(e))
            return
        except ProxyWarning, e:
            pass
        (yield self.respondWithProxies(self.dir, command, principal, "write"))


    @inlineCallbacks
    def command_listReadProxies(self, command):
        principal = principalForPrincipalID(command['Principal'], directory=self.dir)
        if principal is None:
            self.respondWithError("Principal not found: %s" % (command['Principal'],))
            return
        (yield self.respondWithProxies(self.dir, command, principal, "read"))


    @inlineCallbacks
    def command_addReadProxy(self, command):
        principal = principalForPrincipalID(command['Principal'], directory=self.dir)
        if principal is None:
            self.respondWithError("Principal not found: %s" % (command['Principal'],))
            return
        proxy = principalForPrincipalID(command['Proxy'], directory=self.dir)
        if proxy is None:
            self.respondWithError("Proxy not found: %s" % (command['Proxy'],))
            return
        try:
            (yield addProxy(self.root, self.dir, self.store, principal, "read", proxy))
        except ProxyError, e:
            self.respondWithError(str(e))
            return
        except ProxyWarning, e:
            pass
        (yield self.respondWithProxies(self.dir, command, principal, "read"))


    @inlineCallbacks
    def command_removeReadProxy(self, command):
        principal = principalForPrincipalID(command['Principal'], directory=self.dir)
        if principal is None:
            self.respondWithError("Principal not found: %s" % (command['Principal'],))
            return
        proxy = principalForPrincipalID(command['Proxy'], directory=self.dir)
        if proxy is None:
            self.respondWithError("Proxy not found: %s" % (command['Proxy'],))
            return
        try:
            (yield removeProxy(self.root, self.dir, self.store, principal, proxy, proxyTypes=("read",)))
        except ProxyError, e:
            self.respondWithError(str(e))
            return
        except ProxyWarning, e:
            pass
        (yield self.respondWithProxies(self.dir, command, principal, "read"))


    @inlineCallbacks
    def command_purgeOldEvents(self, command):
        """
        Convert RetainDays from the command dictionary into a date, then purge
        events older than that date.

        @param command: the dictionary parsed from the plist read from stdin
        @type command: C{dict}
        """
        retainDays = command.get("RetainDays", DEFAULT_RETAIN_DAYS)
        cutoff = DateTime.getToday()
        cutoff.setDateOnly(False)
        cutoff.offsetDay(-retainDays)
        eventCount = (yield PurgeOldEventsService.purgeOldEvents(self.store, cutoff, DEFAULT_BATCH_SIZE))
        self.respond(command, {'EventsRemoved' : eventCount, "RetainDays" : retainDays})


    @inlineCallbacks
    def respondWithProxies(self, directory, command, principal, proxyType):
        proxies = []
        subPrincipal = proxySubprincipal(principal, proxyType)
        if subPrincipal is not None:
            membersProperty = (yield subPrincipal.readProperty(davxml.GroupMemberSet, None))
            if membersProperty.children:
                for member in membersProperty.children:
                    proxyPrincipal = principalForPrincipalID(str(member), directory=directory)
                    proxies.append(proxyPrincipal.record.guid)

        self.respond(command, {
            'Principal' : principal.record.guid, 'Proxies' : proxies
        })


    def respondWithRecordsOfTypes(self, directory, command, recordTypes):
        result = []
        for recordType in recordTypes:
            for record in directory.listRecords(recordType):
                recordDict = recordToDict(record)
                result.append(recordDict)
        self.respond(command, result)


    def respond(self, command, result):
        self.output.write(writePlistToString({'command' : command['command'], 'result' : result}))


    def respondWithError(self, msg, status=1):
        self.output.write(writePlistToString({'error' : msg, }))



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



def respondWithError(msg, status=1):
    sys.stdout.write(writePlistToString({'error' : msg, }))



if __name__ == "__main__":
    main()
