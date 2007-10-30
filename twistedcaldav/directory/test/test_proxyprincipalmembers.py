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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

import os

from twisted.web2.dav.fileop import rmdir

from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.directory.test.test_xmlfile import xmlFile
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource

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

    def test_groupMembersRegular(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        members = self._getRecordByShortName(DirectoryService.recordType_groups, "both_coasts").groupMembers()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set(('Chris Lecroy', 'David Reid', 'Wilfredo Sanchez', 'West Coast', 'East Coast', 'Cyrus Daboo',)))

    def test_groupMembersRecursive(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        members = self._getRecordByShortName(DirectoryService.recordType_groups, "recursive1_coasts").groupMembers()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set(('Wilfredo Sanchez', 'Recursive2 Coasts', 'Cyrus Daboo',)))

    def test_groupMembersProxySingleUser(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        members = self._getRecordByShortName(DirectoryService.recordType_locations, "gemini").getChild("calendar-proxy-write").groupMembers()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set(('Wilfredo Sanchez',)))

    def test_groupMembersProxySingleGroup(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        members = self._getRecordByShortName(DirectoryService.recordType_locations, "mercury").getChild("calendar-proxy-write").groupMembers()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set(('Chris Lecroy', 'David Reid', 'Wilfredo Sanchez', 'West Coast',)))

    def test_groupMembersProxySingleGroupWithNestedGroups(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        members = self._getRecordByShortName(DirectoryService.recordType_locations, "apollo").getChild("calendar-proxy-write").groupMembers()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set(('Chris Lecroy', 'David Reid', 'Wilfredo Sanchez', 'West Coast', 'East Coast', 'Cyrus Daboo', 'Both Coasts',)))

    def test_groupMembersProxySingleGroupWithNestedRecursiveGroups(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        members = self._getRecordByShortName(DirectoryService.recordType_locations, "orion").getChild("calendar-proxy-write").groupMembers()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set(('Wilfredo Sanchez', 'Cyrus Daboo', 'Recursive1 Coasts', 'Recursive2 Coasts',)))

    def test_groupMembersProxySingleGroupWithNonCalendarGroup(self):
        """
        DirectoryPrincipalResource.groupMembers()
        """
        members = self._getRecordByShortName(DirectoryService.recordType_resources, "non_calendar_proxy").getChild("calendar-proxy-write").groupMembers()
        members = set([p.displayName() for p in members])
        self.assertEquals(members, set(('Chris Lecroy', 'Cyrus Daboo', 'Non-calendar group')))

        memberships = self._getRecordByShortName(DirectoryService.recordType_groups, "non_calendar_group").groupMemberships()
        memberships = set([p.principalUID() for p in memberships])
        self.assertEquals(memberships, set(('non_calendar_proxy#calendar-proxy-write',)))

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
