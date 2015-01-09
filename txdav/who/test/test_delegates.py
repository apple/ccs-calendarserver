##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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

"""
Delegates implementation tests
"""

from txdav.common.datastore.sql import CommonStoreTransaction
from txdav.who.delegates import Delegates, RecordType as DelegateRecordType
from txdav.who.groups import GroupCacher
from twext.who.idirectory import RecordType
from twisted.internet.defer import inlineCallbacks
from twistedcaldav.test.util import StoreTestCase


class DelegationTest(StoreTestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(DelegationTest, self).setUp()
        self.store = self.storeUnderTest()
        self.groupCacher = GroupCacher(self.directory)

        yield Delegates._memcacher.flushAll()


    @inlineCallbacks
    def test_recordCreation(self):
        """
        Verify the record we get back from recordWithShortName has a shortName
        that matches the one we looked up.
        """
        record = yield self.directory.recordWithShortName(
            DelegateRecordType.readDelegateGroup,
            "foo"
        )
        self.assertEquals(record.shortNames[0], "foo")


    @inlineCallbacks
    def test_directDelegation(self):
        txn = self.store.newTransaction(label="test_directDelegation")

        delegator = yield self.directory.recordWithUID(u"__wsanchez1__")
        delegate1 = yield self.directory.recordWithUID(u"__sagen1__")
        delegate2 = yield self.directory.recordWithUID(u"__cdaboo1__")

        # Add 1 delegate
        yield Delegates.addDelegate(txn, delegator, delegate1, True)
        delegates = (yield Delegates.delegatesOf(txn, delegator, True))
        self.assertEquals([u"__sagen1__"], [d.uid for d in delegates])
        delegators = (yield Delegates.delegatedTo(txn, delegate1, True))
        self.assertEquals([u"__wsanchez1__"], [d.uid for d in delegators])

        yield txn.commit()  # So delegateService will see the changes
        txn = self.store.newTransaction(label="test_directDelegation")

        # The "proxy-write" pseudoGroup will have one member
        pseudoGroup = yield self.directory.recordWithShortName(
            DelegateRecordType.writeDelegateGroup,
            u"__wsanchez1__"
        )
        self.assertEquals(pseudoGroup.uid, u"__wsanchez1__#calendar-proxy-write")
        self.assertEquals(
            [r.uid for r in (yield pseudoGroup.members())],
            [u"__sagen1__"]
        )
        # The "proxy-read" pseudoGroup will have no members
        pseudoGroup = yield self.directory.recordWithShortName(
            DelegateRecordType.readDelegateGroup,
            u"__wsanchez1__"
        )
        self.assertEquals(pseudoGroup.uid, u"__wsanchez1__#calendar-proxy-read")
        self.assertEquals(
            [r.uid for r in (yield pseudoGroup.members())],
            []
        )
        # The "proxy-write-for" pseudoGroup will have one member
        pseudoGroup = yield self.directory.recordWithShortName(
            DelegateRecordType.writeDelegatorGroup,
            u"__sagen1__"
        )
        self.assertEquals(pseudoGroup.uid, u"__sagen1__#calendar-proxy-write-for")
        self.assertEquals(
            [r.uid for r in (yield pseudoGroup.members())],
            [u"__wsanchez1__"]
        )
        # The "proxy-read-for" pseudoGroup will have no members
        pseudoGroup = yield self.directory.recordWithShortName(
            DelegateRecordType.readDelegatorGroup,
            u"__sagen1__"
        )
        self.assertEquals(pseudoGroup.uid, u"__sagen1__#calendar-proxy-read-for")
        self.assertEquals(
            [r.uid for r in (yield pseudoGroup.members())],
            []
        )

        # Add another delegate
        yield Delegates.addDelegate(txn, delegator, delegate2, True)
        delegates = (yield Delegates.delegatesOf(txn, delegator, True))
        self.assertEquals(
            set([u"__sagen1__", u"__cdaboo1__"]),
            set([d.uid for d in delegates])
        )
        delegators = (yield Delegates.delegatedTo(txn, delegate2, True))
        self.assertEquals([u"__wsanchez1__"], [d.uid for d in delegators])

        # Remove 1 delegate
        yield Delegates.removeDelegate(txn, delegator, delegate1, True)
        delegates = (yield Delegates.delegatesOf(txn, delegator, True))
        self.assertEquals([u"__cdaboo1__"], [d.uid for d in delegates])
        delegators = (yield Delegates.delegatedTo(txn, delegate1, True))
        self.assertEquals(0, len(delegators))

        # Remove the other delegate
        yield Delegates.removeDelegate(txn, delegator, delegate2, True)
        delegates = (yield Delegates.delegatesOf(txn, delegator, True))
        self.assertEquals(0, len(delegates))
        delegators = (yield Delegates.delegatedTo(txn, delegate2, True))
        self.assertEquals(0, len(delegators))

        yield txn.commit()  # So delegateService will see the changes

        # Now set delegate assignments by using pseudoGroup.setMembers()
        pseudoGroup = yield self.directory.recordWithShortName(
            DelegateRecordType.writeDelegateGroup,
            u"__wsanchez1__"
        )
        yield pseudoGroup.setMembers([delegate1, delegate2])

        # Verify the assignments were made
        txn = self.store.newTransaction(label="test_directDelegation")
        delegates = (yield Delegates.delegatesOf(txn, delegator, True))
        self.assertEquals(
            set([u"__sagen1__", u"__cdaboo1__"]),
            set([d.uid for d in delegates])
        )
        yield txn.commit()

        # Set a different group of assignments:
        yield pseudoGroup.setMembers([delegate2])

        # Verify the assignments were made
        txn = self.store.newTransaction(label="test_directDelegation")
        delegates = (yield Delegates.delegatesOf(txn, delegator, True))
        self.assertEquals(
            set([u"__cdaboo1__"]),
            set([d.uid for d in delegates])
        )
        yield txn.commit()


    @inlineCallbacks
    def test_indirectDelegation(self):
        txn = self.store.newTransaction(label="test_indirectDelegation")

        delegator = yield self.directory.recordWithUID(u"__wsanchez1__")
        delegate1 = yield self.directory.recordWithUID(u"__sagen1__")
        group1 = yield self.directory.recordWithUID(u"__top_group_1__")
        group2 = yield self.directory.recordWithUID(u"__sub_group_1__")

        # Add group delegate
        yield Delegates.addDelegate(txn, delegator, group1, True)
        # Passing expanded=False will return the group
        delegates = (yield Delegates.delegatesOf(txn, delegator, True, expanded=False))
        self.assertEquals(1, len(delegates))
        self.assertEquals(delegates[0].uid, u"__top_group_1__")
        # Passing expanded=True will return not the group -- it only returns
        # non-groups
        delegates = (yield Delegates.delegatesOf(txn, delegator, True, expanded=True))
        self.assertEquals(
            set([u"__sagen1__", u"__cdaboo1__", u"__glyph1__"]),
            set([d.uid for d in delegates])
        )
        delegators = (yield Delegates.delegatedTo(txn, delegate1, True))
        self.assertEquals([u"__wsanchez1__"], [d.uid for d in delegators])

        # Verify we can ask for all delegated-to groups
        yield Delegates.addDelegate(txn, delegator, group2, True)
        groups = (yield txn.allGroupDelegates())
        self.assertEquals(
            set([u'__sub_group_1__', u'__top_group_1__']), set(groups)
        )

        # Delegate to a user who is already indirectly delegated-to
        yield Delegates.addDelegate(txn, delegator, delegate1, True)
        delegates = (yield Delegates.delegatesOf(txn, delegator, True, expanded=True))
        self.assertEquals(
            set([u"__sagen1__", u"__cdaboo1__", u"__glyph1__"]),
            set([d.uid for d in delegates])
        )

        # Add a member to the group; they become a delegate
        newSet = set()
        for name in (u"wsanchez1", u"cdaboo1", u"sagen1", u"glyph1", u"dre1"):
            record = (
                yield self.directory.recordWithShortName(RecordType.user, name)
            )
            newSet.add(record.uid)
        (
            groupID, name, _ignore_membershipHash, _ignore_modified,
            _ignore_extant
        ) = (yield txn.groupByUID(group1.uid))
        _ignore_added, _ignore_removed = (
            yield self.groupCacher.synchronizeMembers(txn, groupID, newSet)
        )
        delegates = (yield Delegates.delegatesOf(txn, delegator, True, expanded=True))
        self.assertEquals(
            set([u"__sagen1__", u"__cdaboo1__", u"__glyph1__", u"__dre1__"]),
            set([d.uid for d in delegates])
        )

        # Remove delegate access from the top group
        yield Delegates.removeDelegate(txn, delegator, group1, True)
        delegates = (yield Delegates.delegatesOf(txn, delegator, True, expanded=True))
        self.assertEquals(
            set([u"__sagen1__", u"__cdaboo1__"]),
            set([d.uid for d in delegates])
        )

        # Remove delegate access from the sub group
        yield Delegates.removeDelegate(txn, delegator, group2, True)
        delegates = (yield Delegates.delegatesOf(txn, delegator, True, expanded=True))
        self.assertEquals(
            set([u"__sagen1__"]),
            set([d.uid for d in delegates])
        )
        yield txn.commit()


    @inlineCallbacks
    def test_noDuplication(self):
        """
        Make sure addDelegate( ) is idempotent
        """
        delegator = yield self.directory.recordWithUID(u"__wsanchez1__")

        # Delegate users:
        delegate1 = yield self.directory.recordWithUID(u"__sagen1__")

        txn = self.store.newTransaction(label="test_noDuplication")
        yield Delegates.addDelegate(txn, delegator, delegate1, True)
        yield txn.commit()

        txn = self.store.newTransaction(label="test_noDuplication")
        yield Delegates.addDelegate(txn, delegator, delegate1, True)
        yield txn.commit()

        txn = self.store.newTransaction(label="test_noDuplication")
        results = (
            yield txn._selectDelegatesQuery.on(
                txn,
                delegator=delegator.uid.encode("utf-8"),
                readWrite=1
            )
        )
        yield txn.commit()
        self.assertEquals([["__sagen1__"]], results)

        # Delegate groups:
        group1 = yield self.directory.recordWithUID(u"__top_group_1__")

        txn = self.store.newTransaction(label="test_noDuplication")
        yield Delegates.addDelegate(txn, delegator, group1, True)
        yield txn.commit()

        txn = self.store.newTransaction(label="test_noDuplication")
        yield Delegates.addDelegate(txn, delegator, group1, True)
        yield txn.commit()

        txn = self.store.newTransaction(label="test_noDuplication")
        results = (
            yield txn._selectDelegateGroupsQuery.on(
                txn,
                delegator=delegator.uid.encode("utf-8"),
                readWrite=1
            )
        )
        yield txn.commit()
        self.assertEquals([["__top_group_1__"]], results)



class DelegationCachingTest(StoreTestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(DelegationCachingTest, self).setUp()
        self.store = self.storeUnderTest()
        self.groupCacher = GroupCacher(self.directory)

        yield Delegates._memcacher.flushAll()


    @inlineCallbacks
    def _memcacherMemberResults(self, delegate, readWrite, expanded, results):
        delegateUIDs = yield Delegates._memcacher.getMembers(delegate.uid, readWrite, expanded)
        self.assertEqual(
            set(delegateUIDs) if delegateUIDs is not None else None,
            set([result.uid for result in results]) if results is not None else None,
            msg="uid:{}, rw={}, expanded={}".format(delegate.uid, readWrite, expanded)
        )


    @inlineCallbacks
    def _memcacherAllMemberResults(self, delegate, results1, results2, results3, results4):
        for readWrite, expanded, results in (
            (True, False, results1),
            (True, True, results2),
            (False, False, results3),
            (False, True, results4),
        ):
            yield self._memcacherMemberResults(delegate, readWrite, expanded, results)


    @inlineCallbacks
    def _memcacherMembershipResults(self, delegate, readWrite, results):
        delegatorUIDs = yield Delegates._memcacher.getMemberships(delegate.uid, readWrite)
        self.assertEqual(
            set(delegatorUIDs) if delegatorUIDs is not None else None,
            set([delegator.uid for delegator in results]) if results is not None else None,
            msg="uid:{}, rw={}".format(delegate.uid, readWrite)
        )


    @inlineCallbacks
    def _memcacherAllMembershipResults(self, delegate, results1, results2):
        for readWrite, results in (
            (True, results1),
            (False, results2),
        ):
            yield self._memcacherMembershipResults(delegate, readWrite, results)


    @inlineCallbacks
    def _delegatesOfResults(self, delegator, readWrite, expanded, results):
        delegates = (yield Delegates.delegatesOf(self.transactionUnderTest(), delegator, readWrite, expanded))
        self.assertEquals(
            set([d.uid for d in delegates]),
            set([delegate.uid for delegate in results]),
            msg="uid:{}, rw={}, expanded={}".format(delegator.uid, readWrite, expanded)
        )


    @inlineCallbacks
    def _delegatesOfAllResults(self, delegator, results1, results2, results3, results4):
        for readWrite, expanded, results in (
            (True, False, results1),
            (True, True, results2),
            (False, False, results3),
            (False, True, results4),
        ):
            yield self._delegatesOfResults(delegator, readWrite, expanded, results)


    @inlineCallbacks
    def _delegatedToResults(self, delegate, readWrite, results):
        delegators = (yield Delegates.delegatedTo(self.transactionUnderTest(), delegate, readWrite))
        self.assertEquals(
            set([d.uid for d in delegators]),
            set([delegator.uid for delegator in results]),
            msg="uid:{}, rw={}".format(delegate.uid, readWrite)
        )


    @inlineCallbacks
    def _delegatedToAllResults(self, delegator, results1, results2):
        for readWrite, results in (
            (True, results1),
            (False, results2),
        ):
            yield self._delegatedToResults(delegator, readWrite, results)


    @inlineCallbacks
    def test_cacheUsed(self):

        delegator = yield self.directory.recordWithUID(u"__wsanchez1__")
        delegate1 = yield self.directory.recordWithUID(u"__sagen1__")

        # Patch transaction so we can monitor whether cache is being used
        original_delegates = CommonStoreTransaction.delegates
        delegates_query = [0]
        def _delegates(self, delegator, readWrite, expanded=False):
            delegates_query[0] += 1
            return original_delegates(self, delegator, readWrite, expanded)
        self.patch(CommonStoreTransaction, "delegates", _delegates)

        original_delegators = CommonStoreTransaction.delegators
        delegators_query = [0]
        def _delegators(self, delegate, readWrite):
            delegators_query[0] += 1
            return original_delegators(self, delegate, readWrite)
        self.patch(CommonStoreTransaction, "delegators", _delegators)

        # Not used
        yield Delegates.delegatesOf(self.transactionUnderTest(), delegator, True, False)
        self.assertEqual(delegates_query[0], 1)

        # Used
        yield Delegates.delegatesOf(self.transactionUnderTest(), delegator, True, False)
        self.assertEqual(delegates_query[0], 1)

        # Not used
        yield Delegates.delegatesOf(self.transactionUnderTest(), delegator, False, False)
        self.assertEqual(delegates_query[0], 2)

        # Used
        yield Delegates.delegatesOf(self.transactionUnderTest(), delegator, False, False)
        self.assertEqual(delegates_query[0], 2)

        # Not used
        yield Delegates.delegatedTo(self.transactionUnderTest(), delegate1, True)
        self.assertEqual(delegators_query[0], 1)

        # Used
        yield Delegates.delegatedTo(self.transactionUnderTest(), delegate1, True)
        self.assertEqual(delegators_query[0], 1)

        # Not used
        yield Delegates.delegatedTo(self.transactionUnderTest(), delegate1, False)
        self.assertEqual(delegators_query[0], 2)

        # Used
        yield Delegates.delegatedTo(self.transactionUnderTest(), delegate1, False)
        self.assertEqual(delegators_query[0], 2)


    @inlineCallbacks
    def test_addRemoveDelegation(self):

        delegator = yield self.directory.recordWithUID(u"__wsanchez1__")
        delegate1 = yield self.directory.recordWithUID(u"__sagen1__")
        delegate2 = yield self.directory.recordWithUID(u"__cdaboo1__")

        # Add delegate
        yield Delegates.addDelegate(self.transactionUnderTest(), delegator, delegate1, True)
        yield self.commit()

        # Some cache entries invalid
        yield self._memcacherAllMemberResults(delegator, None, [delegate1], None, None)
        yield self._memcacherAllMemberResults(delegate1, None, None, None, None)
        yield self._memcacherAllMemberResults(delegate2, None, None, None, None)
        yield self._memcacherAllMembershipResults(delegator, None, None)
        yield self._memcacherAllMembershipResults(delegate1, None, None)
        yield self._memcacherAllMembershipResults(delegate2, None, None)

        # Read the delegate information twice - first time should be without cache, second with
        for _ignore in range(2):
            yield self._delegatesOfAllResults(
                delegator,
                [delegate1], [delegate1], [], [],
            )

            yield self._delegatesOfAllResults(
                delegate1,
                [], [], [], [],
            )

            yield self._delegatesOfAllResults(
                delegate2,
                [], [], [], [],
            )

            yield self._delegatedToAllResults(
                delegator,
                [], [],
            )

            yield self._delegatedToAllResults(
                delegate1,
                [delegator], [],
            )

            yield self._delegatedToAllResults(
                delegate2,
                [], [],
            )

            # Check cache
            yield self._memcacherAllMemberResults(delegator, [delegate1], [delegate1], [], [])
            yield self._memcacherAllMemberResults(delegate1, [], [], [], [])
            yield self._memcacherAllMemberResults(delegate2, [], [], [], [])
            yield self._memcacherAllMembershipResults(delegator, [], [])
            yield self._memcacherAllMembershipResults(delegate1, [delegator], [])
            yield self._memcacherAllMembershipResults(delegate2, [], [])

        # Remove delegate
        yield Delegates.removeDelegate(self.transactionUnderTest(), delegator, delegate1, True)
        yield self.commit()

        # Some cache entries invalid
        yield self._memcacherAllMemberResults(delegator, None, [], [], [])
        yield self._memcacherAllMemberResults(delegate1, [], [], [], [])
        yield self._memcacherAllMemberResults(delegate2, [], [], [], [])
        yield self._memcacherAllMembershipResults(delegator, [], [])
        yield self._memcacherAllMembershipResults(delegate1, None, [])
        yield self._memcacherAllMembershipResults(delegate2, [], [])

        # Read the delegate information twice - first time should be without cache, second with
        for _ignore in range(2):
            yield self._delegatesOfAllResults(
                delegator,
                [], [], [], [],
            )

            yield self._delegatesOfAllResults(
                delegate1,
                [], [], [], [],
            )

            yield self._delegatesOfAllResults(
                delegate2,
                [], [], [], [],
            )

            yield self._delegatedToAllResults(
                delegator,
                [], [],
            )

            yield self._delegatedToAllResults(
                delegate1,
                [], [],
            )

            yield self._delegatedToAllResults(
                delegate2,
                [], [],
            )

            # Check cache
            yield self._memcacherAllMemberResults(delegator, [], [], [], [])
            yield self._memcacherAllMemberResults(delegate1, [], [], [], [])
            yield self._memcacherAllMemberResults(delegate2, [], [], [], [])
            yield self._memcacherAllMembershipResults(delegator, [], [])
            yield self._memcacherAllMembershipResults(delegate1, [], [])
            yield self._memcacherAllMembershipResults(delegate2, [], [])


    @inlineCallbacks
    def test_setDelegation(self):

        delegator = yield self.directory.recordWithUID(u"__wsanchez1__")
        delegates = [
            (yield self.directory.recordWithUID(u"__sagen1__")),
            (yield self.directory.recordWithUID(u"__cdaboo1__")),
            (yield self.directory.recordWithUID(u"__dre1__")),
        ]

        # Add delegates
        yield Delegates.setDelegates(self.transactionUnderTest(), delegator, [delegates[0], delegates[1]], True)
        yield self.commit()

        # Some cache entries invalid
        yield self._memcacherAllMemberResults(delegator, None, [delegates[0], delegates[1]], None, None)
        yield self._memcacherAllMembershipResults(delegator, None, None)
        for delegate in delegates:
            yield self._memcacherAllMemberResults(delegate, None, None, None, None)
            yield self._memcacherAllMembershipResults(delegate, None, None)

        # Read the delegate information twice - first time should be without cache, second with
        for _ignore in range(2):
            yield self._delegatesOfAllResults(delegator, [delegates[0], delegates[1]], [delegates[0], delegates[1]], [], [])
            for delegate in delegates:
                yield self._delegatesOfAllResults(delegate, [], [], [], [])

            yield self._delegatedToAllResults(delegator, [], [])
            yield self._delegatedToAllResults(delegates[0], [delegator], [])
            yield self._delegatedToAllResults(delegates[1], [delegator], [])
            yield self._delegatedToAllResults(delegates[2], [], [])

            # Check cache
            yield self._memcacherAllMemberResults(delegator, [delegates[0], delegates[1]], [delegates[0], delegates[1]], [], [])
            for delegate in delegates:
                yield self._memcacherAllMemberResults(delegate, [], [], [], [])
            yield self._memcacherAllMembershipResults(delegator, [], [])
            yield self._memcacherAllMembershipResults(delegates[0], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[1], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[2], [], [])

        # Remove delegate
        yield Delegates.setDelegates(self.transactionUnderTest(), delegator, [delegates[1], delegates[2]], True)
        yield self.commit()

        # Some cache entries invalid
        yield self._memcacherAllMemberResults(delegator, None, [delegates[1], delegates[2]], [], [])
        for delegate in delegates:
            yield self._memcacherAllMemberResults(delegate, [], [], [], [])
        yield self._memcacherAllMembershipResults(delegator, [], [])
        yield self._memcacherAllMembershipResults(delegates[0], None, [])
        yield self._memcacherAllMembershipResults(delegates[1], [delegator], [])
        yield self._memcacherAllMembershipResults(delegates[2], None, [])

        # Read the delegate information twice - first time should be without cache, second with
        for _ignore in range(2):
            yield self._delegatesOfAllResults(delegator, [delegates[1], delegates[2]], [delegates[1], delegates[2]], [], [])
            for delegate in delegates:
                yield self._delegatesOfAllResults(delegate, [], [], [], [])

            yield self._delegatedToAllResults(delegator, [], [])
            yield self._delegatedToAllResults(delegates[0], [], [])
            yield self._delegatedToAllResults(delegates[1], [delegator], [])
            yield self._delegatedToAllResults(delegates[2], [delegator], [])

            # Check cache
            yield self._memcacherAllMemberResults(delegator, [delegates[1], delegates[2]], [delegates[1], delegates[2]], [], [])
            for delegate in delegates:
                yield self._memcacherAllMemberResults(delegate, [], [], [], [])
            yield self._memcacherAllMembershipResults(delegator, [], [])
            yield self._memcacherAllMembershipResults(delegates[0], [], [])
            yield self._memcacherAllMembershipResults(delegates[1], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[2], [delegator], [])

        # Add delegate with other mode
        yield Delegates.setDelegates(self.transactionUnderTest(), delegator, [delegates[0]], False)
        yield self.commit()

        # Some cache entries invalid
        yield self._memcacherAllMemberResults(delegator, [delegates[1], delegates[2]], [delegates[1], delegates[2]], None, [delegates[0]])
        for delegate in delegates:
            yield self._memcacherAllMemberResults(delegate, [], [], [], [])
        yield self._memcacherAllMembershipResults(delegator, [], [])
        yield self._memcacherAllMembershipResults(delegates[0], [], None)
        yield self._memcacherAllMembershipResults(delegates[1], [delegator], [])
        yield self._memcacherAllMembershipResults(delegates[2], [delegator], [])

        # Read the delegate information twice - first time should be without cache, second with
        for _ignore in range(2):
            yield self._delegatesOfAllResults(delegator, [delegates[1], delegates[2]], [delegates[1], delegates[2]], [delegates[0]], [delegates[0]])
            for delegate in delegates:
                yield self._delegatesOfAllResults(delegate, [], [], [], [])

            yield self._delegatedToAllResults(delegator, [], [])
            yield self._delegatedToAllResults(delegates[0], [], [delegator])
            yield self._delegatedToAllResults(delegates[1], [delegator], [])
            yield self._delegatedToAllResults(delegates[2], [delegator], [])

            # Check cache
            yield self._memcacherAllMemberResults(delegator, [delegates[1], delegates[2]], [delegates[1], delegates[2]], [delegates[0]], [delegates[0]])
            for delegate in delegates:
                yield self._memcacherAllMemberResults(delegate, [], [], [], [])
            yield self._memcacherAllMembershipResults(delegator, [], [])
            yield self._memcacherAllMembershipResults(delegates[0], [], [delegator])
            yield self._memcacherAllMembershipResults(delegates[1], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[2], [delegator], [])


    @inlineCallbacks
    def test_setGroupDelegation(self):

        delegator = yield self.directory.recordWithUID(u"__wsanchez1__")
        delegates = [
            (yield self.directory.recordWithUID(u"__sagen1__")),
            (yield self.directory.recordWithUID(u"__cdaboo1__")),
            (yield self.directory.recordWithUID(u"__glyph1__")),
            (yield self.directory.recordWithUID(u"__dre1__")),
        ]
        group1 = yield self.directory.recordWithUID(u"__top_group_1__")
        group2 = yield self.directory.recordWithUID(u"__sub_group_1__")
        yield self.transactionUnderTest().groupByUID(u"__top_group_1__")
        yield self.transactionUnderTest().groupByUID(u"__sub_group_1__")
        yield self.commit()

        def delegateMatch(*args):
            return [delegates[i] for i in args]

        # Add group delegate
        yield Delegates.setDelegates(self.transactionUnderTest(), delegator, [group1], True)
        yield self.commit()

        # Some cache entries invalid
        yield self._memcacherAllMemberResults(delegator, None, delegateMatch(0, 1, 2), None, None)
        yield self._memcacherAllMembershipResults(delegator, None, None)
        for delegate in delegates:
            yield self._memcacherAllMemberResults(delegate, None, None, None, None)
            yield self._memcacherAllMembershipResults(delegate, None, None)

        # Read the delegate information twice - first time should be without cache, second with
        for _ignore in range(2):
            yield self._delegatesOfAllResults(delegator, [group1], delegateMatch(0, 1, 2), [], [])
            for delegate in delegates:
                yield self._delegatesOfAllResults(delegate, [], [], [], [])

            yield self._delegatedToAllResults(delegator, [], [])
            yield self._delegatedToAllResults(delegates[0], [delegator], [])
            yield self._delegatedToAllResults(delegates[1], [delegator], [])
            yield self._delegatedToAllResults(delegates[2], [delegator], [])
            yield self._delegatedToAllResults(delegates[3], [], [])

            # Check cache
            yield self._memcacherAllMemberResults(delegator, [group1], delegateMatch(0, 1, 2), [], [])
            for delegate in delegates:
                yield self._memcacherAllMemberResults(delegate, [], [], [], [])
            yield self._memcacherAllMembershipResults(delegator, [], [])
            yield self._memcacherAllMembershipResults(delegates[0], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[1], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[2], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[3], [], [])

        # Add individual delegate
        yield Delegates.setDelegates(self.transactionUnderTest(), delegator, [group1, delegates[3]], True)
        yield self.commit()

        # Some cache entries invalid
        yield self._memcacherAllMemberResults(delegator, None, delegateMatch(0, 1, 2, 3), [], [])
        for delegate in delegates:
            yield self._memcacherAllMemberResults(delegate, [], [], [], [])
        yield self._memcacherAllMembershipResults(delegator, [], [])
        yield self._memcacherAllMembershipResults(delegates[0], [delegator], [])
        yield self._memcacherAllMembershipResults(delegates[1], [delegator], [])
        yield self._memcacherAllMembershipResults(delegates[2], [delegator], [])
        yield self._memcacherAllMembershipResults(delegates[3], None, [])

        # Read the delegate information twice - first time should be without cache, second with
        for _ignore in range(2):
            yield self._delegatesOfAllResults(delegator, [group1, delegates[3]], delegateMatch(0, 1, 2, 3), [], [])
            for delegate in delegates:
                yield self._delegatesOfAllResults(delegate, [], [], [], [])

            yield self._delegatedToAllResults(delegator, [], [])
            yield self._delegatedToAllResults(delegates[0], [delegator], [])
            yield self._delegatedToAllResults(delegates[1], [delegator], [])
            yield self._delegatedToAllResults(delegates[2], [delegator], [])
            yield self._delegatedToAllResults(delegates[3], [delegator], [])

            # Check cache
            yield self._memcacherAllMemberResults(delegator, [group1, delegates[3]], delegateMatch(0, 1, 2, 3), [], [])
            for delegate in delegates:
                yield self._memcacherAllMemberResults(delegate, [], [], [], [])
            yield self._memcacherAllMembershipResults(delegator, [], [])
            yield self._memcacherAllMembershipResults(delegates[0], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[1], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[2], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[3], [delegator], [])

        # Switch to sub-group
        yield Delegates.setDelegates(self.transactionUnderTest(), delegator, [group2, delegates[3]], True)
        yield self.commit()

        # Some cache entries invalid
        yield self._memcacherAllMemberResults(delegator, None, delegateMatch(0, 1, 3), [], [])
        for delegate in delegates:
            yield self._memcacherAllMemberResults(delegate, [], [], [], [])
        yield self._memcacherAllMembershipResults(delegator, [], [])
        yield self._memcacherAllMembershipResults(delegates[0], None, [])
        yield self._memcacherAllMembershipResults(delegates[1], None, [])
        yield self._memcacherAllMembershipResults(delegates[2], None, [])
        yield self._memcacherAllMembershipResults(delegates[3], [delegator], [])

        # Read the delegate information twice - first time should be without cache, second with
        for _ignore in range(2):
            yield self._delegatesOfAllResults(delegator, [group2, delegates[3]], delegateMatch(0, 1, 3), [], [])
            for delegate in delegates:
                yield self._delegatesOfAllResults(delegate, [], [], [], [])

            yield self._delegatedToAllResults(delegator, [], [])
            yield self._delegatedToAllResults(delegates[0], [delegator], [])
            yield self._delegatedToAllResults(delegates[1], [delegator], [])
            yield self._delegatedToAllResults(delegates[2], [], [])
            yield self._delegatedToAllResults(delegates[3], [delegator], [])

            # Check cache
            yield self._memcacherAllMemberResults(delegator, [group2, delegates[3]], delegateMatch(0, 1, 3), [], [])
            for delegate in delegates:
                yield self._memcacherAllMemberResults(delegate, [], [], [], [])
            yield self._memcacherAllMembershipResults(delegator, [], [])
            yield self._memcacherAllMembershipResults(delegates[0], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[1], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[2], [], [])
            yield self._memcacherAllMembershipResults(delegates[3], [delegator], [])

        # Add member of existing group
        yield Delegates.setDelegates(self.transactionUnderTest(), delegator, [group2, delegates[0], delegates[3]], True)
        yield self.commit()

        # Some cache entries invalid
        yield self._memcacherAllMemberResults(delegator, None, delegateMatch(0, 1, 3), [], [])
        for delegate in delegates:
            yield self._memcacherAllMemberResults(delegate, [], [], [], [])
        yield self._memcacherAllMembershipResults(delegator, [], [])
        yield self._memcacherAllMembershipResults(delegates[0], [delegator], [])
        yield self._memcacherAllMembershipResults(delegates[1], [delegator], [])
        yield self._memcacherAllMembershipResults(delegates[2], [], [])
        yield self._memcacherAllMembershipResults(delegates[3], [delegator], [])

        # Read the delegate information twice - first time should be without cache, second with
        for _ignore in range(2):
            yield self._delegatesOfAllResults(delegator, [group2, delegates[0], delegates[3]], delegateMatch(0, 1, 3), [], [])
            for delegate in delegates:
                yield self._delegatesOfAllResults(delegate, [], [], [], [])

            yield self._delegatedToAllResults(delegator, [], [])
            yield self._delegatedToAllResults(delegates[0], [delegator], [])
            yield self._delegatedToAllResults(delegates[1], [delegator], [])
            yield self._delegatedToAllResults(delegates[2], [], [])
            yield self._delegatedToAllResults(delegates[3], [delegator], [])

            # Check cache
            yield self._memcacherAllMemberResults(delegator, [group2, delegates[0], delegates[3]], delegateMatch(0, 1, 3), [], [])
            for delegate in delegates:
                yield self._memcacherAllMemberResults(delegate, [], [], [], [])
            yield self._memcacherAllMembershipResults(delegator, [], [])
            yield self._memcacherAllMembershipResults(delegates[0], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[1], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[2], [], [])
            yield self._memcacherAllMembershipResults(delegates[3], [delegator], [])

        # Remove group
        yield Delegates.setDelegates(self.transactionUnderTest(), delegator, [delegates[0], delegates[3]], True)
        yield self.commit()

        # Some cache entries invalid
        yield self._memcacherAllMemberResults(delegator, None, delegateMatch(0, 3), [], [])
        for delegate in delegates:
            yield self._memcacherAllMemberResults(delegate, [], [], [], [])
        yield self._memcacherAllMembershipResults(delegator, [], [])
        yield self._memcacherAllMembershipResults(delegates[0], [delegator], [])
        yield self._memcacherAllMembershipResults(delegates[1], None, [])
        yield self._memcacherAllMembershipResults(delegates[2], [], [])
        yield self._memcacherAllMembershipResults(delegates[3], [delegator], [])

        # Read the delegate information twice - first time should be without cache, second with
        for _ignore in range(2):
            yield self._delegatesOfAllResults(delegator, [delegates[0], delegates[3]], delegateMatch(0, 3), [], [])
            for delegate in delegates:
                yield self._delegatesOfAllResults(delegate, [], [], [], [])

            yield self._delegatedToAllResults(delegator, [], [])
            yield self._delegatedToAllResults(delegates[0], [delegator], [])
            yield self._delegatedToAllResults(delegates[1], [], [])
            yield self._delegatedToAllResults(delegates[2], [], [])
            yield self._delegatedToAllResults(delegates[3], [delegator], [])

            # Check cache
            yield self._memcacherAllMemberResults(delegator, [delegates[0], delegates[3]], delegateMatch(0, 3), [], [])
            for delegate in delegates:
                yield self._memcacherAllMemberResults(delegate, [], [], [], [])
            yield self._memcacherAllMembershipResults(delegator, [], [])
            yield self._memcacherAllMembershipResults(delegates[0], [delegator], [])
            yield self._memcacherAllMembershipResults(delegates[1], [], [])
            yield self._memcacherAllMembershipResults(delegates[2], [], [])
            yield self._memcacherAllMembershipResults(delegates[3], [delegator], [])
