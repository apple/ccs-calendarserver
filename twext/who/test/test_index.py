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
from twisted.internet.defer import inlineCallbacks, returnValue

from twext.who.idirectory import FieldName as BaseFieldName
from twext.who.idirectory import QueryNotSupportedError
from twext.who.expression import MatchExpression, MatchType
from twext.who.index import DirectoryService, DirectoryRecord
from twext.who.test import test_directory
from twext.who.test.test_directory import RecordStorage



def noLoadDirectoryService(superClass):
    """
    Creates an indexed directory service that has a no-op implementation of
    L{DirectoryService.loadRecords}.

    @param superClass: The superclass of the new service.
    @type superClass: subclass of L{DirectoryService}

    @return: A new directory service class.
    @rtype: subclass of C{superClass}
    """
    assert issubclass(superClass, DirectoryService)

    class NoLoadDirectoryService(superClass):
        def loadRecords(self):
            pass

        def indexedRecordsFromMatchExpression(self, *args, **kwargs):
            self._calledIndexed = True
            return superClass.indexedRecordsFromMatchExpression(
                self, *args, **kwargs
            )

        def unIndexedRecordsFromMatchExpression(self, *args, **kwargs):
            self._calledUnindexed = True
            return superClass.unIndexedRecordsFromMatchExpression(
                self, *args, **kwargs
            )

    return NoLoadDirectoryService


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
    def _test_indexedRecordsFromMatchExpression(
        self, inOut, matchType, fieldName=BaseFieldName.shortNames,
    ):
        service = self.noLoadServicePopulated()

        for subString, uids in (inOut):
            records = yield service.indexedRecordsFromMatchExpression(
                MatchExpression(
                    fieldName, subString,
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


    def test_indexedRecordsFromMatchExpression_notIndexed(self):
        """
        L{DirectoryService.indexedRecordsFromMatchExpression} with an
        unindexed field name.
        """
        result = self._test_indexedRecordsFromMatchExpression(
            (
                (u"zehcnasw", (u"__wsanchez__",)),
            ),
            MatchType.equals,
            fieldName=BaseFieldName.password
        )
        self.assertFailure(result, TypeError)


    def test_indexedRecordsFromMatchExpression_notMatchExpression(self):
        """
        L{DirectoryService.indexedRecordsFromMatchExpression} with a
        non-match expression.
        """
        result = self._test_indexedRecordsFromMatchExpression(
            (
                (u"zehcnasw", (u"__wsanchez__",)),
            ),
            "Not a match type we know about"
        )
        self.assertFailure(result, NotImplementedError)


    @inlineCallbacks
    def _test_unIndexedRecordsFromMatchExpression(
        self, inOut, matchType, fieldName=BaseFieldName.fullNames,
    ):
        service = self.noLoadServicePopulated()

        for subString, uids in (inOut):
            records = yield service.unIndexedRecordsFromMatchExpression(
                MatchExpression(
                    fieldName, subString,
                    matchType
                )
            )
            self.assertEquals(
                set((record.uid for record in records)),
                set(uids)
            )


    def test_unIndexedRecordsFromMatchExpression_startsWith(self):
        """
        L{DirectoryService.unIndexedRecordsFromMatchExpression} with a
        startsWith expression.
        """
        return self._test_unIndexedRecordsFromMatchExpression(
            (
                (u"Wilfredo", (u"__wsanchez__",)),    # Duplicates
                (u"A", (u"__alyssa__", u"__dre__")),  # Multiple
                (u"Andre", (u"__dre__",)),            # Single
            ),
            MatchType.startsWith
        )


    def test_unIndexedRecordsFromMatchExpression_contains(self):
        """
        L{DirectoryService.unIndexedRecordsFromMatchExpression} with a contains
        expression.
        """
        return self._test_unIndexedRecordsFromMatchExpression(
            (
                (u"Sanchez", (u"__wsanchez__",)),     # Duplicates
                (u"A", (u"__alyssa__", u"__dre__")),  # Multiple
                (u"LaBra", (u"__dre__",)),            # Single
            ),
            MatchType.contains
        )


    def test_unIndexedRecordsFromMatchExpression_equals(self):
        """
        L{DirectoryService.unIndexedRecordsFromMatchExpression} with an equals
        expression.
        """
        return self._test_unIndexedRecordsFromMatchExpression(
            (
                (u"Wilfredo Sanchez", (u"__wsanchez__",)),  # MultiValue
                (u"Andre LaBranche", (u"__dre__",)),        # Single value
            ),
            MatchType.equals
        )


    def test_unIndexedRecordsFromMatchExpression_indexed(self):
        """
        L{DirectoryService.unIndexedRecordsFromMatchExpression} with an
        indexed field name.
        """
        self._test_unIndexedRecordsFromMatchExpression(
            (
                (u"wsanchez", (u"__wsanchez__",)),
            ),
            MatchType.equals,
            fieldName=BaseFieldName.shortNames
        )


    def test_unIndexedRecordsFromMatchExpression_notMatchExpression(self):
        """
        L{DirectoryService.unIndexedRecordsFromMatchExpression} with a
        non-match expression.
        """
        result = self._test_unIndexedRecordsFromMatchExpression(
            (
                (u"zehcnasw", (u"__wsanchez__",)),
            ),
            "Not a match type we know about"
        )
        self.assertFailure(result, NotImplementedError)


    @inlineCallbacks
    def _test_recordsFromNonCompoundExpression(self, expression):
        service = self.noLoadServicePopulated()
        yield service.recordsFromNonCompoundExpression(expression)
        returnValue(service)


    @inlineCallbacks
    def test_recordsFromNonCompoundExpression_match_indexed(self):
        """
        L{DirectoryService.recordsFromNonCompoundExpression} with a
        L{MatchExpression} for an indexed field calls
        L{DirectoryRecord.indexedRecordsFromMatchExpression}.
        """
        service = yield self._test_recordsFromNonCompoundExpression(
            MatchExpression(BaseFieldName.shortNames, u"...")
        )
        self.assertTrue(getattr(service, "_calledIndexed", False))
        self.assertFalse(getattr(service, "_calledUnindexed", False))


    @inlineCallbacks
    def test_recordsFromNonCompoundExpression_match_unindexed(self):
        """
        L{DirectoryService.recordsFromNonCompoundExpression} with a
        L{MatchExpression} for an unindexed field calls
        L{DirectoryRecord.unIndexedRecordsFromMatchExpression}.
        """
        service = yield self._test_recordsFromNonCompoundExpression(
            MatchExpression(BaseFieldName.password, u"...")
        )
        self.assertFalse(getattr(service, "_calledIndexed", False))
        self.assertTrue(getattr(service, "_calledUnindexed", False))


    def test_recordsFromNonCompoundExpression_unknown(self):
        """
        L{DirectoryService.recordsFromNonCompoundExpression} with a
        an unknown expression calls superclass, which will result in a
        L{QueryNotSupportedError}.
        """
        result = self._test_recordsFromNonCompoundExpression(object())
        self.assertFailure(result, QueryNotSupportedError)



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
