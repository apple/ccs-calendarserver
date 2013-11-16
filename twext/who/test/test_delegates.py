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

from twext.who.delegates import (
    addDelegate, removeDelegate, delegatesOf, delegatedTo, allGroupDelegates
)
from twext.who.groups import GroupCacher
from twext.who.idirectory import RecordType
from twext.who.test.test_xml import xmlService
from twisted.internet.defer import inlineCallbacks
from twistedcaldav.test.util import StoreTestCase
from uuid import UUID

class DelegationTest(StoreTestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(DelegationTest, self).setUp()
        self.xmlService = xmlService(self.mktemp(), xmlData=testXMLConfig)
        self.groupCacher = GroupCacher(
            None,
            self.xmlService,
            None,
            0
        )


    @inlineCallbacks
    def test_directDelegation(self):
        store = self.storeUnderTest()
        txn = store.newTransaction()

        delegator = yield self.xmlService.recordWithUID("__wsanchez__")
        delegate1 = yield self.xmlService.recordWithUID("__sagen__")
        delegate2 = yield self.xmlService.recordWithUID("__cdaboo__")

        # Add 1 delegate
        yield addDelegate(txn, delegator, delegate1, True)
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals(["sagen"], [d.shortNames[0] for d in delegates])
        delegators = (yield delegatedTo(txn, delegate1, True))
        self.assertEquals(["wsanchez"], [d.shortNames[0] for d in delegators])

        # Add another delegate
        yield addDelegate(txn, delegator, delegate2, True)
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals(set(["sagen", "cdaboo"]),
            set([d.shortNames[0] for d in delegates]))
        delegators = (yield delegatedTo(txn, delegate2, True))
        self.assertEquals(["wsanchez"], [d.shortNames[0] for d in delegators])

        # Remove 1 delegate
        yield removeDelegate(txn, delegator, delegate1, True)
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals(["cdaboo"], [d.shortNames[0] for d in delegates])
        delegators = (yield delegatedTo(txn, delegate1, True))
        self.assertEquals(0, len(delegators))

        # Remove the other delegate
        yield removeDelegate(txn, delegator, delegate2, True)
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals(0, len(delegates))
        delegators = (yield delegatedTo(txn, delegate2, True))
        self.assertEquals(0, len(delegators))


    @inlineCallbacks
    def test_indirectDelegation(self):
        store = self.storeUnderTest()
        txn = store.newTransaction()

        delegator = yield self.xmlService.recordWithUID("__wsanchez__")
        delegate1 = yield self.xmlService.recordWithUID("__sagen__")
        group1 = yield self.xmlService.recordWithUID("__top_group_1__")
        group2 = yield self.xmlService.recordWithUID("__sub_group_1__")

        # Add group delegate, but before the group membership has been
        # pulled in
        yield addDelegate(txn, delegator, group1, True)
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals(0, len(delegates))

        # Now refresh the group and there will be 3 delegates (contained
        # within 2 nested groups)
        # guid = "49b350c69611477b94d95516b13856ab"
        yield self.groupCacher.refreshGroup(txn, group1.guid)
        yield self.groupCacher.refreshGroup(txn, group2.guid)
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals(set(["sagen", "cdaboo", "glyph"]),
            set([d.shortNames[0] for d in delegates]))
        delegators = (yield delegatedTo(txn, delegate1, True))
        self.assertEquals(["wsanchez"], [d.shortNames[0] for d in delegators])

        # Verify we can ask for all delegated-to groups
        yield addDelegate(txn, delegator, group2, True)
        groups = (yield allGroupDelegates(txn))
        self.assertEquals(
            set([
                UUID("49b350c69611477b94d95516b13856ab"),
                UUID("86144f73345a409782f1b782672087c7")
                ]), set(groups))

        # Delegate to a user who is already indirectly delegated-to
        yield addDelegate(txn, delegator, delegate1, True)
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals(set(["sagen", "cdaboo", "glyph"]),
            set([d.shortNames[0] for d in delegates]))

        # Add a member to the group; they become a delegate
        newSet = set()
        for name in ("wsanchez", "cdaboo", "sagen", "glyph", "dre"):
            record = (yield self.xmlService.recordWithShortName(RecordType.user,
                name))
            newSet.add(record.guid)
        groupID, name, membershipHash = (yield txn.groupByGUID(group1.guid)) #@UnusedVariable
        numAdded, numRemoved = (yield self.groupCacher.synchronizeMembers(txn, #@UnusedVariable
            groupID, newSet))
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals(set(["sagen", "cdaboo", "glyph", "dre"]),
            set([d.shortNames[0] for d in delegates]))

        # Remove delegate access from the top group
        yield removeDelegate(txn, delegator, group1, True)
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals(set(["sagen", "cdaboo"]),
            set([d.shortNames[0] for d in delegates]))

        # Remove delegate access from the sub group
        yield removeDelegate(txn, delegator, group2, True)
        delegates = (yield delegatesOf(txn, delegator, True))
        self.assertEquals(set(["sagen"]),
            set([d.shortNames[0] for d in delegates]))



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
