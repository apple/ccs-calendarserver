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

from twisted.internet.defer import deferredGenerator
from twisted.internet.defer import waitForDeferred
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

    @deferredGenerator
    def test_groupMembersRegular(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        d = waitForDeferred(self._getRecordByShortName(DirectoryService.recordType_groups, "both_coasts").groupMembers())
        yield d
        members = d.getResult()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set(('Chris Lecroy', 'David Reid', 'Wilfredo Sanchez', 'West Coast', 'East Coast', 'Cyrus Daboo',)))

    @deferredGenerator
    def test_groupMembersRecursive(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        d = waitForDeferred(self._getRecordByShortName(DirectoryService.recordType_groups, "recursive1_coasts").groupMembers())
        yield d
        members = d.getResult()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set(('Wilfredo Sanchez', 'Recursive2 Coasts', 'Cyrus Daboo',)))

    @deferredGenerator
    def test_groupMembersProxySingleUser(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        d = waitForDeferred(self._getRecordByShortName(DirectoryService.recordType_locations, "gemini").getChild("calendar-proxy-write").groupMembers())
        yield d
        members = d.getResult()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set(('Wilfredo Sanchez',)))

    @deferredGenerator
    def test_groupMembersProxySingleGroup(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        d = waitForDeferred(self._getRecordByShortName(DirectoryService.recordType_locations, "mercury").getChild("calendar-proxy-write").groupMembers())
        yield d
        members = d.getResult()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set(('Chris Lecroy', 'David Reid', 'Wilfredo Sanchez', 'West Coast',)))

    @deferredGenerator
    def test_groupMembersProxySingleGroupWithNestedGroups(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        d = waitForDeferred(self._getRecordByShortName(DirectoryService.recordType_locations, "apollo").getChild("calendar-proxy-write").groupMembers())
        yield d
        members = d.getResult()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set(('Chris Lecroy', 'David Reid', 'Wilfredo Sanchez', 'West Coast', 'East Coast', 'Cyrus Daboo', 'Both Coasts',)))

    @deferredGenerator
    def test_groupMembersProxySingleGroupWithNestedRecursiveGroups(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        d = waitForDeferred(self._getRecordByShortName(DirectoryService.recordType_locations, "orion").getChild("calendar-proxy-write").groupMembers())
        yield d
        members = d.getResult()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set(('Wilfredo Sanchez', 'Cyrus Daboo', 'Recursive1 Coasts', 'Recursive2 Coasts',)))

    @deferredGenerator
    def test_groupMembersProxySingleGroupWithNonCalendarGroup(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        d = waitForDeferred(self._getRecordByShortName(DirectoryService.recordType_resources, "non_calendar_proxy").getChild("calendar-proxy-write").groupMembers())
        yield d
        members = d.getResult()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set(('Chris Lecroy', 'Cyrus Daboo', 'Non-calendar group')))

        d = waitForDeferred(self._getRecordByShortName(DirectoryService.recordType_groups, "non_calendar_group").groupMemberships())
        yield d
        memberships = d.getResult()
        memberships = set([p.principalUID() for p in memberships])
        self.assertEquals(memberships, set(('non_calendar_proxy#calendar-proxy-write',)))

    @deferredGenerator
    def test_groupMembersProxyMissingUser(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """

        # Setup the fake entry in the DB
        proxy = self._getRecordByShortName(DirectoryService.recordType_users, "cdaboo")
        proxy_group = proxy.getChild("calendar-proxy-write")
        d = waitForDeferred(proxy_group._index().getMembers("%s#calendar-proxy-write" % (proxy.principalUID(),)))
        yield d
        members = d.getResult()
        members.add("12345")
        d = waitForDeferred(proxy_group._index().setGroupMembers("%s#calendar-proxy-write" % (proxy.principalUID(),), members))
        yield d
        d.getResult()

        # Do the failing lookup
        d = waitForDeferred(self._getRecordByShortName(DirectoryService.recordType_users, "cdaboo").getChild("calendar-proxy-write").groupMembers())
        yield d
        members = d.getResult()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set())

    @deferredGenerator
    def test_groupMembershipsMissingUser(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """

        # Setup the fake entry in the DB
        fake_uid = "12345"
        proxy = self._getRecordByShortName(DirectoryService.recordType_users, "cdaboo")
        proxy_group = proxy.getChild("calendar-proxy-write")
        d = waitForDeferred(proxy_group._index().getMembers("%s#calendar-proxy-write" % (fake_uid,)))
        yield d
        members = d.getResult()
        members.add("%s#calendar-proxy-write" % (proxy.principalUID(),))
        d = waitForDeferred(proxy_group._index().setGroupMembers("%s#calendar-proxy-write" % (fake_uid,), members))
        yield d
        d.getResult()

        # Do the failing lookup
        d = waitForDeferred(self._getRecordByShortName(DirectoryService.recordType_users, "cdaboo").getChild("calendar-proxy-write").groupMemberships())
        yield d
        memberships = d.getResult()
        memberships = set([p.displayName() for p in memberships])
        self.assertEquals(memberships, set())

    def _getRecordByShortName(self, type, name):
        """
        @return: an iterable of tuples
            C{(provisioningResource, recordType, recordResource, record)}, where
            C{provisioningResource} is the root provisioning resource,
            C{recordType} is the record type,
            C{recordResource} is the principal resource and
            C{record} is the directory service record
            for each record in each directory in C{directoryServices}.
        """
        provisioningResource = self.principalRootResources[directoryService.__class__.__name__]
        return provisioningResource.principalForShortName(type, name)


    def test_setGroupMemberSet(self):
        class StubMemberDB(object):
            def __init__(self):
                self.members = None

            def setGroupMembers(self, uid, members):
                self.members = members


        user = self._getRecordByShortName(directoryService.recordType_users,
                                           "cdaboo")

        proxy_group = user.getChild("calendar-proxy-write")

        memberdb = StubMemberDB()

        proxy_group._index = (lambda: memberdb)

        new_members = davxml.GroupMemberSet(
            davxml.HRef.fromString(
                "/XMLDirectoryService/__uids__/8B4288F6-CC82-491D-8EF9-642EF4F3E7D0/"),
            davxml.HRef.fromString(
                "/XMLDirectoryService/__uids__/5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1/"))

        proxy_group.setGroupMemberSet(new_members, None)

        self.assertEquals(
            set([str(p) for p in memberdb.members]),
            set(["5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1",
                 "8B4288F6-CC82-491D-8EF9-642EF4F3E7D0"]))


    def test_setGroupMemberSetNotifiesPrincipalCaches(self):
        class StubCacheNotifier(object):
            changedCount = 0
            def changed(self):
                self.changedCount += 1

        user = self._getRecordByShortName(directoryService.recordType_users,
                                          "cdaboo")

        proxy_group = user.getChild("calendar-proxy-write")

        notifier = StubCacheNotifier()

        oldCacheNotifier = DirectoryPrincipalResource.cacheNotifierFactory

        try:
            DirectoryPrincipalResource.cacheNotifierFactory = (lambda _1, _2: notifier)

            self.assertEquals(notifier.changedCount, 0)

            proxy_group.setGroupMemberSet(
                davxml.GroupMemberSet(
                    davxml.HRef.fromString(
                        "/XMLDirectoryService/__uids__/5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1/")),
                None)

            self.assertEquals(notifier.changedCount, 1)
        finally:
            DirectoryPrincipalResource.cacheNotifierFactory = oldCacheNotifier
