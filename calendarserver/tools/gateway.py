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

import sys
import os
import plistlib
import xml

import operator
from getopt import getopt, GetoptError
from pwd import getpwnam
from grp import getgrnam

from twisted.python.util import switchUID

from twistedcaldav.config import config, ConfigurationError
from twistedcaldav.directory.directory import DirectoryError

from calendarserver.tools.util import loadConfig, getDirectory, autoDisableMemcached

def usage(e=None):

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options]" % (name,)
    print ""
    print "  TODO: describe usage"
    print ""
    print "options:"
    print "  -h --help: print this help and exit"
    print "  -f --config <path>: Specify caldavd.plist configuration path"
    print ""

    if e:
        sys.exit(64)
    else:
        sys.exit(0)


def main():

    try:
        (optargs, args) = getopt(
            sys.argv[1:], "hf:", [
                "help",
                "config=",
            ],
        )
    except GetoptError, e:
        usage(e)

    #
    # Get configuration
    #
    configFileName = None

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        elif opt in ("-f", "--config"):
            configFileName = arg

        else:
            raise NotImplementedError(opt)

    try:
        loadConfig(configFileName)

        # Shed privileges
        if config.UserName and config.GroupName and os.getuid() == 0:
            uid = getpwnam(config.UserName).pw_uid
            gid = getgrnam(config.GroupName).gr_gid
            switchUID(uid, uid, gid)

        os.umask(config.umask)

        try:
            config.directory = getDirectory()
        except DirectoryError, e:
            abort(e)
        autoDisableMemcached(config)
    except ConfigurationError, e:
        abort(e)

    #
    # Read commands from stdin
    #
    rawInput = sys.stdin.read()
    try:
        plist = plistlib.readPlistFromString(rawInput)
    except xml.parsers.expat.ExpatError, e:
        abort(str(e))

    # If the plist is an array, each element of the array is a separate
    # command dictionary.
    if isinstance(plist, list):
        commands = plist
    else:
        commands = [plist]

    runner = Runner(config.directory, commands)
    runner.validate()
    runner.run()



class Runner(object):

    def __init__(self, directory, commands):
        self.dir = directory
        self.commands = commands

    def validate(self):
        # Make sure commands are valid
        for command in self.commands:
            if not command.has_key('command'):
                abort("'command' missing from plist")
            commandName = command['command']
            methodName = "command_%s" % (commandName,)
            if not hasattr(self, methodName):
                abort("Unknown command '%s'" % (commandName,))

    def run(self):
        for command in self.commands:
            commandName = command['command']
            methodName = "command_%s" % (commandName,)
            if hasattr(self, methodName):
                getattr(self, methodName)(command)
            else:
                abort("Unknown command '%s'" % (commandName,))

    # Locations

    def command_getLocationList(self, command):
        respondWithRecordsOfType(self.dir, command, "locations")

    def command_createLocation(self, command):
        try:
            self.dir.createRecord("locations", guid=command['GeneratedUID'],
                shortNames=command['RecordName'], fullName=command['RealName'])
        except DirectoryError, e:
            abort(str(e))
        respondWithRecordsOfType(self.dir, command, "locations")

    def command_deleteLocation(self, command):
        try:
            self.dir.destroyRecord("locations", guid=command['GeneratedUID'])
        except DirectoryError, e:
            abort(str(e))
        respondWithRecordsOfType(self.dir, command, "locations")

    # Resources

    def command_getResourceList(self, command):
        respondWithRecordsOfType(self.dir, command, "resources")

    def command_createResource(self, command):
        try:
            self.dir.createRecord("resources", guid=command['GeneratedUID'],
                shortNames=command['RecordName'], fullName=command['RealName'])
        except DirectoryError, e:
            abort(str(e))
        respondWithRecordsOfType(self.dir, command, "resources")

    def command_deleteResource(self, command):
        try:
            self.dir.destroyRecord("resources", guid=command['GeneratedUID'])
        except DirectoryError, e:
            abort(str(e))
        respondWithRecordsOfType(self.dir, command, "resources")


def respondWithRecordsOfType(directory, command, recordType):
    result = []
    for record in directory.listRecords(recordType):
        result.append( {
            'GeneratedUID' : record.guid,
            'RecordName' : [n for n in record.shortNames],
            'RealName' : record.fullName,
            'AutoSchedule' : record.autoSchedule,
        } )
    respond(command, result)

def respond(command, result):
    sys.stdout.write(plistlib.writePlistToString( { 'command' : command['command'], 'result' : result } ) )

def abort(msg, status=1):
    sys.stdout.write(plistlib.writePlistToString( { 'error' : msg, } ) )
    sys.exit(status)

if __name__ == "__main__":
    main()
