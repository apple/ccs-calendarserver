##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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
from twistedcaldav.directory.directory import DirectoryService

from txdav.xml import element as davxml
from twext.web2.dav.resource import AccessDeniedError
from twext.web2.test.test_server import SimpleRequest

from twistedcaldav.directory.test.util import maybeCommit
from twistedcaldav.test.util import TestCase, xmlFile


class ProvisionedPrincipals(TestCase):
    """
    Directory service provisioned principals.
    """
    def setUp(self):
        super(ProvisionedPrincipals, self).setUp()

        # Setup the initial directory
        self.createStockDirectoryService()
        self.setupCalendars()

        self.site.resource.setAccessControlList(davxml.ACL())


    def resetCalendars(self):
        del self.site.resource.putChildren["calendars"]
        self.setupCalendars()


    def test_guidchange(self):
        """
        DirectoryPrincipalResource.proxies()
        """
        oldUID = "5A985493-EE2C-4665-94CF-4DFEA3A89500"
        newUID = "38D8AC00-5490-4425-BE3A-05FFB9862444"

        homeResource = "/calendars/users/cdaboo/"
        
        def privs1(result):
            # Change GUID in record
            self.xmlFile.setContent(
                xmlFile.getContent().replace(oldUID, newUID)
            )

            # Force re-read of records (not sure why _fileInfo has to be wiped here...)
            self.directoryService._fileInfo = (0, 0)
            self.directoryService.recordWithShortName(DirectoryService.recordType_users, "cdaboo")

            # Now force the calendar home resource to be reset
            self.resetCalendars()
            
            # Make sure new user cannot access old user's calendar home
            return self._checkPrivileges(None, homeResource, davxml.HRef("/principals/__uids__/" + newUID + "/"), davxml.Write, False)
            
        # Make sure current user has access to their calendar home
        d = self._checkPrivileges(None, homeResource, davxml.HRef("/principals/__uids__/" + oldUID + "/"), davxml.Write, True)
        d.addCallback(privs1)
        return d

    #
    # This test fails because /calendars/users/cdaboo/ actually is a
    # different resource (ie. the /calendars/__uids__/... URL would be
    # different) when the GUID for cdaboo changes.
    #
    # The test needs to create a fixed resource with access granted to
    # the old cdaboo; calendar homes no longer do this.
    #
    # Using the __uids__ URL won't work either because the old URL
    # goes away with the old account.
    #
    test_guidchange.todo = "Test no longer works."

    def _checkPrivileges(self, resource, url, principal, privilege, allowed):
        request = SimpleRequest(self.site, "GET", "/")

        def gotResource(resource):
            d = resource.checkPrivileges(request, (privilege,), principal=davxml.Principal(principal))
            if allowed:
                def onError(f):
                    f.trap(AccessDeniedError)
                    #print resource.readDeadProperty(davxml.ACL).toxml()
                    self.fail("%s should have %s privilege on %r" % (principal, privilege.sname(), resource))
                d.addErrback(onError)
            else:
                def onError(f):
                    f.trap(AccessDeniedError)
                def onSuccess(_):
                    #print resource.readDeadProperty(davxml.ACL).toxml()
                    self.fail("%s should not have %s privilege on %r" % (principal, privilege.sname(), resource))
                d.addCallback(onSuccess)
                d.addErrback(onError)
            def _commit(ignore):
                maybeCommit(request)
            d.addBoth(_commit)
            return d

        d = request.locateResource(url)
        d.addCallback(gotResource)
        return d
