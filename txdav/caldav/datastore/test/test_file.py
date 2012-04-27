##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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
File calendar store tests.
"""

# FIXME: all test cases in this file aside from FileStorageTests should be
# deleted and replaced with either implementation-specific methods on
# FileStorageTests, or implementation-agnostic methods on CommonTests.

from twisted.trial import unittest
from twisted.internet.defer import inlineCallbacks

from twext.python.filepath import CachingFilePath as FilePath

from twext.python.vcomponent import VComponent

from txdav.common.icommondatastore import HomeChildNameNotAllowedError
from txdav.common.icommondatastore import ObjectResourceNameNotAllowedError
from txdav.common.icommondatastore import ObjectResourceUIDAlreadyExistsError
from txdav.common.icommondatastore import NoSuchHomeChildError
from txdav.common.icommondatastore import NoSuchObjectResourceError

from txdav.caldav.datastore.file import CalendarStore, CalendarHome
from txdav.caldav.datastore.file import Calendar, CalendarObject

from txdav.common.datastore.test.util import deriveQuota
from txdav.caldav.datastore.test.common import (
    CommonTests, test_event_text, event1modified_text)

storePath = FilePath(__file__).parent().child("calendar_store")

def _todo(f, why):
    f.todo = why
    return f



featureUnimplemented = lambda f: _todo(f, "Feature unimplemented")
testUnimplemented = lambda f: _todo(f, "Test unimplemented")
todo = lambda why: lambda f: _todo(f, why)



def setUpCalendarStore(test):
    test.root = FilePath(test.mktemp())
    test.root.createDirectory()

    storeRootPath = test.storeRootPath = test.root.child("store")
    calendarPath = storeRootPath.child("calendars").child("__uids__")
    calendarPath.parent().makedirs()
    storePath.copyTo(calendarPath)

    testID = test.id()
    test.calendarStore = CalendarStore(storeRootPath, test.notifierFactory,
                                       quota=deriveQuota(test))
    test.txn = test.calendarStore.newTransaction(testID + "(old)")
    assert test.calendarStore is not None, "No calendar store?"



@inlineCallbacks
def setUpHome1(test):
    setUpCalendarStore(test)
    test.home1 = yield test.txn.calendarHomeWithUID("home1")
    assert test.home1 is not None, "No calendar home?"



@inlineCallbacks
def setUpCalendar1(test):
    yield setUpHome1(test)
    test.calendar1 = yield test.home1.calendarWithName("calendar_1")
    assert test.calendar1 is not None, "No calendar?"



class CalendarStoreTest(unittest.TestCase):
    """
    Test cases for L{CalendarStore}.
    """

    notifierFactory = None

    def setUp(self):
        setUpCalendarStore(self)


    def test_calendarHomeWithUID_dot(self):
        """
        Filenames starting with "." are reserved by this
        implementation, so no UIDs may start with ".".
        """
        self.assertEquals(
            self.calendarStore.newTransaction().calendarHomeWithUID("xyzzy"),
            None
        )



class CalendarHomeTest(unittest.TestCase):

    notifierFactory = None
    def setUp(self):
        return setUpHome1(self)


    def test_init(self):
        """
        L{CalendarHome} has C{_path} and L{_calendarStore} attributes,
        indicating its location on disk and parent store, respectively.
        """
        self.failUnless(
            isinstance(self.home1._path, FilePath),
            self.home1._path
        )
        self.assertEquals(
            self.home1._calendarStore,
            self.calendarStore
        )


    def test_calendarWithName_dot(self):
        """
        Filenames starting with "." are reserved by this
        implementation, so no calendar names may start with ".".
        """
        name = ".foo"
        self.home1._path.child(name).createDirectory()
        self.assertEquals(self.home1.calendarWithName(name), None)


    def test_createCalendarWithName_dot(self):
        """
        Filenames starting with "." are reserved by this
        implementation, so no calendar names may start with ".".
        """
        self.assertRaises(
            HomeChildNameNotAllowedError,
            self.home1.createCalendarWithName, ".foo"
        )


    def test_removeCalendarWithName_dot(self):
        """
        Filenames starting with "." are reserved by this
        implementation, so no calendar names may start with ".".
        """
        name = ".foo"
        self.home1._path.child(name).createDirectory()
        self.assertRaises(
            NoSuchHomeChildError,
            self.home1.removeCalendarWithName, name
        )



class CalendarTest(unittest.TestCase):

    notifierFactory = None

    def setUp(self):
        return setUpCalendar1(self)


    def test_init(self):
        """
        L{Calendar.__init__} sets private attributes to reflect its constructor
        arguments.
        """
        self.failUnless(
            isinstance(self.calendar1._path, FilePath),
            self.calendar1
        )
        self.failUnless(
            isinstance(self.calendar1._calendarHome, CalendarHome),
            self.calendar1._calendarHome
        )


    @inlineCallbacks
    def test_useIndexImmediately(self):
        """
        L{Calendar._index} is usable in the same transaction it is created, with
        a temporary filename.
        """
        self.home1.createCalendarWithName("calendar2")
        calendar = yield self.home1.calendarWithName("calendar2")
        index = calendar._index
        yield self.assertEquals(set((yield index.calendarObjects())),
                                set((yield calendar.calendarObjects())))
        yield self.txn.commit()
        self.txn = self.calendarStore.newTransaction()
        self.home1 = yield self.txn.calendarHomeWithUID("home1")
        calendar = yield self.home1.calendarWithName("calendar2")
        # FIXME: we should be curating our own index here, but in order to fix
        # that the code in the old implicit scheduler needs to change.  This
        # test would be more effective if there were actually some objects in
        # this list.
        index = calendar._index
        self.assertEquals(set((yield index.calendarObjects())),
                          set((yield calendar.calendarObjects())))


    @inlineCallbacks
    def test_calendarObjectWithName_dot(self):
        """
        Filenames starting with "." are reserved by this
        implementation, so no calendar object names may start with
        ".".
        """
        name = ".foo.ics"
        self.home1._path.child(name).touch()
        self.assertEquals(
            (yield self.calendar1.calendarObjectWithName(name)),
            None)


    @featureUnimplemented
    @inlineCallbacks
    def test_calendarObjectWithUID_exists(self):
        """
        Find existing calendar object by name.
        """
        calendarObject = yield self.calendar1.calendarObjectWithUID("1")
        self.failUnless(
            isinstance(calendarObject, CalendarObject),
            calendarObject
        )
        self.assertEquals(
            calendarObject.component(),
            (yield self.calendar1.calendarObjectWithName("1.ics")).component()
        )


    def test_createCalendarObjectWithName_dot(self):
        """
        Filenames starting with "." are reserved by this
        implementation, so no calendar object names may start with
        ".".
        """
        self.assertRaises(
            ObjectResourceNameNotAllowedError,
            self.calendar1.createCalendarObjectWithName,
            ".foo", VComponent.fromString(test_event_text)
        )


    @featureUnimplemented
    @inlineCallbacks
    def test_createCalendarObjectWithName_uidconflict(self):
        """
        Attempt to create a calendar object with a conflicting UID
        should raise.
        """
        name = "foo.ics"
        assert (yield self.calendar1.calendarObjectWithName(name)) is None
        component = VComponent.fromString(event1modified_text)
        self.assertRaises(
            ObjectResourceUIDAlreadyExistsError,
            self.calendar1.createCalendarObjectWithName,
            name, component
        )


    @inlineCallbacks
    def test_removeCalendarObject_delayedEffect(self):
        """
        Removing a calendar object should not immediately remove the underlying
        file; it should only be removed upon commit() of the transaction.
        """
        self.calendar1.removeCalendarObjectWithName("2.ics")
        self.failUnless(self.calendar1._path.child("2.ics").exists())
        yield self.txn.commit()
        self.failIf(self.calendar1._path.child("2.ics").exists())


    def test_removeCalendarObjectWithName_dot(self):
        """
        Filenames starting with "." are reserved by this
        implementation, so no calendar object names may start with
        ".".
        """
        name = ".foo"
        self.calendar1._path.child(name).touch()
        self.assertRaises(
            NoSuchObjectResourceError,
            self.calendar1.removeCalendarObjectWithName, name
        )


    counter = 0
    @inlineCallbacks
    def _refresh(self):
        """
        Re-read the (committed) home1 and calendar1 objects in a new
        transaction.
        """
        self.counter += 1
        self.txn = self.calendarStore.newTransaction(
            self.id() + " (old #" + str(self.counter) + ")"
        )
        self.home1 = yield self.txn.calendarHomeWithUID("home1")
        self.calendar1 = yield self.home1.calendarWithName("calendar_1")


    @inlineCallbacks
    def test_undoCreateCalendarObject(self):
        """
        If a calendar object is created as part of a transaction, it will be
        removed if that transaction has to be aborted.
        """
        # Make sure that the calendar home is actually committed; rolling back
        # calendar home creation will remove the whole directory.
        yield self.txn.commit()
        yield self._refresh()
        self.calendar1.createCalendarObjectWithName(
            "sample.ics",
            VComponent.fromString(test_event_text)
        )
        yield self.txn.abort()
        yield self._refresh()
        self.assertIdentical(
            (yield self.calendar1.calendarObjectWithName("sample.ics")),
            None
        )
        yield self.txn.commit()


    @inlineCallbacks
    def doThenUndo(self):
        """
        Commit the current transaction, but add an operation that will cause it
        to fail at the end.  Finally, refresh all attributes with a new
        transaction so that further operations can be performed in a valid
        context.
        """
        def fail():
            raise RuntimeError("oops")
        self.txn.addOperation(fail, "dummy failing operation")
        self.assertRaises(RuntimeError, self.txn.commit)
        yield self._refresh()


    @inlineCallbacks
    def test_undoModifyCalendarObject(self):
        """
        If an existing calendar object is modified as part of a transaction, it
        should be restored to its previous status if the transaction aborts.
        """
        originalComponent = yield self.calendar1.calendarObjectWithName(
            "1.ics").component()
        (yield self.calendar1.calendarObjectWithName("1.ics")).setComponent(
            VComponent.fromString(event1modified_text)
        )
        # Sanity check.
        self.assertEquals(
            (yield self.calendar1.calendarObjectWithName("1.ics")).component(),
            VComponent.fromString(event1modified_text)
        )
        yield self.doThenUndo()
        self.assertEquals(
            (yield self.calendar1.calendarObjectWithName("1.ics")).component(),
            originalComponent
        )


    @featureUnimplemented
    def test_removeCalendarObjectWithUID_absent(self):
        """
        Attempt to remove an non-existing calendar object should raise.
        """
        self.assertRaises(
            NoSuchObjectResourceError,
            self.calendar1.removeCalendarObjectWithUID, "xyzzy"
        )


    @testUnimplemented
    def test_syncToken(self):
        """
        Sync token is correct.
        """
        raise NotImplementedError()


    @testUnimplemented
    def test_calendarObjectsInTimeRange(self):
        """
        Find calendar objects occuring in a given time range.
        """
        raise NotImplementedError()


    @testUnimplemented
    def test_calendarObjectsSinceToken(self):
        """
        Find calendar objects that have been modified since a given
        sync token.
        """
        raise NotImplementedError()



class CalendarObjectTest(unittest.TestCase):
    notifierFactory = None

    @inlineCallbacks
    def setUp(self):
        yield setUpCalendar1(self)
        self.object1 = yield self.calendar1.calendarObjectWithName("1.ics")


    def test_init(self):
        """
        L{CalendarObject} has instance attributes, C{_path} and C{_calendar},
        which refer to its position in the filesystem and the calendar in which
        it is contained, respectively.
        """ 
        self.failUnless(
            isinstance(self.object1._path, FilePath),
            self.object1._path
        )
        self.failUnless(
            isinstance(self.object1._calendar, Calendar),
            self.object1._calendar
        )


    def test_componentType(self):
        """
        Component type is correct.
        """
        self.assertEquals(self.object1.componentType(), "VEVENT")



class FileStorageTests(CommonTests, unittest.TestCase):
    """
    File storage tests.
    """

    calendarStore = None

    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        if self.calendarStore is None:
            setUpCalendarStore(self)
        return self.calendarStore


    def test_shareWith(self):
        """
        Overridden to be skipped.
        """

    test_shareWith.skip = "Not implemented for file store yet."


    def test_init(self):
        """
        L{CalendarStore} has a C{_path} attribute which refers to its
        constructor argument.
        """
        self.assertEquals(self.storeUnderTest()._path,
                          self.storeRootPath)


    @inlineCallbacks
    def test_calendarObjectsWithDotFile(self):
        """
        Adding a dotfile to the calendar home should not increase the number of
        calendar objects discovered.
        """
        (yield self.homeUnderTest())._path.child(".foo").createDirectory()
        yield self.test_calendarObjects()


    @inlineCallbacks
    def test_calendarObjectsWithDirectory(self):
        """
        If a directory appears (even a non-hidden one) within a calendar, it
        should not show up in the directory listing.
        """
        ((yield self.calendarUnderTest())._path.child("not-a-calendar-object")
         .createDirectory())
        yield self.test_calendarObjects()


    def test_simpleHomeSyncToken(self):
        """
        File store doesn't have a functioning C{resourceNamesSinceToken} for
        L{CalendarHome}.
        """

    test_simpleHomeSyncToken.skip = "Not in file store."

    def test_calendarObjectMetaData(self):
        pass
    test_calendarObjectMetaData.skip = "Example file data has no xattrs"

    def test_notificationSyncToken(self):
        """
        File store doesn't have a functioning C{resourceNamesSinceToken} for
        L{Notifications}.
        """

    test_notificationSyncToken.skip = "Not in file store."
