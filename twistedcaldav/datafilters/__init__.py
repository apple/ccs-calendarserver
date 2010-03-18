##
# Copyright (c) 2009 Apple Inc. All rights reserved.
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

from vobject.base import registerBehavior
from vobject.icalendar import VCalendarComponentBehavior, VCalendar2_0

"""
Data filtering module.
"""

# This is where we register our special components with vobject

class X_CALENDARSERVER_PERUSER(VCalendarComponentBehavior):
    name='X-CALENDARSERVER-PERUSER'
    description='A component used to encapsulate per-user data.'
    sortFirst = ('uid', 'x-calendarserver-peruser-uid')
    knownChildren = {
        'UID':                            (1, 1, None),#min, max, behaviorRegistry id
        'X-CALENDARSERVER-PERUSER-UID':   (1, 1, None),
        'X-CALENDARSERVER-PERINSTANCE':   (0, None, None),
    }
      
registerBehavior(X_CALENDARSERVER_PERUSER)
VCalendar2_0.knownChildren['X-CALENDARSERVER-PERUSER'] = (0, None, None)

class X_CALENDARSERVER_PERINSTANCE(VCalendarComponentBehavior):
    name='X-CALENDARSERVER-PERINSTANCE'
    description='A component used to encapsulate per-user instance data.'
    sortFirst = ('recurrence-id',)
    knownChildren = {
        'RECURRENCE-ID':(0, 1, None),#min, max, behaviorRegistry id
    }
      
registerBehavior(X_CALENDARSERVER_PERINSTANCE)
