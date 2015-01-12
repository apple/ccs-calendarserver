# -*- test-case-name: twistedcaldav -*-
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
CalDAV support for Twext.Web2.

See RFC 4791.
"""

#
# Load in suitable file extension/content-type map from OS X
#

from txweb2.static import File, loadMimeTypes

File.contentTypes = loadMimeTypes(("/etc/apache2/mime.types", "/etc/httpd/mime.types",))

#
# Register additional WebDAV XML elements
#

import twistedcaldav.caldavxml
import twistedcaldav.carddavxml
import twistedcaldav.mkcolxml
import twistedcaldav.customxml
import twistedcaldav.timezonexml

twistedcaldav # Shhh.. pyflakes

#
# DefaultHTTPHandler
#

from txweb2.http_headers import DefaultHTTPHandler, last, singleHeader

DefaultHTTPHandler.updateParsers({
    "If-Schedule-Tag-Match": (last, str),
})
DefaultHTTPHandler.updateGenerators({
    "Schedule-Tag": (str, singleHeader),
})

# Do some PyCalendar init
from pycalendar.icalendar.calendar import Calendar
from pycalendar.icalendar.property import Property
from pycalendar.vcard.card import Card
from pycalendar.value import Value

Calendar.setPRODID("-//CALENDARSERVER.ORG//NONSGML Version 1//EN")
Card.setPRODID("-//CALENDARSERVER.ORG//NONSGML Version 1//EN")

# These are properties we use directly and we want the default value type set for TEXT
Property.registerDefaultValue("X-CALENDARSERVER-PRIVATE-COMMENT", Value.VALUETYPE_TEXT)
Property.registerDefaultValue("X-CALENDARSERVER-ATTENDEE-COMMENT", Value.VALUETYPE_TEXT)

Property.registerDefaultValue("X-APPLE-TRAVEL-DURATION", Value.VALUETYPE_DURATION, always_write_value=True)
Property.registerDefaultValue("X-APPLE-TRAVEL-START", Value.VALUETYPE_URI, always_write_value=True)
Property.registerDefaultValue("X-APPLE-TRAVEL-RETURN-DURATION", Value.VALUETYPE_DURATION, always_write_value=True)
Property.registerDefaultValue("X-APPLE-TRAVEL-RETURN", Value.VALUETYPE_URI, always_write_value=True)
