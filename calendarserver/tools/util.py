##
# Copyright (c) 2008-2010 Apple Inc. All rights reserved.
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

__all__ = [
    "loadConfig",
    "getDirectory",
    "dummyDirectoryRecord",
    "UsageError",
    "booleanArgument",
]

import os
from time import sleep
import socket

from twisted.python.reflect import namedClass

from calendarserver.provision.root import RootResource
from twistedcaldav import memcachepool
from twistedcaldav.config import config, ConfigurationError
from twistedcaldav.directory import augment, calendaruserproxy
from twistedcaldav.directory.aggregate import AggregateDirectoryService
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.notify import installNotificationClient
from twistedcaldav.static import CalendarHomeProvisioningFile
from twistedcaldav.stdconfig import DEFAULT_CONFIG_FILE


def loadConfig(configFileName):
    if configFileName is None:
        configFileName = DEFAULT_CONFIG_FILE

    if not os.path.isfile(configFileName):
        raise ConfigurationError("No config file: %s" % (configFileName,))

    config.load(configFileName)

    return config

def getDirectory():

    class MyDirectoryService (AggregateDirectoryService):
        def getPrincipalCollection(self):
            if not hasattr(self, "_principalCollection"):
                #
                # Instantiating a CalendarHomeProvisioningResource with a directory
                # will register it with the directory (still smells like a hack).
                #
                # We need that in order to locate calendar homes via the directory.
                #
                from twistedcaldav.static import CalendarHomeProvisioningFile
                CalendarHomeProvisioningFile(os.path.join(config.DocumentRoot, "calendars"), self, "/calendars/")

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
                    return principal.calendarHome()
                except AttributeError:
                    pass
            return None

        def calendarHomeForShortName(self, recordType, shortName):
            principal = self.principalCollection.principalForShortName(recordType, shortName)
            if principal:
                return principal.calendarHome()
            return None

        def principalForCalendarUserAddress(self, cua):
            return self.principalCollection.principalForCalendarUserAddress(cua)


    # Load augment/proxy db classes now
    augmentClass = namedClass(config.AugmentService.type)
    augment.AugmentService = augmentClass(**config.AugmentService.params)

    proxydbClass = namedClass(config.ProxyDBService.type)
    calendaruserproxy.ProxyDBService = proxydbClass(**config.ProxyDBService.params)

    # Wait for directory service to become available
    BaseDirectoryService = namedClass(config.DirectoryService.type)
    directory = BaseDirectoryService(config.DirectoryService.params)
    while not directory.isAvailable():
        sleep(5)


    directories = [directory]

    if config.ResourceService.Enabled:
        resourceClass = namedClass(config.ResourceService.type)
        resourceDirectory = resourceClass(config.ResourceService.params)
        directories.append(resourceDirectory)

    aggregate = MyDirectoryService(directories)

    #
    # Wire up the resource hierarchy
    #
    principalCollection = aggregate.getPrincipalCollection()
    root = RootResource(
        config.DocumentRoot,
        principalCollections=(principalCollection,),
    )
    root.putChild("principals", principalCollection)
    calendarCollection = CalendarHomeProvisioningFile(
        os.path.join(config.DocumentRoot, "calendars"),
        aggregate, "/calendars/",
    )
    root.putChild("calendars", calendarCollection)

    return aggregate

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
    firstName = "Dummy",
    lastName = "McDummerson",
)

class UsageError (StandardError):
    pass

def booleanArgument(arg):
    if   arg in ("true",  "yes", "yup",  "uh-huh", "1", "t", "y"):
        return True
    elif arg in ("false", "no",  "nope", "nuh-uh", "0", "f", "n"):
        return False
    else:
        raise ValueError("Not a boolean: %s" % (arg,))

def autoDisableMemcached(config):
    """
    If memcached is not running, set config.Memcached.ClientEnabled to False
    """

    if not config.Memcached.Pools.Default.ClientEnabled:
        return

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        s.connect((config.Memcached.Pools.Default.BindAddress, config.Memcached.Pools.Default.Port))
        s.close()

    except socket.error:
        config.Memcached.Pools.Default.ClientEnabled = False


def setupMemcached(config):
    #
    # Connect to memcached
    #
    memcachepool.installPools(
        config.Memcached.Pools,
        config.Memcached.MaxClients
    )
    autoDisableMemcached(config)

def setupNotifications(config):
    #
    # Connect to notifications
    #
    if config.Notifications.Enabled:
        installNotificationClient(
            config.Notifications.InternalNotificationHost,
            config.Notifications.InternalNotificationPort,
        )

