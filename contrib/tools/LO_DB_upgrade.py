#!/usr/bin/env python
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
from txdav.base.propertystore.base import PropertyName
from twistedcaldav.customxml import TwistedCalendarHasPrivateCommentsProperty,\
    TwistedCalendarAccessProperty, TwistedSchedulingObjectResource,\
    TwistedScheduleMatchETags
import sys
from twext.web2.dav.element.parser import WebDAVDocument
from twistedcaldav.ical import Component
from twext.web2.dav.resource import TwistedQuotaUsedProperty

"""
Tool to manage schema upgrade of SQL database during internal development phase as we don't have
a "real" upgrade in place just yet.

To run: first start the postgres server by hand pointing at the appropriate database, then
run this script - no arguments needed.
"""

import pg
import pgdb

def query(db, sql, params=()):
    
    cursor = db.cursor()
    cursor.execute(sql, params)
    return cursor

def rowsForProperty(propelement):
    pname = PropertyName.fromElement(propelement)
    return query(db, """
        select RESOURCE_ID, VALUE
        from RESOURCE_PROPERTY
        where NAME = %s
    """, (pname.toString(),)
    )

def removeProperty(propelement):
    pname = PropertyName.fromElement(propelement)
    return query(db, """
        delete from RESOURCE_PROPERTY
        where NAME = %s
    """, (pname.toString(),)
    )

