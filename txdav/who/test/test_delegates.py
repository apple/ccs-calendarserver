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

from txdav.who.delegates import (
    addDelegate, removeDelegate, delegatesOf, delegatedTo,
    RecordType as DelegateRecordType
)
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


    @inlineCallbacks
    def test_directDelegation(self):
        txn = self.store.newTransaction(label="test_directDelegation")

        delegator = yield self.directory.recordWithUID(u"__wsanchez1__")
        delegate1 = yield self.directory.recordWithUID(u"__sagen1__")
        delegate2 = yield self.directory.recordWithUID(u"__cdaboo1__")

        # Add 1 delegate
        yield addDelegate(txn, delegator, delegate1, True)
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals([u"__sagen1__"], [d.uid for d in delegates])
        delegators = (yield delegatedTo(txn, delegate1, True))
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
        yield addDelegate(txn, delegator, delegate2, True)
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals(
            set([u"__sagen1__", u"__cdaboo1__"]),
            set([d.uid for d in delegates])
        )
        delegators = (yield delegatedTo(txn, delegate2, True))
        self.assertEquals([u"__wsanchez1__"], [d.uid for d in delegators])

        # Remove 1 delegate
        yield removeDelegate(txn, delegator, delegate1, True)
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals([u"__cdaboo1__"], [d.uid for d in delegates])
        delegators = (yield delegatedTo(txn, delegate1, True))
        self.assertEquals(0, len(delegators))

        # Remove the other delegate
        yield removeDelegate(txn, delegator, delegate2, True)
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals(0, len(delegates))
        delegators = (yield delegatedTo(txn, delegate2, True))
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
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals(
            set([u"__sagen1__", u"__cdaboo1__"]),
            set([d.uid for d in delegates])
        )
        yield txn.commit()

        # Set a different group of assignments:
        yield pseudoGroup.setMembers([delegate2])

        # Verify the assignments were made
        txn = self.store.newTransaction(label="test_directDelegation")
        delegates = (yield delegatesOf(txn, delegator, True))
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

        # Add group delegate, but before the group membership has been
        # pulled in
        yield addDelegate(txn, delegator, group1, True)
        # Passing expanded=False will return the group
        delegates = (yield delegatesOf(txn, delegator, True, expanded=False))
        self.assertEquals(1, len(delegates))
        self.assertEquals(delegates[0].uid, u"__top_group_1__")
        # Passing expanded=True will return not the group -- it only returns
        # non-groups
        delegates = (yield delegatesOf(txn, delegator, True, expanded=True))
        self.assertEquals(0, len(delegates))

        # Now refresh the group and there will be 3 delegates (contained
        # within 2 nested groups)
        # guid = "49b350c69611477b94d95516b13856ab"
        yield self.groupCacher.refreshGroup(txn, group1.uid)
        yield self.groupCacher.refreshGroup(txn, group2.uid)
        delegates = (yield delegatesOf(txn, delegator, True, expanded=True))
        self.assertEquals(
            set([u"__sagen1__", u"__cdaboo1__", u"__glyph1__"]),
            set([d.uid for d in delegates])
        )
        delegators = (yield delegatedTo(txn, delegate1, True))
        self.assertEquals([u"__wsanchez1__"], [d.uid for d in delegators])

        # Verify we can ask for all delegated-to groups
        yield addDelegate(txn, delegator, group2, True)
        groups = (yield txn.allGroupDelegates())
        self.assertEquals(
            set([u'__sub_group_1__', u'__top_group_1__']), set(groups)
        )

        # Delegate to a user who is already indirectly delegated-to
        yield addDelegate(txn, delegator, delegate1, True)
        delegates = (yield delegatesOf(txn, delegator, True, expanded=True))
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
        groupID, name, membershipHash, modified = (yield txn.groupByUID(group1.uid))
        numAdded, numRemoved = (
            yield self.groupCacher.synchronizeMembers(txn, groupID, newSet)
        )
        delegates = (yield delegatesOf(txn, delegator, True, expanded=True))
        self.assertEquals(
            set([u"__sagen1__", u"__cdaboo1__", u"__glyph1__", u"__dre1__"]),
            set([d.uid for d in delegates])
        )

        # Remove delegate access from the top group
        yield removeDelegate(txn, delegator, group1, True)
        delegates = (yield delegatesOf(txn, delegator, True, expanded=True))
        self.assertEquals(
            set([u"__sagen1__", u"__cdaboo1__"]),
            set([d.uid for d in delegates])
        )

        # Remove delegate access from the sub group
        yield removeDelegate(txn, delegator, group2, True)
        delegates = (yield delegatesOf(txn, delegator, True, expanded=True))
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
        yield addDelegate(txn, delegator, delegate1, True)
        yield txn.commit()

        txn = self.store.newTransaction(label="test_noDuplication")
        yield addDelegate(txn, delegator, delegate1, True)
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
        yield addDelegate(txn, delegator, group1, True)
        yield txn.commit()

        txn = self.store.newTransaction(label="test_noDuplication")
        yield addDelegate(txn, delegator, group1, True)
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
