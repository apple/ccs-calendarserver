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
from uuid import UUID


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
        yield self.groupCacher.refreshGroup(txn, record.guid)

        groupID, name, membershipHash = (yield txn.groupByGUID(record.guid))
        self.assertEquals(membershipHash, "4b0e162f2937f0f3daa6d10e5a6a6c33")

        groupGUID, name, membershipHash = (yield txn.groupByID(groupID))
        self.assertEquals(groupGUID, record.guid)
        self.assertEquals(name, "Top Group 1")
        self.assertEquals(membershipHash, "4b0e162f2937f0f3daa6d10e5a6a6c33")

        members = (yield txn.membersOfGroup(groupID))
        self.assertEquals(
            set([UUID("9064df911dbc4e079c2b6839b0953876"),
                 UUID("4ad155cbae9b475f986ce08a7537893e"),
                 UUID("3bdcb95484d54f6d8035eac19a6d6e1f"),
                 UUID("7d45cb10479e456bb54d528958c5734b")]),
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
        groups = (yield self.groupCacher.cachedGroupsFor(txn, record.guid))
        self.assertEquals(set([groupID]), groups)


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
        guid = UUID("49b350c69611477b94d95516b13856ab")
        yield self.groupCacher.refreshGroup(txn, guid)
        groupID, name, membershipHash = (yield txn.groupByGUID(guid))

        # Remove two members, and add one member
        newSet = set()
        for name in (u"wsanchez", u"cdaboo", u"dre"):
            record = (
                yield self.xmlService.recordWithShortName(
                    RecordType.user,
                    name
                )
            )
            newSet.add(record.guid)
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

        guid = UUID("49b350c69611477b94d95516b13856ab")
        hash = "4b0e162f2937f0f3daa6d10e5a6a6c33"
        yield self.groupCacher.refreshGroup(txn, guid)
        groupID, name, membershipHash = (yield txn.groupByGUID(guid))
        results = (yield txn.groupByID(groupID))
        self.assertEquals([guid, "Top Group 1", hash], results)


    @inlineCallbacks
    def test_externalAssignments(self):

        store = self.storeUnderTest()
        txn = store.newTransaction()

        oldExternalAssignments = (yield txn.externalDelegates())
        self.assertEquals(oldExternalAssignments, {})

        newAssignments = {
            UUID("3BDCB954-84D5-4F6D-8035-EAC19A6D6E1F"):
            (None, UUID("49B350C6-9611-477B-94D9-5516B13856AB"))
        }
        yield self.groupCacher.applyExternalAssignments(txn, newAssignments)
        oldExternalAssignments = (yield txn.externalDelegates())
        self.assertEquals(
            oldExternalAssignments,
            {
                UUID("3BDCB954-84D5-4F6D-8035-EAC19A6D6E1F"):
                (
                    None,
                    UUID("49B350C6-9611-477B-94D9-5516B13856AB")
                )
            }
        )

        newAssignments = {
            UUID("7D45CB10-479E-456B-B54D-528958C5734B"):
            (
                UUID("86144F73-345A-4097-82F1-B782672087C7"),
                None
            ),
            UUID("3BDCB954-84D5-4F6D-8035-EAC19A6D6E1F"):
            (
                UUID("86144F73-345A-4097-82F1-B782672087C7"),
                UUID("49B350C6-9611-477B-94D9-5516B13856AB")
            ),
        }
        yield self.groupCacher.applyExternalAssignments(txn, newAssignments)
        oldExternalAssignments = (yield txn.externalDelegates())
        self.assertEquals(
            oldExternalAssignments,
            {
                UUID('3bdcb954-84d5-4f6d-8035-eac19a6d6e1f'):
                (
                    UUID('86144f73-345a-4097-82f1-b782672087c7'),
                    UUID('49b350c6-9611-477b-94d9-5516b13856ab')
                ),
                UUID('7d45cb10-479e-456b-b54d-528958c5734b'):
                (
                    UUID('86144f73-345a-4097-82f1-b782672087c7'),
                    None
                )
            }
        )

        allGroupDelegates = (yield txn.allGroupDelegates())
        self.assertEquals(
            allGroupDelegates,
            set(
                [
                    UUID('49b350c6-9611-477b-94d9-5516b13856ab'),
                    UUID('86144f73-345a-4097-82f1-b782672087c7')
                ]
            )
        )

        # Fault in the read-only group
        yield self.groupCacher.refreshGroup(txn, UUID('86144f73-345a-4097-82f1-b782672087c7'))

        # Wilfredo should have Sagen and Daboo as read-only delegates
        delegates = (yield txn.delegates(
            UUID("3BDCB954-84D5-4F6D-8035-EAC19A6D6E1F"), False)
        )
        self.assertEquals(
            delegates,
            set(
                [
                    UUID('4ad155cb-ae9b-475f-986c-e08a7537893e'),
                    UUID('7d45cb10-479e-456b-b54d-528958c5734b')
                ]
            )
        )

        # Fault in the read-write group
        yield self.groupCacher.refreshGroup(txn, UUID('49b350c6-9611-477b-94d9-5516b13856ab'))

        # Wilfredo should have 4 users as read-write delegates
        delegates = (yield txn.delegates(
            UUID("3BDCB954-84D5-4F6D-8035-EAC19A6D6E1F"), True)
        )
        self.assertEquals(
            delegates,
            set(
                [
                    UUID('3bdcb954-84d5-4f6d-8035-eac19a6d6e1f'),
                    UUID('4ad155cb-ae9b-475f-986c-e08a7537893e'),
                    UUID('7d45cb10-479e-456b-b54d-528958c5734b'),
                    UUID('9064df91-1dbc-4e07-9c2b-6839b0953876')
                ]
            )
        )


        #
        # Now, remove some external assignments
        #
        newAssignments = {
            UUID("3BDCB954-84D5-4F6D-8035-EAC19A6D6E1F"):
            (
                UUID("86144F73-345A-4097-82F1-B782672087C7"),
                None
            ),
        }
        yield self.groupCacher.applyExternalAssignments(txn, newAssignments)
        oldExternalAssignments = (yield txn.externalDelegates())
        self.assertEquals(
            oldExternalAssignments,
            {
                UUID('3bdcb954-84d5-4f6d-8035-eac19a6d6e1f'):
                (
                    UUID('86144f73-345a-4097-82f1-b782672087c7'),
                    None
                ),
            }
        )

        allGroupDelegates = (yield txn.allGroupDelegates())
        self.assertEquals(
            allGroupDelegates,
            set(
                [
                    UUID('86144f73-345a-4097-82f1-b782672087c7')
                ]
            )
        )

        # Wilfredo should have Sagen and Daboo as read-only delegates
        delegates = (yield txn.delegates(
            UUID("3BDCB954-84D5-4F6D-8035-EAC19A6D6E1F"), False)
        )
        self.assertEquals(
            delegates,
            set(
                [
                    UUID('4ad155cb-ae9b-475f-986c-e08a7537893e'),
                    UUID('7d45cb10-479e-456b-b54d-528958c5734b')
                ]
            )
        )

        # Wilfredo should have no read-write delegates
        delegates = (yield txn.delegates(
            UUID("3BDCB954-84D5-4F6D-8035-EAC19A6D6E1F"), True)
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
                    UUID('86144f73-345a-4097-82f1-b782672087c7')
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
    <guid>3BDCB954-84D5-4F6D-8035-EAC19A6D6E1F</guid>
    <short-name>wsanchez</short-name>
    <short-name>wilfredo_sanchez</short-name>
    <full-name>Wilfredo Sanchez</full-name>
    <password>zehcnasw</password>
    <email>wsanchez@bitbucket.calendarserver.org</email>
    <email>wsanchez@devnull.twistedmatrix.com</email>
  </record>

  <record type="user">
    <uid>__glyph__</uid>
    <guid>9064DF91-1DBC-4E07-9C2B-6839B0953876</guid>
    <short-name>glyph</short-name>
    <full-name>Glyph Lefkowitz</full-name>
    <password>hpylg</password>
    <email>glyph@bitbucket.calendarserver.org</email>
    <email>glyph@devnull.twistedmatrix.com</email>
  </record>

  <record type="user">
    <uid>__sagen__</uid>
    <guid>4AD155CB-AE9B-475F-986C-E08A7537893E</guid>
    <short-name>sagen</short-name>
    <full-name>Morgen Sagen</full-name>
    <password>negas</password>
    <email>sagen@bitbucket.calendarserver.org</email>
    <email>shared@example.com</email>
  </record>

  <record type="user">
    <uid>__cdaboo__</uid>
    <guid>7D45CB10-479E-456B-B54D-528958C5734B</guid>
    <short-name>cdaboo</short-name>
    <full-name>Cyrus Daboo</full-name>
    <password>suryc</password>
    <email>cdaboo@bitbucket.calendarserver.org</email>
  </record>

  <record type="user">
    <uid>__dre__</uid>
    <guid>CFC88493-DBFF-42B9-ADC7-9B3DA0B0769B</guid>
    <short-name>dre</short-name>
    <full-name>Andre LaBranche</full-name>
    <password>erd</password>
    <email>dre@bitbucket.calendarserver.org</email>
    <email>shared@example.com</email>
  </record>

  <record type="group">
    <uid>__top_group_1__</uid>
    <guid>49B350C6-9611-477B-94D9-5516B13856AB</guid>
    <short-name>top-group-1</short-name>
    <full-name>Top Group 1</full-name>
    <email>topgroup1@example.com</email>
    <member-uid>__wsanchez__</member-uid>
    <member-uid>__glyph__</member-uid>
    <member-uid>__sub_group_1__</member-uid>
  </record>

  <record type="group">
    <uid>__sub_group_1__</uid>
    <guid>86144F73-345A-4097-82F1-B782672087C7</guid>
    <short-name>sub-group-1</short-name>
    <full-name>Sub Group 1</full-name>
    <email>subgroup1@example.com</email>
    <member-uid>__sagen__</member-uid>
    <member-uid>__cdaboo__</member-uid>
  </record>

</directory>
"""
