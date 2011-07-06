##
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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

from twisted.internet.defer import DeferredList, inlineCallbacks, returnValue,\
    succeed
from twext.web2.dav import davxml
from twext.web2.http import HTTPError

from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.test.util import xmlFile, augmentsFile, proxiesFile
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource,\
    DirectoryPrincipalResource
from twistedcaldav.directory.xmlfile import XMLDirectoryService

import twistedcaldav.test.util
from twistedcaldav.config import config
from twistedcaldav.directory import augment, calendaruserproxy
from twistedcaldav.directory.calendaruserproxyloader import XMLCalendarUserProxyLoader


class ProxyPrincipals (twistedcaldav.test.util.TestCase):
    """
    Directory service provisioned principals.
    """

    @inlineCallbacks
    def setUp(self):
        super(ProxyPrincipals, self).setUp()

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

    def _groupMembersTest(self, recordType, recordName, subPrincipalName, expectedMembers):
        def gotMembers(members):
            memberNames = set([p.displayName() for p in members])
            self.assertEquals(memberNames, set(expectedMembers))

        principal = self._getPrincipalByShortName(recordType, recordName)
        if subPrincipalName is not None:
            principal = principal.getChild(subPrincipalName)

        d = principal.expandedGroupMembers()
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
    
    @inlineCallbacks
    def _addProxy(self, principal, subPrincipalName, proxyPrincipal):

        if isinstance(principal, tuple):
            principal = self._getPrincipalByShortName(principal[0], principal[1])
        principal = principal.getChild(subPrincipalName)
        members = (yield principal.groupMembers())

        if isinstance(proxyPrincipal, tuple):
            proxyPrincipal = self._getPrincipalByShortName(proxyPrincipal[0], proxyPrincipal[1])
        members.add(proxyPrincipal)
        
        yield principal.setGroupMemberSetPrincipals(members)

    @inlineCallbacks
    def _removeProxy(self, recordType, recordName, subPrincipalName, proxyRecordType, proxyRecordName):

        principal = self._getPrincipalByShortName(recordType, recordName)
        principal = principal.getChild(subPrincipalName)
        members = (yield principal.groupMembers())

        proxyPrincipal = self._getPrincipalByShortName(proxyRecordType, proxyRecordName)
        for p in members:
            if p.principalUID() == proxyPrincipal.principalUID():
                members.remove(p)
                break
        
        yield principal.setGroupMemberSetPrincipals(members)

    @inlineCallbacks
    def _clearProxy(self, principal, subPrincipalName):

        if isinstance(principal, tuple):
            principal = self._getPrincipalByShortName(principal[0], principal[1])
        principal = principal.getChild(subPrincipalName)
        yield principal.setGroupMemberSetPrincipals(set())

    @inlineCallbacks
    def _proxyForTest(self, recordType, recordName, expectedProxies, read_write):
        principal = self._getPrincipalByShortName(recordType, recordName)
        proxies = (yield principal.proxyFor(read_write))
        proxies = sorted([principal.displayName() for principal in proxies])
        self.assertEquals(proxies, sorted(expectedProxies))

    @inlineCallbacks
    def test_multipleProxyAssignmentsAtOnce(self):
        yield self._proxyForTest(
            DirectoryService.recordType_users, "userb",
            ('a',),
            True
        )
        yield self._proxyForTest(
            DirectoryService.recordType_users, "userc",
            ('a',),
            True
        )

    def test_groupMembersRegular(self):
        """
        DirectoryPrincipalResource.expandedGroupMembers()
        """
        return self._groupMembersTest(
            DirectoryService.recordType_groups, "both_coasts", None,
            ("Chris Lecroy", "David Reid", "Wilfredo Sanchez", "West Coast", "East Coast", "Cyrus Daboo",),
        )

    def test_groupMembersRecursive(self):
        """
        DirectoryPrincipalResource.expandedGroupMembers()
        """
        return self._groupMembersTest(
            DirectoryService.recordType_groups, "recursive1_coasts", None,
            ("Wilfredo Sanchez", "Recursive2 Coasts", "Cyrus Daboo",),
        )

    def test_groupMembersProxySingleUser(self):
        """
        DirectoryPrincipalResource.expandedGroupMembers()
        """
        return self._groupMembersTest(
            DirectoryService.recordType_locations, "gemini", "calendar-proxy-write",
            ("Wilfredo Sanchez",),
        )

    def test_groupMembersProxySingleGroup(self):
        """
        DirectoryPrincipalResource.expandedGroupMembers()
        """
        return self._groupMembersTest(
            DirectoryService.recordType_locations, "mercury", "calendar-proxy-write",
            ("Chris Lecroy", "David Reid", "Wilfredo Sanchez", "West Coast",),
        )

    def test_groupMembersProxySingleGroupWithNestedGroups(self):
        """
        DirectoryPrincipalResource.expandedGroupMembers()
        """
        return self._groupMembersTest(
            DirectoryService.recordType_locations, "apollo", "calendar-proxy-write",
            ("Chris Lecroy", "David Reid", "Wilfredo Sanchez", "West Coast", "East Coast", "Cyrus Daboo", "Both Coasts",),
        )

    def test_groupMembersProxySingleGroupWithNestedRecursiveGroups(self):
        """
        DirectoryPrincipalResource.expandedGroupMembers()
        """
        return self._groupMembersTest(
            DirectoryService.recordType_locations, "orion", "calendar-proxy-write",
            ("Wilfredo Sanchez", "Cyrus Daboo", "Recursive1 Coasts", "Recursive2 Coasts",),
        )

    def test_groupMembersProxySingleGroupWithNonCalendarGroup(self):
        """
        DirectoryPrincipalResource.expandedGroupMembers()
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
        DirectoryPrincipalResource.expandedGroupMembers()
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
        DirectoryPrincipalResource.expandedGroupMembers()
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

    @inlineCallbacks
    def test_setGroupMemberSet(self):
        class StubMemberDB(object):
            def __init__(self):
                self.members = set()

            def setGroupMembers(self, uid, members):
                self.members = members
                return succeed(None)

            def getMembers(self, uid):
                return succeed(self.members)


        user = self._getPrincipalByShortName(self.directoryService.recordType_users,
                                           "cdaboo")

        proxyGroup = user.getChild("calendar-proxy-write")

        memberdb = StubMemberDB()

        proxyGroup._index = (lambda: memberdb)

        new_members = davxml.GroupMemberSet(
            davxml.HRef.fromString(
                "/XMLDirectoryService/__uids__/8B4288F6-CC82-491D-8EF9-642EF4F3E7D0/"),
            davxml.HRef.fromString(
                "/XMLDirectoryService/__uids__/5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1/"))

        yield proxyGroup.setGroupMemberSet(new_members, None)

        self.assertEquals(
            set([str(p) for p in memberdb.members]),
            set(["5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1",
                 "8B4288F6-CC82-491D-8EF9-642EF4F3E7D0"]))

    @inlineCallbacks
    def test_setGroupMemberSetNotifiesPrincipalCaches(self):
        class StubCacheNotifier(object):
            changedCount = 0
            def changed(self):
                self.changedCount += 1
                return succeed(None)

        user = self._getPrincipalByShortName(self.directoryService.recordType_users, "cdaboo")

        proxyGroup = user.getChild("calendar-proxy-write")

        notifier = StubCacheNotifier()

        oldCacheNotifier = DirectoryPrincipalResource.cacheNotifierFactory

        try:
            DirectoryPrincipalResource.cacheNotifierFactory = (lambda _1, _2, **kwargs: notifier)

            self.assertEquals(notifier.changedCount, 0)

            yield proxyGroup.setGroupMemberSet(
                davxml.GroupMemberSet(
                    davxml.HRef.fromString(
                        "/XMLDirectoryService/__uids__/5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1/")),
                None)

            self.assertEquals(notifier.changedCount, 1)
        finally:
            DirectoryPrincipalResource.cacheNotifierFactory = oldCacheNotifier

    def test_proxyFor(self):

        return self._proxyForTest(
            DirectoryService.recordType_users, "wsanchez", 
            ("Mercury Seven", "Gemini Twelve", "Apollo Eleven", "Orion", ),
            True
        )

    @inlineCallbacks
    def test_proxyForDuplicates(self):

        yield self._addProxy(
            (DirectoryService.recordType_locations, "gemini",),
            "calendar-proxy-write",
            (DirectoryService.recordType_groups, "grunts",),
        )

        yield self._proxyForTest(
            DirectoryService.recordType_users, "wsanchez", 
            ("Mercury Seven", "Gemini Twelve", "Apollo Eleven", "Orion", ),
            True
        )

    def test_readOnlyProxyFor(self):

        return self._proxyForTest(
            DirectoryService.recordType_users, "wsanchez", 
            ("Non-calendar proxy", ),
            False
        )

    @inlineCallbacks
    def test_UserProxy(self):
        
        for proxyType in ("calendar-proxy-read", "calendar-proxy-write"):

            yield self._addProxy(
                (DirectoryService.recordType_users, "wsanchez",),
                proxyType,
                (DirectoryService.recordType_users, "cdaboo",),
            )
    
            yield self._groupMembersTest(
                DirectoryService.recordType_users, "wsanchez",
                proxyType,
                ("Cyrus Daboo",),
            )
            
            yield self._addProxy(
                (DirectoryService.recordType_users, "wsanchez",),
                proxyType,
                (DirectoryService.recordType_users, "lecroy",),
            )
    
            yield self._groupMembersTest(
                DirectoryService.recordType_users, "wsanchez",
                proxyType,
                ("Cyrus Daboo", "Chris Lecroy",),
            )
    
            yield self._removeProxy(
                DirectoryService.recordType_users, "wsanchez",
                proxyType,
                DirectoryService.recordType_users, "cdaboo",
            )
    
            yield self._groupMembersTest(
                DirectoryService.recordType_users, "wsanchez",
                proxyType,
                ("Chris Lecroy",),
            )

    @inlineCallbacks
    def test_InvalidUserProxy(self):


        # Set up the in-memory (non-null) memcacher:
        config.ProcessType = "Single"
        calendaruserproxy.ProxyDBService._memcacher._memcacheProtocol = None
        principal = self._getPrincipalByShortName(
            DirectoryService.recordType_users, "wsanchez")
        db = principal._calendar_user_proxy_index()

        # Set the clock to the epoch:
        theTime = 0
        db._memcacher.theTime = theTime


        for doMembershipFirst in (True, False):
            for proxyType in ("calendar-proxy-read", "calendar-proxy-write"):

                principal = self._getPrincipalByShortName(DirectoryService.recordType_users, "wsanchez")
                proxyGroup = principal.getChild(proxyType)

                testPrincipal = self._getPrincipalByShortName(DirectoryService.recordType_users, "cdaboo")

                fakePrincipal = self._getPrincipalByShortName(DirectoryService.recordType_users, "dreid")
                fakeProxyGroup = fakePrincipal.getChild(proxyType)

                yield self._addProxy(
                    principal,
                    proxyType,
                    testPrincipal,
                )

                members = yield proxyGroup._index().getMembers(proxyGroup.uid)
                self.assertEquals(len(members), 1)

                yield self._addProxy(
                    fakePrincipal,
                    proxyType,
                    testPrincipal,
                )
                members = yield fakeProxyGroup._index().getMembers(fakeProxyGroup.uid)
                self.assertEquals(len(members), 1)

                uids = [p.principalUID() for p in (yield testPrincipal.groupMemberships())]
                self.assertTrue("5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1#%s" % (proxyType,) in uids)

                memberships = yield testPrincipal._calendar_user_proxy_index().getMemberships(testPrincipal.principalUID())
                self.assertEquals(len(memberships), 2)

                yield self._addProxy(
                    principal,
                    proxyType,
                    fakePrincipal,
                )
                members = yield proxyGroup._index().getMembers(proxyGroup.uid)
                self.assertEquals(len(members), 2)

                # Remove the dreid user from the directory service

                delRec = self.directoryService.recordWithShortName(
                    DirectoryService.recordType_users, "dreid")
                self.directoryService._removeFromIndex(delRec)

                cacheTimeout = config.DirectoryService.params.get("cacheTimeout", 30) * 60 * 2

                @inlineCallbacks
                def _membershipTest():

                    uids = [p.principalUID() for p in (yield testPrincipal.groupMemberships())]
                    self.assertTrue("5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1#%s" % (proxyType,) not in uids)

                    memberships = yield testPrincipal._calendar_user_proxy_index().getMemberships(testPrincipal.principalUID())
                    self.assertEquals(len(memberships), 1)

                @inlineCallbacks
                def _membersTest(theTime):
                    yield self._groupMembersTest(
                        DirectoryService.recordType_users, "wsanchez",
                        proxyType,
                        ("Cyrus Daboo",),
                    )

                    # Trigger the proxy DB clean up, which won't actually
                    # remove anything because we haven't exceeded the timeout
                    yield proxyGroup.groupMembers()

                    # Advance 10 seconds
                    theTime += 10
                    db._memcacher.theTime = theTime

                    # When we first examine the members, we have not exceeded
                    # the clean-up timeout, so we'll still have 2:
                    members = yield proxyGroup._index().getMembers(proxyGroup.uid)
                    self.assertEquals(len(members), 2)

                    # Restore removed user
                    self.directoryService._forceReload()

                    # Trigger the proxy DB clean up, which will actually
                    # remove the deletion timer because the principal has been
                    # restored
                    yield proxyGroup.groupMembers()

                    # Verify the deletion timer has been removed
                    result = yield db._memcacher.checkDeletionTimer("5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1")
                    self.assertEquals(result, None)

                    # Remove the dreid user from the directory service
                    delRec = self.directoryService.recordWithShortName(
                        DirectoryService.recordType_users, "dreid")
                    self.directoryService._removeFromIndex(delRec)

                    # Trigger the proxy DB clean up, which won't actually
                    # remove anything because we haven't exceeded the timeout
                    yield proxyGroup.groupMembers()

                    # Advance beyond the timeout
                    theTime += cacheTimeout
                    db._memcacher.theTime = theTime

                    # Trigger the proxy DB clean up
                    yield proxyGroup.groupMembers()

                    # The missing principal has now been cleaned out of the
                    # proxy DB
                    members = yield proxyGroup._index().getMembers(proxyGroup.uid)
                    self.assertEquals(len(members), 1)
                    returnValue(theTime)


                if doMembershipFirst:
                    yield _membershipTest()
                    theTime = yield _membersTest(theTime)
                else:
                    theTime = yield _membersTest(theTime)
                    yield _membershipTest()

                # Restore removed user
                self.directoryService._forceReload()

                yield self._clearProxy(principal, proxyType)
                yield self._clearProxy(fakePrincipal, proxyType)


    @inlineCallbacks
    def test_NonAsciiProxy(self):
        """
        Ensure that principalURLs with non-ascii don't cause problems
        within CalendarUserProxyPrincipalResource
        """

        recordType = DirectoryService.recordType_users
        proxyType = "calendar-proxy-read"

        record = self.directoryService.recordWithGUID("320B73A1-46E2-4180-9563-782DFDBE1F63")
        provisioningResource = self.principalRootResources[self.directoryService.__class__.__name__]
        principal =  provisioningResource.principalForRecord(record)
        proxyPrincipal = provisioningResource.principalForShortName(recordType,
            "wsanchez")

        yield self._addProxy(principal, proxyType, proxyPrincipal)
        memberships = yield proxyPrincipal._calendar_user_proxy_index().getMemberships(proxyPrincipal.principalUID())
        for uid in memberships:
            provisioningResource.principalForUID(uid)


    @inlineCallbacks
    def test_proxyMemberCache(self):
        """
        Ensure we get back what we put in
        """
        cache = calendaruserproxy.ProxyMemberCache("ProxyDB")

        yield cache.setMembers("a", ["b", "c", "d"]) # has members
        members = (yield cache.getMembers("a"))
        self.assertEquals(members, set(["b", "c", "d"]))

        yield cache.setMembers("b", []) # has no members
        members = (yield cache.getMembers("b"))
        self.assertEquals(members, set())

        members = (yield cache.getMembers("c")) # wasn't specified at all
        self.assertEquals(members, None)


        yield cache.setProxyFor("a", "read", ["b", "c", "d"]) # has members
        proxyFor = (yield cache.getProxyFor("a", "read"))
        self.assertEquals(proxyFor, set(["b", "c", "d"]))

        yield cache.setProxyFor("b", "read", []) # has no members
        proxyFor = (yield cache.getProxyFor("b", "read"))
        self.assertEquals(proxyFor, set())

        proxyFor = (yield cache.getProxyFor("c", "read"))
        # wasn't specified at all
        self.assertEquals(proxyFor, None)


    @inlineCallbacks
    def test_expandedGroupMembersFromCache(self):
        """
        Put proxy data directly into cache, then make sure
        CalendarUserProxyPrincipalResour.expandedGroupMembers( ) goes to the
        cache for that info.
        """

        cdaboo = "5A985493-EE2C-4665-94CF-4DFEA3A89500"
        lecroy = "8B4288F6-CC82-491D-8EF9-642EF4F3E7D0"

        cache = calendaruserproxy.ProxyMemberCache("ProxyDB")

        delegator = self._getPrincipalByShortName(DirectoryService.recordType_users, "wsanchez")

        # Having a proxyCache assigned to the directory service is the
        # trigger to use such a cache:
        self.directoryService.proxyCache = cache

        proxyGroup = delegator.getChild("calendar-proxy-write")
        yield cache.setMembers(proxyGroup.uid, [cdaboo, lecroy])
        yield cache.createMarker()

        members = (yield proxyGroup.expandedGroupMembers())
        self.assertEquals(
            set([p.record.guid for p in members]),
            set([cdaboo, lecroy])
        )


    @inlineCallbacks
    def test_proxyMemberCacheUpdater(self):
        """
        Let the ProxyMemberCacheUpdater populate the cache, then make
        sure CalendarUserProxyPrincipalResource.expandedGroupMembers( ) goes
        to the cache for that info.
        """
        cache = calendaruserproxy.ProxyMemberCache("ProxyDB")
        updater = calendaruserproxy.ProxyMemberCacheUpdater(
            calendaruserproxy.ProxyDBService, self.directoryService,
            cache=cache)
        yield updater.updateCache()

        delegator = self._getPrincipalByShortName(DirectoryService.recordType_locations, "apollo")

        # Having a proxyCache assigned to the directory service is the
        # trigger to use such a cache:
        self.directoryService.proxyCache = cache

        proxyGroup = delegator.getChild("calendar-proxy-write")

        members = (yield proxyGroup.expandedGroupMembers())
        self.assertEquals(
            set([p.record.guid for p in members]),
            set(['8B4288F6-CC82-491D-8EF9-642EF4F3E7D0',
                 '6423F94A-6B76-4A3A-815B-D52CFD77935D',
                 '5A985493-EE2C-4665-94CF-4DFEA3A89500',
                 '5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1',
                 'both_coasts',
                 'left_coast',
                 'right_coast'])
        )

        delegates = (

            # record name
            # read-write delegators
            # read-only delegators
            # groups delegate is in (which is now just the "sub principals")

            ("wsanchez",
             set(["mercury", "apollo", "orion", "gemini"]),
             set(["non_calendar_proxy"]),
             set(['apollo#calendar-proxy-write',
                  'gemini#calendar-proxy-write',
                  'mercury#calendar-proxy-write',
                  'non_calendar_proxy#calendar-proxy-read',
                  'orion#calendar-proxy-write']),
            ),
            ("cdaboo",
             set(["apollo", "orion", "non_calendar_proxy"]),
             set(["non_calendar_proxy"]),
             set(['apollo#calendar-proxy-write',
                  'non_calendar_proxy#calendar-proxy-read',
                  'non_calendar_proxy#calendar-proxy-write',
                  'orion#calendar-proxy-write']),
            ),
            ("lecroy",
             set(["apollo", "mercury", "non_calendar_proxy"]),
             set(),
             set(['apollo#calendar-proxy-write',
                  'mercury#calendar-proxy-write',
                  'non_calendar_proxy#calendar-proxy-write']),
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
            self.assertEquals(
                set([p.uid for p in groupsIn]),
                groups,
            )

        #
        # Remove proxy assignments and see that the appropriate memcached
        # keys are updated/deleted
        #
        usera = self._getPrincipalByShortName(DirectoryService.recordType_users,
                                              "usera")
        userb = self._getPrincipalByShortName(DirectoryService.recordType_users,
                                              "userb")
        userc = self._getPrincipalByShortName(DirectoryService.recordType_users,
                                              "userc")
        useraProxyGroup = usera.getChild("calendar-proxy-write")

        # First, make sure there are two in the usera write proxy group
        members = (yield cache.getMembers(useraProxyGroup.uid))
        self.assertEquals(members, set([userb.record.guid, userc.record.guid]))
        members = (yield useraProxyGroup.expandedGroupMembers())
        self.assertEquals(
            set([p.record.shortNames[0] for p in members]),
            set(["userb", "userc"])
        )
        # ...and that userc is a write proxy for usera, talking directly to
        # the cache, and by going through principal.proxyFor( )
        proxyFor = (yield cache.getProxyFor(userc.record.guid, "write"))
        self.assertEquals(proxyFor, set([usera.record.guid]))
        proxyFor = (yield userc.proxyFor(True))
        self.assertEquals(set([p.record.shortNames[0] for p in proxyFor]),
                          set(["usera"]))

        # Remove userb as a proxy
        yield self._removeProxy(
            DirectoryService.recordType_users, "usera",
            "calendar-proxy-write",
            DirectoryService.recordType_users, "userb",
        )
        yield updater.updateCache()

        # Next, there should only be one in the group
        members = (yield cache.getMembers(useraProxyGroup.uid))
        self.assertEquals(
            members,
            set([userc.record.guid])
        )
        members = (yield useraProxyGroup.expandedGroupMembers())
        self.assertEquals(
            set([p.record.shortNames[0] for p in members]),
            set(["userc"])
        )
        yield self._removeProxy(
            DirectoryService.recordType_users, "usera",
            "calendar-proxy-write",
            DirectoryService.recordType_users, "userc",
        )
        yield updater.updateCache()

        # Finally the group is empty and the key should be deleted
        members = (yield cache.getMembers(useraProxyGroup.uid))
        self.assertEquals(members, None)
        members = (yield useraProxyGroup.expandedGroupMembers())
        self.assertEquals(members, set())

        # ...and userc is not a write proxy for usera
        proxyFor = (yield cache.getProxyFor(userc.record.guid, "write"))
        self.assertEquals(proxyFor, None)
        proxyFor = (yield userc.proxyFor(True))
        self.assertEquals(proxyFor, set())


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
    def test_proxyCacheMarker(self):
        """
        If the proxy member cache is not populated (as noted by the existence
        of a special memcached key), a 503 should be raised
        """
        cache = calendaruserproxy.ProxyMemberCache("ProxyDB")
        # Having a proxyCache assigned to the directory service is the
        # trigger to use such a cache:
        self.directoryService.proxyCache = cache

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

        usercProxyGroup = userc.getChild("calendar-proxy-write")
        try:
            yield usercProxyGroup.expandedGroupMembers()
        except HTTPError:
            pass
        else:
            self.fail("HTTPError was unexpectedly not raised")
