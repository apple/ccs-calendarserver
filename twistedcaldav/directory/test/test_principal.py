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

from twisted.web2.dav.fileop import rmdir

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
        super(Principals, self).setUp()
        
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

    def test_hierarchy(self):
        """
        listChildren(), getChildren()
        """
        for directory in directoryServices:
            #print "\n -> %s" % (directory.__class__.__name__,)
            provisioningResource = self.principalRootResources[directory.__class__.__name__]

            recordTypes = set(provisioningResource.listChildren())
            self.assertEquals(recordTypes, set(directory.recordTypes()))

            for recordType in recordTypes:
                #print "   -> %s" % (recordType,)
                typeResource = provisioningResource.getChild(recordType)
                self.failUnless(isinstance(typeResource, DirectoryPrincipalTypeResource))

                shortNames = set(typeResource.listChildren())
                self.assertEquals(shortNames, set(r.shortName for r in directory.listRecords(recordType)))
                
                for shortName in shortNames:
                    #print "     -> %s" % (shortName,)
                    recordResource = typeResource.getChild(shortName)
                    self.failUnless(isinstance(recordResource, DirectoryPrincipalResource))
