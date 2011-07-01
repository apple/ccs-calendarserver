##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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

from twext.web2.dav import davxml

##
# Timezone Service XML Definitions
##

timezone_namespace = "urn:ietf:params:xml:ns:timezone-service"

class Capabilities (davxml.WebDAVElement):
    namespace = timezone_namespace
    name = "capabilities"
    allowed_children = {
        (timezone_namespace, "operation"): (0, None),
    }

class Operation (davxml.WebDAVElement):
    namespace = timezone_namespace
    name = "operation"
    allowed_children = {
        (timezone_namespace, "action"): (1, 1),
        (timezone_namespace, "description"): (0, 1),
        (timezone_namespace, "accept-parameter"): (0, None),
    }

class Action (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "action"

class Description (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "description"

class AcceptParameter (davxml.WebDAVElement):
    namespace = timezone_namespace
    name = "accept-parameter"
    allowed_children = {
        (timezone_namespace, "name"): (1, 1),
        (timezone_namespace, "required"): (1, 1),
        (timezone_namespace, "multi"): (1, 1),
        (timezone_namespace, "value"): (0, None),
        (timezone_namespace, "description"): (0, 1),
    }

class Name (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "name"

class Required (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "required"

class Multi (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "multi"

class Value (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "value"

class TimezoneList (davxml.WebDAVElement):
    namespace = timezone_namespace
    name = "timezone-list"
    allowed_children = {
        (timezone_namespace, "dtstamp"): (1, 1),
        (timezone_namespace, "summary"): (0, None),
    }

class Dtstamp (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "dtstamp"

class Summary (davxml.WebDAVElement):
    namespace = timezone_namespace
    name = "summary"
    allowed_children = {
        (timezone_namespace, "tzid"): (1, 1),
        (timezone_namespace, "last-modified"): (1, 1),
        (timezone_namespace, "local-name"): (0, None),
        (timezone_namespace, "alias"): (0, None),
        (timezone_namespace, "inactive"): (0, 1),
    }

class Tzid (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "tzid"

class LastModified (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "last-modified"

class LocalName (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "local-name"

class Alias (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "alias"

class Inactive (davxml.WebDAVEmptyElement):
    namespace = timezone_namespace
    name = "inactive"

class Timezones (davxml.WebDAVElement):
    namespace = timezone_namespace
    name = "timezones"
    allowed_children = {
        (timezone_namespace, "dtstamp"): (1, 1),
        (timezone_namespace, "tzdata"): (0, None),
    }

class Tzdata (davxml.WebDAVElement):
    namespace = timezone_namespace
    name = "tzdata"
    allowed_children = {
        (timezone_namespace, "tzid"): (1, 1),
        (timezone_namespace, "calscale"): (0, 1),
        (timezone_namespace, "observance"): (0, None),
    }

class Calscale (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "calscale"

class Observance (davxml.WebDAVElement):
    namespace = timezone_namespace
    name = "observance"
    allowed_children = {
        (timezone_namespace, "name"): (1, 1),
        (timezone_namespace, "local-name"): (0, None),
        (timezone_namespace, "onset"): (1, 1),
        (timezone_namespace, "utc-offset-from"): (1, 1),
        (timezone_namespace, "utc-offset-to"): (1, 1),
    }

class Onset (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "onset"

class UTCOffsetFrom (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "utc-offset-from"

class UTCOffsetTo (davxml.WebDAVTextElement):
    namespace = timezone_namespace
    name = "utc-offset-to"