if __name__ == "__main__":

    db = pgdb.connect(database='caldav', host='localhost')

    # Alter the CALENDAR_OBJECT table and add columns
    print "Alter the CALENDAR_OBJECT table"
    try:
        query(db, """
            alter table CALENDAR_OBJECT
            add column
              ACCESS           integer default 0 not null,
            add column
              SCHEDULE_OBJECT  boolean default false not null,
            add column
              SCHEDULE_ETAGS   text    default null,
            add column
              PRIVATE_COMMENTS boolean default false not null;

            -- Enumeration of calendar access types
            
            create table CALENDAR_ACCESS_TYPE (
              ID          integer     primary key,
              DESCRIPTION varchar(32) not null unique
            );
            
            insert into CALENDAR_ACCESS_TYPE values (0, ''             );
            insert into CALENDAR_ACCESS_TYPE values (1, 'public'       );
            insert into CALENDAR_ACCESS_TYPE values (2, 'private'      );
            insert into CALENDAR_ACCESS_TYPE values (3, 'confidential' );
            insert into CALENDAR_ACCESS_TYPE values (4, 'restricted'   );
        """)
        
    except pg.DatabaseError, e:
        if str(e).find("already exists") == -1:
            print "Fatal SQL error: %s" % (e,)
            sys.exit(1)
    db.commit()
    
    # Copy and remove each dead property
    
    # TwistedCalendarAccessProperty - copy string value into column.
    print "Move TwistedCalendarAccessProperty"
    for row in rowsForProperty(TwistedCalendarAccessProperty):
        resource_id, value = row
        prop = WebDAVDocument.fromString(value).root_element
        mapped = {
            "":                           0,
            Component.ACCESS_PUBLIC:      1,
            Component.ACCESS_PRIVATE:     2,
            Component.ACCESS_CONFIDENTIAL:3,
            Component.ACCESS_RESTRICTED:  4,
        }[str(prop)]
        query(db, """
            update CALENDAR_OBJECT
            set ACCESS = %s
            where RESOURCE_ID = %s
        """, (mapped, resource_id,)
        )
    removeProperty(TwistedCalendarAccessProperty)
    db.commit()
    
    # TwistedSchedulingObjectResource - copy boolean value into column.
    print "Move TwistedSchedulingObjectResource"
    for row in rowsForProperty(TwistedSchedulingObjectResource):
        resource_id, value = row
        prop = WebDAVDocument.fromString(value).root_element
        query(db, """
            update CALENDAR_OBJECT
            set SCHEDULE_OBJECT = %s
            where RESOURCE_ID = %s
        """, (str(prop), resource_id,)
        )
    removeProperty(TwistedSchedulingObjectResource)
    db.commit()
    
    # TwistedScheduleMatchETags - copy string-list value into column.
    print "Move TwistedScheduleMatchETags"
    for row in rowsForProperty(TwistedScheduleMatchETags):
        resource_id, value = row
        etags = [str(etag) for etag in WebDAVDocument.fromString(value).root_element.children]
        query(db, """
            update CALENDAR_OBJECT
            set SCHEDULE_ETAGS = %s
            where RESOURCE_ID = %s
        """, (",".join(etags), resource_id,)
        )
    removeProperty(TwistedScheduleMatchETags)
    db.commit()

    # TwistedCalendarHasPrivateCommentsProperty - copy boolean true value into column.
    print "Move TwistedCalendarHasPrivateCommentsProperty"
    for row in rowsForProperty(TwistedCalendarHasPrivateCommentsProperty):
        resource_id, value = row
        prop = WebDAVDocument.fromString(value).root_element
        query(db, """
            update CALENDAR_OBJECT
            set PRIVATE_COMMENTS = true
            where RESOURCE_ID = %s
        """, (resource_id,)
        )
    removeProperty(TwistedCalendarHasPrivateCommentsProperty)
    db.commit()
    
    # Create the CALENDAR_HOME_METADATA table
    print "Create the CALENDAR_HOME_METADATA table"
    try:
        query(db, """
            ----------------------------
            -- Calendar Home Metadata --
            ----------------------------
            
            create table CALENDAR_HOME_METADATA (
              RESOURCE_ID      integer      not null references CALENDAR_HOME on delete cascade,
              QUOTA_USED_BYTES integer      default 0 not null
            );
        """)
        
        # Provision with empty data
        query(db, """
            insert into CALENDAR_HOME_METADATA
            select RESOURCE_ID from CALENDAR_HOME
        """, ()
        )
        
    except pg.DatabaseError, e:
        if str(e).find("already exists") == -1:
            print "Fatal SQL error: %s" % (e,)
            sys.exit(1)
    db.commit()
    
    # Alter the ADDRESSBOOK_HOME_METADATA table
    print "Create the ADDRESSBOOK_HOME_METADATA table"
    try:
        query(db, """
            --------------------------------
            -- AddressBook Home Meta-data --
            --------------------------------
            
            create table ADDRESSBOOK_HOME_METADATA (
              RESOURCE_ID      integer      not null references ADDRESSBOOK_HOME on delete cascade,
              QUOTA_USED_BYTES integer      default 0 not null
            );
        """)
        
        # Provision with empty data
        query(db, """
            insert into ADDRESSBOOK_HOME_METADATA
            select RESOURCE_ID from ADDRESSBOOK_HOME
        """, ()
        )
        
    except pg.DatabaseError, e:
        if str(e).find("already exists") == -1:
            print "Fatal SQL error: %s" % (e,)
            sys.exit(1)
    db.commit()
    
    # Copy and remove each dead property
    
    # TwistedQuotaUsedProperty - copy string value into column.
    print "Move TwistedQuotaUsedProperty"
    for row in rowsForProperty(TwistedQuotaUsedProperty):
        resource_id, value = row
        prop = WebDAVDocument.fromString(value).root_element
        
        # Since we don't know whether the resource-id is a calendar home or addressbook home
        # just try updating both tables - the one that does not match will simply be ignored.
        query(db, """
            update CALENDAR_HOME_METADATA
            set QUOTA_USED_BYTES = %s
            where RESOURCE_ID = %s
        """, (int(str(prop)), resource_id,)
        )
        query(db, """
            update ADDRESSBOOK_HOME_METADATA
            set QUOTA_USED_BYTES = %s
            where RESOURCE_ID = %s
        """, (int(str(prop)), resource_id,)
        )
    removeProperty(TwistedQuotaUsedProperty)
    db.commit()
    
