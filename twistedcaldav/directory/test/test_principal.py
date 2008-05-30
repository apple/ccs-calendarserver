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

import os

from twisted.internet.defer import inlineCallbacks
from twisted.web2.dav import davxml
from twisted.web2.dav.fileop import rmdir
from twisted.web2.dav.resource import AccessDeniedError
from twisted.web2.test.test_server import SimpleRequest
from twisted.web2.dav.test.util import serialize

from twistedcaldav.static import CalendarHomeProvisioningFile
from twistedcaldav.directory.apache import BasicDirectoryService, DigestDirectoryService
from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.directory.test.test_apache import basicUserFile, digestUserFile, groupFile, digestRealm
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.directory.test.test_xmlfile import xmlFile
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory.principal import DirectoryPrincipalTypeProvisioningResource
from twistedcaldav.directory.principal import DirectoryPrincipalResource
from twistedcaldav.directory.principal import DirectoryCalendarPrincipalResource

from twistedcaldav.cache import DisabledCacheNotifier

import twistedcaldav.test.util

directoryServices = (
    BasicDirectoryService(digestRealm, basicUserFile, groupFile),
    DigestDirectoryService(digestRealm, digestUserFile, groupFile),
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
            name = directory.__class__.__name__
            url = "/" + name + "/"
            path = os.path.join(self.docroot, url[1:])

            if os.path.exists(path):
                rmdir(path)
            os.mkdir(path)

            provisioningResource = DirectoryPrincipalProvisioningResource(path, url, directory)

            self.site.resource.putChild(name, provisioningResource)

            self.principalRootResources[directory.__class__.__name__] = provisioningResource

    def test_hierarchy(self):
        """
        DirectoryPrincipalProvisioningResource.listChildren(),
        DirectoryPrincipalProvisioningResource.getChildren(),
        DirectoryPrincipalProvisioningResource.principalCollectionURL(),
        DirectoryPrincipalProvisioningResource.principalCollections()

        DirectoryPrincipalTypeProvisioningResource.listChildren(),
        DirectoryPrincipalTypeProvisioningResource.getChildren(),
        DirectoryPrincipalTypeProvisioningResource.principalCollectionURL(),
        DirectoryPrincipalTypeProvisioningResource.principalCollections()

        DirectoryPrincipalResource.principalURL(),
        """
        for directory in directoryServices:
            #print "\n -> %s" % (directory.__class__.__name__,)
            provisioningResource = self.principalRootResources[directory.__class__.__name__]

            provisioningURL = "/" + directory.__class__.__name__ + "/"
            self.assertEquals(provisioningURL, provisioningResource.principalCollectionURL())

            principalCollections = provisioningResource.principalCollections()
            self.assertEquals(set((provisioningURL,)), set(pc.principalCollectionURL() for pc in principalCollections))

            recordTypes = set(provisioningResource.listChildren())
            self.assertEquals(recordTypes, set(directory.recordTypes()))

            for recordType in recordTypes:
                #print "   -> %s" % (recordType,)
                typeResource = provisioningResource.getChild(recordType)
                self.failUnless(isinstance(typeResource, DirectoryPrincipalTypeProvisioningResource))

                typeURL = provisioningURL + recordType + "/"
                self.assertEquals(typeURL, typeResource.principalCollectionURL())

                principalCollections = typeResource.principalCollections()
                self.assertEquals(set((provisioningURL,)), set(pc.principalCollectionURL() for pc in principalCollections))

                shortNames = set(typeResource.listChildren())
                self.assertEquals(shortNames, set(r.shortName for r in directory.listRecords(recordType)))

                for shortName in shortNames:
                    #print "     -> %s" % (shortName,)
                    recordResource = typeResource.getChild(shortName)
                    self.failUnless(isinstance(recordResource, DirectoryPrincipalResource))

                    recordURL = typeURL + shortName + "/"
                    self.assertIn(recordURL, (recordResource.principalURL(),) + tuple(recordResource.alternateURIs()))

                    principalCollections = recordResource.principalCollections()
                    self.assertEquals(set((provisioningURL,)), set(pc.principalCollectionURL() for pc in principalCollections))

    def test_allRecords(self):
        """
        Test of a test routine...
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            self.assertEquals(recordResource.record, record)

    ##
    # DirectoryPrincipalProvisioningResource
    ##

    def test_principalForShortName(self):
        """
        DirectoryPrincipalProvisioningResource.principalForShortName()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            principal = provisioningResource.principalForShortName(recordType, record.shortName)
            self.failIf(principal is None)
            self.assertEquals(record, principal.record)

    def test_principalForUser(self):
        """
        DirectoryPrincipalProvisioningResource.principalForUser()
        """
        for directory in directoryServices:
            provisioningResource = self.principalRootResources[directory.__class__.__name__]

            for user in directory.listRecords(DirectoryService.recordType_users):
                userResource = provisioningResource.principalForUser(user.shortName)
                self.failIf(userResource is None)
                self.assertEquals(user, userResource.record)

    def test_principalForGUID(self):
        """
        DirectoryPrincipalProvisioningResource.principalForGUID()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            principal = provisioningResource.principalForGUID(record.guid)
            self.failIf(principal is None)
            self.assertEquals(record, principal.record)

    def test_principalForRecord(self):
        """
        DirectoryPrincipalProvisioningResource.principalForRecord()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            principal = provisioningResource.principalForRecord(record)
            self.failIf(principal is None)
            self.assertEquals(record, principal.record)

    def test_principalForCalendarUserAddress(self):
        """
        DirectoryPrincipalProvisioningResource.principalForCalendarUserAddress()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            principalURL = recordResource.principalURL()
            if principalURL.endswith("/"):
                alternateURL = principalURL[:-1]
            else:
                alternateURL = principalURL + "/"

            for address in tuple(record.calendarUserAddresses) + (principalURL, alternateURL):
                principal = provisioningResource.principalForCalendarUserAddress(address)
                if record.enabledForCalendaring:
                    self.failIf(principal is None)
                    self.assertEquals(record, principal.record)
                else:
                    self.failIf(principal is not None)

    def test_autoSchedule(self):
        """
        DirectoryPrincipalProvisioningResource.principalForCalendarUserAddress()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            principal = provisioningResource.principalForRecord(record)
            self.failIf(principal is None)
            if record.enabledForCalendaring:
                self.assertEquals(record.autoSchedule, principal.autoSchedule())
                if record.shortName == "gemini":
                    self.assertTrue(principal.autoSchedule())
                else:
                    self.assertFalse(principal.autoSchedule())

    def test_enabledForCalendaring(self):
        """
        DirectoryPrincipalProvisioningResource.principalForCalendarUserAddress()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            principal = provisioningResource.principalForRecord(record)
            self.failIf(principal is None)
            if record.enabledForCalendaring:
                self.assertTrue(isinstance(principal, DirectoryCalendarPrincipalResource))
            else:
                self.assertTrue(isinstance(principal, DirectoryPrincipalResource))
                self.assertFalse(isinstance(principal, DirectoryCalendarPrincipalResource))

    # FIXME: Run DirectoryPrincipalProvisioningResource tests on DirectoryPrincipalTypeProvisioningResource also

    ##
    # DirectoryPrincipalResource
    ##

    def test_cacheNotifier(self):
        """
        Each DirectoryPrincipalResource should have a cacheNotifier attribute
        that is an instance of XattrCacheChangeNotifier
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            self.failUnless(isinstance(recordResource.cacheNotifier,
                                       DisabledCacheNotifier))

    def test_displayName(self):
        """
        DirectoryPrincipalResource.displayName()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            self.failUnless(recordResource.displayName())

    @inlineCallbacks
    def test_groupMembers(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            members = yield recordResource.groupMembers()
            self.failUnless(set(record.members()).issubset(set(r.record for r in members)))

    @inlineCallbacks
    def test_groupMemberships(self):
        """
        DirectoryPrincipalResource.groupMemberships()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            memberships = yield recordResource.groupMemberships()
            self.failUnless(set(record.groups()).issubset(set(r.record for r in memberships if hasattr(r, "record"))))

    def test_proxies(self):
        """
        DirectoryPrincipalResource.proxies()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabledForCalendaring:
                self.failUnless(set(record.proxies()).issubset(set(r.record for r in recordResource.proxies())))
                self.assertEqual(record.hasEditableProxyMembership(), recordResource.hasEditableProxyMembership())

    def test_read_only_proxies(self):
        """
        DirectoryPrincipalResource.proxies()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabledForCalendaring:
                self.failUnless(set(record.readOnlyProxies()).issubset(set(r.record for r in recordResource.readOnlyProxies())))
                self.assertEqual(record.hasEditableProxyMembership(), recordResource.hasEditableProxyMembership())

    def test_principalUID(self):
        """
        DirectoryPrincipalResource.principalUID()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            self.assertEquals(record.guid, recordResource.principalUID())

    def test_calendarUserAddresses(self):
        """
        DirectoryPrincipalResource.calendarUserAddresses()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabledForCalendaring:
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
            if record.enabledForCalendaring:
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
            if record.enabledForCalendaring:
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

    def test_defaultAccessControlList_principals(self):
        """
        Default access controls for principals.
        """
        def work():
            for provisioningResource, recordType, recordResource, record in self._allRecords():
                for args in _authReadOnlyPrivileges(recordResource, recordResource.principalURL()):
                    yield args

        return serialize(self._checkPrivileges, work())

    def test_defaultAccessControlList_provisioners(self):
        """
        Default access controls for principal provisioning resources.
        """
        def work():
            for directory in directoryServices:
                #print "\n -> %s" % (directory.__class__.__name__,)
                provisioningResource = self.principalRootResources[directory.__class__.__name__]

                for args in _authReadOnlyPrivileges(provisioningResource, provisioningResource.principalCollectionURL()):
                    yield args

                for recordType in provisioningResource.listChildren():
                    #print "   -> %s" % (recordType,)
                    typeResource = provisioningResource.getChild(recordType)

                    for args in _authReadOnlyPrivileges(typeResource, typeResource.principalCollectionURL()):
                        yield args

        return serialize(self._checkPrivileges, work())

    def _allRecords(self):
        """
        @return: an iterable of tuples
            C{(provisioningResource, recordType, recordResource, record)}, where
            C{provisioningResource} is the root provisioning resource,
            C{recordType} is the record type,
            C{recordResource} is the principal resource and
            C{record} is the directory service record
            for each record in each directory in C{directoryServices}.
        """
        for directory in directoryServices:
            provisioningResource = self.principalRootResources[directory.__class__.__name__]
            for recordType in directory.recordTypes():
                for record in directory.listRecords(recordType):
                    recordResource = provisioningResource.principalForRecord(record)
                    yield provisioningResource, recordType, recordResource, record

    def _checkPrivileges(self, resource, url, principal, privilege, allowed):
        request = SimpleRequest(self.site, "GET", "/")

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

def _authReadOnlyPrivileges(resource, url):
    for principal, privilege, allowed in (
        ( davxml.All()             , davxml.Read()  , False ),
        ( davxml.All()             , davxml.Write() , False ),
        ( davxml.Unauthenticated() , davxml.Read()  , False ),
        ( davxml.Unauthenticated() , davxml.Write() , False ),
        ( davxml.Authenticated()   , davxml.Read()  , True  ),
        ( davxml.Authenticated()   , davxml.Write() , False ),
    ):
        yield resource, url, principal, privilege, allowed
