##
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

from twisted.trial.unittest import TestCase

from contrib.performance.loadtest.resources import Event, Calendar
class EventTests(TestCase):
    """
    Tests for L{Event}.
    """
    def test_uid(self):
        """
        When the C{vevent} attribute of an L{Event} instance is set,
        L{Event.getUID} returns the UID value from it.
        """
        event = Event(None, u'/foo/bar', u'etag', Component.fromString(EVENT))
        self.assertEquals(event.getUID(), EVENT_UID)


    def test_withoutUID(self):
        """
        When an L{Event} has a C{vevent} attribute set to C{None},
        L{Event.getUID} returns C{None}.
        """
        event = Event(None, u'/bar/baz', u'etag')
        self.assertIdentical(event.getUID(), None)
