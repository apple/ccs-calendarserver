#
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks, returnValue
from twext.python.log import Logger

log = Logger()

@inlineCallbacks
def getCalendarObjectForPrincipals(txn, principal, uid, allow_shared=False):
    """
    Get a copy of the event for a principal.

    NOTE: if more than one resource with the same UID is found, we will delete all but
    one of them to avoid scheduling problems.
    """

    if principal and principal.locallyHosted():
        # Get principal's calendar-home
        calendar_home = yield txn.calendarHomeWithUID(principal.uid())

        # Get matching newstore objects
        objectResources = (yield calendar_home.getCalendarResourcesForUID(uid, allow_shared))

        if len(objectResources) > 1:
            # Delete all but the first one
            log.debug("Should only have zero or one scheduling object resource with UID '%s' in calendar home: %s" % (uid, calendar_home,))
            for resource in objectResources[1:]:
                yield resource._parentCollection.removeObjectResource(resource)
            objectResources = objectResources[:1]

        returnValue(objectResources[0] if len(objectResources) == 1 else None)
    else:
        returnValue(None)
