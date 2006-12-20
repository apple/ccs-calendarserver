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
 Account Stats: 
  # of calendars
  # of events
  # storage used (including things that don't count against quota?)
  Last login?
"""

from twistedcaldav.admin import util

class PrincipalAction(object):
    def __init__(self, config, type):
        self.config = config
        self.type = type
        self.quota = self.config['quota']

        self.formatter = self.config.parent.formatter
        self.root = self.config.parent.root
        self.calendarCollection = self.config.parent.calendarCollection
        self.principalCollection = self.config.parent.principalCollection
    
    def run(self):
        report = {'type': self.type,
                  'records': []}

        if not self.config.params:
            principals = util.getPrincipalList(self.principalCollection,
                                               self.type,
                                               disabled=self.config['disabled'])

        else:
            principals = []
            for p in self.config.params:
                p = self.principalCollection.child(self.type).child(p)

                if p.exists():
                    if self.config['disabled']:
                        if util.isPrincipalDisabled(p):
                            principals.append(p)

                    else:
                        principals.append(p)

        def _getRecords():
            for p in principals:
                precord = {}
                
                pcal = self.calendarCollection.child(
                    self.type
                    ).child(p.basename())
            
                precord['principalName'] = p.basename()
                
                precord['calendarHome'] = pcal.path

                precord.update(
                    util.getQuotaStatsForPrincipal(
                        self.config,
                        pcal,
                        self.quota))

                precord.update(
                    util.getCalendarDataCounts(pcal))

                precord['diskUsage'] = util.getDiskUsage(self.config, pcal)
                
                precord['disabled'] = util.isPrincipalDisabled(p)
                
                yield precord

        report['records'] = _getRecords()
        
        return report
