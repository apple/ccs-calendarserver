##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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

#from twisted.web2 import responsecode
#from twisted.web2.iweb import IResponse
#from twisted.web2.dav import davxml
#from twisted.web2.dav.util import davXMLFromStream
#from twisted.web2.test.test_server import SimpleRequest
#from twistedcaldav import caldavxml

import os

from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.fileop import rmdir
from twisted.web2.iweb import IResponse
from twisted.web2.test.test_server import SimpleRequest

from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory.test.test_xmlfile import xmlFile
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.static import CalendarHomeProvisioningFile

import twistedcaldav.test.util

class ProvisionedCalendars (twistedcaldav.test.util.TestCase):
    """
    Directory service provisioned principals.
    """
    def setUp(self):
        super(ProvisionedCalendars, self).setUp()
        
        # Setup the initial directory
        self.xmlfile = self.mktemp()
        fd = open(self.xmlfile, "w")
        fd.write(open(xmlFile.path, "r").read())
        fd.close()
        self.directoryService = XMLDirectoryService(self.xmlfile)
        
        # Set up a principals hierarchy for each service we're testing with
        name = "principals"
        url = "/" + name + "/"
        path = os.path.join(self.docroot, url[1:])

        if os.path.exists(path):
            rmdir(path)
        os.mkdir(path)

        provisioningResource = DirectoryPrincipalProvisioningResource(path, url, self.directoryService)

        self.site.resource.putChild("principals", provisioningResource)

        self.setupCalendars()

        self.site.resource.setAccessControlList(davxml.ACL())

    def setupCalendars(self):
        calendarCollection = CalendarHomeProvisioningFile(
            os.path.join(self.docroot, "calendars"),
            self.directoryService,
            "/calendars/"
        )
        self.site.resource.putChild("calendars", calendarCollection)

    def test_NonExistentCalendarHome(self):

        def _response(resource):
            if resource is not None:
                self.fail("Incorrect response to GET on non-existent calendar home.")

        request = SimpleRequest(self.site, "GET", "/calendars/users/12345/")
        d = request.locateResource(request.uri)
        d.addCallback(_response)
