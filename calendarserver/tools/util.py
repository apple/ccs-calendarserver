##
# Copyright (c) 2008-2009 Apple Inc. All rights reserved.
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
]

import sys
import os

from twisted.python.reflect import namedClass

from twistedcaldav.config import config, defaultConfigFile
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord

def loadConfig(configFileName):
    if configFileName is None:
        configFileName = defaultConfigFile

    if not os.path.isfile(configFileName):
        sys.stderr.write("No config file: %s\n" % (configFileName,))
        sys.exit(1)

    config.loadConfig(configFileName)

    return config

def getDirectory():
    BaseDirectoryService = namedClass(config.DirectoryService.type)

    class MyDirectoryService (BaseDirectoryService):
        def principalCollection(self):
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

        def calendarHomeForShortName(self, recordType, shortName):
            principal = self.principalCollection().principalForShortName(recordType, shortName)
            if principal:
                return principal.calendarHome()
            return None

    return MyDirectoryService(**config.DirectoryService.params)

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
    emailAddresses = (),
    calendarUserAddresses = (),
    autoSchedule = False,
)
