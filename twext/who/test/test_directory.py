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
Generic directory service base implementation tests.
"""

from uuid import UUID
from textwrap import dedent

from zope.interface.verify import verifyObject, BrokenMethodImplementation

from twisted.python.constants import Names, NamedConstant
from twisted.trial import unittest
from twisted.trial.unittest import SkipTest
from twisted.internet.defer import inlineCallbacks
from twisted.internet.defer import succeed

from twext.who.idirectory import QueryNotSupportedError, NotAllowedError
from twext.who.idirectory import RecordType, FieldName
from twext.who.idirectory import IDirectoryService, IDirectoryRecord
from twext.who.idirectory import Operand
from twext.who.expression import CompoundExpression
from twext.who.directory import DirectoryService, DirectoryRecord


class ServiceMixIn(object):
    """
    MixIn that sets up a service appropriate for testing.
    """
    realmName = u"xyzzy"


    def service(self):
        if not hasattr(self, "_service"):
            self._service = DirectoryService(self.realmName)
        return self._service



class BaseDirectoryServiceTest(ServiceMixIn):
    """
    Tests for directory services.
    """

    def test_interface(self):
        """
        Service instance conforms to L{IDirectoryService}.
        """
        service = self.service()
        try:
            verifyObject(IDirectoryService, service)
        except BrokenMethodImplementation as e:
            self.fail(e)


    def test_init(self):
        """
        Test initialization.
        """
        service = self.service()
        self.assertEquals(service.realmName, self.realmName)


    def test_repr(self):
        """
        C{repr} returns the expected string.
        """
        service = self.service()
        self.assertEquals(repr(service), "<DirectoryService u'xyzzy'>")


    def test_recordTypes(self):
        """
        C{recordTypes} returns the supported set of record types.
        For L{DirectoryService}, that's the set of constants in the
        C{recordType} attribute.
        """
        service = self.service()
        self.assertEquals(
            set(service.recordTypes()),
            set(service.recordType.iterconstants())
        )


    def test_recordsFromNonCompoundExpression_unknownExpression(self):
        """
        C{recordsFromNonCompoundExpression} with an unknown expression type
        fails with L{QueryNotSupportedError}.
        """
        service = self.service()
        self.assertFailure(
            service.recordsFromNonCompoundExpression(object()),
            QueryNotSupportedError
        )


    @inlineCallbacks
    def test_recordsFromNonCompoundExpression_emptyRecords(self):
        """
        C{recordsFromNonCompoundExpression} with an unknown expression type
        and an empty C{records} set returns an empty result.
        """
        service = self.service()
        result = (
            yield service.recordsFromNonCompoundExpression(
                object(), records=()
            )
        )
        self.assertEquals(set(result), set(()))


    def test_recordsFromNonCompoundExpression_nonEmptyRecords(self):
        """
        C{recordsFromNonCompoundExpression} with an unknown expression type
        and a non-empty C{records} fails with L{QueryNotSupportedError}.
        """
        service = self.service()

        wsanchez = DirectoryRecord(
            service,
            {
                service.fieldName.recordType: service.recordType.user,
                service.fieldName.uid: u"__wsanchez__",
                service.fieldName.shortNames: [u"wsanchez"],
            }
        )

        self.assertFailure(
            service.recordsFromNonCompoundExpression(
                object(), records=((wsanchez,))
            ),
            QueryNotSupportedError
        )


    def test_recordsFromExpression_unknownExpression(self):
        """
        C{recordsFromExpression} with an unknown expression type fails with
        L{QueryNotSupportedError}.
        """
        service = self.service()
        result = yield(service.recordsFromExpression(object()))
        self.assertFailure(result, QueryNotSupportedError)


    @inlineCallbacks
    def test_recordsFromExpression_emptyExpression(self):
        """
        C{recordsFromExpression} with an unknown expression type and an empty
        L{CompoundExpression} returns an empty result.
        """
        service = self.service()

        for operand in Operand.iterconstants():
            result = yield(service.recordsFromExpression(
                CompoundExpression((), operand)
            ))
            self.assertEquals(set(result), set(()))


    def _unimplemented(self):
        """
        Unimplemented test.
        """
        raise NotImplementedError("Subclasses should implement this test.")


    test_recordWithUID = _unimplemented
    test_recordWithGUID = _unimplemented
    test_recordsWithRecordType = _unimplemented
    test_recordWithShortName = _unimplemented
    test_recordsWithEmailAddress = _unimplemented


    def test_updateRecordsEmpty(self):
        """
        Updating no records is not an error.
        """
        service = self.service()
        for create in (True, False):
            service.updateRecords((), create=create),


    def test_removeRecordsEmpty(self):
        """
        Removing no records is allowed.
        """
        service = self.service()

        service.removeRecords(())



class DirectoryServiceTest(unittest.TestCase, BaseDirectoryServiceTest):
    @inlineCallbacks
    def test_recordsFromExpression_single(self):
        """
        C{recordsFromExpression} handles a single expression
        """
        service = StubDirectoryService()

        result = yield service.recordsFromExpression("twistedmatrix.com")

        self.assertEquals(
            set((
                u"__wsanchez__",
                u"__glyph__",
                u"__exarkun__",
                u"__dreid__",
            )),
            set((record.uid for record in result))
        )


    @inlineCallbacks
    def test_recordsFromExpression_OR(self):
        """
        C{recordsFromExpression} handles a L{CompoundExpression} with
        L{Operand.OR}.
        """
        service = StubDirectoryService()

        result = yield service.recordsFromExpression(
            CompoundExpression(
                (
                    u"twistedmatrix.com",
                    u"calendarserver.org",
                ),
                Operand.OR
            )
        )

        self.assertEquals(
            set((
                u"__wsanchez__",
                u"__glyph__",
                u"__sagen__",
                u"__cdaboo__",
                u"__dre__",
                u"__exarkun__",
                u"__dreid__",
            )),
            set((record.uid for record in result))
        )


    @inlineCallbacks
    def test_recordsFromExpression_AND(self):
        """
        C{recordsFromExpression} handles a L{CompoundExpression} with
        L{Operand.AND}.
        """
        service = StubDirectoryService()

        result = yield service.recordsFromExpression(
            CompoundExpression(
                (
                    u"twistedmatrix.com",
                    u"calendarserver.org",
                ),
                Operand.AND
            )
        )

        self.assertEquals(
            set((
                u"__wsanchez__",
                u"__glyph__",
            )),
            set((record.uid for record in result))
        )


    @inlineCallbacks
    def test_recordsFromExpression_AND_optimized(self):
        """
        C{recordsFromExpression} handles a L{CompoundExpression} with
        L{Operand.AND}, and when one of the expression matches no records, the
        subsequent expressions are skipped.
        """
        service = StubDirectoryService()

        result = yield service.recordsFromExpression(
            CompoundExpression(
                (
                    u"twistedmatrix.com",
                    u"None",
                    u"calendarserver.org",
                ),
                Operand.AND
            )
        )

        self.assertEquals(
            set(()),
            set((record.uid for record in result))
        )

        self.assertEquals(
            [u"twistedmatrix.com", u"None"],
            service.seenExpressions
        )


    def test_recordsFromExpression_unknownOperand(self):
        """
        C{recordsFromExpression} fails with L{QueryNotSupportedError} when
        given a L{CompoundExpression} with an unknown operand.
        """
        service = StubDirectoryService()

        results = service.recordsFromExpression(
            CompoundExpression(
                (
                    u"twistedmatrix.com",
                    u"calendarserver.org",
                ),
                WackyOperand.WHUH
            )
        )

        self.assertFailure(results, QueryNotSupportedError)


    def test_recordWithUID(self):
        """
        C{recordWithUID} fails with L{QueryNotSupportedError}.
        """
        service = self.service()

        self.assertFailure(
            service.recordWithUID(u""),
            QueryNotSupportedError
        )


    def test_recordWithGUID(self):
        """
        C{recordWithGUID} fails with L{QueryNotSupportedError}.
        """
        service = self.service()

        self.assertFailure(
            service.recordWithGUID(UUID(int=0)),
            QueryNotSupportedError
        )


    def test_recordsWithRecordType(self):
        """
        C{recordsWithRecordType} fails with L{QueryNotSupportedError}.
        """
        service = self.service()

        for recordType in RecordType.iterconstants():
            self.assertFailure(
                service.recordsWithRecordType(recordType),
                QueryNotSupportedError
            )


    def test_recordWithShortName(self):
        """
        C{recordWithShortName} fails with L{QueryNotSupportedError}.
        """
        service = self.service()

        for recordType in RecordType.iterconstants():
            self.assertFailure(
                service.recordWithShortName(recordType, u""),
                QueryNotSupportedError
            )


    def test_recordsWithEmailAddress(self):
        """
        C{recordsWithEmailAddress} fails with L{QueryNotSupportedError}.
        """
        service = self.service()

        self.assertFailure(
            service.recordsWithEmailAddress("a@b"),
            QueryNotSupportedError
        )



class BaseDirectoryServiceImmutableTest(ServiceMixIn):
    """
    Immutable directory record tests.
    """

    def test_updateRecordsNotAllowed(self):
        """
        Updating records is not allowed.
        """
        service = self.service()

        newRecord = DirectoryRecord(
            service,
            fields={
                service.fieldName.uid: u"__plugh__",
                service.fieldName.recordType: service.recordType.user,
                service.fieldName.shortNames: (u"plugh",),
            }
        )

        for create in (True, False):
            self.assertFailure(
                service.updateRecords((newRecord,), create=create),
                NotAllowedError,
            )


    def test_removeRecordsNotAllowed(self):
        """
        Removing records is not allowed.
        """
        service = self.service()

        self.assertFailure(
            service.removeRecords((u"foo",)),
            NotAllowedError,
        )



class DirectoryServiceImmutableTest(
    unittest.TestCase,
    BaseDirectoryServiceImmutableTest,
):
    pass



class BaseDirectoryRecordTest(ServiceMixIn):
    fields_wsanchez = {
        FieldName.uid: u"UID:wsanchez",
        FieldName.recordType: RecordType.user,
        FieldName.shortNames: (u"wsanchez", u"wilfredo_sanchez"),
        FieldName.fullNames: (
            u"Wilfredo Sanchez",
            u"Wilfredo Sanchez Vega",
        ),
        FieldName.emailAddresses: (
            u"wsanchez@calendarserver.org",
            u"wsanchez@example.com",
        )
    }

    fields_glyph = {
        FieldName.uid: u"UID:glyph",
        FieldName.recordType: RecordType.user,
        FieldName.shortNames: (u"glyph",),
        FieldName.fullNames: (u"Glyph Lefkowitz",),
        FieldName.emailAddresses: (u"glyph@calendarserver.org",)
    }

    fields_sagen = {
        FieldName.uid: u"UID:sagen",
        FieldName.recordType: RecordType.user,
        FieldName.shortNames: (u"sagen",),
        FieldName.fullNames: (u"Morgen Sagen",),
        FieldName.emailAddresses: (u"sagen@CalendarServer.org",)
    }

    fields_nobody = {
        FieldName.uid: u"UID:nobody",
        FieldName.recordType: RecordType.user,
        FieldName.shortNames: (u"nobody",),
    }

    fields_staff = {
        FieldName.uid: u"UID:staff",
        FieldName.recordType: RecordType.group,
        FieldName.shortNames: (u"staff",),
        FieldName.fullNames: (u"Staff",),
        FieldName.emailAddresses: (u"staff@CalendarServer.org",)
    }


    def makeRecord(self, fields=None, service=None):
        """
        Create a directory record from fields and a service.

        @param fields: Record fields.
        @type fields: L{dict} with L{FieldName} keys

        @param service: Directory service.
        @type service: L{DirectoryService}

        @return: A directory record.
        @rtype: L{DirectoryRecord}
        """
        if fields is None:
            fields = self.fields_wsanchez
        if service is None:
            service = self.service()
        return DirectoryRecord(service, fields)


    def test_interface(self):
        """
        L{DirectoryRecord} complies with L{IDirectoryRecord}.
        """
        record = self.makeRecord()
        try:
            verifyObject(IDirectoryRecord, record)
        except BrokenMethodImplementation as e:
            self.fail(e)


    def test_init(self):
        """
        L{DirectoryRecord} initialization sets service and fields.
        """
        service  = self.service()
        wsanchez = self.makeRecord(self.fields_wsanchez, service=service)

        self.assertEquals(wsanchez.service, service)
        self.assertEquals(wsanchez.fields, self.fields_wsanchez)


    def test_initWithNoUID(self):
        """
        Directory records must have a UID.
        """
        fields = self.fields_wsanchez.copy()
        del fields[FieldName.uid]
        self.assertRaises(ValueError, self.makeRecord, fields)

        fields = self.fields_wsanchez.copy()
        fields[FieldName.uid] = u""
        self.assertRaises(ValueError, self.makeRecord, fields)


    def test_initWithNoRecordType(self):
        """
        Directory records must have a record type.
        """
        fields = self.fields_wsanchez.copy()
        del fields[FieldName.recordType]
        self.assertRaises(ValueError, self.makeRecord, fields)

        fields = self.fields_wsanchez.copy()
        fields[FieldName.recordType] = None
        self.assertRaises(ValueError, self.makeRecord, fields)


    def test_initWithBogusRecordType(self):
        """
        Directory records must have a known record type.
        """
        fields = self.fields_wsanchez.copy()
        fields[FieldName.recordType] = object()
        self.assertRaises(ValueError, self.makeRecord, fields)


    def test_initWithNoShortNames(self):
        """
        Directory records must have a short name.
        """
        fields = self.fields_wsanchez.copy()
        del fields[FieldName.shortNames]
        self.assertRaises(ValueError, self.makeRecord, fields)

        fields = self.fields_wsanchez.copy()
        fields[FieldName.shortNames] = ()
        self.assertRaises(ValueError, self.makeRecord, fields)

        fields = self.fields_wsanchez.copy()
        fields[FieldName.shortNames] = (u"",)
        self.assertRaises(ValueError, self.makeRecord, fields)

        fields = self.fields_wsanchez.copy()
        fields[FieldName.shortNames] = (u"wsanchez", u"")
        self.assertRaises(ValueError, self.makeRecord, fields)


    def test_initNormalizeEmailLowercase(self):
        """
        Email addresses are normalized to lowercase.
        """
        sagen = self.makeRecord(self.fields_sagen)

        self.assertEquals(
            sagen.fields[FieldName.emailAddresses],
            (u"sagen@calendarserver.org",)
        )


    def test_repr(self):
        """
        C{repr} returns the expected string.
        """
        wsanchez = self.makeRecord(self.fields_wsanchez)

        self.assertEquals(
            "<DirectoryRecord (user)wsanchez>",
            repr(wsanchez)
        )


    def test_compare(self):
        """
        Comparison of records.
        """
        fields_glyphmod = self.fields_glyph.copy()
        del fields_glyphmod[FieldName.emailAddresses]

        plugh = DirectoryService(u"plugh")

        wsanchez    = self.makeRecord(self.fields_wsanchez)
        wsanchezmod = self.makeRecord(self.fields_wsanchez, plugh)
        glyph       = self.makeRecord(self.fields_glyph)
        glyphmod    = self.makeRecord(fields_glyphmod)

        self.assertEquals(wsanchez, wsanchez)
        self.assertNotEqual(wsanchez, glyph)
        self.assertNotEqual(glyph, glyphmod)  # UID matches, other fields don't
        self.assertNotEqual(glyphmod, wsanchez)
        self.assertNotEqual(wsanchez, wsanchezmod)  # Different service


    def test_attributeAccess(self):
        """
        Fields can be accessed as attributes.
        """
        wsanchez = self.makeRecord(self.fields_wsanchez)

        self.assertEquals(
            wsanchez.recordType,
            wsanchez.fields[FieldName.recordType]
        )
        self.assertEquals(
            wsanchez.uid,
            wsanchez.fields[FieldName.uid]
        )
        self.assertEquals(
            wsanchez.shortNames,
            wsanchez.fields[FieldName.shortNames]
        )
        self.assertEquals(
            wsanchez.emailAddresses,
            wsanchez.fields[FieldName.emailAddresses]
        )

        self.assertRaises(AttributeError, lambda: wsanchez.fooBarBaz)

        nobody = self.makeRecord(self.fields_nobody)

        self.assertRaises(AttributeError, lambda: nobody.emailAddresses)


    def test_description(self):
        """
        C{description} returns the expected string.
        """
        sagen = self.makeRecord(self.fields_sagen)

        self.assertEquals(
            dedent(
                u"""
                DirectoryRecord:
                  UID = UID:sagen
                  record type = user
                  short names = (u'sagen',)
                  full names = (u'Morgen Sagen',)
                  email addresses = ('sagen@calendarserver.org',)
                """[1:]
            ),
            sagen.description()
        )


    def test_members_group(self):
        """
        Group members.
        """
        raise SkipTest("Subclasses should implement this test.")


    @inlineCallbacks
    def test_members_nonGroup(self):
        """
        Non-groups have no members.
        """
        wsanchez = self.makeRecord(self.fields_wsanchez)

        self.assertEquals(
            set((yield wsanchez.members())),
            set()
        )


    def test_groups(self):
        """
        Group memberships.
        """
        raise SkipTest("Subclasses should implement this test.")



class DirectoryRecordTest(unittest.TestCase, BaseDirectoryRecordTest):
    def test_members_group(self):
        staff = self.makeRecord(self.fields_staff)

        self.assertFailure(staff.members(), NotImplementedError)


    def test_groups(self):
        wsanchez = self.makeRecord(self.fields_wsanchez)

        self.assertFailure(wsanchez.groups(), NotImplementedError)



class StubDirectoryService(DirectoryService):
    """
    Stubn directory service with some built-in records and an implementation
    of C{recordsFromNonCompoundExpression}.
    """

    def __init__(self):
        DirectoryService.__init__(self, u"Stub")

        self.records = []
        self._addRecords()


    def _addRecords(self):
        """
        Add a known set of records to this service.
        """
        self._addUser(
            shortNames=[u"wsanchez", u"wilfredo_sanchez"],
            fullNames=[u"Wilfredo S\xe1nchez Vega"],
            emailAddresses=[
                u"wsanchez@bitbucket.calendarserver.org",
                u"wsanchez@devnull.twistedmatrix.com",
            ],
        )

        self._addUser(
            shortNames=[u"glyph"],
            fullNames=[u"Glyph Lefkowitz"],
            emailAddresses=[
                u"glyph@bitbucket.calendarserver.org",
                u"glyph@devnull.twistedmatrix.com",
            ],
        )

        self._addUser(
            shortNames=[u"sagen"],
            fullNames=[u"Morgen Sagen"],
            emailAddresses=[
                u"sagen@bitbucket.calendarserver.org",
                u"shared@example.com",
            ],
        )

        self._addUser(
            shortNames=[u"cdaboo"],
            fullNames=[u"Cyrus Daboo"],
            emailAddresses=[
                u"cdaboo@bitbucket.calendarserver.org",
            ],
        )

        self._addUser(
            shortNames=[u"dre"],
            fullNames=[u"Andre LaBranche"],
            emailAddresses=[
                u"dre@bitbucket.calendarserver.org",
                u"shared@example.com",
            ],
        )

        self._addUser(
            shortNames=[u"exarkun"],
            fullNames=[u"Jean-Paul Calderone"],
            emailAddresses=[
                u"exarkun@devnull.twistedmatrix.com",
            ],
        )

        self._addUser(
            shortNames=[u"dreid"],
            fullNames=[u"David Reid"],
            emailAddresses=[
                u"dreid@devnull.twistedmatrix.com",
            ],
        )

        self._addUser(
            shortNames=[u"joe"],
            fullNames=[u"Joe Schmoe"],
            emailAddresses=[
                u"joe@example.com",
            ],
        )

        self._addUser(
            shortNames=[u"alyssa"],
            fullNames=[u"Alyssa P. Hacker"],
            emailAddresses=[
                u"alyssa@example.com",
            ],
        )


    def _addUser(self, shortNames, fullNames, emailAddresses=[]):
        """
        Add a user record with the given field information.

        @param shortNames: Record short names.
        @type shortNames: L{list} of L{unicode}s

        @param fullNames: Record full names.
        @type fullNames: L{list} of L{unicode}s

        @param emailAddresses: Record email addresses.
        @type emailAddresses: L{list} of L{unicode}s
        """
        self.records.append(DirectoryRecord(self, {
            self.fieldName.recordType: self.recordType.user,
            self.fieldName.uid: u"__{0}__".format(shortNames[0]),
            self.fieldName.shortNames: shortNames,
            self.fieldName.fullNames: fullNames,
            self.fieldName.password: u"".join(reversed(shortNames[0])),
            self.fieldName.emailAddresses: emailAddresses,
        }))


    def recordsFromExpression(self, expression):
        self.seenExpressions = []

        return DirectoryService.recordsFromExpression(self, expression)


    def recordsFromNonCompoundExpression(self, expression, records=None):
        self.seenExpressions.append(expression)

        if expression == u"None":
            return succeed([])

        if expression in (u"twistedmatrix.com", u"calendarserver.org"):
            result = []
            for record in self.records:
                for email in record.emailAddresses:
                    if email.endswith(expression):
                        result.append(record)
                        break
            return succeed(result)

        return DirectoryService.recordsFromNonCompoundExpression(
            self, expression, records=records
        )


class WackyOperand(Names):
    """
    Wacky operands.
    """
    WHUH = NamedConstant()
