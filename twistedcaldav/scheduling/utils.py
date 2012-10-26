#
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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
from twext.web2.dav.util import joinURL
from twext.python.log import Logger

log = Logger()

@inlineCallbacks
def getCalendarObjectForPrincipals(request, principal, uid, allow_shared=False):
    """
    Get a copy of the event for a principal.
    """

    result = {
        "resource": None,
        "resource_name": None,
        "calendar_collection": None,
        "calendar_collection_uri": None,
    }

    if principal and principal.locallyHosted():
        # Get principal's calendar-home
        calendar_home = yield principal.calendarHome(request)

        # FIXME: because of the URL->resource request mapping thing, we have to
        # force the request to recognize this resource.
        request._rememberResource(calendar_home, calendar_home.url())

        # Get matching newstore objects
        objectResources = (yield calendar_home.getCalendarResourcesForUID(uid, allow_shared))

        # We really want only one or zero of these
        if len(objectResources) == 1:
            result["calendar_collection_uri"] = joinURL(calendar_home.url(), objectResources[0]._parentCollection.name())
            result["calendar_collection"] = (yield request.locateResource(result["calendar_collection_uri"]))
            result["resource_name"] = objectResources[0].name()
            result["resource"] = (yield request.locateResource(joinURL(result["calendar_collection_uri"], result["resource_name"])))
        elif len(objectResources):
            log.debug("Should only have zero or one scheduling object resource with UID '%s' in calendar home: %s" % (uid, calendar_home,))

    returnValue((result["resource"], result["resource_name"], result["calendar_collection"], result["calendar_collection_uri"],))
