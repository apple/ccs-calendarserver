##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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
    "CardDAVServiceMaker",
]

import errno
import os

from zope.interface import implements

from twisted.python.filepath import FilePath
from twisted.plugin import IPlugin
from twisted.internet.reactor import callLater
from twisted.application.service import IServiceMaker

from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource

from twistedcaldav.config import config
from twistedcaldav.stdconfig import DEFAULT_CARDDAV_CONFIG_FILE
from twistedcaldav.static import AddressBookHomeProvisioningFile, DirectoryBackedAddressBookFile
from twext.log import Logger

log = Logger()

from calendarserver.tap.caldav import CalDAVServiceMaker, CalDAVOptions

try:
    from twistedcaldav.authkerb import NegotiateCredentialFactory
except ImportError:
    NegotiateCredentialFactory = None

from calendarserver.provision.root import RootResource as _ParentRootResource



class RootResource (_ParentRootResource):
    """
    A special root resource that contains support checking SACLs
    as well as adding responseFilters.
    """

    saclService = "addressbook"



class CardDAVOptions(CalDAVOptions):
    """
    The same as L{CalDAVOptions}, but with a different default config file.
    """

    optParameters = [[
        "config", "f", DEFAULT_CARDDAV_CONFIG_FILE, "Path to configuration file."
    ]]



class CardDAVServiceMaker (CalDAVServiceMaker):
    implements(IPlugin, IServiceMaker)

    tapname = "carddav"
    description = "Darwin Contacts Server"
    options = CardDAVOptions

    #
    # Default resource classes
    #
    rootResourceClass            = RootResource
    principalResourceClass       = DirectoryPrincipalProvisioningResource
    addressBookResourceClass     = AddressBookHomeProvisioningFile
    directoryBackedAddressBookResourceClass = DirectoryBackedAddressBookFile

    def makeService_Slave(self, options):
        result = super(CardDAVServiceMaker, self).makeService_Slave(options)

        directory = self.directory
        principalCollection = self.principalCollection

        if config.EnableCardDAV:
            log.info("Setting up address book collection: %r" % (self.addressBookResourceClass,))
    
            addressBookCollection = self.addressBookResourceClass(
                os.path.join(config.DocumentRoot, "addressbooks"),
                directory, "/addressbooks/"
            )
            
            directoryPath = os.path.join(config.DocumentRoot, "directory")
            doBacking = config.DirectoryAddressBook and config.EnableSearchAddressBook
            if doBacking:
                log.info("Setting up directory address book: %r" % (self.directoryBackedAddressBookResourceClass,))
    
                directoryBackedAddressBookCollection = self.directoryBackedAddressBookResourceClass(
                    directoryPath,
                    principalCollections=(principalCollection,)
                )
                # do this after process is owned by carddav user, not root
                callLater(1.0, directoryBackedAddressBookCollection.provisionDirectory)
            else:
                # remove /directory from previous runs that may have created it
                try:
                    FilePath(directoryPath).remove()
                    self.log_info("Deleted: %s" %    directoryPath)
                except (OSError, IOError), e:
                    if e.errno != errno.ENOENT:
                        self.log_error("Could not delete: %s : %r" %  (directoryPath, e,))
            root = self.root

            root.putChild('addressbooks', addressBookCollection)
            if doBacking:
                root.putChild('directory', directoryBackedAddressBookCollection)
        return result

    makeService_Single   = makeService_Slave
