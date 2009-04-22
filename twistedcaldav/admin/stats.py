##
# Copyright (c) 2006-2009 Apple Inc. All rights reserved.
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
import socket 
import plistlib 
import time 

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

class StatsWatchAction(object):
    """
    Pulls the current server stats from the main server process via a socket
    For example:

    bin/caladmin --config conf/caldavd-dev.plist statswatch
    bin/caladmin --config conf/caldavd-dev.plist statswatch --refresh
    """
 
    def __init__(self, config):
        self.config = config
        self.refresh = None
 
    def getHitStats(self):
        response = ""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.config.parent.masterConfig.GlobalStatsSocket)
        while 1:
            data = sock.recv(8192)
            if not data: break
            response += data
            sock.close()
            return response
 
    def run(self):
        if self.config['refresh'] is not None:
            self.refresh = int(self.config['refresh'])
 
        response = self.getHitStats()
        plist = plistlib.readPlistFromString(response)
        total = plist['totalHits']
        since = time.time() - plist['recentHits']['since']
        if self.refresh is None:
            print "Total hits:\t%8d" % (total,)
            if plist['recentHits']['frequency'] is not 0:
                print "Last %dm%ds:\t%8d" % (since / 60, since % 60, plist['recentHits']['count'])
                print "Rate:\t\t%8.2f" % (plist['recentHits']['count'] * 1.0 / (since if since != 0 else 1))
                units = "second"
                interval = plist['recentHits']['period'] * 60 / plist['recentHits']['frequency']
                if interval % 60 is 0:
                    interval = interval / 60
                    units = "minute"
                    print "Update interval: %d %s%s" % (interval, units, ("", "s")[interval > 1])
                else:
                    print "Recent stats are not updated."
        else:
            # attempt to gauge the recent hits for the first line of output
            total_prev = (total - (plist['recentHits']['count'] / (since if since != 0 else 1) * self.refresh))
            while 1:
                print "Total hits: %10d\tLast %7s: %8d\tRate: %8.2f" % (
                    total,
                    "%dm%02ds" % (since / 60, since % 60),
                    plist['recentHits']['count'],
                    (total - total_prev) * 1.0 / (self.refresh if self.refresh != 0 else 1)
                )
                total_prev = total
                time.sleep(self.refresh)
                response = self.getHitStats()
                plist = plistlib.readPlistFromString(response)
                total = plist['totalHits']
                since = time.time() - plist['recentHits']['since']
 
        return None

