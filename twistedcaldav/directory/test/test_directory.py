##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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
from twistedcaldav.test.util import xmlFile, augmentsFile, proxiesFile
from twistedcaldav.config import config
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord, GroupMembershipCacherService, GroupMembershipCache, GroupMembershipCacheUpdater
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.directory.calendaruserproxyloader import XMLCalendarUserProxyLoader
from twistedcaldav.directory import augment, calendaruserproxy
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource

import cPickle as pickle

def StubCheckSACL(cls, username, service):
    services = {
        "calendar" : ["amanda", "betty"],
        "addressbook" : ["amanda", "carlene"],
    }
    if username in services[service]:
        return 0
    return 1

class SALCTests(TestCase):

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
        service = GroupMembershipCacherService(
            None, None, "Testing", 30, 60, reactor=clock,
            updateMethod=self._updateMethod)

        yield service.startService()

        self.assertEquals(self.count, 1)
        clock.advance(29)
        self.assertEquals(self.count, 1)
        clock.advance(1)
        self.assertEquals(self.count, 2)

        service.stopService()



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

        yield cache.setGroupsFor("a", ["b", "c", "d"]) # a is in b, c, d
        members = (yield cache.getGroupsFor("a"))
        self.assertEquals(members, set(["b", "c", "d"]))

        yield cache.setGroupsFor("b", []) # b not in any groups
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
        cache = GroupMembershipCache("ProxyDB", 60)
        # Having a groupMembershipCache assigned to the directory service is the
        # trigger to use such a cache:
        self.directoryService.groupMembershipCache = cache

        updater = GroupMembershipCacheUpdater(
            calendaruserproxy.ProxyDBService, self.directoryService, 30,
            cache=cache, useExternalProxies=False)

        # Exercise getGroups()
        groups = updater.getGroups()
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

        yield updater.updateCache()

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


    @inlineCallbacks
    def test_groupMembershipCacheUpdaterExternalProxies(self):
        """
        Exercise external proxy assignment support (assignments come from the
        directory service itself)
        """
        cache = GroupMembershipCache("ProxyDB", 60)
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
            calendaruserproxy.ProxyDBService, self.directoryService, 30,
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
        cache = GroupMembershipCache("ProxyDB", 60)
        # Having a groupMembershipCache assigned to the directory service is the
        # trigger to use such a cache:
        self.directoryService.groupMembershipCache = cache

        updater = GroupMembershipCacheUpdater(
            calendaruserproxy.ProxyDBService, self.directoryService, 30,
            cache=cache)

        dataRoot = FilePath(config.DataRoot)
        snapshotFile = dataRoot.child("memberships_cache")

        # Snapshot doesn't exist initially
        self.assertFalse(snapshotFile.exists())

        # Try a fast update (as when the server starts up for the very first
        # time), but since the snapshot doesn't exist we fault in from the
        # directory (fast now is False), and snapshot will get created
        fast, numMembers = (yield updater.updateCache(fast=True))
        self.assertEquals(fast, False)
        self.assertEquals(numMembers, 8)
        self.assertTrue(snapshotFile.exists())

        # Try another fast update where the snapshot already exists (as in a
        # server-restart scenario), which will only read from the snapshot
        # as indicated by the return value for "fast"
        fast, numMembers = (yield updater.updateCache(fast=True))
        self.assertEquals(fast, True)
        self.assertEquals(numMembers, 8)

        # Try an update which faults in from the directory (fast=False)
        fast, numMembers = (yield updater.updateCache(fast=False))
        self.assertEquals(fast, False)
        self.assertEquals(numMembers, 8)

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
