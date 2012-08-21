##
# Copyright (c) 2011-2012 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import Clock
from twisted.python.filepath import FilePath

from twistedcaldav.test.util import TestCase
from twistedcaldav.test.util import xmlFile, augmentsFile, proxiesFile, dirTest
from twistedcaldav.config import config
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord, GroupMembershipCacherService, GroupMembershipCache, GroupMembershipCacheUpdater
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.directory.calendaruserproxyloader import XMLCalendarUserProxyLoader
from twistedcaldav.directory import augment, calendaruserproxy
from twistedcaldav.directory.util import normalizeUUID
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource

import cPickle as pickle
import uuid

def StubCheckSACL(cls, username, service):
    services = {
        "calendar" : ["amanda", "betty"],
        "addressbook" : ["amanda", "carlene"],
    }
    if username in services[service]:
        return 0
    return 1

class SACLTests(TestCase):

    def setUp(self):
        self.patch(DirectoryRecord, "CheckSACL", StubCheckSACL)
        self.patch(config, "EnableSACLs", True)
        self.service = DirectoryService()
        self.service.setRealm("test")
        self.service.baseGUID = "0E8E6EC2-8E52-4FF3-8F62-6F398B08A498"


    def test_applySACLs(self):
        """
        Users not in calendar SACL will have enabledForCalendaring set to
        False.
        Users not in addressbook SACL will have enabledForAddressBooks set to
        False.
        """

        data = [
            ("amanda",  True,  True,),
            ("betty",   True,  False,),
            ("carlene", False, True,),
            ("daniel",  False, False,),
        ]
        for username, cal, ab in data:
            record = DirectoryRecord(self.service, "users", None, (username,),
                enabledForCalendaring=True, enabledForAddressBooks=True)
            record.applySACLs()
            self.assertEquals(record.enabledForCalendaring, cal)
            self.assertEquals(record.enabledForAddressBooks, ab)

