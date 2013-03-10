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

from txdav.xml.element import registerElement
from txdav.xml.element import WebDAVElement, WebDAVEmptyElement, WebDAVTextElement


##
# Timezone Service XML Definitions
##

timezone_namespace = "urn:ietf:params:xml:ns:timezone-service"


@registerElement
class Capabilities (WebDAVElement):
    namespace = timezone_namespace
    name = "capabilities"
    allowed_children = {
        (timezone_namespace, "operation"): (0, None),
    }



@registerElement
class Operation (WebDAVElement):
    namespace = timezone_namespace
    name = "operation"
    allowed_children = {
        (timezone_namespace, "action"): (1, 1),
        (timezone_namespace, "description"): (0, 1),
        (timezone_namespace, "accept-parameter"): (0, None),
    }



@registerElement
class Action (WebDAVTextElement):
    namespace = timezone_namespace
    name = "action"



@registerElement
class Description (WebDAVTextElement):
    namespace = timezone_namespace
    name = "description"



@registerElement
class AcceptParameter (WebDAVElement):
    namespace = timezone_namespace
    name = "accept-parameter"
    allowed_children = {
        (timezone_namespace, "name"): (1, 1),
        (timezone_namespace, "required"): (1, 1),
        (timezone_namespace, "multi"): (1, 1),
        (timezone_namespace, "value"): (0, None),
        (timezone_namespace, "description"): (0, 1),
    }



@registerElement
class Name (WebDAVTextElement):
    namespace = timezone_namespace
    name = "name"



@registerElement
class Required (WebDAVTextElement):
    namespace = timezone_namespace
    name = "required"



@registerElement
class Multi (WebDAVTextElement):
    namespace = timezone_namespace
    name = "multi"



@registerElement
class Value (WebDAVTextElement):
    namespace = timezone_namespace
    name = "value"



@registerElement
class TimezoneList (WebDAVElement):
    namespace = timezone_namespace
    name = "timezone-list"
    allowed_children = {
        (timezone_namespace, "dtstamp"): (1, 1),
        (timezone_namespace, "summary"): (0, None),
    }



@registerElement
class Dtstamp (WebDAVTextElement):
    namespace = timezone_namespace
    name = "dtstamp"



@registerElement
class Summary (WebDAVElement):
    namespace = timezone_namespace
    name = "summary"
    allowed_children = {
        (timezone_namespace, "tzid"): (1, 1),
        (timezone_namespace, "last-modified"): (1, 1),
        (timezone_namespace, "local-name"): (0, None),
        (timezone_namespace, "alias"): (0, None),
        (timezone_namespace, "inactive"): (0, 1),
    }



@registerElement
class Tzid (WebDAVTextElement):
    namespace = timezone_namespace
    name = "tzid"



@registerElement
class LastModified (WebDAVTextElement):
    namespace = timezone_namespace
    name = "last-modified"



@registerElement
class LocalName (WebDAVTextElement):
    namespace = timezone_namespace
    name = "local-name"



@registerElement
class Alias (WebDAVTextElement):
    namespace = timezone_namespace
    name = "alias"



@registerElement
class Inactive (WebDAVEmptyElement):
    namespace = timezone_namespace
    name = "inactive"



@registerElement
class Timezones (WebDAVElement):
    namespace = timezone_namespace
    name = "timezones"
    allowed_children = {
        (timezone_namespace, "dtstamp"): (1, 1),
        (timezone_namespace, "tzdata"): (0, None),
    }



@registerElement
class Tzdata (WebDAVElement):
    namespace = timezone_namespace
    name = "tzdata"
    allowed_children = {
        (timezone_namespace, "tzid"): (1, 1),
        (timezone_namespace, "calscale"): (0, 1),
        (timezone_namespace, "observance"): (0, None),
    }



@registerElement
class Calscale (WebDAVTextElement):
    namespace = timezone_namespace
    name = "calscale"



@registerElement
class Observance (WebDAVElement):
    namespace = timezone_namespace
    name = "observance"
    allowed_children = {
        (timezone_namespace, "name"): (1, 1),
        (timezone_namespace, "local-name"): (0, None),
        (timezone_namespace, "onset"): (1, 1),
        (timezone_namespace, "utc-offset-from"): (1, 1),
        (timezone_namespace, "utc-offset-to"): (1, 1),
    }



@registerElement
class Onset (WebDAVTextElement):
    namespace = timezone_namespace
    name = "onset"



@registerElement
class UTCOffsetFrom (WebDAVTextElement):
    namespace = timezone_namespace
    name = "utc-offset-from"



@registerElement
class UTCOffsetTo (WebDAVTextElement):
    namespace = timezone_namespace
    name = "utc-offset-to"
