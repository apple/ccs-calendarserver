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
from twext.web2.http import HTTPError

from twistedcaldav.test.util import TestCase
from twistedcaldav.test.util import xmlFile, augmentsFile, proxiesFile
from twistedcaldav.config import config
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord, GroupMembershipCacherService, GroupMembershipCache, GroupMembershipCacheUpdater
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.directory.calendaruserproxyloader import XMLCalendarUserProxyLoader
from twistedcaldav.directory import augment, calendaruserproxy
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
   

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



    @inlineCallbacks
    def test_groupMembershipCacheMarker(self):
        """
        If the group member cache is not populated (as noted by the existence
        of a special memcached key), a 503 should be raised
        """
        cache = GroupMembershipCache("ProxyDB")
        # Having a groupMembershipCache assigned to the directory service is the
        # trigger to use such a cache:
        self.directoryService.groupMembershipCache = cache

        userc = self._getPrincipalByShortName(DirectoryService.recordType_users, "userc")

        try:
            yield userc.proxyFor(True)
        except HTTPError:
            pass
        else:
            self.fail("HTTPError was unexpectedly not raised")

        try:
            yield userc.groupMemberships(True)
        except HTTPError:
            pass
        else:
            self.fail("HTTPError was unexpectedly not raised")


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
            cache=cache)
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