class GroupMembershipTests (TestCase):

    @inlineCallbacks
    def setUp(self):
        super(GroupMembershipTests, self).setUp()

        self.directoryService = XMLDirectoryService(
            {
                'xmlFile' : xmlFile,
                'augmentService' :
                    augment.AugmentXMLDB(xmlFiles=(augmentsFile.path,)),
            }
        )
        calendaruserproxy.ProxyDBService = calendaruserproxy.ProxySqliteDB("proxies.sqlite")

        # Set up a principals hierarchy for each service we're testing with
        self.principalRootResources = {}
        name = self.directoryService.__class__.__name__
        url = "/" + name + "/"

        provisioningResource = DirectoryPrincipalProvisioningResource(url, self.directoryService)

        self.site.resource.putChild(name, provisioningResource)

        self.principalRootResources[self.directoryService.__class__.__name__] = provisioningResource

        yield XMLCalendarUserProxyLoader(proxiesFile.path).updateProxyDB()

    def tearDown(self):
        """ Empty the proxy db between tests """
        return calendaruserproxy.ProxyDBService.clean()

    def _getPrincipalByShortName(self, type, name):
        provisioningResource = self.principalRootResources[self.directoryService.__class__.__name__]
        return provisioningResource.principalForShortName(type, name)

    def _updateMethod(self):
        """
        Update a counter in the following test
        """
        self.count += 1

    @inlineCallbacks
    def test_groupMembershipCacherService(self):
        """
        Instantiate a GroupMembershipCacherService and make sure its update
        method fires at the right interval, in this case 30 seconds.  The
        updateMethod keyword arg is purely for testing purposes, so we can
        directly detect it getting called in this test.
        """
        clock = Clock()
        self.count = 0

        # Deliberately set the expireSeconds lower than updateSeconds to verify
        # expireSeconds gets set to 2 * updateSeconds in that scenario

        service = GroupMembershipCacherService(
            None, None, "Testing", 30, 20, 30, reactor=clock,
            updateMethod=self._updateMethod)

        # expireSeconds = 2 * 30 updateSeconds
        self.assertEquals(service.updater.cache.expireSeconds, 60)

        yield service.startService()

        self.assertEquals(self.count, 1)
        clock.advance(29)
        self.assertEquals(self.count, 1)
        clock.advance(1)
        self.assertEquals(self.count, 2)

        service.stopService()

        service.updateInProgress = True
        self.assertTrue((yield service.update()))
        self.assertTrue(service.updateAwaiting)

        service.updateInProgress = False
        self.assertFalse((yield service.update()))
        self.assertFalse(service.updateAwaiting)



    def test_expandedMembers(self):
        """
        Make sure expandedMembers( ) returns a complete, flattened set of
        members of a group, including all sub-groups.
        """
        bothCoasts = self.directoryService.recordWithShortName(
            DirectoryService.recordType_groups, "both_coasts")
        self.assertEquals(
            set([r.guid for r in bothCoasts.expandedMembers()]),
            set(['8B4288F6-CC82-491D-8EF9-642EF4F3E7D0',
                 '6423F94A-6B76-4A3A-815B-D52CFD77935D',
                 '5A985493-EE2C-4665-94CF-4DFEA3A89500',
                 '5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1',
                 'left_coast',
                 'right_coast'])
        )


    @inlineCallbacks
    def test_groupMembershipCache(self):
        """
        Ensure we get back what we put in
        """
        cache = GroupMembershipCache("ProxyDB", expireSeconds=10)

        yield cache.setGroupsFor("a", set(["b", "c", "d"])) # a is in b, c, d
        members = (yield cache.getGroupsFor("a"))
        self.assertEquals(members, set(["b", "c", "d"]))

        yield cache.setGroupsFor("b", set()) # b not in any groups
        members = (yield cache.getGroupsFor("b"))
        self.assertEquals(members, set())

        cache._memcacheProtocol.advanceClock(10)

        members = (yield cache.getGroupsFor("a")) # has expired
        self.assertEquals(members, set())




    @inlineCallbacks
    def test_groupMembershipCacheUpdater(self):
        """
        Let the GroupMembershipCacheUpdater populate the cache, then make
        sure proxyFor( ) and groupMemberships( ) work from the cache
        """
        cache = GroupMembershipCache("ProxyDB", expireSeconds=60)
        # Having a groupMembershipCache assigned to the directory service is the
        # trigger to use such a cache:
        self.directoryService.groupMembershipCache = cache

        updater = GroupMembershipCacheUpdater(
            calendaruserproxy.ProxyDBService, self.directoryService, 30, 30,
            cache=cache, useExternalProxies=False)

        # Exercise getGroups()
        groups, aliases = (yield updater.getGroups())
        self.assertEquals(
            groups,
            {
                '9FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1':
                    set(['8B4288F6-CC82-491D-8EF9-642EF4F3E7D0']),
                'admin':
                    set(['9FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1']),
                'both_coasts':
                    set(['left_coast', 'right_coast']),
                'grunts':
                    set(['5A985493-EE2C-4665-94CF-4DFEA3A89500',
                         '5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1',
                         '6423F94A-6B76-4A3A-815B-D52CFD77935D']),
                'left_coast':
                    set(['5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1',
                         '6423F94A-6B76-4A3A-815B-D52CFD77935D',
                         '8B4288F6-CC82-491D-8EF9-642EF4F3E7D0']),
                'non_calendar_group':
                    set(['5A985493-EE2C-4665-94CF-4DFEA3A89500',
                         '8B4288F6-CC82-491D-8EF9-642EF4F3E7D0']),
                'recursive1_coasts':
                    set(['6423F94A-6B76-4A3A-815B-D52CFD77935D',
                         'recursive2_coasts']),
                'recursive2_coasts':
                    set(['5A985493-EE2C-4665-94CF-4DFEA3A89500',
                         'recursive1_coasts']),
                'right_coast':
                    set(['5A985493-EE2C-4665-94CF-4DFEA3A89500'])
            }
        )
        self.assertEquals(
            aliases,
            {
                '9FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1':
                    '9FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1',
                 'admin': 'admin',
                 'both_coasts': 'both_coasts',
                 'grunts': 'grunts',
                 'left_coast': 'left_coast',
                 'non_calendar_group': 'non_calendar_group',
                 'recursive1_coasts': 'recursive1_coasts',
                 'recursive2_coasts': 'recursive2_coasts',
                 'right_coast': 'right_coast'
            }
        )

        # Exercise expandedMembers()
        self.assertEquals(
            updater.expandedMembers(groups, "both_coasts"),
            set(['5A985493-EE2C-4665-94CF-4DFEA3A89500',
                 '5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1',
                 '6423F94A-6B76-4A3A-815B-D52CFD77935D',
                 '8B4288F6-CC82-491D-8EF9-642EF4F3E7D0',
                 'left_coast',
                 'right_coast']
            )
        )

        # Prevent an update by locking the cache
        acquiredLock = (yield cache.acquireLock())
        self.assertTrue(acquiredLock)
        self.assertEquals((False, 0), (yield updater.updateCache()))

        # You can't lock when already locked:
        acquiredLockAgain = (yield cache.acquireLock())
        self.assertFalse(acquiredLockAgain)

        # Allow an update by unlocking the cache
        yield cache.releaseLock()
        self.assertEquals((False, 8, 8), (yield updater.updateCache()))

        # Verify cache is populated:
        self.assertTrue((yield cache.isPopulated()))

        delegates = (

            # record name
            # read-write delegators
            # read-only delegators
            # groups delegate is in (restricted to only those groups
            #   participating in delegation)

            ("wsanchez",
             set(["mercury", "apollo", "orion", "gemini"]),
             set(["non_calendar_proxy"]),
             set(['left_coast',
                  'both_coasts',
                  'recursive1_coasts',
                  'recursive2_coasts',
                  'gemini#calendar-proxy-write',
                ]),
            ),
            ("cdaboo",
             set(["apollo", "orion", "non_calendar_proxy"]),
             set(["non_calendar_proxy"]),
             set(['both_coasts',
                  'non_calendar_group',
                  'recursive1_coasts',
                  'recursive2_coasts',
                ]),
            ),
            ("lecroy",
             set(["apollo", "mercury", "non_calendar_proxy"]),
             set(),
             set(['both_coasts',
                  'left_coast',
                  'non_calendar_group',
                ]),
            ),
            ("usera",
             set(),
             set(),
             set(),
            ),
            ("userb",
             set(['7423F94A-6B76-4A3A-815B-D52CFD77935D']),
             set(),
             set(['7423F94A-6B76-4A3A-815B-D52CFD77935D#calendar-proxy-write']),
            ),
            ("userc",
             set(['7423F94A-6B76-4A3A-815B-D52CFD77935D']),
             set(),
             set(['7423F94A-6B76-4A3A-815B-D52CFD77935D#calendar-proxy-write']),
            ),
        )

        for name, write, read, groups in delegates:
            delegate = self._getPrincipalByShortName(DirectoryService.recordType_users, name)

            proxyFor = (yield delegate.proxyFor(True))
            self.assertEquals(
                set([p.record.guid for p in proxyFor]),
                write,
            )
            proxyFor = (yield delegate.proxyFor(False))
            self.assertEquals(
                set([p.record.guid for p in proxyFor]),
                read,
            )
            groupsIn = (yield delegate.groupMemberships())
            uids = set()
            for group in groupsIn:
                try:
                    uid = group.uid # a sub-principal
                except AttributeError:
                    uid = group.record.guid # a regular group
                uids.add(uid)
            self.assertEquals(
                set(uids),
                groups,
            )

        # Verify CalendarUserProxyPrincipalResource.containsPrincipal( ) works
        delegator = self._getPrincipalByShortName(DirectoryService.recordType_locations, "mercury")
        proxyPrincipal = delegator.getChild("calendar-proxy-write")
        for expected, name in [(True, "wsanchez"), (False, "cdaboo")]:
            delegate = self._getPrincipalByShortName(DirectoryService.recordType_users, name)
            self.assertEquals(expected, (yield proxyPrincipal.containsPrincipal(delegate)))

        # Verify that principals who were previously members of delegated-to groups but
        # are no longer members have their proxyFor info cleaned out of the cache:
        # Remove wsanchez from all groups in the directory, run the updater, then check
        # that wsanchez is only a proxy for gemini (since that assignment does not involve groups)
        self.directoryService.xmlFile = dirTest.child("accounts-modified.xml")
        self.directoryService._alwaysStat = True
        self.assertEquals((False, 7, 1), (yield updater.updateCache()))
        delegate = self._getPrincipalByShortName(DirectoryService.recordType_users, "wsanchez")
        proxyFor = (yield delegate.proxyFor(True))
        self.assertEquals(
          set([p.record.guid for p in proxyFor]),
          set(['gemini'])
        )


    @inlineCallbacks
    def test_groupMembershipCacheUpdaterExternalProxies(self):
        """
        Exercise external proxy assignment support (assignments come from the
        directory service itself)
        """
        cache = GroupMembershipCache("ProxyDB", expireSeconds=60)
        # Having a groupMembershipCache assigned to the directory service is the
        # trigger to use such a cache:
        self.directoryService.groupMembershipCache = cache

        # This time, we're setting some external proxy assignments for the
        # "transporter" resource...
        def fakeExternalProxies():
            return [
                (
                    "transporter#calendar-proxy-write",
                    set(["6423F94A-6B76-4A3A-815B-D52CFD77935D",
                         "8B4288F6-CC82-491D-8EF9-642EF4F3E7D0"])
                ),
                (
                    "transporter#calendar-proxy-read",
                    set(["5A985493-EE2C-4665-94CF-4DFEA3A89500"])
                ),
            ]

        updater = GroupMembershipCacheUpdater(
            calendaruserproxy.ProxyDBService, self.directoryService, 30, 30,
            cache=cache, useExternalProxies=True,
            externalProxiesSource=fakeExternalProxies)

        yield updater.updateCache()

        delegates = (

            # record name
            # read-write delegators
            # read-only delegators
            # groups delegate is in (restricted to only those groups
            #   participating in delegation)

            ("wsanchez",
             set(["mercury", "apollo", "orion", "gemini", "transporter"]),
             set(["non_calendar_proxy"]),
             set(['left_coast',
                  'both_coasts',
                  'recursive1_coasts',
                  'recursive2_coasts',
                  'gemini#calendar-proxy-write',
                  'transporter#calendar-proxy-write',
                ]),
            ),
            ("cdaboo",
             set(["apollo", "orion", "non_calendar_proxy"]),
             set(["non_calendar_proxy", "transporter"]),
             set(['both_coasts',
                  'non_calendar_group',
                  'recursive1_coasts',
                  'recursive2_coasts',
                  'transporter#calendar-proxy-read',
                ]),
            ),
            ("lecroy",
             set(["apollo", "mercury", "non_calendar_proxy", "transporter"]),
             set(),
             set(['both_coasts',
                  'left_coast',
                  'non_calendar_group',
                  'transporter#calendar-proxy-write',
                ]),
            ),
        )

        for name, write, read, groups in delegates:
            delegate = self._getPrincipalByShortName(DirectoryService.recordType_users, name)

            proxyFor = (yield delegate.proxyFor(True))
            self.assertEquals(
                set([p.record.guid for p in proxyFor]),
                write,
            )
            proxyFor = (yield delegate.proxyFor(False))
            self.assertEquals(
                set([p.record.guid for p in proxyFor]),
                read,
            )
            groupsIn = (yield delegate.groupMemberships())
            uids = set()
            for group in groupsIn:
                try:
                    uid = group.uid # a sub-principal
                except AttributeError:
                    uid = group.record.guid # a regular group
                uids.add(uid)
            self.assertEquals(
                set(uids),
                groups,
            )


    @inlineCallbacks
    def test_groupMembershipCacheSnapshot(self):
        """
        The group membership cache creates a snapshot (a pickle file) of
        the member -> groups dictionary, and can quickly refresh memcached
        from that snapshot when restarting the server.
        """
        cache = GroupMembershipCache("ProxyDB", expireSeconds=60)
        # Having a groupMembershipCache assigned to the directory service is the
        # trigger to use such a cache:
        self.directoryService.groupMembershipCache = cache

        updater = GroupMembershipCacheUpdater(
            calendaruserproxy.ProxyDBService, self.directoryService, 30, 30,
            cache=cache)

        dataRoot = FilePath(config.DataRoot)
        snapshotFile = dataRoot.child("memberships_cache")

        # Snapshot doesn't exist initially
        self.assertFalse(snapshotFile.exists())

        # Try a fast update (as when the server starts up for the very first
        # time), but since the snapshot doesn't exist we fault in from the
        # directory (fast now is False), and snapshot will get created

        # Note that because fast=True and isPopulated() is False, locking is
        # ignored:
        yield cache.acquireLock()

        self.assertFalse((yield cache.isPopulated()))
        fast, numMembers, numChanged = (yield updater.updateCache(fast=True))
        self.assertEquals(fast, False)
        self.assertEquals(numMembers, 8)
        self.assertEquals(numChanged, 8)
        self.assertTrue(snapshotFile.exists())
        self.assertTrue((yield cache.isPopulated()))

        yield cache.releaseLock()

        # Try another fast update where the snapshot already exists (as in a
        # server-restart scenario), which will only read from the snapshot
        # as indicated by the return value for "fast".  Note that the cache
        # is already populated so updateCache( ) in fast mode will not do
        # anything, and numMembers will be 0.
        fast, numMembers = (yield updater.updateCache(fast=True))
        self.assertEquals(fast, True)
        self.assertEquals(numMembers, 0)

        # Try an update which faults in from the directory (fast=False)
        fast, numMembers, numChanged = (yield updater.updateCache(fast=False))
        self.assertEquals(fast, False)
        self.assertEquals(numMembers, 8)
        self.assertEquals(numChanged, 0)

        # Verify the snapshot contains the pickled dictionary we expect
        members = pickle.loads(snapshotFile.getContent())
        self.assertEquals(
            members,
            {
                "5A985493-EE2C-4665-94CF-4DFEA3A89500":
                    set([
                        u"non_calendar_group",
                        u"recursive1_coasts",
                        u"recursive2_coasts",
                        u"both_coasts"
                    ]),
                "6423F94A-6B76-4A3A-815B-D52CFD77935D":
                    set([
                        u"left_coast",
                        u"recursive1_coasts",
                        u"recursive2_coasts",
                        u"both_coasts"
                    ]),
                "5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1":
                    set([
                        u"left_coast",
                        u"both_coasts"
                    ]),
                "8B4288F6-CC82-491D-8EF9-642EF4F3E7D0":
                    set([
                        u"non_calendar_group",
                        u"left_coast",
                        u"both_coasts"
                    ]),
                "left_coast":
                     set([
                         u"both_coasts"
                     ]),
                "recursive1_coasts":
                     set([
                         u"recursive1_coasts",
                         u"recursive2_coasts"
                     ]),
                "recursive2_coasts":
                    set([
                        u"recursive1_coasts",
                        u"recursive2_coasts"
                    ]),
                "right_coast":
                    set([
                        u"both_coasts"
                    ])
            }
        )

