#!/usr/bin/env python
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
Prints out an SQL statement that can be used in an SQL shell against
an sqlstore database to return the calendar or address data for the provided
filestore or HTTP path.
"""

import getopt
import sys


def usage(error_msg=None):
    if error_msg:
        print error_msg

    print "sqldata_from_path PATH"
    print
    print "PATH   filestore or HTTP path"
    print
    print """Prints out an SQL statement that can be used in an SQL shell against
an sqlstore database to return the calendar or address data for the provided
filestore or HTTP path. Path must be a __uids__ path.
"""

    if error_msg:
        raise ValueError(error_msg)
    else:
        sys.exit(0)

if __name__ == '__main__':
    
    options, args = getopt.getopt(sys.argv[1:], "", [])
    if options:
        usage("No options allowed")
    
    if len(args) != 1:
        usage("One argument only must be provided.")
        
    # Determine the type of path
    segments = args[0].split("/")

    if len(segments) not in (6, 8,):
        usage("Must provide a path to a calendar or addressbook object resource.")
        
    if segments[0] != "":
        usage("Must provide a /calendars/... or /addressbooks/... path.")
    if segments[1] not in ("calendars", "addressbooks",):
        usage("Must provide a /calendars/... or /addressbooks/... path.")
    if segments[2] != "__uids__":
        usage("Must provide a /.../__uids__/... path.")

        
    datatype = segments[1]
    uid = segments[5 if len(segments[3]) == 2 else 3]
    collection = segments[6 if len(segments[3]) == 2 else 4]
    resource = segments[7 if len(segments[3]) == 2 else 5]
    
    sqlstrings = {
        "calendars": {
            "home_table"        : "CALENDAR_HOME",
            "bind_table"        : "CALENDAR_BIND",
            "object_table"      : "CALENDAR_OBJECT",

            "bind_home_id"      : "CALENDAR_HOME_RESOURCE_ID",
            "bind_name"         : "CALENDAR_RESOURCE_NAME",
            "bind_id"           : "CALENDAR_RESOURCE_ID",
            
            "object_bind_id"    : "CALENDAR_RESOURCE_ID",
            "object_name"       : "RESOURCE_NAME",
            "object_data"       : "ICALENDAR_TEXT",
        },

        "addressbooks": {
            "home_table"        : "ADDRESSBOOK_HOME",
            "bind_table"        : "ADDRESSBOOK_BIND",
            "object_table"      : "ADDRESSBOOK_OBJECT",

            "bind_home_id"      : "ADDRESSBOOK_HOME_RESOURCE_ID",
            "bind_name"         : "ADDRESSBOOK_RESOURCE_NAME",
            "bind_id"           : "ADDRESSBOOK_RESOURCE_ID",
            
            "object_bind_id"    : "ADDRESSBOOK_RESOURCE_ID",
            "object_name"       : "RESOURCE_NAME",
            "object_data"       : "VCARD_TEXT",
        },
    }
    
    sqlstrings[datatype]["uid"] = uid
    sqlstrings[datatype]["collection"] = collection
    sqlstrings[datatype]["resource"] = resource

    print """select %(object_data)s from %(object_table)s where
    %(object_name)s = '%(resource)s' and %(object_bind_id)s = (
        select %(bind_id)s from %(bind_table)s where
            %(bind_name)s = '%(collection)s' and %(bind_home_id)s = (
                select RESOURCE_ID from %(home_table)s where OWNER_UID = '%(uid)s'
            )
    );""" % sqlstrings[datatype]
    
