# -*- test-case-name: txdav.carddav.datastore.test -*-
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
from twisted.trial.unittest import TestCase
from twext.python.clsprop import classproperty
from twisted.internet.defer import inlineCallbacks

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
