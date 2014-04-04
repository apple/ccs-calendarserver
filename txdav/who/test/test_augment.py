##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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
Augment service tests
"""

from twisted.internet.defer import inlineCallbacks
from twistedcaldav.test.util import StoreTestCase
from txdav.who.groups import GroupCacher


class AugmentTest(StoreTestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(AugmentTest, self).setUp()
        self.groupCacher = GroupCacher(self.directory)


    @inlineCallbacks
    def test_groups(self):
        """
        Make sure augmented record groups( ) returns only the groups that have
        been refreshed.
        """

        store = self.storeUnderTest()

        txn = store.newTransaction()
        yield self.groupCacher.refreshGroup(txn, u"__top_group_1__")
        yield txn.commit()
        record = yield self.directory.recordWithUID(u"__sagen1__")
        groups = yield record.groups()
        self.assertEquals(
            set(["__top_group_1__"]),
            set([g.uid for g in groups])
        )

        txn = store.newTransaction()
        yield self.groupCacher.refreshGroup(txn, u"__sub_group_1__")
        yield txn.commit()

        record = yield self.directory.recordWithUID(u"__sagen1__")
        groups = yield record.groups()
        self.assertEquals(
            set(["__top_group_1__", "__sub_group_1__"]),
            set([g.uid for g in groups])
        )
