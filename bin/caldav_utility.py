#!/usr/bin/env python

##
# Copyright (c) 2006-2009 Apple Inc. All rights reserved.
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

from __future__ import with_statement

import sys

if "PYTHONPATH" in globals():
    sys.path.insert(0, PYTHONPATH)
else:
    from os.path import dirname, abspath, join
    from subprocess import Popen, PIPE

    home = dirname(dirname(abspath(__file__)))
    run = join(home, "run")

    child = Popen((run, "-p"), stdout=PIPE)
    path, stderr = child.communicate()

    if child.wait() == 0:
        sys.path[0:0] = path.split(":")

# sys.path.insert(0, "/usr/share/caldavd/lib/python")

import os
import itertools
from code import interact

from getopt import getopt, GetoptError
from os.path import dirname, abspath

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.python import log
from twisted.python.reflect import namedClass
from twisted.web2.dav import davxml
# from twisted.web2.http import Request

from twistedcaldav import ical
from twistedcaldav import caldavxml
from twistedcaldav.resource import isPseudoCalendarCollectionResource
from twistedcaldav.static import CalDAVFile, CalendarHomeFile, CalendarHomeProvisioningFile
from twistedcaldav.config import config, defaultConfigFile
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource

from calendarserver.provision.root import RootResource


from twistedcaldav import memcachepool
from twistedcaldav.notify import installNotificationClient
from twisted.internet.address import IPv4Address

# This dictionary is a mapping of symbols that other modules might want
# to use; it's populated by the @exportmethod decorator below.
exportedSymbols = { }

def exportmethod(method):
    """ Add the method to exportedSymbols """
    global exportedSymbols
    exportedSymbols[method.func_name] = method
    return method

def getExports(**kw):
    """ Return a copy of exportedSymbols, with kw included """
    exports = exportedSymbols.copy()
    exports.update(**kw)
    return exports



def loadConfig(configFileName):
    if configFileName is None:
        configFileName = defaultConfigFile

    if not os.path.isfile(configFileName):
        sys.stderr.write("No config file: %s\n" % (configFileName,))
        sys.exit(1)

    config.loadConfig(configFileName)

    return config


def getDirectory():
    BaseDirectoryService = namedClass(config.DirectoryService["type"])

    class MyDirectoryService (BaseDirectoryService):
        def getPrincipalCollection(self):
            if not hasattr(self, "_principalCollection"):
                from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
                self._principalCollection = DirectoryPrincipalProvisioningResource("/principals/", self)

            return self._principalCollection

        def setPrincipalCollection(self, coll):
            # See principal.py line 237:  self.directory.principalCollection = self
            pass

        principalCollection = property(getPrincipalCollection, setPrincipalCollection)

        def calendarHomeForRecord(self, record):
            principal = self.principalCollection.principalForRecord(record)
            if principal:
                try:
                    return principal._calendarHome()
                except AttributeError:
                    pass
            return None

        def calendarHomeForShortName(self, recordType, shortName):
            principal = self.principalCollection.principalForShortName(recordType, shortName)
            if principal:
                try:
                    return principal._calendarHome()
                except AttributeError:
                    pass
            return None

        def principalForCalendarUserAddress(self, cua):
            return self.principalCollection.principalForCalendarUserAddress(cua)


    return MyDirectoryService(**config.DirectoryService["params"])

class DummyDirectoryService (DirectoryService):
    realmName = ""
    baseGUID = "51856FD4-5023-4890-94FE-4356C4AAC3E4"
    def recordTypes(self): return ()
    def listRecords(self): return ()
    def recordWithShortName(self): return None

dummyDirectoryRecord = DirectoryRecord(
    service = DummyDirectoryService(),
    recordType = "dummy",
    guid = "8EF0892F-7CB6-4B8E-B294-7C5A5321136A",
    shortNames = ("dummy",),
    fullName = "Dummy McDummerson",
    calendarUserAddresses = set(),
    autoSchedule = False,
)

def setup():

    directory = getDirectory()
    if config.Memcached["ClientEnabled"]:
        memcachepool.installPool(
            IPv4Address(
                'TCP',
                config.Memcached["BindAddress"],
                config.Memcached["Port"]
            ),
            config.Memcached["MaxClients"]
        )
    if config.Notifications["Enabled"]:
        installNotificationClient(
            config.Notifications["InternalNotificationHost"],
            config.Notifications["InternalNotificationPort"],
        )
    principalCollection = directory.getPrincipalCollection()
    root = RootResource(
        config.DocumentRoot,
        principalCollections=(principalCollection,),
    )
    root.putChild("principals", principalCollection)
    calendarCollection = CalendarHomeProvisioningFile(
        os.path.join(config.DocumentRoot, "calendars"),
        directory, "/calendars/",
    )
    root.putChild("calendars", calendarCollection)

    return (directory, root)



class UsageError (StandardError):
    pass

def usage(e=None):
    if e:
        print e
        print ""

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options] [input_specifiers]" % (name,)
    print ""
    print "Change calendar user addresses"
    print __doc__
    print "options:"
    print "  -h --help: print this help and exit"
    print "  -f --config: Specify caldavd.plist configuration path"
    print ""
    print "input specifiers:"
    print "  -c --changes: add all calendar homes"
    print "  --dry-run: Don't actually change the data"

    if e:
        sys.exit(64)
    else:
        sys.exit(0)

def loadChanges(fileName):
    addresses = {}
    with open(fileName) as input:
        count = 1
        for line in input:
            line = line.strip()
            if line and not line.startswith("#"):
                try:
                    oldAddr, newAddr = line.split()
                    addresses[oldAddr] = newAddr
                except Exception, e:
                    print "Could not parse line %d: %s" % (count, line)
                    sys.exit(2)
            count += 1
    return addresses




class ResourceWrapper(object):

    def __init__(self, resource):
        self.resource = resource

@exportmethod
def byPath(root, path):
    resource = root
    segments = path.strip("/").split("/")
    for segment in segments:
        resource = resource.getChild(segment)
    return ResourceWrapper(resource)

def main():
    try:
        (optargs, args) = getopt(
            sys.argv[1:], "hf:", [
                "config=",
                "help",
                "dry-run",
            ],
        )
    except GetoptError, e:
        usage(e)

    configFileName = None
    logFileName = "/dev/stdout"
    modifyData = True
    changesFile = None

    directory = None
    calendarHomePaths = set()
    calendarHomes = set()

    def checkExists(resource):
        if not resource.exists():
            sys.stderr.write("No such file: %s\n" % (resource.fp.path,))
            sys.exit(1)

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        elif opt in ("-f", "--config"):
            configFileName = arg

        elif opt in ("--dry-run",):
            modifyData = False

    if args:
        usage("Too many arguments: %s" % (" ".join(args),))

    observer = log.FileLogObserver(open(logFileName, "a"))
    log.addObserver(observer.emit)

    loadConfig(configFileName)

    directory, root = setup()
    exportedSymbols['root'] = root
    exportedSymbols['directory'] = directory

    banner = "\nWelcome to calendar server\n"
    interact(banner, None, getExports(__name__="__console__", __doc__=None))


if __name__ == "__main__":

    main()
