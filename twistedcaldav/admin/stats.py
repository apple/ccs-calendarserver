##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
Statisitcs Types:

    Overall Stats:
        # of accounts
        # of calendars
        # of events

"""

import os

from twistedcaldav.admin import util        

class StatsAction(object):
    def __init__(self, config):
        self.config = config
        self.formatter = self.config.parent.formatter
        self.root = self.config.parent.root
        self.calendarCollection = self.config.parent.calendarCollection
        self.principalCollection = self.config.parent.principalCollection
        
        self.calCount = 0
        self.eventCount = 0
        self.todoCount = 0

        self.gatherers = [
            self.getAccountCount,
            self.getGroupCount,
            self.getResourceCount,
            self.getLocationCount,
            self.getDiskUsage]

    def getDiskUsage(self):
        return ("diskUsage", 
                util.getDiskUsage(self.config, self.root))

    def getAccountCount(self):
        return ("accountCount", 
                len(util.getPrincipalList(
                    self.principalCollection,
                    'users')))

    def getGroupCount(self):
        return ("groupCount", 
                len(util.getPrincipalList(
                    self.principalCollection,
                    'groups')))

    def getResourceCount(self):
        return ("resourceCount", 
                len(util.getPrincipalList(
                    self.principalCollection,
                    'resources')))

    def getLocationCount(self):
        return ("locationCount", 
                len(util.getPrincipalList(
                    self.principalCollection,
                    'locations')))

    def run(self):
        assert self.root.exists(), "Calendar server document root directory does not exist: %s" % (self.root.path,)
        assert os.access(self.root.path, os.R_OK), "Cannot read calendar server document root directory: %s" % (self.root.path,)

        report = {'type': 'stats',
                  'data': {}}

        report['data'].update(
            util.getCalendarDataCounts(
                self.calendarCollection))

        for gatherer in self.gatherers:
            stat, value = gatherer()
            report['data'][stat] = value

        return report
