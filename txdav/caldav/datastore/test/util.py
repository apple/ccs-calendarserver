# -*- test-case-name: txdav.carddav.datastore.test -*-
##
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
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
from twisted.internet.defer import inlineCallbacks
from twext.python.clsprop import classproperty
from twistedcaldav.ical import Component, normalize_iCalStr, diff_iCalStrs
from pycalendar.datetime import DateTime

"""
Store test utility functions
"""

from txdav.common.datastore.test.util import (
    CommonCommonTests, populateCalendarsFrom
)


class CommonStoreTests(CommonCommonTests, TestCase):

    @inlineCallbacks
    def setUp(self):
        yield super(CommonStoreTests, self).setUp()
        yield self.buildStoreAndDirectory()
        yield self.populate()


    @inlineCallbacks
    def populate(self):
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()


    @classproperty(cache=False)
    def requirements(cls): #@NoSelf
        return {
            "user01": {
                "calendar_1": {
                },
                "inbox": {
                },
            },
            "user02": {
                "calendar_1": {
                },
                "inbox": {
                },
            },
            "user03": {
                "calendar_1": {
                },
                "inbox": {
                },
            },
            "user04": {
                "calendar_1": {
                },
                "inbox": {
                },
            },
        }



class DateTimeSubstitutionsMixin(object):
    """
    Mix-in class for tests that defines a set of str.format() substitutions for date-time values
    relative to the current time. This allows tests to always use relative-to-now values rather
    than fixed values which may become in valid in the future (e.g., a test that needs an event
    in the future and uses 2017 works fine up until 2017 and then starts to fail.
    """

    def setupDateTimeValues(self):

        self.dtsubs = {}

        # Set of "now" values that are directly accessible
        self.now = DateTime.getNowUTC()
        self.now.setHHMMSS(0, 0, 0)
        self.now12 = DateTime.getNowUTC()
        self.now12.setHHMMSS(12, 0, 0)
        self.nowDate = self.now.duplicate()
        self.nowDate.setDateOnly(True)
        self.nowFloating = self.now.duplicate()
        self.nowFloating.setTimezoneID(None)

        self.dtsubs["now"] = self.now
        self.dtsubs["now12"] = self.now12
        self.dtsubs["nowDate"] = self.nowDate
        self.dtsubs["nowFloating"] = self.nowFloating

        # Values going 30 days back from now
        for i in range(30):
            attrname = "now_back%s" % (i + 1,)
            setattr(self, attrname, self.now.duplicate())
            getattr(self, attrname).offsetDay(-(i + 1))
            self.dtsubs[attrname] = getattr(self, attrname)

            attrname_12h = "now_back%s_12h" % (i + 1,)
            setattr(self, attrname_12h, getattr(self, attrname).duplicate())
            getattr(self, attrname_12h).offsetHours(12)
            self.dtsubs[attrname_12h] = getattr(self, attrname_12h)

            attrname_1 = "now_back%s_1" % (i + 1,)
            setattr(self, attrname_1, getattr(self, attrname).duplicate())
            getattr(self, attrname_1).offsetSeconds(-1)
            self.dtsubs[attrname_1] = getattr(self, attrname_1)

            attrname = "nowDate_back%s" % (i + 1,)
            setattr(self, attrname, self.nowDate.duplicate())
            getattr(self, attrname).offsetDay(-(i + 1))
            self.dtsubs[attrname] = getattr(self, attrname)

            attrname = "nowFloating_back%s" % (i + 1,)
            setattr(self, attrname, self.nowFloating.duplicate())
            getattr(self, attrname).offsetDay(-(i + 1))
            self.dtsubs[attrname] = getattr(self, attrname)

            attrname_1 = "nowFloating_back%s_1" % (i + 1,)
            setattr(self, attrname_1, getattr(self, attrname).duplicate())
            getattr(self, attrname_1).offsetSeconds(-1)
            self.dtsubs[attrname_1] = getattr(self, attrname_1)

        # Values going 30 days forward from now
        for i in range(30):
            attrname = "now_fwd%s" % (i + 1,)
            setattr(self, attrname, self.now.duplicate())
            getattr(self, attrname).offsetDay(i + 1)
            self.dtsubs[attrname] = getattr(self, attrname)

            attrname_12h = "now_fwd%s_12h" % (i + 1,)
            setattr(self, attrname_12h, getattr(self, attrname).duplicate())
            getattr(self, attrname_12h).offsetHours(12)
            self.dtsubs[attrname_12h] = getattr(self, attrname_12h)

            attrname = "nowDate_fwd%s" % (i + 1,)
            setattr(self, attrname, self.nowDate.duplicate())
            getattr(self, attrname).offsetDay(i + 1)
            self.dtsubs[attrname] = getattr(self, attrname)

            attrname = "nowFloating_fwd%s" % (i + 1,)
            setattr(self, attrname, self.nowFloating.duplicate())
            getattr(self, attrname).offsetDay(i + 1)
            self.dtsubs[attrname] = getattr(self, attrname)


    def assertEqualCalendarData(self, cal1, cal2):
        if isinstance(cal1, str):
            cal1 = Component.fromString(cal1)
        if isinstance(cal2, str):
            cal2 = Component.fromString(cal2)
        ncal1 = normalize_iCalStr(cal1)
        ncal2 = normalize_iCalStr(cal2)
        self.assertEqual(ncal1, ncal2, msg=diff_iCalStrs(ncal1, ncal2))
