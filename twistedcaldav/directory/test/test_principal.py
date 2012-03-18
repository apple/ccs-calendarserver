##
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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
from twisted.internet.defer import inlineCallbacks
from txdav.xml import element as davxml
from twext.web2.dav.fileop import rmdir
from twext.web2.dav.resource import AccessDeniedError
from twext.web2.http import HTTPError
from twext.web2.test.test_server import SimpleRequest

from twistedcaldav.cache import DisabledCacheNotifier
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.directory import augment, calendaruserproxy
from twistedcaldav.directory.addressbook import DirectoryAddressBookHomeProvisioningResource
from twistedcaldav.directory.calendar import DirectoryCalendarHomeProvisioningResource
from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.directory.test.test_xmlfile import xmlFile, augmentsFile
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory.principal import DirectoryPrincipalTypeProvisioningResource
from twistedcaldav.directory.principal import DirectoryPrincipalResource
from twistedcaldav.directory.principal import DirectoryCalendarPrincipalResource
from twistedcaldav import carddavxml
import twistedcaldav.test.util

from txdav.common.datastore.file import CommonDataStore
from urllib import quote



class ProvisionedPrincipals (twistedcaldav.test.util.TestCase):
    """
    Directory service provisioned principals.
    """
    def setUp(self):
        super(ProvisionedPrincipals, self).setUp()

        self.directoryServices = (
            XMLDirectoryService(
                {
                    'xmlFile' : xmlFile,
                    'augmentService' :
                        augment.AugmentXMLDB(xmlFiles=(augmentsFile.path,)),
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

        calendaruserproxy.ProxyDBService = calendaruserproxy.ProxySqliteDB(os.path.abspath(self.mktemp()))


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

            recordTypes = set((yield provisioningResource.listChildren()))
            self.assertEquals(recordTypes, set(directory.recordTypes()))

            for recordType in recordTypes:
                #print "   -> %s" % (recordType,)
                typeResource = provisioningResource.getChild(recordType)
                self.failUnless(isinstance(typeResource, DirectoryPrincipalTypeProvisioningResource))

                typeURL = provisioningURL + recordType + "/"
                self.assertEquals(typeURL, typeResource.principalCollectionURL())

                principalCollections = typeResource.principalCollections()
                self.assertEquals(set((provisioningURL,)), set(pc.principalCollectionURL() for pc in principalCollections))

                shortNames = set((yield typeResource.listChildren()))
                # Handle records with mulitple shortNames
                expected = []
                for r in directory.listRecords(recordType):
                    if r.uid != "disabled":
                        expected.extend(r.shortNames)
                self.assertEquals(shortNames, set(expected))

                for shortName in shortNames:
                    #print "     -> %s" % (shortName,)
                    recordResource = typeResource.getChild(shortName)
                    self.failUnless(isinstance(recordResource, DirectoryPrincipalResource))

                    # shortName may be non-ascii
                    recordURL = typeURL + quote(shortName) + "/"
                    self.assertIn(recordURL, (recordResource.principalURL(),) + tuple(recordResource.alternateURIs()))

                    principalCollections = recordResource.principalCollections()
                    self.assertEquals(set((provisioningURL,)), set(pc.principalCollectionURL() for pc in principalCollections))

    def test_allRecords(self):
        """
        Test of a test routine...
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabled:
                self.assertEquals(recordResource.record, record)

    ##
    # DirectoryPrincipalProvisioningResource
    ##

    def test_principalForShortName(self):
        """
        DirectoryPrincipalProvisioningResource.principalForShortName()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            principal = provisioningResource.principalForShortName(recordType, record.shortNames[0])
            if record.enabled:
                self.failIf(principal is None)
                self.assertEquals(record, principal.record)
            else:
                self.failIf(principal is not None)

    def test_principalForUser(self):
        """
        DirectoryPrincipalProvisioningResource.principalForUser()
        """
        for directory in self.directoryServices:
            provisioningResource = self.principalRootResources[directory.__class__.__name__]

            for user in directory.listRecords(DirectoryService.recordType_users):
                userResource = provisioningResource.principalForUser(user.shortNames[0])
                if user.enabled:
                    self.failIf(userResource is None)
                    self.assertEquals(user, userResource.record)
                else:
                    self.failIf(userResource is not None)

    def test_principalForAuthID(self):
        """
        DirectoryPrincipalProvisioningResource.principalForAuthID()
        """
        for directory in self.directoryServices:
            provisioningResource = self.principalRootResources[directory.__class__.__name__]

            for user in directory.listRecords(DirectoryService.recordType_users):
                creds = UsernamePassword(user.shortNames[0], "bogus")
                userResource = provisioningResource.principalForAuthID(creds)
                if user.enabled:
                    self.failIf(userResource is None)
                    self.assertEquals(user, userResource.record)
                else:
                    self.failIf(userResource is not None)

    def test_principalForUID(self):
        """
        DirectoryPrincipalProvisioningResource.principalForUID()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            principal = provisioningResource.principalForUID(record.uid)
            if record.enabled:
                self.failIf(principal is None)
                self.assertEquals(record, principal.record)
            else:
                self.failIf(principal is not None)

    def test_principalForRecord(self):
        """
        DirectoryPrincipalProvisioningResource.principalForRecord()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            principal = provisioningResource.principalForRecord(record)
            if record.enabled:
                self.failIf(principal is None)
                self.assertEquals(record, principal.record)
            else:
                self.failIf(principal is not None)

    def test_principalForCalendarUserAddress(self):
        """
        DirectoryPrincipalProvisioningResource.principalForCalendarUserAddress()
        """
        for (
            provisioningResource, recordType, recordResource, record
        ) in self._allRecords():
        
            test_items = tuple(record.calendarUserAddresses)
            if recordResource:
                principalURL = recordResource.principalURL()
                if principalURL.endswith("/"):
                    alternateURL = principalURL[:-1]
                else:
                    alternateURL = principalURL + "/"
                test_items += (principalURL, alternateURL)

            for address in test_items:
                principal = provisioningResource.principalForCalendarUserAddress(address)
                if record.enabledForCalendaring:
                    self.failIf(principal is None)
                    self.assertEquals(record, principal.record)
                else:
                    self.failIf(principal is not None)

        # Explicitly check the disabled record
        provisioningResource = self.principalRootResources['XMLDirectoryService']

        self.failUnlessIdentical(
            provisioningResource.principalForCalendarUserAddress(
                "mailto:nocalendar@example.com"
            ),
            None
        )
        self.failUnlessIdentical(
            provisioningResource.principalForCalendarUserAddress(
                "urn:uuid:543D28BA-F74F-4D5F-9243-B3E3A61171E5"
            ),
            None
        )
        self.failUnlessIdentical(
            provisioningResource.principalForCalendarUserAddress(
                "/principals/users/nocalendar/"
            ),
            None
        )
        self.failUnlessIdentical(
            provisioningResource.principalForCalendarUserAddress(
                "/principals/__uids__/543D28BA-F74F-4D5F-9243-B3E3A61171E5/"
            ),
            None
        )

    @inlineCallbacks
    def test_enabledForCalendaring(self):
        """
        DirectoryPrincipalProvisioningResource.principalForCalendarUserAddress()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            principal = provisioningResource.principalForRecord(record)
            if record.enabled:
                self.failIf(principal is None)
            else:
                self.failIf(principal is not None)
                continue
            if record.enabledForCalendaring:
                self.assertTrue(isinstance(principal, DirectoryCalendarPrincipalResource))
            else:
                self.assertTrue(isinstance(principal, DirectoryPrincipalResource))
                if record.enabledForAddressBooks:
                    self.assertTrue(isinstance(principal, DirectoryCalendarPrincipalResource))
                else:
                    self.assertFalse(isinstance(principal, DirectoryCalendarPrincipalResource))

            @inlineCallbacks
            def hasProperty(property):
                self.assertTrue(property in principal.liveProperties())
                yield principal.readProperty(property, None)
                
            @inlineCallbacks
            def doesNotHaveProperty(property):
                self.assertTrue(property not in principal.liveProperties())
                try:
                    yield principal.readProperty(property, None)
                except HTTPError:
                    pass
                except:
                    self.fail("Wrong exception type")
                else:
                    self.fail("No exception principal: %s, property %s" % (principal, property,))
                
            if record.enabledForCalendaring:
                yield hasProperty((caldav_namespace, "calendar-home-set"))
                yield hasProperty((caldav_namespace, "calendar-user-address-set"))
                yield hasProperty((caldav_namespace, "schedule-inbox-URL"))
                yield hasProperty((caldav_namespace, "schedule-outbox-URL"))
                yield hasProperty((caldav_namespace, "calendar-user-type"))
                yield hasProperty((calendarserver_namespace, "calendar-proxy-read-for"))
                yield hasProperty((calendarserver_namespace, "calendar-proxy-write-for"))
                yield hasProperty((calendarserver_namespace, "auto-schedule"))
            else:
                yield doesNotHaveProperty((caldav_namespace, "calendar-home-set"))
                yield doesNotHaveProperty((caldav_namespace, "calendar-user-address-set"))
                yield doesNotHaveProperty((caldav_namespace, "schedule-inbox-URL"))
                yield doesNotHaveProperty((caldav_namespace, "schedule-outbox-URL"))
                yield doesNotHaveProperty((caldav_namespace, "calendar-user-type"))
                yield doesNotHaveProperty((calendarserver_namespace, "calendar-proxy-read-for"))
                yield doesNotHaveProperty((calendarserver_namespace, "calendar-proxy-write-for"))
                yield doesNotHaveProperty((calendarserver_namespace, "auto-schedule"))

            if record.enabledForAddressBooks:
                yield hasProperty(carddavxml.AddressBookHomeSet.qname())
            else:
                yield doesNotHaveProperty(carddavxml.AddressBookHomeSet.qname())

    def test_enabledAsOrganizer(self):
        """
        DirectoryPrincipalProvisioningResource.principalForCalendarUserAddress()
        """
        
        ok_types = (
            DirectoryService.recordType_users,
        )
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            
            if record.enabledForCalendaring:
                principal = provisioningResource.principalForRecord(record)
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
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            
            if record.enabledForCalendaring:
                principal = provisioningResource.principalForRecord(record)
                self.failIf(principal is None)
                self.assertEqual(principal.enabledAsOrganizer(), recordType in ok_types)

    # FIXME: Run DirectoryPrincipalProvisioningResource tests on DirectoryPrincipalTypeProvisioningResource also

    ##
    # DirectoryPrincipalResource
    ##

    def test_cacheNotifier(self):
        """
        Each DirectoryPrincipalResource should have a cacheNotifier attribute
        that is an instance of DisabledCacheNotifier
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabled:
                self.failUnless(isinstance(recordResource.cacheNotifier,
                                           DisabledCacheNotifier))

    def test_displayName(self):
        """
        DirectoryPrincipalResource.displayName()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabled:
                self.failUnless(recordResource.displayName())

    @inlineCallbacks
    def test_groupMembers(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabled:
                members = yield recordResource.groupMembers()
                self.failUnless(set(record.members()).issubset(set(r.record for r in members)))

    @inlineCallbacks
    def test_groupMemberships(self):
        """
        DirectoryPrincipalResource.groupMemberships()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabled:
                memberships = yield recordResource.groupMemberships()
                self.failUnless(set(record.groups()).issubset(set(r.record for r in memberships if hasattr(r, "record"))))

    def test_principalUID(self):
        """
        DirectoryPrincipalResource.principalUID()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabled:
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

                # Verify that if not enabled for calendaring, no CUAs:
                record.enabledForCalendaring = False
                self.failIf(recordResource.calendarUserAddresses())

    def test_canonicalCalendarUserAddress(self):
        """
        DirectoryPrincipalResource.canonicalCalendarUserAddress()
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabledForCalendaring:
                self.failUnless(recordResource.canonicalCalendarUserAddress().startswith("urn:uuid:"))

    def test_addressBookHomeURLs(self):
        """
        DirectoryPrincipalResource.addressBookHomeURLs(),
        """
        # No addressbook home provisioner should result in no addressbook homes.
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabledForAddressBooks:
                self.failIf(tuple(recordResource.addressBookHomeURLs()))

        # Need to create a addressbook home provisioner for each service.
        addressBookRootResources = {}

        for directory in self.directoryServices:
            path = os.path.join(self.docroot, directory.__class__.__name__)

            if os.path.exists(path):
                rmdir(path)
            os.mkdir(path)

            # Need a data store
            _newStore = CommonDataStore(path, None, True, False)

            provisioningResource = DirectoryAddressBookHomeProvisioningResource(
                directory,
                "/addressbooks/",
                _newStore
            )

            addressBookRootResources[directory.__class__.__name__] = provisioningResource

        # AddressBook home provisioners should result in addressBook homes.
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabledForAddressBooks:
                homeURLs = tuple(recordResource.addressBookHomeURLs())
                self.failUnless(homeURLs)

                # Turn off enabledForAddressBooks and addressBookHomeURLs should
                # be empty
                record.enabledForAddressBooks = False
                self.failIf(tuple(recordResource.addressBookHomeURLs()))
                record.enabledForAddressBooks = True

                addressBookRootURL = addressBookRootResources[record.service.__class__.__name__].url()

                for homeURL in homeURLs:
                    self.failUnless(homeURL.startswith(addressBookRootURL))

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

        for directory in self.directoryServices:
            path = os.path.join(self.docroot, directory.__class__.__name__)

            if os.path.exists(path):
                rmdir(path)
            os.mkdir(path)

            # Need a data store
            _newStore = CommonDataStore(path, None, True, False)

            provisioningResource = DirectoryCalendarHomeProvisioningResource(
                directory,
                "/calendars/",
                _newStore
            )

            calendarRootResources[directory.__class__.__name__] = provisioningResource

        # Calendar home provisioners should result in calendar homes.
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabledForCalendaring:
                homeURLs = tuple(recordResource.calendarHomeURLs())
                self.failUnless(homeURLs)

                # Turn off enabledForCalendaring and calendarHomeURLs should
                # be empty
                record.enabledForCalendaring = False
                self.failIf(tuple(recordResource.calendarHomeURLs()))
                record.enabledForCalendaring = True

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

    def test_canAutoSchedule(self):
        """
        DirectoryPrincipalResource.canAutoSchedule()
        """
        
        # Set all resources and locations to auto-schedule, plus one user
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabledForCalendaring:
                if recordType in ("locations", "resources") or record.uid == "cdaboo":
                    recordResource.record.autoSchedule = True

        # Default state - resources and locations, enabled, others not
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabledForCalendaring:
                if recordType in ("locations", "resources"):
                    self.assertTrue(recordResource.canAutoSchedule())
                else:
                    self.assertFalse(recordResource.canAutoSchedule())

        # Set config to allow users
        self.patch(config.Scheduling.Options.AutoSchedule, "AllowUsers", True)
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabledForCalendaring:
                if recordType in ("locations", "resources") or record.uid == "cdaboo":
                    self.assertTrue(recordResource.canAutoSchedule())
                else:
                    self.assertFalse(recordResource.canAutoSchedule())

        # Set config to disallow all
        self.patch(config.Scheduling.Options.AutoSchedule, "Enabled", False)
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabledForCalendaring:
                self.assertFalse(recordResource.canAutoSchedule())

    @inlineCallbacks
    def test_defaultAccessControlList_principals(self):
        """
        Default access controls for principals.
        """
        for provisioningResource, recordType, recordResource, record in self._allRecords():
            if record.enabled:
                for args in _authReadOnlyPrivileges(self, recordResource, recordResource.principalURL()):
                    yield self._checkPrivileges(*args)

    @inlineCallbacks
    def test_defaultAccessControlList_provisioners(self):
        """
        Default access controls for principal provisioning resources.
        """
        for directory in self.directoryServices:
            #print "\n -> %s" % (directory.__class__.__name__,)
            provisioningResource = self.principalRootResources[directory.__class__.__name__]

            for args in _authReadOnlyPrivileges(self, provisioningResource, provisioningResource.principalCollectionURL()):
                yield self._checkPrivileges(*args)

            for recordType in (yield provisioningResource.listChildren()):
                #print "   -> %s" % (recordType,)
                typeResource = provisioningResource.getChild(recordType)

                for args in _authReadOnlyPrivileges(self, typeResource, typeResource.principalCollectionURL()):
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
        for directory in self.directoryServices:
            provisioningResource = self.principalRootResources[
                directory.__class__.__name__
            ]
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
                def expectAccessDenied(f):
                    f.trap(AccessDeniedError)
                def onSuccess(_):
                    #print resource.readDeadProperty(davxml.ACL)
                    self.fail("%s should not have %s privilege on %r" % (principal.sname(), privilege.sname(), resource))
                d.addCallbacks(onSuccess, expectAccessDenied)
            return d

        d = request.locateResource(url)
        d.addCallback(gotResource)
        return d

def _authReadOnlyPrivileges(self, resource, url):
    items = []
    for provisioningResource, recordType, recordResource, record in self._allRecords():
        if record.enabled:
            items.append(( davxml.HRef().fromString(recordResource.principalURL()), davxml.Read()  , True ))
            items.append(( davxml.HRef().fromString(recordResource.principalURL()), davxml.Write() , False ))
    items.append(( davxml.Unauthenticated() , davxml.Read()  , False ))
    items.append(( davxml.Unauthenticated() , davxml.Write() , False ))
            
    for principal, privilege, allowed in items:
        yield resource, url, principal, privilege, allowed
