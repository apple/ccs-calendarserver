# -*- test-case-name: txdav.caldav.datastore.test.test_scheduling -*-
##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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
from zope.interface.declarations import implements
from txdav.caldav.icalendarstore import ICalendarHome, ICalendar, ICalendarObject, \
    ICalendarTransaction, ICalendarStore

from twisted.python.util import FancyEqMixin
from twisted.python.components import proxyForInterface
from twisted.internet.defer import inlineCallbacks, returnValue



class ImplicitTransaction(
        proxyForInterface(ICalendarTransaction,
                          originalAttribute="_transaction")):
    """
    Wrapper around an L{ICalendarStoreTransaction}.
    """

    def __init__(self, transaction):
        """
        Initialize an L{ImplicitTransaction}.

        @type transaction: L{ICalendarStoreTransaction}
        """
        self._transaction = transaction


    @inlineCallbacks
    def calendarHomeWithUID(self, uid, create=False):
        # FIXME: 'create' flag
        newHome = yield super(ImplicitTransaction, self).calendarHomeWithUID(uid, create)
#        return ImplicitCalendarHome(newHome, self)
        if newHome is None:
            returnValue(None)
        else:
            # FIXME: relay transaction
            returnValue(ImplicitCalendarHome(newHome, None))



class ImplicitCalendarHome(proxyForInterface(ICalendarHome, "_calendarHome")):

    implements(ICalendarHome)

    def __init__(self, calendarHome, transaction):
        """
        Initialize L{ImplicitCalendarHome} with an underlying
        calendar home and L{ImplicitTransaction}.
        """
        self._calendarHome = calendarHome
        self._transaction = transaction


#    def properties(self):
#        # FIXME: wrap?
#        return self._calendarHome.properties()

    @inlineCallbacks
    def calendars(self):
        superCalendars = (yield super(ImplicitCalendarHome, self).calendars())
        wrapped = []
        for calendar in superCalendars:
            wrapped.append(ImplicitCalendar(self, calendar))
        returnValue(wrapped)


    @inlineCallbacks
    def loadCalendars(self):
        superCalendars = (yield super(ImplicitCalendarHome, self).loadCalendars())
        wrapped = []
        for calendar in superCalendars:
            wrapped.append(ImplicitCalendar(self, calendar))
        returnValue(wrapped)


    def createCalendarWithName(self, name):
        self._calendarHome.createCalendarWithName(name)


    def removeCalendarWithName(self, name):
        self._calendarHome.removeCalendarWithName(name)


    @inlineCallbacks
    def calendarWithName(self, name):
        calendar = yield self._calendarHome.calendarWithName(name)
        if calendar is not None:
            returnValue(ImplicitCalendar(self, calendar))
        else:
            returnValue(None)


    def hasCalendarResourceUIDSomewhereElse(self, uid, ok_object, type):
        return self._calendarHome.hasCalendarResourceUIDSomewhereElse(uid, ok_object, type)


    def getCalendarResourcesForUID(self, uid):
        return self._calendarHome.getCalendarResourcesForUID(uid)



class ImplicitCalendarObject(object):
    implements(ICalendarObject)

    def setComponent(self, component):
        pass


    def component(self):
        pass


    def uid(self):
        pass


    def componentType(self):
        pass


    def organizer(self):
        pass


    def properties(self):
        pass



class ImplicitCalendar(FancyEqMixin,
                       proxyForInterface(ICalendar, "_subCalendar")):

    compareAttributes = (
        "_subCalendar",
        "_parentHome",
    )

    def __init__(self, parentHome, subCalendar):
        self._parentHome = parentHome
        self._subCalendar = subCalendar
        self._supportedComponents = None

#    def ownerCalendarHome(self):
#        return self._parentHome
#    def calendarObjects(self):
#        # FIXME: wrap
#        return self._subCalendar.calendarObjects()
#    def calendarObjectWithUID(self, uid): ""
#    def createCalendarObjectWithName(self, name, component):
#        # FIXME: implement most of StoreCalendarObjectResource here!
#        self._subCalendar.createCalendarObjectWithName(name, component)
#    def syncToken(self): ""
#    def calendarObjectsInTimeRange(self, start, end, timeZone): ""
#    def calendarObjectsSinceToken(self, token): ""
#    def properties(self):
#        # FIXME: probably need to wrap this as well
#        return self._subCalendar.properties()
#
#    def calendarObjectWithName(self, name):
#        #FIXME: wrap
#        return self._subCalendar.calendarObjectWithName(name)


    def _createCalendarObjectWithNameInternal(self, name, component, internal_state, options=None):
        return self.createCalendarObjectWithName(name, component, options)


    def setSupportedComponents(self, supported_components):
        """
        Update the database column with the supported components. Technically this should only happen once
        on collection creation, but for migration we may need to change after the fact - hence a separate api.
        """
        self._supportedComponents = supported_components


    def getSupportedComponents(self):
        return self._supportedComponents



class ImplicitStore(proxyForInterface(ICalendarStore, "_calendarStore")):
    """
    This is a wrapper around an L{ICalendarStore} that implements implicit
    scheduling.
    """

    def __init__(self, calendarStore):
        """
        Create an L{ImplicitStore} wrapped around another
        L{ICalendarStore} provider.
        """
        self._calendarStore = calendarStore


    def newTransaction(self, label="unlabeled"):
        """
        Wrap an underlying L{ITransaction}.
        """
        return ImplicitTransaction(self._calendarStore.newTransaction(label))