class RecordsMatchingTokensTests(TestCase):

    @inlineCallbacks
    def setUp(self):
        super(RecordsMatchingTokensTests, self).setUp()

        self.directoryService = XMLDirectoryService(
            {
                'xmlFile' : xmlFile,
                'augmentService' :
                    augment.AugmentXMLDB(xmlFiles=(augmentsFile.path,)),
            }
        )
        calendaruserproxy.ProxyDBService = calendaruserproxy.ProxySqliteDB("proxies.sqlite")

        # Set up a principals hierarchy for each service we're testing with
        self.principalRootResources = {}
        name = self.directoryService.__class__.__name__
        url = "/" + name + "/"

        provisioningResource = DirectoryPrincipalProvisioningResource(url, self.directoryService)

        self.site.resource.putChild(name, provisioningResource)

        self.principalRootResources[self.directoryService.__class__.__name__] = provisioningResource

        yield XMLCalendarUserProxyLoader(proxiesFile.path).updateProxyDB()

    def tearDown(self):
        """ Empty the proxy db between tests """
        return calendaruserproxy.ProxyDBService.clean()

    @inlineCallbacks
    def test_recordsMatchingTokens(self):
        """
        Exercise the default recordsMatchingTokens implementation
        """
        records = list((yield self.directoryService.recordsMatchingTokens(["Use", "01"])))
        self.assertEquals(len(records), 1)
        self.assertEquals(records[0].shortNames[0], "user01")

        records = list((yield self.directoryService.recordsMatchingTokens(['"quotey"'],
            context=self.directoryService.searchContext_attendee)))
        self.assertEquals(len(records), 1)
        self.assertEquals(records[0].shortNames[0], "doublequotes")

        records = list((yield self.directoryService.recordsMatchingTokens(["coast"])))
        self.assertEquals(len(records), 5)

        records = list((yield self.directoryService.recordsMatchingTokens(["poll"],
            context=self.directoryService.searchContext_location)))
        self.assertEquals(len(records), 1)
        self.assertEquals(records[0].shortNames[0], "apollo")


 
