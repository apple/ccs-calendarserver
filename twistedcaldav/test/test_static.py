##
# Copyright (c) 2008 Apple Inc. All rights reserved.
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

from twisted.trial.unittest import TestCase

from twistedcaldav.static import CalendarHomeFile, CalDAVFile
from twistedcaldav.cache import CacheChangeNotifier
from twistedcaldav.test.util import StubCacheChangeNotifier

class StubParentResource(object):
    def principalCollections(self):
        return set([])


class CalendarHomeFileTests(TestCase):
    def setUp(self):
        self.calendarHome = CalendarHomeFile(self.mktemp(),
                                             StubParentResource(),
                                             object())


    def test_hasCacheNotifier(self):
        self.failUnless(isinstance(self.calendarHome.cacheNotifier,
                                   CacheChangeNotifier))


    def test_childrenHaveCacheNotifier(self):
        child = self.calendarHome.createSimilarFile('/fake/path')
        self.assertEquals(child.cacheNotifier, self.calendarHome.cacheNotifier)


class CalDAVFileTests(TestCase):
    def setUp(self):
        self.caldavFile = CalDAVFile(self.mktemp())
        self.caldavFile.fp.createDirectory()
        self.caldavFile.cacheNotifier = StubCacheChangeNotifier()
        self.assertEquals(self.caldavFile.cacheNotifier.changedCount, 0)
        self.caldavFile.isCollection = (lambda: True)


    def test_updateCTagNotifiesCache(self):
        self.caldavFile.updateCTag()
        self.assertEquals(self.caldavFile.cacheNotifier.changedCount, 1)


    def test_updateCTagDoesntFailWithoutACacheNotifier(self):
        del self.caldavFile.cacheNotifier
        self.caldavFile.updateCTag()
