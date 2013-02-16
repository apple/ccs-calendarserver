##
# Copyright (c) 2008-2013 Apple Inc. All rights reserved.
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

"""
Utility functionality shared between calendarserver tools.
"""

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
from pwd import getpwnam
from grp import getgrnam

from twisted.python.filepath import FilePath
from twisted.python.reflect import namedClass
from twext.python.log import Logger


from calendarserver.provision.root import RootResource

from twistedcaldav import memcachepool
from twistedcaldav.config import config, ConfigurationError
from twistedcaldav.directory import calendaruserproxy
from twistedcaldav.directory.aggregate import AggregateDirectoryService
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from calendarserver.push.notifier import NotifierFactory
from twistedcaldav.stdconfig import DEFAULT_CONFIG_FILE

from txdav.common.datastore.file import CommonDataStore

log = Logger()

def loadConfig(configFileName):
    """
    Helper method for command-line utilities to load configuration plist
    and override certain values.
    """
    if configFileName is None:
        configFileName = DEFAULT_CONFIG_FILE

    if not os.path.isfile(configFileName):
        raise ConfigurationError("No config file: %s" % (configFileName,))

    config.load(configFileName)

    # Command-line utilities always want these enabled:
    config.EnableCalDAV = True
    config.EnableCardDAV = True

    return config

def getDirectory(config=config):

    class MyDirectoryService (AggregateDirectoryService):
        def getPrincipalCollection(self):
            if not hasattr(self, "_principalCollection"):

                if config.Notifications.Enabled:
                    # FIXME: NotifierFactory needs reference to the store in order
                    # to get a txn in order to create a Work item
                    notifierFactory = NotifierFactory(
                        None, config.ServerHostName,
                    )
                else:
                    notifierFactory = None

                # Need a data store
                _newStore = CommonDataStore(FilePath(config.DocumentRoot), 
                    notifierFactory, True, False)
                if notifierFactory is not None:
                    notifierFactory.store = _newStore

                #
                # Instantiating a DirectoryCalendarHomeProvisioningResource with a directory
                # will register it with the directory (still smells like a hack).
                #
                # We need that in order to locate calendar homes via the directory.
                #
                from twistedcaldav.directory.calendar import DirectoryCalendarHomeProvisioningResource
                DirectoryCalendarHomeProvisioningResource(self, "/calendars/", _newStore)

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
    if config.AugmentService.type:
        augmentClass = namedClass(config.AugmentService.type)
        augmentService = augmentClass(**config.AugmentService.params)
    else:
        augmentService = None

    proxydbClass = namedClass(config.ProxyDBService.type)
    calendaruserproxy.ProxyDBService = proxydbClass(**config.ProxyDBService.params)

    # Wait for directory service to become available
    BaseDirectoryService = namedClass(config.DirectoryService.type)
    config.DirectoryService.params.augmentService = augmentService
    directory = BaseDirectoryService(config.DirectoryService.params)
    while not directory.isAvailable():
        sleep(5)


    directories = [directory]

    if config.ResourceService.Enabled:
        resourceClass = namedClass(config.ResourceService.type)
        config.ResourceService.params.augmentService = augmentService
        resourceDirectory = resourceClass(config.ResourceService.params)
        resourceDirectory.realmName = directory.realmName
        directories.append(resourceDirectory)

    aggregate = MyDirectoryService(directories, None)
    aggregate.augmentService = augmentService

    #
    # Wire up the resource hierarchy
    #
    principalCollection = aggregate.getPrincipalCollection()
    root = RootResource(
        config.DocumentRoot,
        principalCollections=(principalCollection,),
    )
    root.putChild("principals", principalCollection)

    # Need a data store
    _newStore = CommonDataStore(FilePath(config.DocumentRoot), None, True, False)

    from twistedcaldav.directory.calendar import DirectoryCalendarHomeProvisioningResource
    calendarCollection = DirectoryCalendarHomeProvisioningResource(
        aggregate, "/calendars/",
        _newStore,
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


def checkDirectory(dirpath, description, access=None, create=None, wait=False):
    """
    Make sure dirpath is an existing directory, and optionally ensure it has the
    expected permissions.  Alternatively the function can create the directory or
    can wait for someone else to create it.

    @param dirpath: The directory path we're checking
    @type dirpath: string
    @param description: A description of what the directory path represents, used in
        log messages
    @type description: string
    @param access: The type of access we're expecting, either os.W_OK or os.R_OK
    @param create: A tuple of (file permissions mode, username, groupname) to use
        when creating the directory.  If create=None then no attempt will be made
        to create the directory.
    @type create: tuple
    @param wait: Wether the function should wait in a loop for the directory to be
        created by someone else (or mounted, etc.)
    @type wait: boolean
    """
    if not os.path.exists(dirpath):

        if wait:
            while not os.path.exists(dirpath):
                log.error("Path does not exist: %s" % (dirpath,))
                sleep(1)
        else:
            try:
                mode, username, groupname = create
            except TypeError:
                raise ConfigurationError("%s does not exist: %s"
                                         % (description, dirpath))
            try:
                os.mkdir(dirpath)
            except (OSError, IOError), e:
                log.error("Could not create %s: %s" % (dirpath, e))
                raise ConfigurationError(
                    "%s does not exist and cannot be created: %s"
                    % (description, dirpath)
                )

            if username:
                uid = getpwnam(username).pw_uid
            else:
                uid = -1

            if groupname:
                gid = getgrnam(groupname).gr_gid
            else:
                gid = -1

            try:
                os.chmod(dirpath, mode)
                os.chown(dirpath, uid, gid)
            except (OSError, IOError), e:
                log.error("Unable to change mode/owner of %s: %s"
                               % (dirpath, e))

            log.info("Created directory: %s" % (dirpath,))

    if not os.path.isdir(dirpath):
        raise ConfigurationError("%s is not a directory: %s"
                                 % (description, dirpath))

    if access and not os.access(dirpath, access):
        raise ConfigurationError(
            "Insufficient permissions for server on %s directory: %s"
            % (description, dirpath)
        )



