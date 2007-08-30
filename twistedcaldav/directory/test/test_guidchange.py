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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.static import CalendarHomeProvisioningFile
from twistedcaldav.directory.directory import DirectoryService

import os

from twisted.web2.dav import davxml
from twisted.web2.dav.fileop import rmdir
from twisted.web2.dav.resource import AccessDeniedError
from twisted.web2.test.test_server import SimpleRequest

from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.directory.test.test_xmlfile import xmlFile

import twistedcaldav.test.util


class ProvisionedPrincipals (twistedcaldav.test.util.TestCase):
    """
    Directory service provisioned principals.
    """
    def setUp(self):
        super(ProvisionedPrincipals, self).setUp()
        
        # Setup the initial directory
        self.xmlfile = self.mktemp()
        fd = open(self.xmlfile, "w")
        fd.write(open(xmlFile.path, "r").read())
        fd.close()
        self.directoryService = XMLDirectoryService(self.xmlfile)
        
        # Set up a principals hierarchy for each service we're testing with
        name = 'principals'
        url = "/" + name + "/"
        path = os.path.join(self.docroot, url[1:])

        if os.path.exists(path):
            rmdir(path)
        os.mkdir(path)

        provisioningResource = DirectoryPrincipalProvisioningResource(path, url, self.directoryService)

        self.site.resource.putChild('principals', provisioningResource)

        self.setupCalendars()

        self.site.resource.setAccessControlList(davxml.ACL())

    def setupCalendars(self):
        calendarCollection = CalendarHomeProvisioningFile(
            os.path.join(self.docroot, 'calendars'),
            self.directoryService,
            '/calendars/'
        )
        self.site.resource.putChild('calendars', calendarCollection)

    def resetCalendars(self):
        del self.site.resource.putChildren['calendars']
        self.setupCalendars()

    def test_guidchange(self):
        """
        DirectoryPrincipalResource.proxies()
        """
        
        def privs1(result):
            # Change GUID in record
            fd = open(self.xmlfile, "w")
            fd.write(open(xmlFile.path, "r").read().replace("5A985493-EE2C-4665-94CF-4DFEA3A89500", "38D8AC00-5490-4425-BE3A-05FFB9862444"))
            fd.close()
            fd = None

            # Force re-read of records (not sure why _fileInfo has to be wiped here...)
            self.directoryService._fileInfo = (0, 0)
            self.directoryService.recordWithShortName(DirectoryService.recordType_users, "cdaboo")

            # Now force the calendar home resource to be reset
            self.resetCalendars()
            
            # Make sure new user cannot access old user's calendar home
            return self._checkPrivileges(None, "/calendars/users/cdaboo/", davxml.HRef("/principals/__uids__/38D8AC00-5490-4425-BE3A-05FFB9862444/"), davxml.Write, False)
            
        # Make sure current user has access to their calendar home
        d = self._checkPrivileges(None, "/calendars/users/cdaboo/", davxml.HRef("/principals/__uids__/5A985493-EE2C-4665-94CF-4DFEA3A89500/"), davxml.Write, True)
        d.addCallback(privs1)
        return d
        

    def _checkPrivileges(self, resource, url, principal, privilege, allowed):
        request = SimpleRequest(self.site, "GET", "/calendars/users/cdaboo/")

        def gotResource(resource):
            d = resource.checkPrivileges(request, (privilege,), principal=davxml.Principal(principal))
            if allowed:
                def onError(f):
                    f.trap(AccessDeniedError)
                    #print resource.readDeadProperty(davxml.ACL)
                    self.fail("%s should have %s privilege on %r" % (principal.sname(), privilege.sname(), resource))
                d.addErrback(onError)
            else:
                def onError(f):
                    f.trap(AccessDeniedError)
                def onSuccess(_):
                    #print resource.readDeadProperty(davxml.ACL)
                    self.fail("%s should not have %s privilege on %r" % (principal.sname(), privilege.sname(), resource))
                d.addCallback(onSuccess)
                d.addErrback(onError)
            return d

        d = request.locateResource(url)
        d.addCallback(gotResource)
        return d
