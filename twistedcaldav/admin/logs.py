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

import datetime
import plistlib
import sys
import time

from twistedcaldav.admin import util

PLIST_VERSION = 4

statsTemplate = plistlib.Dict(
    version=PLIST_VERSION,
    bytesOut="0",
    startDate="",
    endDate="",
    requestStats={},
    timeOfDayStats=[0] * 96,
    requestByTimeOfDayStats={},
    statusStats={},
    invitations={
        "day":0, 
        "week":0, 
        "month":0, 
        },
    userAgents={},
    activeUsers={},
    )

def _strAdd(value, add):
    return str(long(value) + add)

class Stats(object):
    def __init__(self, fp, append, days):
        self.fp = fp
        self._data = None

        if self.fp.exists() and append:
            self._data = plistlib.readPlist(self.fp.path)
            if self._data.version != PLIST_VERSION:
                self._data = None
        
        if self._data is None:
            self._data = statsTemplate
            self.save()
            
        self.earliest_date = datetime.date.today() - datetime.timedelta(days=days)

    MONTH_MAP = {
        'Jan':1,
        'Feb':2,
        'Mar':3,
        'Apr':4,
        'May':5,
        'Jun':6,
        'Jul':7,
        'Aug':8,
        'Sep':9,
        'Oct':10,
        'Nov':11,
        'Dec':12,
    }

    def addDate(self, date):
        # Check that log entry is within our earliest date bound
        day = int(date[0:2])
        month = Stats.MONTH_MAP[date[3:6]]
        year = int(date[7:11])
        log_date = datetime.date(year=year, month=month, day=day)
        if log_date < self.earliest_date:
            return False

        if not self._data.startDate:
            self._data.startDate = date
        self._data.endDate = date
        
        return True

    def getDateRange(self):
        return (self._data.startDate, self._data.endDate)

    def addBytes(self, bytes):
        self._data.bytesOut = _strAdd(self._data.bytesOut, bytes)

    def getBytes(self):
        return long(self._data.bytesOut)

    def addRequestStats(self, request, status, bytes, time):
        if request in self._data.requestStats:
            request_stat = self._data.requestStats[request]
            old_num = long(request_stat['num'])
            request_stat['num'] = _strAdd(request_stat['num'], 1)
            if status >= 200 and status < 300:
                request_stat['numOK'] = _strAdd(request_stat['numOK'], 1)
            elif status == 500:
                request_stat['numISE'] = _strAdd(request_stat['numISE'], 1)
            elif status >= 400 and status < 600:
                request_stat['numBAD'] = _strAdd(request_stat['numBAD'], 1)
            else:
                request_stat['numOther'] = _strAdd(request_stat['numOther'], 1)
            if bytes < long(request_stat['minbytes']):
                request_stat['minbytes'] = str(bytes)
            if bytes > long(request_stat['maxbytes']):
                request_stat['maxbytes'] = str(bytes)
            request_stat['avbytes'] = str((long(request_stat['avbytes']) * old_num + bytes) / (old_num + 1))
            if time < request_stat['mintime']:
                request_stat['mintime'] = time
            if time > request_stat['maxtime']:
                request_stat['maxtime'] = time
            request_stat['avtime'] = (request_stat['avtime'] * old_num + time) / (old_num + 1)
        else:
            self._data.requestStats[request] = {}
            request_stat = self._data.requestStats[request]
            request_stat['num'] = "1"
            request_stat['numOK'] = "0"
            request_stat['numBAD'] = "0"
            request_stat['numISE'] = "0"
            request_stat['numOther'] = "0"
            if status >= 200 and status < 300:
                request_stat['numOK'] = "1"
            elif status == 500:
                request_stat['numISE'] = "1"
            elif status >= 400 and status < 600:
                request_stat['numBAD'] = "1"
            else:
                request_stat['numOther'] = "1"
            request_stat['minbytes'] = str(bytes)
            request_stat['maxbytes'] = str(bytes)
            request_stat['avbytes'] = str(bytes)
            request_stat['mintime'] = time
            request_stat['maxtime'] = time
            request_stat['avtime'] = time
    
    def getRequestStats(self):
        return self._data.requestStats

    def addTimeOfDayStats(self, request, time):
        hour, minute = time.split(":")
        bucket = int(hour) * 4 + divmod(int(minute), 15)[0]
        self._data.timeOfDayStats[bucket] = self._data.timeOfDayStats[bucket] + 1
        if request not in self._data.requestByTimeOfDayStats:
            self._data.requestByTimeOfDayStats[request] = [0] * 96
        self._data.requestByTimeOfDayStats[request][bucket] = self._data.requestByTimeOfDayStats[request][bucket] + 1
    
    def getTimeOfDayStats(self):
        return self._data.timeOfDayStats

    def getRequestByTimeOfDayStats(self):
        return self._data.requestByTimeOfDayStats

    def addStatusStats(self, status):
        old = self._data.statusStats.get(str(status), "0")
        self._data.statusStats[str(status)] = _strAdd(old, 1)

    def getStatusStats(self):
        return self._data.statusStats

    def addUserAgent(self, useragent):
        if useragent in self._data.userAgents:
            self._data.userAgents[useragent] += 1
        else:
            self._data.userAgents[useragent] = 1

    def getUserAgents(self):
        return self._data.userAgents

    def addActiveUser(self, principal):
        if principal in self._data.activeUsers:
            self._data.activeUsers[principal] += 1
        else:
            self._data.activeUsers[principal] = 1

    def getActiveUsers(self):
        return self._data.activeUsers

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
        self.stats = Stats(self.config['statsfile'], self.config['append'], self.config['days'])

    def run(self):

        if not self.readOnly:
            total_count = -1
            for total_count, line in enumerate(self.logfile.open()):
                pass
            total_count += 1
            print "Reading file: %s (%d lines)" % (self.logfile.basename(), total_count,)
            print "|" + "----|" * 10 + "\n.",
            last_count = 0
            start_time = time.time()
            try:
                for line_count, line in enumerate(self.logfile.open()):
                    if (line.startswith('Log opened') or 
                        line.startswith('Log closed')):
                        continue
                    else:
                        pline = parseCLFLine(line)
                        
                        if self.stats.addDate(pline[3]):
                            self.stats.addBytes(int(pline[6]))
                            self.stats.addRequestStats(pline[4].split(' ')[0], int(pline[5]), int(pline[6]), float(pline[9][:-3]))
                            self.stats.addTimeOfDayStats(pline[4].split(' ')[0], pline[3][pline[3].find(":") + 1:][:5])
                            self.stats.addStatusStats(int(pline[5]))
        
                            if len(pline) > 7:
                                self.stats.addUserAgent(pline[8])
        
                            if pline[2] != "-":
                                self.stats.addActiveUser(pline[2])
                            
                    if (50 * line_count) / total_count > last_count:
                        sys.stdout.write(".")
                        sys.stdout.flush()
                        last_count = (50 * line_count) / total_count
            except Exception, e:
                print "Problem at line: %d, %s" % (line_count, e)
                raise

            print ".\nTime taken: %.1f secs\n" % (time.time() - start_time)

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
                    'requestByTimeOfDayStats': self.stats.getRequestByTimeOfDayStats(),
                    'statusStats': self.stats.getStatusStats(),
                    'userAgents': self.stats.getUserAgents(),
                    'activeUsers': self.stats.getActiveUsers(),
                    }
                }

            return report

        return None
