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

import os

from twisted.cred.credentials import UsernamePassword
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web2.dav import davxml
from twisted.web2.dav.fileop import rmdir
from twisted.web2.dav.resource import AccessDeniedError
from twisted.web2.test.test_server import SimpleRequest

from twistedcaldav.static import CalendarHomeProvisioningFile
from twistedcaldav.config import config
from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.directory.test.test_xmlfile import xmlFile, XMLFile
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory.principal import DirectoryPrincipalTypeProvisioningResource
from twistedcaldav.directory.principal import DirectoryPrincipalResource
from twistedcaldav.directory.principal import DirectoryCalendarPrincipalResource

from twistedcaldav.cache import DisabledCacheNotifier

import twistedcaldav.test.util


class ProvisionedPrincipals (twistedcaldav.test.util.TestCase):
    """
    Directory service provisioned principals.
    """
    def setUp(self):
        super(ProvisionedPrincipals, self).setUp()

        self.directoryServices = (
            # realm 'Test' with 'digest' users
            # realm 'Test' with 'basic' users
            XMLDirectoryService(
                {
                    'xmlFile' : xmlFile,
                }
            ),
        )

        # Set up a principals hierarchy for each service we're testing with
        self.principalRootResources = {}
        for directory in self.directoryServices:
            name = directory.__class__.__name__
            url = "/" + name + "/"

            provisioningResource = DirectoryPrincipalProvisioningResource(url, directory)

            self.site.resource.putChild(name, provisioningResource)

            self.principalRootResources[directory.__class__.__name__] = provisioningResource

    @inlineCallbacks
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
        for directory in self.directoryServices:
            #print "\n -> %s" % (directory.__class__.__name__,)
            provisioningResource = self.principalRootResources[directory.__class__.__name__]

            provisioningURL = "/" + directory.__class__.__name__ + "/"
            self.assertEquals(provisioningURL, provisioningResource.principalCollectionURL())

            principalCollections = provisioningResource.principalCollections()
            self.assertEquals(set((provisioningURL,)), set(pc.principalCollectionURL() for pc in principalCollections))

            children = (yield provisioningResource.listChildren())
            recordTypes = set(children)
            self.assertEquals(recordTypes, set(directory.recordTypes()))

            for recordType in recordTypes:
                #print "   -> %s" % (recordType,)
                typeResource = (yield provisioningResource.getChild(recordType))
                self.failUnless(isinstance(typeResource, DirectoryPrincipalTypeProvisioningResource))

                typeURL = provisioningURL + recordType + "/"
                self.assertEquals(typeURL, typeResource.principalCollectionURL())

                principalCollections = typeResource.principalCollections()
                self.assertEquals(set((provisioningURL,)), set(pc.principalCollectionURL() for pc in principalCollections))
                shortNames = set((yield typeResource.listChildren()))
                self.assertEquals(shortNames, set(r.shortNames[0] for r in (yield directory.listRecords(recordType))))

                for shortName in shortNames:
                    #print "     -> %s" % (shortName,)
                    recordResource = (yield typeResource.getChild(shortName))
                    self.failUnless(isinstance(recordResource, DirectoryPrincipalResource))

                    recordURL = typeURL + shortName + "/"
                    self.assertIn(recordURL, (recordResource.principalURL(),) + tuple(recordResource.alternateURIs()))

                    principalCollections = recordResource.principalCollections()
                    self.assertEquals(set((provisioningURL,)), set(pc.principalCollectionURL() for pc in principalCollections))
                    

    @inlineCallbacks
    def test_allRecords(self):
        """
        Test of a test routine...
        """
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            self.assertEquals(recordResource.record, record)

    ##
    # DirectoryPrincipalProvisioningResource
    ##

    @inlineCallbacks
    def test_principalForShortName(self):
        """
        DirectoryPrincipalProvisioningResource.principalForShortName()
        """
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            principal = (yield provisioningResource.principalForShortName(recordType, record.shortNames[0]))
            self.failIf(principal is None)
            self.assertEquals(record, principal.record)

    @inlineCallbacks
    def test_principalForUser(self):
        """
        DirectoryPrincipalProvisioningResource.principalForUser()
        """
        for directory in self.directoryServices:
            provisioningResource = self.principalRootResources[directory.__class__.__name__]

            for user in (yield directory.listRecords(DirectoryService.recordType_users)):
                userResource = (yield provisioningResource.principalForUser(user.shortNames[0]))
                self.failIf(userResource is None)
                self.assertEquals(user, userResource.record)

    @inlineCallbacks
    def test_principalForAuthID(self):
        """
        DirectoryPrincipalProvisioningResource.principalForAuthID()
        """
        for directory in self.directoryServices:
            provisioningResource = self.principalRootResources[directory.__class__.__name__]

            for user in (yield directory.listRecords(DirectoryService.recordType_users)):
                creds = UsernamePassword(user.shortNames[0], "bogus")
                userResource = (yield provisioningResource.principalForAuthID(creds))
                self.failIf(userResource is None)
                self.assertEquals(user, userResource.record)

    @inlineCallbacks
    def test_principalForUID(self):
        """
        DirectoryPrincipalProvisioningResource.principalForUID()
        """
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            principal = (yield provisioningResource.principalForUID(record.uid))
            self.failIf(principal is None)
            self.assertEquals(record, principal.record)

    @inlineCallbacks
    def test_principalForRecord(self):
        """
        DirectoryPrincipalProvisioningResource.principalForRecord()
        """
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            principal = (yield provisioningResource.principalForRecord(record))
            self.failIf(principal is None)
            self.assertEquals(record, principal.record)


    @inlineCallbacks
    def _warmCache(self):
        """
        Load some records into the cache so that listRecords() will actually
        return something from an XMLDirectoryService.

        XXX TODO this method shouldn't really be necessary; instead, we should
        be able to express the appropriate 'list' functionality to the
        IDirectoryService API and not rely on XMLDirectoryService's caching
        behavior.
        """
        for svc in self.directoryServices:
            for user in XMLFile.users:
                record = (yield svc.recordWithShortName(DirectoryService.recordType_users, user))


    @inlineCallbacks
    def test_principalForCalendarUserAddress(self):
        """
        DirectoryPrincipalProvisioningResource.principalForCalendarUserAddress()
        """

        yield self._warmCache()
        for (provisioningResource, recordType, recordResource, record) in (yield self._allRecords()):
            principalURL = recordResource.principalURL()
            if principalURL.endswith("/"):
                alternateURL = principalURL[:-1]
            else:
                alternateURL = principalURL + "/"

            for address in tuple(record.calendarUserAddresses) + (principalURL, alternateURL):
                principal = (yield provisioningResource.principalForCalendarUserAddress(address))
                if record.enabledForCalendaring:
                    self.failIf(principal is None)
                    self.assertEquals(record, principal.record)
                else:
                    self.failIf(principal is not None)

        # Explicitly check the disabled record
        self.failIf((yield provisioningResource.principalForCalendarUserAddress("mailto:nocalendar@example.com")) is not None)
        self.failIf((yield provisioningResource.principalForCalendarUserAddress("urn:uuid:543D28BA-F74F-4D5F-9243-B3E3A61171E5")) is not None)
        self.failIf((yield provisioningResource.principalForCalendarUserAddress("/principals/users/nocalendar/")) is not None)
        self.failIf((yield provisioningResource.principalForCalendarUserAddress("/principals/__uids__/543D28BA-F74F-4D5F-9243-B3E3A61171E5/")) is not None)

    @inlineCallbacks
    def test_enabledForCalendaring(self):
        """
        DirectoryPrincipalProvisioningResource.principalForCalendarUserAddress()
        """
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            principal = (yield provisioningResource.principalForRecord(record))
            self.failIf(principal is None)
            if record.enabledForCalendaring:
                self.assertTrue(isinstance(principal, DirectoryCalendarPrincipalResource))
            else:
                self.assertTrue(isinstance(principal, DirectoryPrincipalResource))
                self.assertFalse(isinstance(principal, DirectoryCalendarPrincipalResource))

    @inlineCallbacks
    def test_enabledAsOrganizer(self):
        """
        DirectoryPrincipalProvisioningResource.principalForCalendarUserAddress()
        """
        
        ok_types = (
            DirectoryService.recordType_users,
        )
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            
            if record.enabledForCalendaring:
                principal = (yield provisioningResource.principalForRecord(record))
                self.failIf(principal is None)
                self.assertEqual(principal.enabledAsOrganizer(), recordType in ok_types)

        config.Scheduling.Options.AllowGroupAsOrganizer = True
        config.Scheduling.Options.AllowLocationAsOrganizer = True
        config.Scheduling.Options.AllowResourceAsOrganizer = True
        ok_types = (
            DirectoryService.recordType_users,
            DirectoryService.recordType_groups,
            DirectoryService.recordType_locations,
            DirectoryService.recordType_resources,
        )
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            
            if record.enabledForCalendaring:
                principal = (yield provisioningResource.principalForRecord(record))
                self.failIf(principal is None)
                self.assertEqual(principal.enabledAsOrganizer(), recordType in ok_types)

    # FIXME: Run DirectoryPrincipalProvisioningResource tests on DirectoryPrincipalTypeProvisioningResource also

    ##
    # DirectoryPrincipalResource
    ##

    @inlineCallbacks
    def test_cacheNotifier(self):
        """
        Each DirectoryPrincipalResource should have a cacheNotifier attribute
        that is an instance of XattrCacheChangeNotifier
        """
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            self.failUnless(isinstance(recordResource.cacheNotifier,
                                       DisabledCacheNotifier))

    @inlineCallbacks
    def test_displayName(self):
        """
        DirectoryPrincipalResource.displayName()
        """
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            self.failUnless(recordResource.displayName())

    @inlineCallbacks
    def test_groupMembers(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            members = yield recordResource.groupMembers()
            self.failUnless(set((yield record.members())).issubset(set(r.record for r in members)))

    @inlineCallbacks
    def test_groupMemberships(self):
        """
        DirectoryPrincipalResource.groupMemberships()
        """
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            memberships = yield recordResource.groupMemberships()
            self.failUnless(set((yield record.groups())).issubset(set(r.record for r in memberships if hasattr(r, "record"))))

    @inlineCallbacks
    def test_principalUID(self):
        """
        DirectoryPrincipalResource.principalUID()
        """
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            self.assertEquals(record.guid, recordResource.principalUID())

    @inlineCallbacks
    def test_calendarUserAddresses(self):
        """
        DirectoryPrincipalResource.calendarUserAddresses()
        """
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            if record.enabledForCalendaring:
                self.failUnless(
                    (
                        set((recordResource.principalURL(),)) |
                        set(record.calendarUserAddresses)
                    ).issubset(set((yield recordResource.calendarUserAddresses())))
                )

    @inlineCallbacks
    def test_calendarHomeURLs(self):
        """
        DirectoryPrincipalResource.calendarHomeURLs(),
        DirectoryPrincipalResource.scheduleInboxURL(),
        DirectoryPrincipalResource.scheduleOutboxURL()
        """
        # No calendar home provisioner should result in no calendar homes.
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            if record.enabledForCalendaring:
                urls = (yield recordResource.calendarHomeURLs())
                self.assertEqual(len(urls), 0)
                self.failIf((yield recordResource.scheduleInboxURL()))
                self.failIf((yield recordResource.scheduleOutboxURL()))

        # Need to create a calendar home provisioner for each service.
        calendarRootResources = {}

        for directory in self.directoryServices:
            url = "/homes_" + directory.__class__.__name__ + "/"
            path = os.path.join(self.docroot, url[1:])

            if os.path.exists(path):
                rmdir(path)
            os.mkdir(path)

            provisioningResource = (yield CalendarHomeProvisioningFile.fetch(
                None, path, directory, url))

            calendarRootResources[directory.__class__.__name__] = provisioningResource

        # Calendar home provisioners should result in calendar homes.
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            if record.enabledForCalendaring:
                homeURLs = tuple((yield recordResource.calendarHomeURLs()))
                self.failUnless(homeURLs)

                calendarRootURL = calendarRootResources[record.service.__class__.__name__].url()

                inboxURL = (yield recordResource.scheduleInboxURL())
                outboxURL = (yield recordResource.scheduleOutboxURL())

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



    @inlineCallbacks
    def test_defaultAccessControlList_principals(self):
        """
        Default access controls for principals.
        """
        for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
            for args in (yield _authReadOnlyPrivileges(self, recordResource, recordResource.principalURL())):
                yield self._checkPrivileges(*args)

    @inlineCallbacks
    def test_defaultAccessControlList_provisioners(self):
        """
        Default access controls for principal provisioning resources.
        """
        for directory in self.directoryServices:
            #print "\n -> %s" % (directory.__class__.__name__,)
            provisioningResource = self.principalRootResources[directory.__class__.__name__]

            for args in (yield _authReadOnlyPrivileges(self, provisioningResource, provisioningResource.principalCollectionURL())):
                yield self._checkPrivileges(*args)
            children = yield provisioningResource.listChildren()
            for recordType in children:
                #print "   -> %s" % (recordType,)
                typeResource = (yield provisioningResource.getChild(recordType))

                for args in (yield _authReadOnlyPrivileges(self, typeResource, typeResource.principalCollectionURL())):
                    yield self._checkPrivileges(*args)

    def test_propertyToField(self):

        class stubElement(object):
            def __init__(self, ns, name):
                self.ns = ns
                self.name = name

            def qname(self):
                return self.ns, self.name

        provisioningResource = self.principalRootResources['XMLDirectoryService']

        expected = (
            ("DAV:", "displayname", "morgen", "fullName", "morgen"),
            ("urn:ietf:params:xml:ns:caldav", "calendar-user-type", "INDIVIDUAL", "recordType", "users"),
            ("urn:ietf:params:xml:ns:caldav", "calendar-user-type", "GROUP", "recordType", "groups"),
            ("urn:ietf:params:xml:ns:caldav", "calendar-user-type", "RESOURCE", "recordType", "resources"),
            ("urn:ietf:params:xml:ns:caldav", "calendar-user-type", "ROOM", "recordType", "locations"),
            ("urn:ietf:params:xml:ns:caldav", "calendar-user-address-set", "/principals/__uids__/AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA/", "guid", "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"),
            ("urn:ietf:params:xml:ns:caldav", "calendar-user-address-set", "http://example.com:8008/principals/__uids__/AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA/", "guid", "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"),
            ("urn:ietf:params:xml:ns:caldav", "calendar-user-address-set", "urn:uuid:AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA", "guid", "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"),
            ("urn:ietf:params:xml:ns:caldav", "calendar-user-address-set", "/principals/users/example/", "recordName", "example"),
            ("urn:ietf:params:xml:ns:caldav", "calendar-user-address-set", "https://example.com:8443/principals/users/example/", "recordName", "example"),
            ("urn:ietf:params:xml:ns:caldav", "calendar-user-address-set", "mailto:example@example.com", "emailAddresses", "example@example.com"),
            ("http://calendarserver.org/ns/", "first-name", "morgen", "firstName", "morgen"),
            ("http://calendarserver.org/ns/", "last-name", "sagen", "lastName", "sagen"),
            ("http://calendarserver.org/ns/", "email-address-set", "example@example.com", "emailAddresses", "example@example.com"),
        )

        for ns, property, match, field, converted in expected:
            el = stubElement(ns, property)
            self.assertEquals(
                provisioningResource.propertyToField(el, match),
                (field, converted)
            )

    @inlineCallbacks
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
        results = []
        for directory in self.directoryServices:
            provisioningResource = self.principalRootResources[directory.__class__.__name__]
            for recordType in directory.recordTypes():
                for record in (yield directory.listRecords(recordType)):
                    recordResource = (yield provisioningResource.principalForRecord(record))
                    results.append((provisioningResource, recordType, recordResource, record))
        returnValue(results)

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

@inlineCallbacks
def _authReadOnlyPrivileges(self, resource, url):
    items = []
    for provisioningResource, recordType, recordResource, record in (yield self._allRecords()):
        if recordResource == resource:
            items.append(( davxml.HRef().fromString(recordResource.principalURL()), davxml.Read()  , True ))
            items.append(( davxml.HRef().fromString(recordResource.principalURL()), davxml.Write() , True ))
        else:
            items.append(( davxml.HRef().fromString(recordResource.principalURL()), davxml.Read()  , True ))
            items.append(( davxml.HRef().fromString(recordResource.principalURL()), davxml.Write() , False ))
    items.append(( davxml.Unauthenticated() , davxml.Read()  , False ))
    items.append(( davxml.Unauthenticated() , davxml.Write() , False ))
            
    results = []
    for principal, privilege, allowed in items:
        results.append((resource, url, principal, privilege, allowed))
    returnValue(results)
