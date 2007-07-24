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

import datetime

from twistedcaldav.sql import db_prefix

def purgeEvents(collection, purgeDate):
    """
    Recursively purge all events older than purgeDate.

    for VTODO: 
     * if completed
       * purge if it's dueDate is older than purgeDate.

    for V*:
     * purge if endDate is older than purgeDate
     """

    from twistedcaldav import ical

    files = []
    directories = []

    for child in collection.children():
        if child.basename().startswith(db_prefix):
            continue

        if child.isdir():
            directories.append(child)

        elif child.isfile():
            files.append(child)

    for directory in directories:
        purgeEvents(directory, purgeDate)

    for f in files:
        try:
            component = ical.Component.fromStream(f.open())
        except ValueError:
            # Not a calendar file?
            continue

        endDate = component.mainComponent().getEndDateUTC()
        
        if component.resourceType() == 'VTODO':
            if component.mainComponent().hasProperty('COMPLETED'):
                endDate = component.mainComponent().getDueDateUTC()
            else:
                endDate = None

        if isinstance(endDate, datetime.datetime):
            endDate = endDate.date()

        if endDate:
            if purgeDate > endDate:
                print "Purging %s, %s, %s" % (component.resourceType(), 
                                               component.resourceUID(), 
                                               endDate.isoformat())
                f.remove()


class PurgeAction(object):
    def __init__(self, config):
        self.config = config
        self.calendarCollection = config.parent.calendarCollection

    def run(self):
        if self.config.params:
            collections = [self.calendarCollection.child(p) 
                           for p in self.config.params]
            
        else:
            collections = []
            
            for type in self.calendarCollection.children():
                collections.extend(type.children())
                    
        purgeDate = datetime.date.today()
        purgeDate = purgeDate - datetime.timedelta(int(self.config['days']))

        for collection in collections:
            purgeEvents(collection, purgeDate)
