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

__all__ = [
    "migrateResources",
]

from getopt import getopt, GetoptError
from grp import getgrnam
import os
from pwd import getpwnam
import sys

from calendarserver.tools.util import (
    loadConfig, setupMemcached, checkDirectory
)
from twext.python.log import Logger, StandardIOObserver
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.python.util import switchUID
from twistedcaldav.config import config, ConfigurationError
from txdav.who.util import directoryFromConfig

try:
    from twext.who.opendirectory import (
        DirectoryService as OpenDirectoryService
    )
except ImportError:
    pass

log = Logger()



def usage():

    name = os.path.basename(sys.argv[0])
    print("usage: %s [options] " % (name,))
    print("")
    print("  Migrates resources and locations from OD to Calendar Server")
    print("")
    print("options:")
    print("  -h --help: print this help and exit")
    print("  -f --config <path>: Specify caldavd.plist configuration path")
    print("  -v --verbose: print debugging information")
    print("")

    sys.exit(0)



def abort(msg, status=1):
    sys.stdout.write("%s\n" % (msg,))
    try:
        reactor.stop()
    except RuntimeError:
        pass
    sys.exit(status)



def main():
    try:
        (optargs, _ignore_args) = getopt(
            sys.argv[1:], "hf:v", [
                "help",
                "config=",
                "verbose",
            ],
        )
    except GetoptError, e:
        usage(e)

    #
    # Get configuration
    #
    configFileName = None
    verbose = False

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        elif opt in ("-v", "--verbose"):
            verbose = True

        elif opt in ("-f", "--config"):
            configFileName = arg

        else:
            raise NotImplementedError(opt)

    #
    # Get configuration
    #
    try:
        loadConfig(configFileName)

        # Do this first, because modifying the config object will cause
        # some logging activity at whatever log level the plist says
        log.publisher.levels.clearLogLevels()

        config.DefaultLogLevel = "info" if verbose else "error"

        #
        # Send logging output to stdout
        #
        observer = StandardIOObserver()
        observer.start()

        # Create the DataRoot directory before shedding privileges
        if config.DataRoot.startswith(config.ServerRoot + os.sep):
            checkDirectory(
                config.DataRoot,
                "Data root",
                access=os.W_OK,
                create=(0750, config.UserName, config.GroupName),
            )

        # Shed privileges
        if config.UserName and config.GroupName and os.getuid() == 0:
            uid = getpwnam(config.UserName).pw_uid
            gid = getgrnam(config.GroupName).gr_gid
            switchUID(uid, uid, gid)

        os.umask(config.umask)

        # Configure memcached client settings prior to setting up resource
        # hierarchy
        setupMemcached(config)

        config.directory = directoryFromConfig(config)

    except ConfigurationError, e:
        abort(e)

    sourceService = OpenDirectoryService()
    destService = config.directory

    #
    # Start the reactor
    #
    reactor.callLater(
        0, migrate, sourceService, destService, verbose=verbose
    )
    reactor.run()



@inlineCallbacks
def migrate(sourceService, destService, verbose=False):
    """
    Simply a wrapper around migrateResources in order to stop the reactor
    """

    try:
        yield migrateResources(sourceService, destService, verbose=verbose)
    finally:
        reactor.stop()



@inlineCallbacks
def migrateResources(sourceService, destService, verbose=False):

    destRecords = []

    for recordType in (
        sourceService.recordType.resource,
        sourceService.recordType.location,
    ):
        records = yield sourceService.recordsWithRecordType(recordType)
        for sourceRecord in records:
            destRecord = yield destService.recordWithUID(sourceRecord.uid)
            if destRecord is None:
                if verbose:
                    print(
                        "Migrating {name} {recordType} {uid}".format(
                            name=sourceRecord.displayName,
                            recordType=recordType.name,
                            uid=sourceRecord.uid
                        )
                    )
                destRecord = type(sourceRecord)(destService, sourceRecord.fields.copy())
                destRecords.append(destRecord)

    if destRecords:
        yield destService.updateRecords(destRecords, create=True)



if __name__ == "__main__":
    main()
