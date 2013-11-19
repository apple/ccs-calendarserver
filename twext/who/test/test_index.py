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

from twext.who.directory import DirectoryService, DirectoryRecord

from twext.who.test import test_directory



class BaseDirectoryServiceTest(test_directory.BaseDirectoryServiceTest):
    """
    Tests for indexed directory services.
    """
    serviceClass = DirectoryService
    directoryRecordClass = DirectoryRecord



class DirectoryServiceTest(unittest.TestCase, BaseDirectoryServiceTest):
    def _noop(self):
        """
        Does nothing for this class.
        """
        if self.__class__ is not DirectoryServiceTest:
            raise NotImplementedError("Subclasses should implement this test.")


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
    serviceClass = DirectoryService
    directoryRecordClass = DirectoryRecord



class DirectoryServiceImmutableTest(
    unittest.TestCase, BaseDirectoryServiceImmutableTest
):
    pass



class BaseDirectoryRecordTest(test_directory.BaseDirectoryRecordTest):
    """
    Tests for indexed directory records.
    """
    serviceClass = DirectoryService
    directoryRecordClass = DirectoryRecord



class DirectoryRecordTest(unittest.TestCase, BaseDirectoryRecordTest):
    def _noop(self):
        """
        Does nothing for this class.
        """
        if self.__class__ is not DirectoryRecordTest:
            raise NotImplementedError("Subclasses should implement this test.")


    test_members_group = _noop
    test_memberships = _noop
