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
Indexed directory service base implementation tests.
"""

from twisted.trial import unittest

from twext.who.index import DirectoryService, DirectoryRecord
from twext.who.test import test_directory



class NoLoadDirectoryService(DirectoryService):
    def loadRecords(self):
        pass



class BaseDirectoryServiceTest(test_directory.BaseDirectoryServiceTest):
    """
    Tests for indexed directory services.
    """



class DirectoryServiceTest(unittest.TestCase, BaseDirectoryServiceTest):
    """
    Tests for L{DirectoryService}.
    """
    serviceClass = DirectoryService
    directoryRecordClass = DirectoryRecord


    def test_init_noIndex(self):
        """
        Index starts as C{None}.
        """
        service = self.service()
        self.assertIdentical(service._index, None)


    def test_index_get(self):
        """
        Getting the C{index} property calls C{loadRecords} and returns the
        index set by C{loadRecords}.
        """
        class TestService(DirectoryService):
            def loadRecords(self):
                self.index = self.indexToLoad

        service = TestService(u"")

        for index in ({}, {}, {}):
            service.indexToLoad = index
            self.assertIdentical(service.index, index)


    def test_index_set(self):
        """
        Setting the index and getting it gives us back the same value.
        """
        service = NoLoadDirectoryService(u"")

        for index in ({}, {}, {}):
            service.index = index
            self.assertIdentical(service.index, index)


    def test_loadRecords(self):
        """
        L{DirectoryService.loadRecords} raises C{NotImplementedError}.
        """
        service = self.service()
        self.assertRaises(NotImplementedError, service.loadRecords)


    def test_flush(self):
        """
        C{flush} sets the index to C{None}.
        """
        service = NoLoadDirectoryService(u"")
        service._index = {}
        service.flush()
        self.assertIdentical(service._index, None)


    def _noop(self):
        """
        Does nothing.
        """


    test_recordWithUID = _noop
    test_recordWithGUID = _noop
    test_recordsWithRecordType = _noop
    test_recordWithShortName = _noop
    test_recordsWithEmailAddress = _noop



class BaseDirectoryServiceImmutableTest(
    test_directory.BaseDirectoryServiceImmutableTest
):
    """
    Tests for immutable indexed directory services.
    """



class DirectoryServiceImmutableTest(
    unittest.TestCase, BaseDirectoryServiceImmutableTest
):
    """
    Tests for immutable L{DirectoryService}.
    """
    serviceClass = DirectoryService
    directoryRecordClass = DirectoryRecord



class BaseDirectoryRecordTest(test_directory.BaseDirectoryRecordTest):
    """
    Tests for indexed directory records.
    """



class DirectoryRecordTest(unittest.TestCase, BaseDirectoryRecordTest):
    """
    Tests for L{DirectoryRecord}.
    """
    serviceClass = DirectoryService
    directoryRecordClass = DirectoryRecord

    def _noop(self):
        """
        Does nothing for this class.
        """
        if self.__class__ is not DirectoryRecordTest:
            raise NotImplementedError("Subclasses should implement this test.")


    test_members_group = _noop
    test_memberships = _noop
