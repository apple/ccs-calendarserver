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
#
# DRI: David Reid, dreid@apple.com
##
"""
 Log Stats:
  # Invitations sent per day/week/month
  # bytes out (bytes in not provided in the current log format.)/
  # requests
  user agents

"""

import plistlib

from twistedcaldav.admin import util

PLIST_VERSION = 1

statsTemplate = plistlib.Dict(
    version=PLIST_VERSION,
    bytesOut="0",
    startDate="",
    endDate="",
    requestStats=plistlib.Dict(
        ),
    timeOfDayStats=[0] * 96,
    invitations=plistlib.Dict(
        day=0, 
        week=0, 
        month=0, 
        ),
    userAgents=plistlib.Dict(),
    )

class Stats(object):
    def __init__(self, fp):
        self.fp = fp
        self._data = None

        if self.fp.exists():
            self._data = plistlib.readPlist(self.fp.path)
            if self._data.version != PLIST_VERSION:
                self._data = None
        
        if self._data is None:
            self._data = statsTemplate
            self.save()

    def addDate(self, date):
        if not self._data.startDate:
            self._data.startDate = date
        self._data.endDate = date

    def getDateRange(self):
        return (self._data.startDate, self._data.endDate)

    def getBytes(self):
        return long(self._data.bytesOut)

    def addBytes(self, bytes):
        self._data.bytesOut = str(long(self._data.bytesOut) + bytes)

    def addRequestStats(self, request, status, bytes, time):
        if request in self._data.requestStats:
            old_num = self._data.requestStats[request]['num']
            self._data.requestStats[request]['num'] = old_num + 1
            if status >= 200 and status < 300:
                self._data.requestStats[request]['numOK'] = self._data.requestStats[request]['numOK'] + 1
            elif status == 500:
                self._data.requestStats[request]['numISE'] = self._data.requestStats[request]['numISE'] + 1
            elif status >= 400 and status < 600:
                self._data.requestStats[request]['numBAD'] = self._data.requestStats[request]['numBAD'] + 1
            else:
                self._data.requestStats[request]['numOther'] = self._data.requestStats[request]['numOther'] + 1
            if bytes < self._data.requestStats[request]['minbytes']:
                self._data.requestStats[request]['minbytes'] = bytes
            if bytes > self._data.requestStats[request]['maxbytes']:
                self._data.requestStats[request]['maxbytes'] = bytes
            self._data.requestStats[request]['avbytes'] = (self._data.requestStats[request]['avbytes'] * old_num + bytes) / (old_num + 1)
            if time < self._data.requestStats[request]['mintime']:
                self._data.requestStats[request]['mintime'] = time
            if time > self._data.requestStats[request]['maxtime']:
                self._data.requestStats[request]['maxtime'] = time
            self._data.requestStats[request]['avtime'] = (self._data.requestStats[request]['avtime'] * old_num + time) / (old_num + 1)
        else:
            self._data.requestStats[request] = {}
            self._data.requestStats[request]['num'] = 1
            self._data.requestStats[request]['numOK'] = 0
            self._data.requestStats[request]['numBAD'] = 0
            self._data.requestStats[request]['numISE'] = 0
            self._data.requestStats[request]['numOther'] = 0
            if status >= 200 and status < 300:
                self._data.requestStats[request]['numOK'] = 1
            elif status == 500:
                self._data.requestStats[request]['numISE'] = 1
            elif status >= 400 and status < 600:
                self._data.requestStats[request]['numBAD'] = 1
            else:
                self._data.requestStats[request]['numOther'] = 1
            self._data.requestStats[request]['minbytes'] = bytes
            self._data.requestStats[request]['maxbytes'] = bytes
            self._data.requestStats[request]['avbytes'] = bytes
            self._data.requestStats[request]['mintime'] = time
            self._data.requestStats[request]['maxtime'] = time
            self._data.requestStats[request]['avtime'] = time
    
    def getRequestStats(self):
        return self._data.requestStats

    def addTimeOfDayStats(self, request, time):
        hour, minute = time.split(":")
        bucket = int(hour) * 4 + divmod(int(minute), 15)[0]
        self._data.timeOfDayStats[bucket] = self._data.timeOfDayStats[bucket] + 1
    
    def getTimeOfDayStats(self):
        return self._data.timeOfDayStats

    def addUserAgent(self, useragent):
        if useragent in self._data.userAgents:
            self._data.userAgents[useragent] += 1
        else:
            self._data.userAgents[useragent] = 1

    def getUserAgents(self):
        return self._data.userAgents

    def save(self):
        plistlib.writePlist(self._data, self.fp.path)

NORMAL = 1
INDATE = 2
INSTRING = 3

def parseCLFLine(line):
    state = NORMAL
    elements = []
    
    rest = []

    for c in line:
        if c == ' ':
            if state == NORMAL:
                elements.append(''.join(rest))
                rest = []

            elif state == INSTRING or state == INDATE:
                rest.append(c)
                    
        elif c == '[':
            if state != INSTRING:
                state = INDATE
                        
        elif c == ']':
            if state == INDATE:
                state = NORMAL

        elif c == '"':
            if state == INSTRING:
                state = NORMAL
            else:
                state = INSTRING
        elif c == '\n':
            if state == NORMAL:
                elements.append(''.join(rest))
                rest = []

        else:
            rest.append(c)

    return elements

                    
class LogAction(object):
    def __init__(self, config):
        self.config = config

        self.noOutput = self.config['nooutput']
        self.readOnly = self.config['readonly']

        self.logfile = self.config['logfile']
        self.stats = Stats(self.config['statsfile'])

    def run(self):

        if not self.readOnly:
            total_count = -1
            for total_count, line in enumerate(self.logfile.open()):
                pass
            total_count += 1
            print "Reading file: %s (%d lines)" % (self.logfile.basename(), total_count,)
            print "|" + "--" * 48 + "|"
            last_count = 0
            for line_count, line in enumerate(self.logfile.open()):
                if (line.startswith('Log opened') or 
                    line.startswith('Log closed')):
                    continue
                else:
                    pline = parseCLFLine(line)
                    
                    self.stats.addDate(pline[3])
                    self.stats.addBytes(int(pline[6]))
                    self.stats.addRequestStats(pline[4].split(' ')[0], int(pline[5]), int(pline[6]), float(pline[9][:-3]))
                    self.stats.addTimeOfDayStats(pline[4].split(' ')[0], pline[3][pline[3].find(":") + 1:][:5])

                    if len(pline) > 7:
                        self.stats.addUserAgent(pline[8])
                        
                if (50 * line_count) / total_count > last_count:
                    print ".",
                    last_count = (50 * line_count) / total_count

            print "\n\n"

            self.stats.save()    

        if not self.noOutput:
            report = {
                'type': 'logs',
                'data': {
                    'dateRange': self.stats.getDateRange(),
                    'bytesOut': util.prepareByteValue(self.config, 
                                                      self.stats.getBytes()),
                    'requestStats': self.stats.getRequestStats(),
                    'timeOfDayStats': self.stats.getTimeOfDayStats(),
                    'userAgents': self.stats.getUserAgents(),
                    }
                }

            return report

        return None
