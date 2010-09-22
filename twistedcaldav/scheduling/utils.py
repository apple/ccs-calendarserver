#
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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
from twistedcaldav.method import report_common
from twext.web2.dav.util import joinURL

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

        # Run a UID query against the UID.
        @inlineCallbacks
        def queryCalendarCollection(collection, uri):
            if not allow_shared:
                if collection.isVirtualShare():
                    returnValue(True)

            rname = yield collection.index().resourceNameForUID(uid)
            if rname:
                resource = yield collection.getChild(rname)
                request._rememberResource(resource, joinURL(uri, rname))

                result["resource"] = resource
                result["resource_name"] = rname
                result["calendar_collection"] = collection
                result["calendar_collection_uri"] = uri
                returnValue(False)
            else:
                returnValue(True)

        # NB We are by-passing privilege checking here. That should be OK as
        # the data found is not exposed to the user.
        yield report_common.applyToCalendarCollections(
            calendar_home, request, calendar_home.url(),
            "infinity", queryCalendarCollection, None
        )

    returnValue((result["resource"], result["resource_name"], result["calendar_collection"], result["calendar_collection_uri"],))

