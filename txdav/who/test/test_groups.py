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

from txdav.who.groups import GroupCacher, expandedMembers, diffAssignments
from twext.who.idirectory import RecordType
from twext.who.test.test_xml import xmlService
from twisted.internet.defer import inlineCallbacks
from twistedcaldav.test.util import StoreTestCase
from txdav.common.icommondatastore import NotFoundError


class GroupCacherTest(StoreTestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(GroupCacherTest, self).setUp()
        self.xmlService = xmlService(self.mktemp(), xmlData=testXMLConfig)
        self.groupCacher = GroupCacher(self.xmlService)


    @inlineCallbacks
    def test_expandedMembers(self):
        """
        Verify expandedMembers() returns a "flattened" set of records
        belonging to a group (and does not return sub-groups themselves,
        only their members)
        """
        record = yield self.xmlService.recordWithUID(u"__top_group_1__")
        memberUIDs = set()
        for member in (yield expandedMembers(record)):
            memberUIDs.add(member.uid)
        self.assertEquals(
            memberUIDs,
            set(["__cdaboo__", "__glyph__", "__sagen__", "__wsanchez__"])
        )

        # Non group records return an empty set() of members
        record = yield self.xmlService.recordWithUID(u"__sagen__")
        members = yield expandedMembers(record)
        self.assertEquals(0, len(list(members)))


    @inlineCallbacks
    def test_refreshGroup(self):
        """
        Verify refreshGroup() adds a group to the Groups table with the
        expected membership hash value and members
        """

        store = self.storeUnderTest()
        txn = store.newTransaction()

        record = yield self.xmlService.recordWithUID(u"__top_group_1__")
        yield self.groupCacher.refreshGroup(txn, record.uid)

        groupID, name, membershipHash = (yield txn.groupByUID(record.uid))

        self.assertEquals(membershipHash, "f380860ff5e02c2433fbd4b5ed3e090c")

        groupUID, name, membershipHash = (yield txn.groupByID(groupID))
        self.assertEquals(groupUID, record.uid)
        self.assertEquals(name, u"Top Group 1")
        self.assertEquals(membershipHash, "f380860ff5e02c2433fbd4b5ed3e090c")

        members = (yield txn.membersOfGroup(groupID))
        self.assertEquals(
            set([u'__cdaboo__', u'__glyph__', u'__sagen__', u'__wsanchez__']),
            members
        )

        records = (yield self.groupCacher.cachedMembers(txn, groupID))
        self.assertEquals(
            set([r.shortNames[0] for r in records]),
            set(["wsanchez", "cdaboo", "glyph", "sagen"])
        )

        # sagen is in the top group, even though it's actually one level
        # removed
        record = yield self.xmlService.recordWithUID(u"__sagen__")
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
        for name in (u"wsanchez", u"cdaboo", u"dre"):
            record = (
                yield self.xmlService.recordWithShortName(
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
            set(["wsanchez", "cdaboo", "dre"])
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
        hash = "f380860ff5e02c2433fbd4b5ed3e090c"
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
            u"__wsanchez__": (None, u"__top_group_1__")
        }
        yield self.groupCacher.applyExternalAssignments(txn, newAssignments)
        oldExternalAssignments = (yield txn.externalDelegates())
        self.assertEquals(
            oldExternalAssignments,
            {
                u"__wsanchez__":
                (
                    None,
                    u"__top_group_1__"
                )
            }
        )

        newAssignments = {
            u"__cdaboo__":
            (
                u"__sub_group_1__",
                None
            ),
            u"__wsanchez__":
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
                u"__wsanchez__":
                (
                    u"__sub_group_1__",
                    u"__top_group_1__"
                ),
                u"__cdaboo__":
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
            u"__wsanchez__", False, expanded=True)
        )
        self.assertEquals(
            delegates,
            set(
                [
                    u"__sagen__",
                    u"__cdaboo__"
                ]
            )
        )

        # Fault in the read-write group
        yield self.groupCacher.refreshGroup(txn, u"__top_group_1__")

        # Wilfredo should have 4 users as read-write delegates
        delegates = (yield txn.delegates(
            u"__wsanchez__", True, expanded=True)
        )
        self.assertEquals(
            delegates,
            set(
                [
                    u"__wsanchez__",
                    u"__sagen__",
                    u"__cdaboo__",
                    u"__glyph__"
                ]
            )
        )


        #
        # Now, remove some external assignments
        #
        newAssignments = {
            u"__wsanchez__":
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
                u"__wsanchez__":
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
            u"__wsanchez__", False, expanded=True)
        )
        self.assertEquals(
            delegates,
            set(
                [
                    u"__sagen__",
                    u"__cdaboo__"
                ]
            )
        )

        # Wilfredo should have no read-write delegates
        delegates = (yield txn.delegates(
            u"__wsanchez__", True, expanded=True)
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

testXMLConfig = """<?xml version="1.0" encoding="utf-8"?>

<directory realm="xyzzy">

  <record type="user">
    <uid>__wsanchez__</uid>
    <short-name>wsanchez</short-name>
    <short-name>wilfredo_sanchez</short-name>
    <full-name>Wilfredo Sanchez</full-name>
    <password>zehcnasw</password>
    <email>wsanchez@bitbucket.calendarserver.org</email>
    <email>wsanchez@devnull.twistedmatrix.com</email>
  </record>

  <record type="user">
    <uid>__glyph__</uid>
    <short-name>glyph</short-name>
    <full-name>Glyph Lefkowitz</full-name>
    <password>hpylg</password>
    <email>glyph@bitbucket.calendarserver.org</email>
    <email>glyph@devnull.twistedmatrix.com</email>
  </record>

  <record type="user">
    <uid>__sagen__</uid>
    <short-name>sagen</short-name>
    <full-name>Morgen Sagen</full-name>
    <password>negas</password>
    <email>sagen@bitbucket.calendarserver.org</email>
    <email>shared@example.com</email>
  </record>

  <record type="user">
    <uid>__cdaboo__</uid>
    <short-name>cdaboo</short-name>
    <full-name>Cyrus Daboo</full-name>
    <password>suryc</password>
    <email>cdaboo@bitbucket.calendarserver.org</email>
  </record>

  <record type="user">
    <uid>__dre__</uid>
    <short-name>dre</short-name>
    <full-name>Andre LaBranche</full-name>
    <password>erd</password>
    <email>dre@bitbucket.calendarserver.org</email>
    <email>shared@example.com</email>
  </record>

  <record type="group">
    <uid>__top_group_1__</uid>
    <short-name>top-group-1</short-name>
    <full-name>Top Group 1</full-name>
    <email>topgroup1@example.com</email>
    <member-uid>__wsanchez__</member-uid>
    <member-uid>__glyph__</member-uid>
    <member-uid>__sub_group_1__</member-uid>
  </record>

  <record type="group">
    <uid>__sub_group_1__</uid>
    <short-name>sub-group-1</short-name>
    <full-name>Sub Group 1</full-name>
    <email>subgroup1@example.com</email>
    <member-uid>__sagen__</member-uid>
    <member-uid>__cdaboo__</member-uid>
  </record>

</directory>
"""
