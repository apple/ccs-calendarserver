##
# Copyright (c) 2005-2015 Apple Inc. All rights reserved.
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
CalDAV GET method.
"""

__all__ = ["http_GET"]

from twisted.internet.defer import inlineCallbacks, returnValue
from txweb2 import responsecode
from txdav.xml import element as davxml
from txweb2.dav.http import ErrorResponse
from txweb2.dav.util import parentForURL
from txweb2.http import HTTPError, StatusResponse
from txweb2.http import Response
from txweb2.http_headers import MimeType
from txweb2.stream import MemoryStream

from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.datafilters.hiddeninstance import HiddenInstanceFilter
from twistedcaldav.datafilters.privateevents import PrivateEventFilter
from twistedcaldav.ical import Component
from twistedcaldav.resource import isPseudoCalendarCollectionResource, \
    CalDAVResource
from twistedcaldav.util import bestAcceptType

@inlineCallbacks
def http_GET(self, request):

    if self.exists():
        # Special sharing request on a calendar or address book
        if self.isCalendarCollection() or self.isAddressBookCollection():

            # Check for action=share
            if request.args:
                action = request.args.get("action", ("",))
                if len(action) != 1:
                    raise HTTPError(ErrorResponse(
                        responsecode.BAD_REQUEST,
                        (calendarserver_namespace, "valid-action"),
                        "Invalid action parameter: %s" % (action,),
                    ))
                action = action[0]

                dispatch = {
                    "share"   : self.directShare,
                }.get(action, None)

                if dispatch is None:
                    raise HTTPError(ErrorResponse(
                        responsecode.BAD_REQUEST,
                        (calendarserver_namespace, "supported-action"),
                        "Action not supported: %s" % (action,),
                    ))

                response = (yield dispatch(request))
                returnValue(response)

        else:
            # FIXME: this should be implemented in storebridge.CalendarObject.render

            # Look for calendar access restriction on existing resource.
            parentURL = parentForURL(request.uri)
            parent = (yield request.locateResource(parentURL))
            if isPseudoCalendarCollectionResource(parent):

                # Check authorization first
                yield self.authorize(request, (davxml.Read(),))

                # Accept header handling
                accepted_type = bestAcceptType(request.headers.getHeader("accept"), Component.allowedTypes())
                if accepted_type is None:
                    raise HTTPError(StatusResponse(responsecode.NOT_ACCEPTABLE, "Cannot generate requested data type"))

                caldata = (yield self.iCalendarForUser())

                # Filter any attendee hidden instances
                caldata = HiddenInstanceFilter().filter(caldata)

                if self.accessMode:

                    # Non DAV:owner's have limited access to the data
                    isowner = (yield self.isOwner(request))

                    # Now "filter" the resource calendar data
                    caldata = PrivateEventFilter(self.accessMode, isowner).filter(caldata)

                response = Response()
                response.stream = MemoryStream(caldata.getTextWithTimezones(includeTimezones=not config.EnableTimezonesByReference, format=accepted_type))
                response.headers.setHeader("content-type", MimeType.fromString("%s; charset=utf-8" % (accepted_type,)))

                # Add Schedule-Tag header if property is present
                if self.scheduleTag:
                    response.headers.setHeader("Schedule-Tag", self.scheduleTag)

                returnValue(response)

    # Do normal GET behavior
    response = (yield super(CalDAVResource, self).http_GET(request))
    returnValue(response)
