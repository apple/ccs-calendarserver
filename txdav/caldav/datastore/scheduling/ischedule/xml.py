##
# Copyright (c) 2011-2013 Apple Inc. All rights reserved.
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
This module provides XML definitions for use with Timezone Standard Service.
"""

from twistedcaldav.config import config
from twistedcaldav.ical import Component as iComponent
from txdav.xml.element import PCDATAElement, WebDAVElement, WebDAVEmptyElement, WebDAVTextElement
from txdav.xml.element import registerElement


##
# iSchedule XML Definitions
##

ischedule_namespace = "urn:ietf:params:xml:ns:ischedule"


@registerElement
class QueryResult (WebDAVElement):
    namespace = ischedule_namespace
    name = "query-result"

    allowed_children = {
        (ischedule_namespace, "capability-set"): (0, None),
    }



@registerElement
class Capabilities (WebDAVElement):
    namespace = ischedule_namespace
    name = "capabilities"

    allowed_children = {
        (ischedule_namespace, "serial-number"): (1, 1),
        (ischedule_namespace, "versions"): (1, 1),
        (ischedule_namespace, "scheduling-messages"): (1, 1),
        (ischedule_namespace, "calendar-data-types"): (1, 1),
        (ischedule_namespace, "attachments"): (1, 1),
        (ischedule_namespace, "supported-recipient-uri-scheme-set"): (1, 1),
        (ischedule_namespace, "max-content-length"): (1, 1),
        (ischedule_namespace, "min-date-time"): (1, 1),
        (ischedule_namespace, "max-date-time"): (1, 1),
        (ischedule_namespace, "max-instances"): (1, 1),
        (ischedule_namespace, "max-recipients"): (1, 1),
        (ischedule_namespace, "administrator"): (1, 1),
    }



@registerElement
class SerialNumber (WebDAVTextElement):
    namespace = ischedule_namespace
    name = "serial-number"



@registerElement
class Versions (WebDAVElement):
    namespace = ischedule_namespace
    name = "versions"

    allowed_children = {
        (ischedule_namespace, "version"): (1, None),
    }



@registerElement
class Version (WebDAVTextElement):
    namespace = ischedule_namespace
    name = "version"



@registerElement
class SchedulingMessages (WebDAVElement):
    namespace = ischedule_namespace
    name = "scheduling-messages"

    allowed_children = {
        (ischedule_namespace, "component"): (1, None),
    }



@registerElement
class Component (WebDAVElement):
    namespace = ischedule_namespace
    name = "component"

    allowed_children = {
        (ischedule_namespace, "method"): (0, None),
    }
    allowed_attributes = {"name": True}



@registerElement
class Method (WebDAVEmptyElement):
    namespace = ischedule_namespace
    name = "method"

    allowed_attributes = {"name": True}



@registerElement
class CalendarDataTypes (WebDAVElement):
    namespace = ischedule_namespace
    name = "calendar-data-types"

    allowed_children = {
        (ischedule_namespace, "calendar-data-type"): (1, None),
    }



@registerElement
class CalendarDataType (WebDAVTextElement):
    namespace = ischedule_namespace
    name = "calendar-data-type"

    allowed_attributes = {
        "content-type": True,
        "version": True,
    }



@registerElement
class Attachments (WebDAVElement):
    namespace = ischedule_namespace
    name = "attachments"

    allowed_children = {
        (ischedule_namespace, "inline"): (0, 1),
        (ischedule_namespace, "external"): (0, 1),
    }



@registerElement
class Inline (WebDAVEmptyElement):
    namespace = ischedule_namespace
    name = "inline"



@registerElement
class External (WebDAVEmptyElement):
    namespace = ischedule_namespace
    name = "external"



@registerElement
class MaxContentLength (WebDAVTextElement):
    namespace = ischedule_namespace
    name = "max-content-length"



@registerElement
class MinDateTime (WebDAVTextElement):
    namespace = ischedule_namespace
    name = "min-date-time"



@registerElement
class MaxDateTime (WebDAVTextElement):
    namespace = ischedule_namespace
    name = "max-date-time"



@registerElement
class MaxInstances (WebDAVTextElement):
    namespace = ischedule_namespace
    name = "max-instances"



@registerElement
class MaxRecipients (WebDAVTextElement):
    namespace = ischedule_namespace
    name = "max-recipients"



@registerElement
class Administrator (WebDAVTextElement):
    namespace = ischedule_namespace
    name = "administrator"



@registerElement
class ScheduleResponse (WebDAVTextElement):
    namespace = ischedule_namespace
    name = "schedule-response"

    allowed_children = {
        (ischedule_namespace, "response"): (0, None),
    }



@registerElement
class Response (WebDAVElement):
    namespace = ischedule_namespace
    name = "response"

    allowed_children = {
        (ischedule_namespace, "recipient"): (1, 1),
        (ischedule_namespace, "request-status"): (1, 1),
        (ischedule_namespace, "calendar-data"): (0, 1),
        (ischedule_namespace, "error"): (0, 1),
        (ischedule_namespace, "response-description"): (0, 1),
    }



@registerElement
class Recipient (WebDAVTextElement):
    namespace = ischedule_namespace
    name = "recipient"



@registerElement
class RequestStatus (WebDAVTextElement):
    namespace = ischedule_namespace
    name = "request-status"



@registerElement
class CalendarData (WebDAVTextElement):
    namespace = ischedule_namespace
    name = "calendar-data"


    @classmethod
    def fromCalendar(clazz, calendar, format=None):
        attrs = {}
        if format is not None and format != "text/calendar":
            attrs["content-type"] = format

        if isinstance(calendar, str):
            if not calendar:
                raise ValueError("Missing calendar data")
            return clazz(PCDATAElement(calendar))
        elif isinstance(calendar, iComponent):
            assert calendar.name() == "VCALENDAR", "Not a calendar: %r" % (calendar,)
            return clazz(PCDATAElement(calendar.getTextWithTimezones(includeTimezones=not config.EnableTimezonesByReference, format=format)))
        else:
            raise ValueError("Not a calendar: %s" % (calendar,))

    fromTextData = fromCalendar



@registerElement
class Error (WebDAVElement):
    namespace = ischedule_namespace
    name = "error"

    allowed_children = {WebDAVElement: (0, None)}



@registerElement
class ResponseDescription (WebDAVTextElement):
    namespace = ischedule_namespace
    name = "response-description"
