##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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

from twext.python.filepath import CachingFilePath as FilePath
from twisted.trial import unittest

from twext.python.vcomponent import VComponent

from txdav.common.icommondatastore import HomeChildNameNotAllowedError
from txdav.common.icommondatastore import ObjectResourceNameNotAllowedError
from txdav.common.icommondatastore import ObjectResourceUIDAlreadyExistsError
from txdav.common.icommondatastore import NoSuchHomeChildError
from txdav.common.icommondatastore import NoSuchObjectResourceError

from txcaldav.calendarstore.file import CalendarStore, CalendarHome
from txcaldav.calendarstore.file import Calendar, CalendarObject

from txcaldav.calendarstore.test.common import (
    CommonTests, event4_text, event1modified_text, StubNotifierFactory)

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

    test.notifierFactory = StubNotifierFactory()
    test.calendarStore = CalendarStore(storeRootPath, test.notifierFactory)
    test.txn = test.calendarStore.newTransaction()
    assert test.calendarStore is not None, "No calendar store?"



def setUpHome1(test):
    setUpCalendarStore(test)
    test.home1 = test.txn.calendarHomeWithUID("home1")
    assert test.home1 is not None, "No calendar home?"



def setUpCalendar1(test):
    setUpHome1(test)
    test.calendar1 = test.home1.calendarWithName("calendar_1")
    assert test.calendar1 is not None, "No calendar?"



class CalendarStoreTest(unittest.TestCase):
    """
    Test cases for L{CalendarStore}.
    """

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

    def setUp(self):
        setUpHome1(self)


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

    def setUp(self):
        setUpCalendar1(self)


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


    def test_useIndexImmediately(self):
        """
        L{Calendar._index} is usable in the same transaction it is created, with
        a temporary filename.
        """
        self.home1.createCalendarWithName("calendar2")
        calendar = self.home1.calendarWithName("calendar2")
        index = calendar._index
        self.assertEquals(set(index.calendarObjects()),
                          set(calendar.calendarObjects()))
        self.txn.commit()
        self.txn = self.calendarStore.newTransaction()
        self.home1 = self.txn.calendarHomeWithUID("home1")
        calendar = self.home1.calendarWithName("calendar2")
        # FIXME: we should be curating our own index here, but in order to fix
        # that the code in the old implicit scheduler needs to change.  This
        # test would be more effective if there were actually some objects in
        # this list.
        index = calendar._index
        self.assertEquals(set(index.calendarObjects()),
                          set(calendar.calendarObjects()))


    def test_calendarObjectWithName_dot(self):
        """
        Filenames starting with "." are reserved by this
        implementation, so no calendar object names may start with
        ".".
        """
        name = ".foo.ics"
        self.home1._path.child(name).touch()
        self.assertEquals(self.calendar1.calendarObjectWithName(name), None)


    @featureUnimplemented
    def test_calendarObjectWithUID_exists(self):
        """
        Find existing calendar object by name.
        """
        calendarObject = self.calendar1.calendarObjectWithUID("1")
        self.failUnless(
            isinstance(calendarObject, CalendarObject),
            calendarObject
        )
        self.assertEquals(
            calendarObject.component(),
            self.calendar1.calendarObjectWithName("1.ics").component()
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
            ".foo", VComponent.fromString(event4_text)
        )


    @featureUnimplemented
    def test_createCalendarObjectWithName_uidconflict(self):
        """
        Attempt to create a calendar object with a conflicting UID
        should raise.
        """
        name = "foo.ics"
        assert self.calendar1.calendarObjectWithName(name) is None
        component = VComponent.fromString(event1modified_text)
        self.assertRaises(
            ObjectResourceUIDAlreadyExistsError,
            self.calendar1.createCalendarObjectWithName,
            name, component
        )


    def test_removeCalendarObject_delayedEffect(self):
        """
        Removing a calendar object should not immediately remove the underlying
        file; it should only be removed upon commit() of the transaction.
        """
        self.calendar1.removeCalendarObjectWithName("2.ics")
        self.failUnless(self.calendar1._path.child("2.ics").exists())
        self.txn.commit()
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


    def _refresh(self):
        """
        Re-read the (committed) home1 and calendar1 objects in a new
        transaction.
        """
        self.txn = self.calendarStore.newTransaction()
        self.home1 = self.txn.calendarHomeWithUID("home1")
        self.calendar1 = self.home1.calendarWithName("calendar_1")


    def test_undoCreateCalendarObject(self):
        """
        If a calendar object is created as part of a transaction, it will be
        removed if that transaction has to be aborted.
        """
        # Make sure that the calendar home is actually committed; rolling back
        # calendar home creation will remove the whole directory.
        self.txn.commit()
        self._refresh()
        self.calendar1.createCalendarObjectWithName(
            "sample.ics",
            VComponent.fromString(event4_text)
        )
        self._refresh()
        self.assertIdentical(
            self.calendar1.calendarObjectWithName("sample.ics"),
            None
        )


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
        self._refresh()


    def test_undoModifyCalendarObject(self):
        """
        If an existing calendar object is modified as part of a transaction, it
        should be restored to its previous status if the transaction aborts.
        """
        originalComponent = self.calendar1.calendarObjectWithName(
            "1.ics").component()
        self.calendar1.calendarObjectWithName("1.ics").setComponent(
            VComponent.fromString(event1modified_text)
        )
        # Sanity check.
        self.assertEquals(
            self.calendar1.calendarObjectWithName("1.ics").component(),
            VComponent.fromString(event1modified_text)
        )
        self.doThenUndo()
        self.assertEquals(
            self.calendar1.calendarObjectWithName("1.ics").component(),
            originalComponent
        )


    def test_modifyCalendarObjectCaches(self):
        """
        Modifying a calendar object should cache the modified component in
        memory, to avoid unnecessary parsing round-trips.
        """
        modifiedComponent = VComponent.fromString(event1modified_text)
        self.calendar1.calendarObjectWithName("1.ics").setComponent(
            modifiedComponent
        )
        self.assertIdentical(
            modifiedComponent,
            self.calendar1.calendarObjectWithName("1.ics").component()
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
    def setUp(self):
        setUpCalendar1(self)
        self.object1 = self.calendar1.calendarObjectWithName("1.ics")


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

    def storeUnderTest(self):
        """
        Create and return a L{CalendarStore} for testing.
        """
        setUpCalendarStore(self)
        return self.calendarStore


    def test_init(self):
        """
        L{CalendarStore} has a C{_path} attribute which refers to its
        constructor argument.
        """
        self.assertEquals(self.storeUnderTest()._path,
                          self.storeRootPath)


    def test_calendarObjectsWithDotFile(self):
        """
        Adding a dotfile to the calendar home should not increase
        """
        self.homeUnderTest()._path.child(".foo").createDirectory()
        self.test_calendarObjects()