class GUIDTests(TestCase):

    def setUp(self):
        self.service = DirectoryService()
        self.service.setRealm("test")
        self.service.baseGUID = "0E8E6EC2-8E52-4FF3-8F62-6F398B08A498"

    def test_normalizeUUID(self):

        # Ensure that record.guid automatically gets normalized to
        # uppercase+hyphenated form if the value is one that uuid.UUID( )
        # recognizes.

        data = (
            (
                "0543A85A-D446-4CF6-80AE-6579FA60957F",
                "0543A85A-D446-4CF6-80AE-6579FA60957F"
            ),
            (
                "0543a85a-d446-4cf6-80ae-6579fa60957f",
                "0543A85A-D446-4CF6-80AE-6579FA60957F"
            ),
            (
                "0543A85AD4464CF680AE-6579FA60957F",
                "0543A85A-D446-4CF6-80AE-6579FA60957F"
            ),
            (
                "0543a85ad4464cf680ae6579fa60957f",
                "0543A85A-D446-4CF6-80AE-6579FA60957F"
            ),
            (
                "foo",
                "foo"
            ),
            (
                None,
                None
            ),
        )
        for original, expected in data:
            self.assertEquals(expected, normalizeUUID(original))
            record = DirectoryRecord(self.service, "users", original,
                shortNames=("testing",))
            self.assertEquals(expected, record.guid)

class DirectoryRecordTests(TestCase):
    """
    Test L{DirectoryRecord} apis.
    """

    def setUp(self):
        self.service = DirectoryService()
        self.service.setRealm("test")
        self.service.baseGUID = "0E8E6EC2-8E52-4FF3-8F62-6F398B08A498"

    def test_cacheToken(self):
        """
        Test that DirectoryRecord.cacheToken is different for different records, and its value changes
        as attributes on the record change.
        """

        record1 = DirectoryRecord(self.service, "users", str(uuid.uuid4()), shortNames=("testing1",))
        record2 = DirectoryRecord(self.service, "users", str(uuid.uuid4()), shortNames=("testing2",))
        self.assertNotEquals(record1.cacheToken(), record2.cacheToken())

        cache1 = record1.cacheToken()
        record1.enabled = True
        self.assertNotEquals(cache1, record1.cacheToken())

        cache1 = record1.cacheToken()
        record1.enabledForCalendaring = True
        self.assertNotEquals(cache1, record1.cacheToken())
