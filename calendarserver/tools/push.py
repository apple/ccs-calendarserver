#!/usr/bin/env python
##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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

from calendarserver.tap.util import getRootResource
from calendarserver.tools.cmdline import utilityMain
from errno import ENOENT, EACCES
from getopt import getopt, GetoptError
from twext.python.log import Logger
from twisted.application.service import Service
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twistedcaldav.config import config, ConfigurationError
import os
import sys
import time

log = Logger()

def usage(e=None):

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options] [user ...]" % (name,)
    print ""
    print "  Display Apple Push Notification subscriptions"
    print ""
    print "options:"
    print "  -h --help: print this help and exit"
    print "  -f --config <path>: Specify caldavd.plist configuration path"
    print ""

    if e:
        sys.stderr.write("%s\n" % (e,))
        sys.exit(64)
    else:
        sys.exit(0)


class WorkerService(Service):

    def __init__(self, store):
        self._store = store

    def rootResource(self):
        try:
            rootResource = getRootResource(config, self._store)
        except OSError, e:
            if e.errno == ENOENT:
                # Trying to re-write resources.xml but its parent directory does
                # not exist.  The server's never been started, so we're missing
                # state required to do any work.  (Plus, what would be the point
                # of purging stuff from a server that's completely empty?)
                raise ConfigurationError(
                    "It appears that the server has never been started.\n"
                    "Please start it at least once before purging anything.")
            elif e.errno == EACCES:
                # Trying to re-write resources.xml but it is not writable by the
                # current user.  This most likely means we're in a system
                # configuration and the user doesn't have sufficient privileges
                # to do the other things the tool might need to do either.
                raise ConfigurationError("You must run this tool as root.")
            else:
                raise
        return rootResource


    @inlineCallbacks
    def startService(self):
        try:
            yield self.doWork()
        except ConfigurationError, ce:
            sys.stderr.write("Error: %s\n" % (str(ce),))
        except Exception, e:
            sys.stderr.write("Error: %s\n" % (e,))
            raise
        finally:
            reactor.stop()


class DisplayAPNSubscriptions(WorkerService):

    users = []

    def doWork(self):
        rootResource = self.rootResource()
        directory = rootResource.getDirectory()
        return displayAPNSubscriptions(self._store, directory, rootResource,
            self.users)


def main():

    try:
        (optargs, args) = getopt(
            sys.argv[1:], "f:h", [
                "config=",
                "help",
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

    if not args:
        usage("Not enough arguments")


    DisplayAPNSubscriptions.users = args

    utilityMain(
        configFileName,
        DisplayAPNSubscriptions,
    )




@inlineCallbacks
def displayAPNSubscriptions(store, directory, root, users):
    for user in users:
        print
        record = directory.recordWithShortName("users", user)
        if record is not None:
            print "User %s (%s)..." % (user, record.uid)
            txn = store.newTransaction(label="Display APN Subscriptions")
            subscriptions = (yield txn.apnSubscriptionsBySubscriber(record.uid))
            (yield txn.commit())
            if subscriptions:
                byKey = { }
                for token, key, timestamp in subscriptions:
                    byKey.setdefault(key, []).append((token, timestamp))
                for key, tokens in byKey.iteritems():
                    print
                    protocol, host, path = key.strip("/").split("/", 2)
                    resource = {
                        "CalDAV" : "calendar",
                        "CardDAV" : "addressbook",
                    }[protocol]
                    if "/" in path:
                        uid, collection = path.split("/")
                    else:
                        uid = path
                        collection = None
                    record = directory.recordWithUID(uid)
                    user = record.shortNames[0]
                    if collection:
                        print "...is subscribed to a share from %s's %s home" % (user, resource),
                    else:
                        print "...is subscribed to %s's %s home" % (user, resource),
                        # print "   (key: %s)\n" % (key,)
                    print "with %d device(s):" % (len(tokens),)
                    for token, timestamp in tokens:
                        print " %s  %ss ago" % (token, int(time.time()) - timestamp)
            else:
                print " ...is not subscribed to anything."
        else:
            print "User %s not found" % (user,)
