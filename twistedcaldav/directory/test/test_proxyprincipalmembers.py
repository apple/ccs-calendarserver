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

from twisted.internet.defer import DeferredList
from twisted.web2.dav.fileop import rmdir
from twisted.web2.dav import davxml

from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.directory.test.test_xmlfile import xmlFile
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory.principal import DirectoryPrincipalResource

import twistedcaldav.test.util

directoryService = XMLDirectoryService(xmlFile)

class ProxyPrincipals (twistedcaldav.test.util.TestCase):
    """
    Directory service provisioned principals.
    """
    def setUp(self):
        super(ProxyPrincipals, self).setUp()

        # Set up a principals hierarchy for each service we're testing with
        self.principalRootResources = {}
        name = directoryService.__class__.__name__
        url = "/" + name + "/"
        path = os.path.join(self.docroot, url[1:])

        if os.path.exists(path):
            rmdir(path)
        os.mkdir(path)

        provisioningResource = DirectoryPrincipalProvisioningResource(path, url, directoryService)

        self.site.resource.putChild(name, provisioningResource)

        self.principalRootResources[directoryService.__class__.__name__] = provisioningResource

    def _getPrincipalByShortName(self, type, name):
        provisioningResource = self.principalRootResources[directoryService.__class__.__name__]
        return provisioningResource.principalForShortName(type, name)

    def _groupMembersTest(self, recordType, recordName, subPrincipalName, expectedMembers):
        def gotMembers(members):
            memberNames = set([p.displayName() for p in members])
            self.assertEquals(memberNames, set(expectedMembers))

        principal = self._getPrincipalByShortName(recordType, recordName)
        if subPrincipalName is not None:
            principal = principal.getChild(subPrincipalName)

        d = principal.groupMembers()
        d.addCallback(gotMembers)
        return d

    def _groupMembershipsTest(self, recordType, recordName, subPrincipalName, expectedMemberships):
        def gotMemberships(memberships):
            uids = set([p.principalUID() for p in memberships])
            self.assertEquals(uids, set(expectedMemberships))

        principal = self._getPrincipalByShortName(recordType, recordName)
        if subPrincipalName is not None:
            principal = principal.getChild(subPrincipalName)

        d = principal.groupMemberships()
        d.addCallback(gotMemberships)
        return d

    def test_groupMembersRegular(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        return self._groupMembersTest(
            DirectoryService.recordType_groups, "both_coasts", None,
            ("Chris Lecroy", "David Reid", "Wilfredo Sanchez", "West Coast", "East Coast", "Cyrus Daboo",),
        )

    def test_groupMembersRecursive(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        return self._groupMembersTest(
            DirectoryService.recordType_groups, "recursive1_coasts", None,
            ("Wilfredo Sanchez", "Recursive2 Coasts", "Cyrus Daboo",),
        )

    def test_groupMembersProxySingleUser(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        return self._groupMembersTest(
            DirectoryService.recordType_locations, "gemini", "calendar-proxy-write",
            ("Wilfredo Sanchez",),
        )

    def test_groupMembersProxySingleGroup(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        return self._groupMembersTest(
            DirectoryService.recordType_locations, "mercury", "calendar-proxy-write",
            ("Chris Lecroy", "David Reid", "Wilfredo Sanchez", "West Coast",),
        )

    def test_groupMembersProxySingleGroupWithNestedGroups(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        return self._groupMembersTest(
            DirectoryService.recordType_locations, "apollo", "calendar-proxy-write",
            ("Chris Lecroy", "David Reid", "Wilfredo Sanchez", "West Coast", "East Coast", "Cyrus Daboo", "Both Coasts",),
        )

    def test_groupMembersProxySingleGroupWithNestedRecursiveGroups(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        return self._groupMembersTest(
            DirectoryService.recordType_locations, "orion", "calendar-proxy-write",
            ("Wilfredo Sanchez", "Cyrus Daboo", "Recursive1 Coasts", "Recursive2 Coasts",),
        )

    def test_groupMembersProxySingleGroupWithNonCalendarGroup(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        ds = []

        ds.append(self._groupMembersTest(
            DirectoryService.recordType_resources, "non_calendar_proxy", "calendar-proxy-write",
            ("Chris Lecroy", "Cyrus Daboo", "Non-calendar group"),
        ))

        ds.append(self._groupMembershipsTest(
            DirectoryService.recordType_groups, "non_calendar_group", None,
            ("non_calendar_proxy#calendar-proxy-write",),
        ))

        return DeferredList(ds)

    def test_groupMembersProxyMissingUser(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        proxy = self._getPrincipalByShortName(DirectoryService.recordType_users, "cdaboo")
        proxyGroup = proxy.getChild("calendar-proxy-write")

        def gotMembers(members):
            members.add("12345")
            return proxyGroup._index().setGroupMembers("%s#calendar-proxy-write" % (proxy.principalUID(),), members)

        def check(_):
            return self._groupMembersTest(
                DirectoryService.recordType_users, "cdaboo", "calendar-proxy-write",
                (),
            )

        # Setup the fake entry in the DB
        d = proxyGroup._index().getMembers("%s#calendar-proxy-write" % (proxy.principalUID(),))
        d.addCallback(gotMembers)
        d.addCallback(check)
        return d

    def test_groupMembershipsMissingUser(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        # Setup the fake entry in the DB
        fake_uid = "12345"
        proxy = self._getPrincipalByShortName(DirectoryService.recordType_users, "cdaboo")
        proxyGroup = proxy.getChild("calendar-proxy-write")

        def gotMembers(members):
            members.add("%s#calendar-proxy-write" % (proxy.principalUID(),))
            return proxyGroup._index().setGroupMembers("%s#calendar-proxy-write" % (fake_uid,), members)

        def check(_):
            return self._groupMembershipsTest(
                DirectoryService.recordType_users, "cdaboo", "calendar-proxy-write",
                (),
            )

        d = proxyGroup._index().getMembers("%s#calendar-proxy-write" % (fake_uid,))
        d.addCallback(gotMembers)
        d.addCallback(check)
        return d

    def test_setGroupMemberSet(self):
        class StubMemberDB(object):
            def __init__(self):
                self.members = None

            def setGroupMembers(self, uid, members):
                self.members = members


        user = self._getPrincipalByShortName(directoryService.recordType_users,
                                           "cdaboo")

        proxyGroup = user.getChild("calendar-proxy-write")

        memberdb = StubMemberDB()

        proxyGroup._index = (lambda: memberdb)

        new_members = davxml.GroupMemberSet(
            davxml.HRef.fromString(
                "/XMLDirectoryService/__uids__/8B4288F6-CC82-491D-8EF9-642EF4F3E7D0/"),
            davxml.HRef.fromString(
                "/XMLDirectoryService/__uids__/5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1/"))

        proxyGroup.setGroupMemberSet(new_members, None)

        self.assertEquals(
            set([str(p) for p in memberdb.members]),
            set(["5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1",
                 "8B4288F6-CC82-491D-8EF9-642EF4F3E7D0"]))


    def test_setGroupMemberSetNotifiesPrincipalCaches(self):
        class StubCacheNotifier(object):
            changedCount = 0
            def changed(self):
                self.changedCount += 1

        user = self._getPrincipalByShortName(directoryService.recordType_users,
                                          "cdaboo")

        proxyGroup = user.getChild("calendar-proxy-write")

        notifier = StubCacheNotifier()

        oldCacheNotifier = DirectoryPrincipalResource.cacheNotifierFactory

        try:
            DirectoryPrincipalResource.cacheNotifierFactory = (lambda _1, _2: notifier)

            self.assertEquals(notifier.changedCount, 0)

            proxyGroup.setGroupMemberSet(
                davxml.GroupMemberSet(
                    davxml.HRef.fromString(
                        "/XMLDirectoryService/__uids__/5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1/")),
                None)

            self.assertEquals(notifier.changedCount, 1)
        finally:
            DirectoryPrincipalResource.cacheNotifierFactory = oldCacheNotifier
