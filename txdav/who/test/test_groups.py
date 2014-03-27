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
Group membership caching implementation tests
"""

from txdav.who.groups import GroupCacher, diffAssignments
from twext.who.idirectory import RecordType
from twisted.internet.defer import inlineCallbacks
from twistedcaldav.test.util import StoreTestCase
from txdav.common.icommondatastore import NotFoundError


class GroupCacherTest(StoreTestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(GroupCacherTest, self).setUp()
        self.groupCacher = GroupCacher(self.directory)


    @inlineCallbacks
    def test_refreshGroup(self):
        """
        Verify refreshGroup() adds a group to the Groups table with the
        expected membership hash value and members
        """

        store = self.storeUnderTest()
        txn = store.newTransaction()

        record = yield self.directory.recordWithUID(u"__top_group_1__")
        yield self.groupCacher.refreshGroup(txn, record.uid)

        groupID, name, membershipHash = (yield txn.groupByUID(record.uid))

        self.assertEquals(membershipHash, "553eb54e3bbb26582198ee04541dbee4")

        groupUID, name, membershipHash = (yield txn.groupByID(groupID))
        self.assertEquals(groupUID, record.uid)
        self.assertEquals(name, u"Top Group 1")
        self.assertEquals(membershipHash, "553eb54e3bbb26582198ee04541dbee4")

        members = (yield txn.membersOfGroup(groupID))
        self.assertEquals(
            set([u'__cdaboo1__', u'__glyph1__', u'__sagen1__', u'__wsanchez1__']),
            members
        )

        records = (yield self.groupCacher.cachedMembers(txn, groupID))
        self.assertEquals(
            set([r.shortNames[0] for r in records]),
            set(["wsanchez1", "cdaboo1", "glyph1", "sagen1"])
        )

        # sagen is in the top group, even though it's actually one level
        # removed
        record = yield self.directory.recordWithUID(u"__sagen1__")
        groups = (yield self.groupCacher.cachedGroupsFor(txn, record.uid))
        self.assertEquals(set([u"__top_group_1__"]), groups)


    @inlineCallbacks
    def test_synchronizeMembers(self):
        """
        After loading in a group via refreshGroup(), pass new member sets to
        synchronizeMembers() and verify members are added and removed as
        expected
        """

        store = self.storeUnderTest()
        txn = store.newTransaction()

        # Refresh the group so it's assigned a group_id
        uid = u"__top_group_1__"
        yield self.groupCacher.refreshGroup(txn, uid)
        groupID, name, membershipHash = (yield txn.groupByUID(uid))

        # Remove two members, and add one member
        newSet = set()
        for name in (u"wsanchez1", u"cdaboo1", u"dre1"):
            record = (
                yield self.directory.recordWithShortName(
                    RecordType.user,
                    name
                )
            )
            newSet.add(record.uid)
        numAdded, numRemoved = (
            yield self.groupCacher.synchronizeMembers(
                txn, groupID, newSet
            )
        )
        self.assertEquals(numAdded, 1)
        self.assertEquals(numRemoved, 2)
        records = (yield self.groupCacher.cachedMembers(txn, groupID))
        self.assertEquals(
            set([r.shortNames[0] for r in records]),
            set(["wsanchez1", "cdaboo1", "dre1"])
        )

        # Remove all members
        numAdded, numRemoved = (
            yield self.groupCacher.synchronizeMembers(txn, groupID, set())
        )
        self.assertEquals(numAdded, 0)
        self.assertEquals(numRemoved, 3)
        records = (yield self.groupCacher.cachedMembers(txn, groupID))
        self.assertEquals(len(records), 0)


    @inlineCallbacks
    def test_groupByID(self):

        store = self.storeUnderTest()
        txn = store.newTransaction()

        # Non-existent groupID
        self.failUnlessFailure(txn.groupByID(42), NotFoundError)

        uid = u"__top_group_1__"
        hash = "553eb54e3bbb26582198ee04541dbee4"
        yield self.groupCacher.refreshGroup(txn, uid)
        groupID, name, membershipHash = (yield txn.groupByUID(uid))
        results = (yield txn.groupByID(groupID))
        self.assertEquals((uid, u"Top Group 1", hash), results)


    @inlineCallbacks
    def test_externalAssignments(self):

        store = self.storeUnderTest()
        txn = store.newTransaction()

        oldExternalAssignments = (yield txn.externalDelegates())
        self.assertEquals(oldExternalAssignments, {})

        newAssignments = {
            u"__wsanchez1__": (None, u"__top_group_1__")
        }
        yield self.groupCacher.applyExternalAssignments(txn, newAssignments)
        oldExternalAssignments = (yield txn.externalDelegates())
        self.assertEquals(
            oldExternalAssignments,
            {
                u"__wsanchez1__":
                (
                    None,
                    u"__top_group_1__"
                )
            }
        )

        newAssignments = {
            u"__cdaboo1__":
            (
                u"__sub_group_1__",
                None
            ),
            u"__wsanchez1__":
            (
                u"__sub_group_1__",
                u"__top_group_1__"
            ),
        }
        yield self.groupCacher.applyExternalAssignments(txn, newAssignments)
        oldExternalAssignments = (yield txn.externalDelegates())
        self.assertEquals(
            oldExternalAssignments,
            {
                u"__wsanchez1__":
                (
                    u"__sub_group_1__",
                    u"__top_group_1__"
                ),
                u"__cdaboo1__":
                (
                    u"__sub_group_1__",
                    None
                )
            }
        )

        allGroupDelegates = (yield txn.allGroupDelegates())
        self.assertEquals(
            allGroupDelegates,
            set(
                [
                    u"__top_group_1__",
                    u"__sub_group_1__"
                ]
            )
        )

        # Fault in the read-only group
        yield self.groupCacher.refreshGroup(txn, u"__sub_group_1__")

        # Wilfredo should have Sagen and Daboo as read-only delegates
        delegates = (yield txn.delegates(
            u"__wsanchez1__", False, expanded=True)
        )
        self.assertEquals(
            delegates,
            set(
                [
                    u"__sagen1__",
                    u"__cdaboo1__"
                ]
            )
        )

        # Fault in the read-write group
        yield self.groupCacher.refreshGroup(txn, u"__top_group_1__")

        # Wilfredo should have 4 users as read-write delegates
        delegates = (yield txn.delegates(
            u"__wsanchez1__", True, expanded=True)
        )
        self.assertEquals(
            delegates,
            set(
                [
                    u"__wsanchez1__",
                    u"__sagen1__",
                    u"__cdaboo1__",
                    u"__glyph1__"
                ]
            )
        )


        #
        # Now, remove some external assignments
        #
        newAssignments = {
            u"__wsanchez1__":
            (
                u"__sub_group_1__",
                None
            ),
        }
        yield self.groupCacher.applyExternalAssignments(txn, newAssignments)
        oldExternalAssignments = (yield txn.externalDelegates())
        self.assertEquals(
            oldExternalAssignments,
            {
                u"__wsanchez1__":
                (
                    u"__sub_group_1__",
                    None
                ),
            }
        )

        allGroupDelegates = (yield txn.allGroupDelegates())
        self.assertEquals(
            allGroupDelegates,
            set(
                [
                    u"__sub_group_1__"
                ]
            )
        )

        # Wilfredo should have Sagen and Daboo as read-only delegates
        delegates = (yield txn.delegates(
            u"__wsanchez1__", False, expanded=True)
        )
        self.assertEquals(
            delegates,
            set(
                [
                    u"__sagen1__",
                    u"__cdaboo1__"
                ]
            )
        )

        # Wilfredo should have no read-write delegates
        delegates = (yield txn.delegates(
            u"__wsanchez1__", True, expanded=True)
        )
        self.assertEquals(
            delegates,
            set([])
        )

        # Only 1 group as delegate now:
        allGroupDelegates = (yield txn.allGroupDelegates())
        self.assertEquals(
            allGroupDelegates,
            set(
                [
                    u"__sub_group_1__"
                ]
            )
        )

    def test_diffAssignments(self):
        """
        Ensure external proxy assignment diffing works
        """

        self.assertEquals(
            (
                # changed
                [],
                # removed
                [],
            ),
            diffAssignments(
                # old
                {},
                # new
                {}
            )
        )

        self.assertEquals(
            (
                # changed
                [],
                # removed
                [],
            ),
            diffAssignments(
                # old
                {"B": ("1", "2")},
                # new
                {"B": ("1", "2")},
            )
        )

        self.assertEquals(
            (
                # changed
                [("A", ("1", "2")), ("B", ("3", "4"))],
                # removed
                [],
            ),
            diffAssignments(
                # old
                {},
                # new
                {"A": ("1", "2"), "B": ("3", "4")}
            )
        )

        self.assertEquals(
            (
                # changed
                [],
                # removed
                ["A", "B"],
            ),
            diffAssignments(
                # old
                {"A": ("1", "2"), "B": ("3", "4")},
                # new
                {},
            )
        )

        self.assertEquals(
            (
                # changed
                [('C', ('4', '5')), ('D', ('7', '8'))],
                # removed
                ["B"],
            ),
            diffAssignments(
                # old
                {"A": ("1", "2"), "B": ("3", "4"), "C": ("5", "6")},
                # new
                {"D": ("7", "8"), "C": ("4", "5"), "A": ("1", "2")},
            )
        )
