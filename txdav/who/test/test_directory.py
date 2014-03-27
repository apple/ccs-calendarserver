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
Directory tests
"""

from twisted.internet.defer import inlineCallbacks
from twistedcaldav.test.util import StoreTestCase


class DirectoryTestCase(StoreTestCase):

    @inlineCallbacks
    def test_expandedMembers(self):

        record = yield self.directory.recordWithUID(u"both_coasts")

        direct = yield record.members()
        self.assertEquals(
            set([u"left_coast", u"right_coast"]),
            set([r.uid for r in direct])
        )

        expanded = yield record.expandedMembers()
        self.assertEquals(
            set([u"Chris Lecroy", u"Cyrus Daboo", u"David Reid", u"Wilfredo Sanchez"]),
            set([r.displayName for r in expanded])
        )
