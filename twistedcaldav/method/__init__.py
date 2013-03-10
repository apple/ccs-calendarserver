##
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

"""
CalDAV methods.

Modules in this package are imported by twistedcaldav.resource in order to
bind methods to CalDAVResource.
"""

__all__ = [
    "acl",
    "copymove",
    "delete",
    "get",
    "mkcalendar",
    "mkcol",
    "post",
    "propfind",
    "put",
    "report",
    "report_freebusy",
    "report_calendar_multiget",
    "report_calendar_query",
    "report_addressbook_multiget",
    "report_addressbook_query",
    "report_sync_collection",
]
