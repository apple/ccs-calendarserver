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

from twext.who.groups import GroupCacher, _expandedMembers
from twext.who.test.test_xml import xmlService
from twext.who.idirectory import RecordType
from twisted.internet.defer import inlineCallbacks
from twistedcaldav.test.util import StoreTestCase
from txdav.common.icommondatastore import NotFoundError

class GroupCacherTest(StoreTestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(GroupCacherTest, self).setUp()
        self.xmlService = xmlService(self.mktemp(), xmlData=testXMLConfig)
        self.groupCacher = GroupCacher(
            None,
            self.xmlService,
            None,
            0
        )


    @inlineCallbacks
    def test_expandedMembers(self):
        record = yield self.xmlService.recordWithUID("__top_group_1__")
        memberUIDs = set()
        for member in (yield _expandedMembers(record)):
            memberUIDs.add(member.uid)
        self.assertEquals(memberUIDs, set(["__cdaboo__",
            "__glyph__", "__sagen__", "__wsanchez__"]))

        record = yield self.xmlService.recordWithUID("__sagen__")
        members = yield _expandedMembers(record)
        self.assertEquals(0, len(list(members)))


    @inlineCallbacks
    def test_refreshGroup(self):
        """
        Verify refreshGroup() adds a group to the Groups table with the
        expected membership hash value and members
        """

        store = self.storeUnderTest()
        txn = store.newTransaction()

        guid = "49b350c69611477b94d95516b13856ab"
        yield self.groupCacher.refreshGroup(txn, guid)

        groupID, name, membershipHash = (yield txn.groupByGUID(guid))
        self.assertEquals(membershipHash, "e90052eb63d47f32d5b03df0073f7854")

        groupGUID, name, membershipHash = (yield txn.groupByID(groupID))
        self.assertEquals(groupGUID, guid)
        self.assertEquals(name, "Top Group 1")
        self.assertEquals(membershipHash, "e90052eb63d47f32d5b03df0073f7854")

        results = (yield txn.membersOfGroup(groupID))
        self.assertEquals(
            set(["9064df911dbc4e079c2b6839b0953876",
                 "4ad155cbae9b475f986ce08a7537893e",
                 "3bdcb95484d54f6d8035eac19a6d6e1f",
                 "7d45cb10479e456bb54d528958c5734b"]),
            set([r[0] for r in results])
        )

        records = (yield self.groupCacher.cachedMembers(txn, groupID))
        self.assertEquals(
            set([r.shortNames[0] for r in records]),
            set(["wsanchez", "cdaboo", "glyph", "sagen"])
        )


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
        guid = "49b350c69611477b94d95516b13856ab"
        yield self.groupCacher.refreshGroup(txn, guid)
        groupID, name, membershipHash = (yield txn.groupByGUID(guid))

        # Remove two members, and add one member
        newSet = set()
        for name in ("wsanchez", "cdaboo", "dre"):
            record = (yield self.xmlService.recordWithShortName(RecordType.user,
                name))
            newSet.add(record.guid)
        numAdded, numRemoved = (yield self.groupCacher.synchronizeMembers(txn,
            groupID, newSet))
        self.assertEquals(numAdded, 1)
        self.assertEquals(numRemoved, 2)
        records = (yield self.groupCacher.cachedMembers(txn, groupID))
        self.assertEquals(
            set([r.shortNames[0] for r in records]),
            set(["wsanchez", "cdaboo", "dre"])
        )

        # Remove all members
        numAdded, numRemoved = (yield self.groupCacher.synchronizeMembers(txn,
            groupID, set()))
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

        guid = "49b350c69611477b94d95516b13856ab"
        hash = "e90052eb63d47f32d5b03df0073f7854"
        yield self.groupCacher.refreshGroup(txn, guid)
        groupID, name, membershipHash = (yield txn.groupByGUID(guid))
        results = (yield txn.groupByID(groupID))
        self.assertEquals([guid, "Top Group 1", hash], results)


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
