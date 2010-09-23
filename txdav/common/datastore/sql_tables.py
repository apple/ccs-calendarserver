# -*- test-case-name: txdav.caldav.datastore.test.test_sql -*-
##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
SQL Table definitions.
"""

CALENDAR_HOME_TABLE = {
    "name"               : "CALENDAR_HOME",
    "column_RESOURCE_ID" : "RESOURCE_ID",
    "column_OWNER_UID"   : "OWNER_UID",
}

ADDRESSBOOK_HOME_TABLE = {
    "name"               : "ADDRESSBOOK_HOME",
    "column_RESOURCE_ID" : "RESOURCE_ID",
    "column_OWNER_UID"   : "OWNER_UID",
}

NOTIFICATION_HOME_TABLE = {
    "name"               : "NOTIFICATION_HOME",
    "column_RESOURCE_ID" : "RESOURCE_ID",
    "column_OWNER_UID"   : "OWNER_UID",
}

CALENDAR_TABLE = {
    "name"               : "CALENDAR",
    "column_RESOURCE_ID" : "RESOURCE_ID",
    "column_CREATED"     : "CREATED",
    "column_MODIFIED"    : "MODIFIED",
}

ADDRESSBOOK_TABLE = {
    "name"               : "ADDRESSBOOK",
    "column_RESOURCE_ID" : "RESOURCE_ID",
    "column_CREATED"     : "CREATED",
    "column_MODIFIED"    : "MODIFIED",
}

CALENDAR_BIND_TABLE = {
    "name"                    : "CALENDAR_BIND",
    "column_HOME_RESOURCE_ID" : "CALENDAR_HOME_RESOURCE_ID",
    "column_RESOURCE_ID"      : "CALENDAR_RESOURCE_ID",
    "column_RESOURCE_NAME"    : "CALENDAR_RESOURCE_NAME",
    "column_BIND_MODE"        : "BIND_MODE",
    "column_BIND_STATUS"      : "BIND_STATUS",
    "column_SEEN_BY_OWNER"    : "SEEN_BY_OWNER",
    "column_SEEN_BY_SHAREE"   : "SEEN_BY_SHAREE",
    "column_MESSAGE"          : "MESSAGE",
}

ADDRESSBOOK_BIND_TABLE = {
    "name"                    : "ADDRESSBOOK_BIND",
    "column_HOME_RESOURCE_ID" : "ADDRESSBOOK_HOME_RESOURCE_ID",
    "column_RESOURCE_ID"      : "ADDRESSBOOK_RESOURCE_ID",
    "column_RESOURCE_NAME"    : "ADDRESSBOOK_RESOURCE_NAME",
    "column_BIND_MODE"        : "BIND_MODE",
    "column_BIND_STATUS"      : "BIND_STATUS",
    "column_SEEN_BY_OWNER"    : "SEEN_BY_OWNER",
    "column_SEEN_BY_SHAREE"   : "SEEN_BY_SHAREE",
    "column_MESSAGE"          : "MESSAGE",
}

CALENDAR_OBJECT_REVISIONS_TABLE = {
    "name"                    : "CALENDAR_OBJECT_REVISIONS",
    "sequence"                : "REVISION_SEQ",
    "column_HOME_RESOURCE_ID" : "CALENDAR_HOME_RESOURCE_ID",
    "column_RESOURCE_ID"      : "CALENDAR_RESOURCE_ID",
    "column_RESOURCE_NAME"    : "RESOURCE_NAME",
    "column_REVISION"         : "REVISION",
    "column_DELETED"          : "DELETED",
}

ADDRESSBOOK_OBJECT_REVISIONS_TABLE = {
    "name"                    : "ADDRESSBOOK_OBJECT_REVISIONS",
    "sequence"                : "REVISION_SEQ",
    "column_HOME_RESOURCE_ID" : "ADDRESSBOOK_HOME_RESOURCE_ID",
    "column_RESOURCE_ID"      : "ADDRESSBOOK_RESOURCE_ID",
    "column_RESOURCE_NAME"    : "RESOURCE_NAME",
    "column_REVISION"         : "REVISION",
    "column_DELETED"          : "DELETED",
}

NOTIFICATION_OBJECT_REVISIONS_TABLE = {
    "name"                    : "NOTIFICATION_OBJECT_REVISIONS",
    "sequence"                : "REVISION_SEQ",
    "column_HOME_RESOURCE_ID" : "NOTIFICATION_HOME_RESOURCE_ID",
    "column_RESOURCE_NAME"    : "RESOURCE_NAME",
    "column_REVISION"         : "REVISION",
    "column_DELETED"          : "DELETED",
}

CALENDAR_OBJECT_TABLE = {
    "name"                      : "CALENDAR_OBJECT",
    "column_RESOURCE_ID"        : "RESOURCE_ID",
    "column_PARENT_RESOURCE_ID" : "CALENDAR_RESOURCE_ID",
    "column_RESOURCE_NAME"      : "RESOURCE_NAME",
    "column_TEXT"               : "ICALENDAR_TEXT",
    "column_UID"                : "ICALENDAR_UID",
    "column_CREATED"            : "CREATED",
    "column_MODIFIED"           : "MODIFIED",
}

ADDRESSBOOK_OBJECT_TABLE = {
    "name"                      : "ADDRESSBOOK_OBJECT",
    "column_RESOURCE_ID"        : "RESOURCE_ID",
    "column_PARENT_RESOURCE_ID" : "ADDRESSBOOK_RESOURCE_ID",
    "column_RESOURCE_NAME"      : "RESOURCE_NAME",
    "column_TEXT"               : "VCARD_TEXT",
    "column_UID"                : "VCARD_UID",
    "column_CREATED"            : "CREATED",
    "column_MODIFIED"           : "MODIFIED",
}


# Various constants

_BIND_STATUS_INVITED = 0
_BIND_STATUS_ACCEPTED = 1
_BIND_STATUS_DECLINED = 2
_BIND_STATUS_INVALID = 3

_ATTACHMENTS_MODE_WRITE = 1

_BIND_MODE_OWN = 0
_BIND_MODE_READ = 1
_BIND_MODE_WRITE = 2
_BIND_MODE_DIRECT = 3
