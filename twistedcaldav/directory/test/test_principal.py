##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

#from twisted.web2 import responsecode
#from twisted.web2.iweb import IResponse
#from twisted.web2.dav import davxml
#from twisted.web2.dav.util import davXMLFromStream
#from twisted.web2.test.test_server import SimpleRequest
#from twistedcaldav import caldavxml

import os

from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.web2.dav.fileop import rmdir

from twistedcaldav.static import CalendarHomeProvisioningFile
from twistedcaldav.directory.apache import BasicDirectoryService, DigestDirectoryService
from twistedcaldav.directory.test.test_apache import basicUserFile, digestUserFile, groupFile
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.directory.test.test_xmlfile import xmlFile
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory.principal import DirectoryPrincipalTypeResource
from twistedcaldav.directory.principal import DirectoryPrincipalResource

import twistedcaldav.test.util

directoryServices = (
    BasicDirectoryService(basicUserFile, groupFile),
    DigestDirectoryService(digestUserFile, groupFile),
    XMLDirectoryService(xmlFile),
)

class ProvisionedPrincipals (twistedcaldav.test.util.TestCase):
    """
    Directory service provisioned principals.
    """
    def setUp(self):
        super(ProvisionedPrincipals, self).setUp()
        
        # Set up a principals hierarchy for each service we're testing with
        self.principalRootResources = {}
        for directory in directoryServices:
            url = "/" + directory.__class__.__name__ + "/"
            path = os.path.join(self.docroot, url[1:])

            if os.path.exists(path):
                rmdir(path)
            os.mkdir(path)

            provisioningResource = DirectoryPrincipalProvisioningResource(path, url, directory)

            self.principalRootResources[directory.__class__.__name__] = provisioningResource

    @deferredGenerator
    def test_hierarchy(self):
        """
        DirectoryPrincipalProvisioningResource.listChildren(),
        DirectoryPrincipalProvisioningResource.getChildren(),
        DirectoryPrincipalProvisioningResource.principalCollectionURL(),
        DirectoryPrincipalProvisioningResource.principalCollections()

        DirectoryPrincipalTypeResource.listChildren(),
        DirectoryPrincipalTypeResource.getChildren(),
        DirectoryPrincipalTypeResource.principalCollectionURL(),
        DirectoryPrincipalTypeResource.principalCollections()

        DirectoryPrincipalResource.principalURL(),
        """
        for directory in directoryServices:
            #print "\n -> %s" % (directory.__class__.__name__,)
            provisioningResource = self.principalRootResources[directory.__class__.__name__]

            provisioningURL = "/" + directory.__class__.__name__ + "/"
            self.assertEquals(provisioningURL, provisioningResource.principalCollectionURL())

            principalCollections = waitForDeferred(provisioningResource.principalCollections(None))
            yield principalCollections
            principalCollections = principalCollections.getResult()
            self.assertEquals(set((provisioningURL,)), set(principalCollections))

            recordTypes = set(provisioningResource.listChildren())
            self.assertEquals(recordTypes, set(directory.recordTypes()))

            for recordType in recordTypes:
                #print "   -> %s" % (recordType,)
                typeResource = provisioningResource.getChild(recordType)
                self.failUnless(isinstance(typeResource, DirectoryPrincipalTypeResource))

                typeURL = provisioningURL + recordType + "/"
                self.assertEquals(typeURL, typeResource.principalCollectionURL())

                principalCollections = waitForDeferred(typeResource.principalCollections(None))
                yield principalCollections
                principalCollections = principalCollections.getResult()
                self.assertEquals(set((provisioningURL,)), set(principalCollections))

                shortNames = set(typeResource.listChildren())
                self.assertEquals(shortNames, set(r.shortName for r in directory.listRecords(recordType)))
                
                for shortName in shortNames:
                    #print "     -> %s" % (shortName,)
                    recordResource = typeResource.getChild(shortName)
                    self.failUnless(isinstance(recordResource, DirectoryPrincipalResource))

                    recordURL = typeURL + shortName
                    self.assertEquals(recordURL, recordResource.principalURL())

                    principalCollections = waitForDeferred(recordResource.principalCollections(None))
                    yield principalCollections
                    principalCollections = principalCollections.getResult()
                    self.assertEquals(set((provisioningURL,)), set(principalCollections))

    def test_principalForUser(self):
        """
        DirectoryPrincipalProvisioningResource.principalForUser()
        """
        for directory in directoryServices:
            provisioningResource = self.principalRootResources[directory.__class__.__name__]

            for user in directory.listRecords("user"):
                userResource = provisioningResource.principalForUser(user.shortName)
                self.failIf(userResource is None)
                self.assertEquals(user, userResource.record)

    def test_principalForRecord(self):
        """
        DirectoryPrincipalProvisioningResource.principalForRecord()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            self.assertEquals(recordResource.record, record)
                    
    def test_displayName(self):
        """
        DirectoryPrincipalResource.displayName()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            self.failUnless(recordResource.displayName())

    def test_groupMembers(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            self.failUnless(set(record.members()).issubset(set(r.record for r in recordResource.groupMembers())))

    def test_groupMemberships(self):
        """
        DirectoryPrincipalResource.groupMemberships()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            self.failUnless(set(record.groups()).issubset(set(r.record for r in recordResource.groupMemberships())))

    def test_principalUID(self):
        """
        DirectoryPrincipalResource.principalUID()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            self.assertEquals(record.shortName, recordResource.principalUID())

    def test_calendarUserAddresses(self):
        """
        DirectoryPrincipalResource.calendarUserAddresses()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            self.failUnless(
                (
                    set((recordResource.principalURL(),)) |
                    set(record.calendarUserAddresses)
                ).issubset(set(recordResource.calendarUserAddresses()))
            )

    def test_calendarHomeURLs(self):
        """
        DirectoryPrincipalResource.calendarHomeURLs(),
        DirectoryPrincipalResource.scheduleInboxURL(),
        DirectoryPrincipalResource.scheduleOutboxURL()
        """
        # No calendar home provisioner should result in no calendar homes.
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            self.failIf(tuple(recordResource.calendarHomeURLs()))
            self.failIf(recordResource.scheduleInboxURL())
            self.failIf(recordResource.scheduleOutboxURL())

        # Need to create a calendar home provisioner for each service.
        calendarRootResources = {}

        for directory in directoryServices:
            url = "/homes_" + directory.__class__.__name__ + "/"
            path = os.path.join(self.docroot, url[1:])

            if os.path.exists(path):
                rmdir(path)
            os.mkdir(path)

            provisioningResource = CalendarHomeProvisioningFile(path, directory, url)

            calendarRootResources[directory.__class__.__name__] = provisioningResource
        
        # Calendar home provisioners should result in calendar homes.
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            homeURLs = tuple(recordResource.calendarHomeURLs())
            self.failUnless(homeURLs)

            calendarRootURL = calendarRootResources[record.service.__class__.__name__].url()

            inboxURL = recordResource.scheduleInboxURL()
            outboxURL = recordResource.scheduleOutboxURL()

            self.failUnless(inboxURL)
            self.failUnless(outboxURL)

            for homeURL in homeURLs:
                self.failUnless(homeURL.startswith(calendarRootURL))

                if inboxURL and inboxURL.startswith(homeURL):
                    self.failUnless(len(inboxURL) > len(homeURL))
                    self.failUnless(inboxURL.endswith("/"))
                    inboxURL = None

                if outboxURL and outboxURL.startswith(homeURL):
                    self.failUnless(len(outboxURL) > len(homeURL))
                    self.failUnless(outboxURL.endswith("/"))
                    outboxURL = None

            self.failIf(inboxURL)
            self.failIf(outboxURL)

    def _allRecords(self):
        for directory in directoryServices:
            provisioningResource = self.principalRootResources[directory.__class__.__name__]
            for recordType in directory.recordTypes():
                for record in directory.listRecords(recordType):
                    recordResource = provisioningResource.principalForRecord(record)
                    yield provisioningResource, recordType, recordResource, record
