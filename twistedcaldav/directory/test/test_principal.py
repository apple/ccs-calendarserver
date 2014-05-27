##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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
from __future__ import print_function

from twext.who.idirectory import RecordType

from twisted.cred.credentials import UsernamePassword
from twisted.internet.defer import inlineCallbacks, returnValue

from twistedcaldav import carddavxml
from twistedcaldav.cache import DisabledCacheNotifier
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.directory.principal import (
    DirectoryCalendarPrincipalResource,
    DirectoryPrincipalResource,
    DirectoryPrincipalTypeProvisioningResource,
)
from twistedcaldav.test.util import StoreTestCase

from txdav.who.delegates import addDelegate
from txdav.who.idirectory import AutoScheduleMode, RecordType as CalRecordType
from txdav.xml import element as davxml

from txweb2.dav.resource import AccessDeniedError
from txweb2.http import HTTPError
from txweb2.test.test_server import SimpleRequest

from urllib import quote
from uuid import UUID


class ProvisionedPrincipals(StoreTestCase):
    """
    Directory service provisioned principals.
    """
    @inlineCallbacks
    def setUp(self):
        yield super(ProvisionedPrincipals, self).setUp()

        self.principalRootResource = self.actualRoot.getChild("principals")


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
        provisioningResource = self.principalRootResource

        provisioningURL = "/principals/"
        self.assertEquals(
            provisioningURL,
            provisioningResource.principalCollectionURL()
        )

        principalCollections = provisioningResource.principalCollections()
        self.assertEquals(
            set((provisioningURL,)),
            set(pc.principalCollectionURL() for pc in principalCollections)
        )

        recordTypes = set((yield provisioningResource.listChildren()))
        self.assertEquals(
            recordTypes,
            set(
                [
                    self.directory.recordTypeToOldName(rt) for rt in
                    (
                        self.directory.recordType.user,
                        self.directory.recordType.group,
                        self.directory.recordType.location,
                        self.directory.recordType.resource,
                        self.directory.recordType.address,
                        self.directory.recordType.macOSXServerWiki,
                    )
                ]
            )
        )

        for recordType in recordTypes:
            typeResource = yield provisioningResource.getChild(recordType)
            self.failUnless(
                isinstance(
                    typeResource,
                    DirectoryPrincipalTypeProvisioningResource
                )
            )

            typeURL = provisioningURL + recordType + "/"
            self.assertEquals(
                typeURL, typeResource.principalCollectionURL()
            )

            principalCollections = typeResource.principalCollections()
            self.assertEquals(
                set((provisioningURL,)),
                set(
                    pc.principalCollectionURL()
                    for pc in principalCollections
                )
            )

            shortNames = set((yield typeResource.listChildren()))
            # Handle records with mulitple shortNames
            expected = []
            for r in (
                yield self.directory.recordsWithRecordType(
                    self.directory.oldNameToRecordType(recordType)
                )
            ):
                expected.extend(r.shortNames)
            self.assertEquals(shortNames, set(expected))

            for shortName in shortNames:
                #print("     -> %s" % (shortName,))
                recordResource = yield typeResource.getChild(shortName)
                self.failUnless(
                    isinstance(recordResource, DirectoryPrincipalResource)
                )

                # shortName may be non-ascii
                recordURL = typeURL + quote(shortName.encode("utf-8")) + "/"
                self.assertIn(
                    recordURL,
                    (
                        (recordResource.principalURL(),) +
                        tuple(recordResource.alternateURIs())
                    )
                )

                principalCollections = (
                    recordResource.principalCollections()
                )
                self.assertEquals(
                    set((provisioningURL,)),
                    set(
                        pc.principalCollectionURL()
                        for pc in principalCollections
                    )
                )


    @inlineCallbacks
    def test_allRecords(self):
        """
        Test of a test routine...
        """
        for (
            _ignore_provisioningResource, _ignore_recordType, recordResource, record
        ) in (yield self._allRecords()):
            if True:  # user.enabled:
                self.assertEquals(recordResource.record, record)


    ##
    # DirectoryPrincipalProvisioningResource
    ##

    @inlineCallbacks
    def test_principalForShortName(self):
        """
        DirectoryPrincipalProvisioningResource.principalForShortName()
        """
        for (
            provisioningResource, recordType, _ignore_recordResource, record
        ) in (yield self._allRecords()):
            principal = yield provisioningResource.principalForShortName(
                recordType, record.shortNames[0]
            )
            if True:  # user.enabled:
                self.failIf(principal is None)
                self.assertEquals(record, principal.record)
            else:
                self.failIf(principal is not None)


    @inlineCallbacks
    def test_principalForUser(self):
        """
        DirectoryPrincipalProvisioningResource.principalForUser()
        """
        provisioningResource = self.principalRootResource

        for user in (
            yield self.directory.recordsWithRecordType(
                self.directory.recordType.user
            )
        ):
            userResource = yield provisioningResource.principalForUser(
                user.shortNames[0]
            )
            if True:  # user.enabled:
                self.failIf(userResource is None)
                self.assertEquals(user, userResource.record)
            else:
                self.failIf(userResource is not None)


    @inlineCallbacks
    def test_principalForAuthID(self):
        """
        DirectoryPrincipalProvisioningResource.principalForAuthID()
        """
        provisioningResource = self.principalRootResource

        for user in (
            yield self.directory.recordsWithRecordType(
                self.directory.recordType.user
            )
        ):
            creds = UsernamePassword(user.shortNames[0], "bogus")
            userResource = yield provisioningResource.principalForAuthID(creds)
            if True:  # user.enabled:
                self.failIf(userResource is None)
                self.assertEquals(user, userResource.record)
            else:
                self.failIf(userResource is not None)


    @inlineCallbacks
    def test_principalForUID(self):
        """
        DirectoryPrincipalProvisioningResource.principalForUID()
        """
        for (
            provisioningResource, _ignore_recordType, _ignore_recordResource, record
        ) in (yield self._allRecords()):
            principal = yield provisioningResource.principalForUID(record.uid)
            if True:  # user.enabled:
                self.failIf(principal is None)
                self.assertEquals(record, principal.record)
            else:
                self.failIf(principal is not None)


    @inlineCallbacks
    def test_principalForRecord(self):
        """
        DirectoryPrincipalProvisioningResource.principalForRecord()
        """
        for (
            provisioningResource, _ignore_recordType, _ignore_recordResource, record
        ) in (yield self._allRecords()):
            principal = yield provisioningResource.principalForRecord(record)
            if True:  # user.enabled:
                self.failIf(principal is None)
                self.assertEquals(record, principal.record)
            else:
                self.failIf(principal is not None)


    @inlineCallbacks
    def test_principalForCalendarUserAddress(self):
        """
        DirectoryPrincipalProvisioningResource
        .principalForCalendarUserAddress()
        """
        for (
            provisioningResource, _ignore_recordType, recordResource, record
        ) in (yield self._allRecords()):

            test_items = tuple(record.calendarUserAddresses)
            if recordResource:
                principalURL = recordResource.principalURL()
                if principalURL.endswith("/"):
                    alternateURL = principalURL[:-1]
                else:
                    alternateURL = principalURL + "/"
                test_items += (principalURL, alternateURL)

            for address in test_items:
                principal = (
                    yield provisioningResource
                    .principalForCalendarUserAddress(address)
                )
                if record.hasCalendars:
                    self.failIf(principal is None)
                    self.assertEquals(record, principal.record)
                else:
                    self.failIf(principal is not None)

        # Explicitly check the disabled record
        provisioningResource = yield self.actualRoot.getChild("principals")

        self.failUnlessIdentical(
            (
                yield provisioningResource.principalForCalendarUserAddress(
                    "mailto:nocalendar@example.com"
                )
            ),
            None
        )
        self.failUnlessIdentical(
            (
                yield provisioningResource.principalForCalendarUserAddress(
                    "urn:uuid:543D28BA-F74F-4D5F-9243-B3E3A61171E5"
                )
            ),
            None
        )
        self.failUnlessIdentical(
            (
                yield provisioningResource.principalForCalendarUserAddress(
                    "/principals/users/nocalendar/"
                )
            ),
            None
        )
        self.failUnlessIdentical(
            (
                yield provisioningResource.principalForCalendarUserAddress(
                    "/principals/__uids__/"
                    "543D28BA-F74F-4D5F-9243-B3E3A61171E5/"
                )
            ),
            None
        )


    @inlineCallbacks
    def test_hasCalendars(self):
        """
        DirectoryPrincipalProvisioningResource
        .principalForCalendarUserAddress()
        """
        for (
            provisioningResource, _ignore_recordType, _ignore_recordResource, record
        ) in (yield self._allRecords()):
            principal = yield provisioningResource.principalForRecord(record)
            if True:  # user.enabled:
                self.failIf(principal is None)
            else:
                self.failIf(principal is not None)
                continue
            if record.hasCalendars:
                self.assertTrue(
                    isinstance(principal, DirectoryCalendarPrincipalResource)
                )
            else:
                self.assertTrue(
                    isinstance(principal, DirectoryPrincipalResource)
                )
                if record.hasContacts:
                    self.assertTrue(
                        isinstance(
                            principal, DirectoryCalendarPrincipalResource
                        )
                    )
                else:
                    self.assertFalse(
                        isinstance(
                            principal, DirectoryCalendarPrincipalResource
                        )
                    )

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
                    self.fail(
                        "No exception principal: %s, property %s"
                        % (principal, property,)
                    )

            if record.hasCalendars:
                yield hasProperty(
                    (caldav_namespace, "calendar-home-set")
                )
                yield hasProperty(
                    (caldav_namespace, "calendar-user-address-set")
                )
                yield hasProperty(
                    (caldav_namespace, "schedule-inbox-URL")
                )
                yield hasProperty(
                    (caldav_namespace, "schedule-outbox-URL")
                )
                yield hasProperty(
                    (caldav_namespace, "calendar-user-type")
                )
                yield hasProperty(
                    (calendarserver_namespace, "calendar-proxy-read-for")
                )
                yield hasProperty(
                    (calendarserver_namespace, "calendar-proxy-write-for")
                )
                # yield hasProperty(
                #     (calendarserver_namespace, "auto-schedule")
                # )
            else:
                yield doesNotHaveProperty(
                    (caldav_namespace, "calendar-home-set")
                )
                yield doesNotHaveProperty(
                    (caldav_namespace, "calendar-user-address-set")
                )
                yield doesNotHaveProperty(
                    (caldav_namespace, "schedule-inbox-URL")
                )
                yield doesNotHaveProperty(
                    (caldav_namespace, "schedule-outbox-URL")
                )
                yield doesNotHaveProperty(
                    (caldav_namespace, "calendar-user-type")
                )
                yield doesNotHaveProperty(
                    (calendarserver_namespace, "calendar-proxy-read-for")
                )
                yield doesNotHaveProperty(
                    (calendarserver_namespace, "calendar-proxy-write-for")
                )
                # yield doesNotHaveProperty(
                #     (calendarserver_namespace, "auto-schedule")
                # )

            if record.hasContacts:
                yield hasProperty(carddavxml.AddressBookHomeSet.qname())
            else:
                yield doesNotHaveProperty(
                    carddavxml.AddressBookHomeSet.qname()
                )


    @inlineCallbacks
    def test_enabledAsOrganizer(self):
        """
        DirectoryPrincipalProvisioningResource
        .principalForCalendarUserAddress()
        """
        ok_types = (
            self.directory.recordType.user,
        )
        for (
            provisioningResource, recordType, _ignore_recordResource, record
        ) in (yield self._allRecords()):

            if record.hasCalendars:
                principal = (
                    yield provisioningResource.principalForRecord(record)
                )
                self.failIf(principal is None)
                self.assertEqual(
                    principal.enabledAsOrganizer(),
                    recordType in ok_types
                )

        config.Scheduling.Options.AllowGroupAsOrganizer = True
        config.Scheduling.Options.AllowLocationAsOrganizer = True
        config.Scheduling.Options.AllowResourceAsOrganizer = True
        ok_types = (
            self.directory.recordType.user,
            self.directory.recordType.group,
            self.directory.recordType.location,
            self.directory.recordType.resource,
        )
        for (
            provisioningResource, recordType, _ignore_recordResource, record
        ) in (yield self._allRecords()):
            if record.hasCalendars:
                principal = (
                    yield provisioningResource.principalForRecord(record)
                )
                self.failIf(principal is None)
                self.assertEqual(
                    principal.enabledAsOrganizer(),
                    recordType in ok_types
                )


    # FIXME: Run DirectoryPrincipalProvisioningResource tests on
    # DirectoryPrincipalTypeProvisioningResource also

    ##
    # DirectoryPrincipalResource
    ##

    @inlineCallbacks
    def test_cacheNotifier(self):
        """
        Each DirectoryPrincipalResource should have a cacheNotifier attribute
        that is an instance of DisabledCacheNotifier
        """
        for (
            _ignore_provisioningResource, _ignore_recordType, recordResource, _ignore_record
        ) in (yield self._allRecords()):
            if True:  # user.enabled:
                self.failUnless(
                    isinstance(
                        recordResource.cacheNotifier,
                        DisabledCacheNotifier
                    )
                )


    @inlineCallbacks
    def test_displayName(self):
        """
        DirectoryPrincipalResource.displayName()
        """
        for (
            _ignore_provisioningResource, _ignore_recordType, recordResource, _ignore_record
        ) in (yield self._allRecords()):
            self.failUnless(recordResource.displayName())


    @inlineCallbacks
    def test_groupMembers(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        for (
            _ignore_provisioningResource, _ignore_recordType, recordResource, record
        ) in (yield self._allRecords()):
            members = yield recordResource.groupMembers()
            self.failUnless(
                set((yield record.members())).issubset(
                    set(r.record for r in members)
                )
            )


    @inlineCallbacks
    def test_groupMemberships(self):
        """
        DirectoryPrincipalResource.groupMemberships()
        """
        for (
            _ignore_provisioningResource, _ignore_recordType, recordResource, record
        ) in (yield self._allRecords()):
            if True:  # user.enabled:
                memberships = yield recordResource.groupMemberships()
                self.failUnless(
                    set((yield record.groups())).issubset(
                        set(
                            r.record
                            for r in memberships if hasattr(r, "record")
                        )
                    )
                )


    @inlineCallbacks
    def test_principalUID(self):
        """
        DirectoryPrincipalResource.principalUID()
        """
        for (
            _ignore_provisioningResource, _ignore_recordType, recordResource, record
        ) in (yield self._allRecords()):
            self.assertEquals(record.uid, recordResource.principalUID())


    @inlineCallbacks
    def test_calendarUserAddresses(self):
        """
        DirectoryPrincipalResource.calendarUserAddresses()
        """
        for (
            _ignore_provisioningResource, _ignore_recordType, recordResource, record
        ) in (yield self._allRecords()):
            if record.hasCalendars:
                self.assertEqual(
                    set(record.calendarUserAddresses),
                    set(recordResource.calendarUserAddresses())
                )

                # Verify that if not enabled for calendaring, no CUAs:
                record.hasCalendars = False
                self.failIf(recordResource.calendarUserAddresses())


    @inlineCallbacks
    def test_canonicalCalendarUserAddress(self):
        """
        DirectoryPrincipalResource.canonicalCalendarUserAddress()
        """
        for (
            _ignore_provisioningResource, _ignore_recordType, recordResource, record
        ) in (yield self._allRecords()):
            if record.hasCalendars:
                self.failUnless(
                    recordResource.canonicalCalendarUserAddress()
                    .startswith("urn:x-uid:")
                )


    @inlineCallbacks
    def test_addressBookHomeURLs(self):
        """
        DirectoryPrincipalResource.addressBookHomeURLs(),
        """

        for (
            _ignore_provisioningResource, _ignore_recordType, recordResource, record
        ) in (yield self._allRecords()):
            if record.hasContacts:
                homeURLs = tuple(recordResource.addressBookHomeURLs())
                self.failUnless(homeURLs)

                # Turn off hasContacts and addressBookHomeURLs
                # should be empty
                record.hasContacts = False
                self.failIf(tuple(recordResource.addressBookHomeURLs()))
                record.hasContacts = True

                addressBookRootResource = yield self.actualRoot.getChild("addressbooks")
                addressBookRootURL = addressBookRootResource.url()

                for homeURL in homeURLs:
                    self.failUnless(homeURL.startswith(addressBookRootURL))


    @inlineCallbacks
    def test_calendarHomeURLs(self):
        """
        DirectoryPrincipalResource.calendarHomeURLs(),
        DirectoryPrincipalResource.scheduleInboxURL(),
        DirectoryPrincipalResource.scheduleOutboxURL()
        """
        # # No calendar home provisioner should result in no calendar homes.
        # for (
        #     provisioningResource, recordType, recordResource, record
        # ) in (yield self._allRecords()):
        #     if record.hasCalendars:
        #         self.failIf(tuple(recordResource.calendarHomeURLs()))
        #         self.failIf(recordResource.scheduleInboxURL())
        #         self.failIf(recordResource.scheduleOutboxURL())

        # # Need to create a calendar home provisioner for each service.
        # calendarRootResources = {}

        # path = os.path.join(self.docroot, self.directory.__class__.__name__)

        # if os.path.exists(path):
        #     rmdir(path)
        # os.mkdir(path)

        # # Need a data store
        # _newStore = CommonDataStore(path, None, None, True, False)

        # provisioningResource = DirectoryCalendarHomeProvisioningResource(
        #     self.directory,
        #     "/calendars/",
        #     _newStore
        # )

        # calendarRootResources[self.directory.__class__.__name__] = (
        #     provisioningResource
        # )

        # Calendar home provisioners should result in calendar homes.
        for (
            _ignore_provisioningResource, _ignore_recordType, recordResource, record
        ) in (yield self._allRecords()):
            if record.hasCalendars:
                homeURLs = tuple(recordResource.calendarHomeURLs())
                self.failUnless(homeURLs)

                # Turn off hasCalendars and calendarHomeURLs should
                # be empty
                record.hasCalendars = False
                self.failIf(tuple(recordResource.calendarHomeURLs()))
                record.hasCalendars = True

                calendarRootResource = yield self.rootResource.getChild("calendars")
                calendarRootURL = calendarRootResource.url()

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


    @inlineCallbacks
    def test_canAutoSchedule(self):
        """
        DirectoryPrincipalResource.canAutoSchedule()
        """

        # This test used to set the autoschedule mode in a separate loop, but
        # the records aren't cached, so I've moved this into the later loop

        # # Set all resources and locations to auto-schedule, plus one user
        # for (
        #     provisioningResource, recordType, recordResource, record
        # ) in (yield self._allRecords()):
        #     if record.hasCalendars:
        #         print("before", record, record.recordType, record.uid)
        #         if (
        #             recordType in (CalRecordType.location, CalRecordType.resource) or
        #             record.uid == "5A985493-EE2C-4665-94CF-4DFEA3A89500"
        #         ):
        #             record.fields[record.service.fieldName.lookupByName("autoScheduleMode")] = AutoScheduleMode.acceptIfFreeDeclineIfBusy
        #             print("modifying", record, record.fields)

        # Default state - resources and locations, enabled, others not
        for (
            _ignore_provisioningResource, recordType, recordResource, record
        ) in (yield self._allRecords()):
            if record.hasCalendars:
                if recordType in (CalRecordType.location, CalRecordType.resource):
                    self.assertTrue((yield recordResource.canAutoSchedule()))
                else:
                    self.assertFalse((yield recordResource.canAutoSchedule()))

        # Set config to allow users
        self.patch(config.Scheduling.Options.AutoSchedule, "AllowUsers", True)
        for (
            _ignore_provisioningResource, recordType, recordResource, record
        ) in (yield self._allRecords()):
            if record.hasCalendars:
                if (
                    recordType in (CalRecordType.location, CalRecordType.resource) or
                    record.uid == u"5A985493-EE2C-4665-94CF-4DFEA3A89500"
                ):
                    record.fields[
                        record.service.fieldName.lookupByName(
                            "autoScheduleMode"
                        )
                    ] = AutoScheduleMode.acceptIfFreeDeclineIfBusy

                    self.assertTrue((yield recordResource.canAutoSchedule()))
                else:
                    self.assertFalse((yield recordResource.canAutoSchedule()))

        # Set config to disallow all
        self.patch(config.Scheduling.Options.AutoSchedule, "Enabled", False)
        for (
            _ignore_provisioningResource, recordType, recordResource, record
        ) in (yield self._allRecords()):
            if record.hasCalendars:
                self.assertFalse((yield recordResource.canAutoSchedule()))


    @inlineCallbacks
    def test_canAutoScheduleAutoAcceptGroup(self):
        """
        DirectoryPrincipalResource.canAutoSchedule(organizer)
        """

        # Location "apollo" has an auto-accept group ("both_coasts") set in
        # augments.xml, therefore any organizer in that group should be able to
        # auto schedule

        record = yield self.directory.recordWithUID(u"apollo")

        # Turn off this record's autoschedule
        record.fields[
            record.service.fieldName.lookupByName(
                "autoScheduleMode"
            )
        ] = AutoScheduleMode.none

        # No organizer
        self.assertFalse((yield record.canAutoSchedule()))

        # Organizer in auto-accept group
        self.assertTrue(
            (
                yield record.canAutoSchedule(
                    organizer="mailto:wsanchez@example.com"
                )
            )
        )
        # Organizer not in auto-accept group
        self.assertFalse(
            (
                yield record.canAutoSchedule(
                    organizer="mailto:a@example.com"
                )
            )
        )


    @inlineCallbacks
    def test_defaultAccessControlList_principals(self):
        """
        Default access controls for principals.
        """
        for (
            _ignore_provisioningResource, _ignore_recordType, recordResource, _ignore_record
        ) in (yield self._allRecords()):
            if True:  # user.enabled:
                for args in (
                    yield _authReadOnlyPrivileges(
                        self, recordResource, recordResource.principalURL()
                    )
                ):
                    yield self._checkPrivileges(*args)


    @inlineCallbacks
    def test_defaultAccessControlList_provisioners(self):
        """
        Default access controls for principal provisioning resources.
        """
        provisioningResource = self.principalRootResource

        for args in (
            yield _authReadOnlyPrivileges(
                self, provisioningResource,
                provisioningResource.principalCollectionURL()
            )
        ):
            yield self._checkPrivileges(*args)

        for recordType in (yield provisioningResource.listChildren()):
            #print("   -> %s" % (recordType,))
            typeResource = yield provisioningResource.getChild(recordType)

            for args in (
                yield _authReadOnlyPrivileges(
                    self, typeResource, typeResource.principalCollectionURL()
                )
            ):
                yield self._checkPrivileges(*args)


    def test_propertyToField(self):

        class stubElement(object):
            def __init__(self, ns, name):
                self.ns = ns
                self.name = name

            def qname(self):
                return self.ns, self.name

        provisioningResource = self.principalRootResource

        expected = (
            (
                "DAV:", "displayname",
                "morgen", "fullNames", "morgen"
            ),
            (
                "urn:ietf:params:xml:ns:caldav", "calendar-user-type",
                "INDIVIDUAL", "recordType", RecordType.user
            ),
            (
                "urn:ietf:params:xml:ns:caldav", "calendar-user-type",
                "GROUP", "recordType", RecordType.group
            ),
            (
                "urn:ietf:params:xml:ns:caldav", "calendar-user-type",
                "RESOURCE", "recordType", CalRecordType.resource
            ),
            (
                "urn:ietf:params:xml:ns:caldav", "calendar-user-type",
                "ROOM", "recordType", CalRecordType.location
            ),
            (
                "urn:ietf:params:xml:ns:caldav", "calendar-user-address-set",
                "/principals/__uids__/AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA/",
                "uid", "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
            ),
            (
                "urn:ietf:params:xml:ns:caldav", "calendar-user-address-set",
                "http://example.com:8008/principals/__uids__/"
                "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA/",
                "uid", "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
            ),
            (
                "urn:ietf:params:xml:ns:caldav", "calendar-user-address-set",
                "urn:uuid:AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
                "guid", UUID("AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA")
            ),
            (
                "urn:ietf:params:xml:ns:caldav", "calendar-user-address-set",
                "/principals/users/example/", "recordName", "example"
            ),
            (
                "urn:ietf:params:xml:ns:caldav", "calendar-user-address-set",
                "https://example.com:8443/principals/users/example/",
                "recordName", "example"
            ),
            (
                "urn:ietf:params:xml:ns:caldav", "calendar-user-address-set",
                "mailto:example@example.com",
                "emailAddresses", "example@example.com"
            ),
            (
                "http://calendarserver.org/ns/", "first-name",
                "morgen", "firstName", "morgen"
            ),
            (
                "http://calendarserver.org/ns/", "last-name",
                "sagen", "lastName", "sagen"
            ),
            (
                "http://calendarserver.org/ns/", "email-address-set",
                "example@example.com", "emailAddresses", "example@example.com"
            ),
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
            C{(provisioningResource, recordType, recordResource, record)},
            where C{provisioningResource} is the root provisioning resource,
            C{recordType} is the record type, C{recordResource} is the
            principal resource and C{record} is the directory service record
            for each record the directory.
        """
        provisioningResource = self.principalRootResource
        results = []
        for recordType in self.directory.recordTypes():
            for record in (
                yield self.directory.recordsWithRecordType(recordType)
            ):
                recordResource = (
                    yield provisioningResource.principalForRecord(record)
                )
                results.append(
                    (provisioningResource, recordType, recordResource, record)
                )
        returnValue(results)


    def _checkPrivileges(self, resource, url, principal, privilege, allowed):
        request = SimpleRequest(self.site, "GET", "/")

        def gotResource(resource):
            d = resource.checkPrivileges(
                request, (privilege,), principal=davxml.Principal(principal)
            )
            if allowed:
                def onError(f):
                    f.trap(AccessDeniedError)
                    #print(resource.readDeadProperty(davxml.ACL))
                    self.fail(
                        "%s should have %s privilege on %r"
                        % (principal.sname(), privilege.sname(), resource)
                    )
                d.addErrback(onError)
            else:
                def expectAccessDenied(f):
                    f.trap(AccessDeniedError)

                def onSuccess(_):
                    #print(resource.readDeadProperty(davxml.ACL))
                    self.fail(
                        "%s should not have %s privilege on %r"
                        % (principal.sname(), privilege.sname(), resource)
                    )
                d.addCallbacks(onSuccess, expectAccessDenied)
            return d

        d = request.locateResource(url)
        d.addCallback(gotResource)
        return d



@inlineCallbacks
def _authReadOnlyPrivileges(self, resource, url):
    items = []
    for (
        _ignore_provisioningResource, _ignore_recordType, recordResource, _ignore_record
    ) in (yield self._allRecords()):
        if True:  # user.enabled:
            items.append((
                davxml.HRef().fromString(recordResource.principalURL()),
                davxml.Read(), True
            ))
            items.append((
                davxml.HRef().fromString(recordResource.principalURL()),
                davxml.Write(), False
            ))
    items.append((
        davxml.Unauthenticated(), davxml.Read(), False
    ))
    items.append((
        davxml.Unauthenticated(), davxml.Write(), False
    ))

    results = []
    for principal, privilege, allowed in items:
        results.append((resource, url, principal, privilege, allowed))

    returnValue(results)



class ProxyPrincipals(StoreTestCase):
    """
    Directory service proxy principals.
    """
    @inlineCallbacks
    def setUp(self):
        yield super(ProxyPrincipals, self).setUp()

        self.principalRootResource = self.actualRoot.getChild("principals")


    @inlineCallbacks
    def test_hideDisabledProxies(self):
        """
        Make sure users that are missing or not enabled for calendaring are removed
        from the proxyFor list.
        """

        # Check proxies empty right now
        principal01 = yield self.principalRootResource.principalForUID((yield self.userUIDFromShortName("user01")))
        self.assertTrue(len((yield principal01.proxyFor(False))) == 0)
        self.assertTrue(len((yield principal01.proxyFor(True))) == 0)

        principal02 = yield self.principalRootResource.principalForUID((yield self.userUIDFromShortName("user02")))
        self.assertTrue(len((yield principal02.proxyFor(False))) == 0)
        self.assertTrue(len((yield principal02.proxyFor(True))) == 0)

        principal03 = yield self.principalRootResource.principalForUID((yield self.userUIDFromShortName("user03")))
        self.assertTrue(len((yield principal03.proxyFor(False))) == 0)
        self.assertTrue(len((yield principal03.proxyFor(True))) == 0)

        # Make user01 a read-only proxy for user02 and user03
        yield addDelegate(self.transactionUnderTest(), principal02.record, principal01.record, False)
        yield addDelegate(self.transactionUnderTest(), principal03.record, principal01.record, False)
        yield self.commit()

        self.assertTrue(len((yield principal01.proxyFor(False))) == 2)
        self.assertTrue(len((yield principal01.proxyFor(True))) == 0)

        # Now disable user02
        yield self.changeRecord(principal02.record, self.directory.fieldName.hasCalendars, False)

        self.assertTrue(len((yield principal01.proxyFor(False))) == 1)
        self.assertTrue(len((yield principal01.proxyFor(True))) == 0)

        # Now enable user02
        yield self.changeRecord(principal02.record, self.directory.fieldName.hasCalendars, True)

        self.assertTrue(len((yield principal01.proxyFor(False))) == 2)
        self.assertTrue(len((yield principal01.proxyFor(True))) == 0)

        # Now remove user02
        yield self.directory.removeRecords((principal02.record.uid,))

        self.assertTrue(len((yield principal01.proxyFor(False))) == 1)
        self.assertTrue(len((yield principal01.proxyFor(True))) == 0)
