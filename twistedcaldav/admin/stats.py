##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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
#
# DRI: David Reid, dreid@apple.com
##

"""
Statisitcs Types:

 Overall Stats:
  # of accounts
  # of calendars
  # of events

"""
import os
import xattr
import commands

from twisted.web import microdom

from twistedcaldav import ical

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
            self.getDiskUsage]

    def getDiskUsage(self):
        return ("diskUsage", 
                util.getDiskUsage(self.config, self.root))

    def getAccountCount(self):
        return ("accountCount", 
                len(util.getPrincipalList(
                    self.principalCollection,
                    'user')))

    def getGroupCount(self):
        return ("groupCount", 
                len(util.getPrincipalList(
                    self.principalCollection,
                    'group')))

    def getResourceCount(self):
        return ("resourceCount", 
                len(util.getPrincipalList(
                    self.principalCollection,
                    'resource')))

    def run(self):
        assert self.root.exists()
        stats = []

        report = {'type': 'stats',
                  'data': {}}

        report['data'].update(
            util.getCalendarDataCounts(
                self.calendarCollection))

        for gatherer in self.gatherers:
            stat, value = gatherer()
            report['data'][stat] = value

        return report
