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
from twisted.internet.defer import inlineCallbacks

from twext.who.idirectory import FieldName as BaseFieldName
from twext.who.expression import MatchExpression, MatchType
from twext.who.index import DirectoryService, DirectoryRecord
from twext.who.test import test_directory
from twext.who.test.test_directory import RecordStorage



def noLoadDirectoryService(superClass):
    class NoLoadDirectoryService(superClass):
        def loadRecords(self):
            pass

    return NoLoadDirectoryService


# class StubDirectoryService(DirectoryService):
#     """
#     Stub directory service with some built-in records and an implementation
#     of C{recordsFromNonCompoundExpression}.
#     """

#     def __init__(self):
#         DirectoryService.__init__(self, u"Stub")

#         self.records = RecordStorage(self, DirectoryRecord)



class BaseDirectoryServiceTest(test_directory.BaseDirectoryServiceTest):
    """
    Tests for indexed directory services.
    """

    def noLoadServicePopulated(self):
        service = self.service(
            subClass=noLoadDirectoryService(self.serviceClass)
        )

        records = RecordStorage(service, DirectoryRecord)
        service.indexRecords(records)
        service.records = records

        return service

    def test_indexRecords_positive(self):
        """
        L{DirectoryService.indexRecords} ensures all record data is in the
        index.
        """
        service = self.noLoadServicePopulated()
        index = service.index

        # Verify that the fields that should be indexed are, in fact, indexed
        # for each record.
        for record in service.records:
            for fieldName in service.indexedFields:
                values = record.fields.get(fieldName, None)

                if values is None:
                    continue

                if not BaseFieldName.isMultiValue(fieldName):
                    values = (values,)

                for value in values:
                    self.assertIn(fieldName, index)
                    self.assertIn(value, index[fieldName])

                    indexedRecords = index[fieldName][value]
                    self.assertIn(record, indexedRecords)


    def test_indexRecords_negative(self):
        """
        L{DirectoryService.indexRecords} does not have extra data in the index.
        """
        service = self.noLoadServicePopulated()
        index = service.index

        # Verify that all data in the index cooresponds to the records passed
        # in.
        for fieldName, fieldIndex in index.iteritems():
            for fieldValue, records in fieldIndex.iteritems():
                for record in records:
                    self.assertIn(fieldName, record.fields)
                    values = record.fields[fieldName]

                    if not BaseFieldName.isMultiValue(fieldName):
                        values = (values,)

                    self.assertIn(fieldValue, values)


    def test_flush(self):
        """
        C{flush} empties the index.
        """
        service = self.noLoadServicePopulated()

        self.assertFalse(emptyIndex(service.index))  # Test the test
        service.flush()
        self.assertTrue(emptyIndex(service.index))


    @inlineCallbacks
    def _test_indexedRecordsFromMatchExpression(self, inOut, matchType):
        service = self.noLoadServicePopulated()

        for subString, uids in (inOut):
            records = yield service.indexedRecordsFromMatchExpression(
                MatchExpression(
                    service.fieldName.shortNames, subString,
                    matchType
                )
            )
            self.assertEquals(
                set((record.uid for record in records)),
                set(uids)
            )


    def test_indexedRecordsFromMatchExpression_startsWith(self):
        """
        L{DirectoryService.indexedRecordsFromMatchExpression} with a startsWith
        expression.
        """
        return self._test_indexedRecordsFromMatchExpression(
            (
                (u"w", (u"__wsanchez__",)),           # Duplicates
                (u"dr", (u"__dre__", u"__dreid__")),  # Multiple
                (u"sage", (u"__sagen__",)),           # Single
            ),
            MatchType.startsWith
        )


    def test_indexedRecordsFromMatchExpression_contains(self):
        """
        L{DirectoryService.indexedRecordsFromMatchExpression} with a contains
        expression.
        """
        return self._test_indexedRecordsFromMatchExpression(
            (
                (u"sanch", (u"__wsanchez__",)),       # Duplicates
                (u"dr", (u"__dre__", u"__dreid__")),  # Multiple
                (u"agen", (u"__sagen__",)),           # Single
            ),
            MatchType.contains
        )


    def test_indexedRecordsFromMatchExpression_equals(self):
        """
        L{DirectoryService.indexedRecordsFromMatchExpression} with an equals
        expression.
        """
        return self._test_indexedRecordsFromMatchExpression(
            (
                (u"wsanchez", (u"__wsanchez__",)),  # MultiValue
                (u"dre", (u"__dre__",)),            # Single value
            ),
            MatchType.equals
        )


    def test_unIndexedRecordsFromMatchExpression(self):
        """
        L{DirectoryService.unIndexedRecordsFromMatchExpression} ...
        """
        raise NotImplementedError()

    test_unIndexedRecordsFromMatchExpression.todo = "Unimplemented"


    def test_recordsFromNonCompoundExpression(self):
        """
        L{DirectoryService.recordsFromNonCompoundExpression} ...
        """
        raise NotImplementedError()

    test_recordsFromNonCompoundExpression.todo = "Unimplemented"



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
        self.assertTrue(emptyIndex(service._index))


    def test_index_get(self):
        """
        Getting the C{index} property calls C{loadRecords}.
        """
        class TestService(DirectoryService):
            loaded = False

            def loadRecords(self):
                self.loaded = True

        service = TestService(u"")
        service.index
        self.assertTrue(service.loaded)


    def test_loadRecords(self):
        """
        L{DirectoryService.loadRecords} raises C{NotImplementedError}.
        """
        service = self.service()
        self.assertRaises(NotImplementedError, service.loadRecords)


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
        Does nothing.
        """


    test_members_group = _noop
    test_memberships = _noop



def emptyIndex(index):
    """
    Determine whether an index is empty.

    @param index: An index.
    @type index: L{dict}

    @return: true if C{index} is empty, otherwise false.
    """
    if not index:
        return True

    for fieldName, fieldIndex in index.iteritems():
        for fieldValue, records in fieldIndex.iteritems():
            for record in records:
                return False

    return True
