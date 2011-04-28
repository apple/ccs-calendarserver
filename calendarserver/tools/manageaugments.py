#!/usr/bin/env python
##
# Copyright (c) 2009-2011 Apple Inc. All rights reserved.
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

from calendarserver.tools.loadaugmentdb import StandardIOObserver
from calendarserver.tools.util import loadConfig, getDirectory,\
    autoDisableMemcached
from grp import getgrnam
from optparse import OptionParser
from pwd import getpwnam
from twext.python.log import setLogLevelForNamespace
from twisted.internet import reactor
from twisted.python.util import switchUID
from twistedcaldav.config import config, ConfigurationError
from twistedcaldav.directory import augment
from twistedcaldav.directory.augment import AugmentRecord
import os
import sys
from twisted.internet.defer import inlineCallbacks

def error(s):
    print s
    sys.exit(1)

def main():

    usage = "%prog [options] ACTION"
    epilog = """
ACTION is one of add|modify|remove|print

  add:    add a user record
  modify: modify a user record
  remove: remove a user record
"""
    description = "Tool to manipulate CalendarServer augments XML file"
    version = "%prog v1.0"
    parser = OptionParser(usage=usage, description=description, version=version)
    parser.epilog = epilog
    parser.format_epilog = lambda _:epilog

    parser.add_option("-f", "--file", dest="configfilename",
                      help="caldavd.plist defining Augment Service", metavar="FILE")
    parser.add_option("-u", "--uid", dest="uid",
                      help="OD GUID to manipulate", metavar="UID")
    parser.add_option("-i", "--uidfile", dest="uidfile",
                      help="File containing a list of GUIDs to manipulate", metavar="UIDFILE")
    parser.add_option("-s", "--server", dest="serverID",
                      help="Server id to assign to UID", metavar="SERVER")
    parser.add_option("-p", "--partition", dest="partitionID",
                      help="Partition id to assign to UID", metavar="PARTITION")
    parser.add_option("-c", "--enable-calendar", action="store_true", dest="enable_calendar",
                      default=True, help="Enable calendaring for this UID: %default")
    parser.add_option("-a", "--enable-addressbooks", action="store_true", dest="enable_addressbook",
                      default=True, help="Enable calendaring for this UID: %default")
    parser.add_option("-x", "--auto-schedule", action="store_true", dest="auto_schedule",
                      default=False, help="Enable auto-schedule for this UID: %default")

    (options, args) = parser.parse_args()

    if len(args) != 1:
        parser.error("incorrect number of arguments")

    observer = StandardIOObserver()
    observer.start()

    #
    # Get configuration
    #
    try:
        loadConfig(options.configfilename)
        setLogLevelForNamespace(None, "warn")

        # Shed privileges
        if config.UserName and config.GroupName and os.getuid() == 0:
            uid = getpwnam(config.UserName).pw_uid
            gid = getgrnam(config.GroupName).gr_gid
            switchUID(uid, uid, gid)

        os.umask(config.umask)

        config.directory = getDirectory()
        autoDisableMemcached(config)
    except ConfigurationError, e:
        usage("Unable to start: %s" % (e,))

    #
    # Start the reactor
    #
    reactor.callLater(0, run, parser, options, args)
    reactor.run()

def makeRecord(uid, options):
    return AugmentRecord(
        uid = uid,
        enabled = True,
        serverID = options.serverID,
        partitionID = options.partitionID,
        enabledForCalendaring = options.enable_calendar,
        enabledForAddressBooks = options.enable_addressbook,
        autoSchedule = options.auto_schedule,
    )

@inlineCallbacks
def run(parser, options, args):
    
    try:
        uids = []
        if options.uid:
            uids.append(options.uid)
        elif options.uidfile:
            if not os.path.exists(options.uidfile):
                parser.error("File containing list of UIDs does not exist")
            with open(options.uidfile) as f:
                for line in f:
                    uids.append(line[:-1])
            
        if args[0] == "add":
            yield augment.AugmentService.addAugmentRecords([makeRecord(uid, options) for uid in uids])
            for uid in uids:
                print "Added uid '%s' to augment database" % (uid,)
        elif args[0] == "modify":
            yield augment.AugmentService.addAugmentRecords([makeRecord(uid, options) for uid in uids])
            for uid in uids:
                print "Modified uid '%s' in augment database" % (uid,)
        elif args[0] == "remove":
            yield augment.AugmentService.removeAugmentRecords(uids)
            for uid in uids:
                print "Removed uid '%s' from augment database" % (uid,)
        else:
            parser.error("Unknown argument")
    finally:
        reactor.stop()

if __name__ == '__main__':
    main()
