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


"""
Tool to manage schema upgrade of SQL database during internal development phase as we don't have
a "real" upgrade in place just yet.

To run: first start the postgres server by hand pointing at the appropriate database, then
run this script - no arguments needed.
"""

from twext.web2.dav.element.parser import WebDAVDocument
from twext.web2.dav.resource import TwistedQuotaUsedProperty
from twistedcaldav.caldavxml import ScheduleTag
from twistedcaldav.customxml import TwistedCalendarHasPrivateCommentsProperty,\
    TwistedCalendarAccessProperty, TwistedSchedulingObjectResource,\
    TwistedScheduleMatchETags
from twistedcaldav.ical import Component
from txdav.base.propertystore.base import PropertyName
import pg
import pgdb
import sys

def query(db, sql, params=()):
    
    cursor = db.cursor()
    cursor.execute(sql, params)
    return cursor

def queryIgnoreAlreadyExists(db, sql, params=()):
    
    try:
        query(db, sql, params)
    except pg.DatabaseError, e:
        if str(e).find("already exists") == -1:
            print "Fatal SQL error: %s" % (e,)
            sys.exit(1)
    db.commit()
    
def queryExit(db, sql, params=()):
    
    try:
        query(db, sql, params)
    except pg.DatabaseError, e:
        print "Fatal SQL error: %s" % (e,)
        sys.exit(1)
    db.commit()
    
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

    # Add CALENDAR_HOME index
    print "Create the CALENDAR_HOME_OWNER_UID index"
    queryIgnoreAlreadyExists(db, "create index CALENDAR_HOME_OWNER_UID on CALENDAR_HOME(OWNER_UID)")
    
    # Create the CALENDAR_HOME_METADATA table and provision with empty data
    print "Create the CALENDAR_HOME_METADATA table"
    queryIgnoreAlreadyExists(db, """
        ----------------------------
        -- Calendar Home Metadata --
        ----------------------------
        
        create table CALENDAR_HOME_METADATA (
          RESOURCE_ID      integer      not null references CALENDAR_HOME on delete cascade,
          QUOTA_USED_BYTES integer      default 0 not null
        );

        create index CALENDAR_HOME_METADATA_RESOURCE_ID
            on CALENDAR_HOME_METADATA(RESOURCE_ID);

        insert into CALENDAR_HOME_METADATA
          select RESOURCE_ID from CALENDAR_HOME
    """)

    # Add INVITE index
    print "Create indexes for INVITE table"
    queryIgnoreAlreadyExists(db, """
        create index INVITE_INVITE_UID on INVITE(INVITE_UID);
    """)
    queryIgnoreAlreadyExists(db, """
        create index INVITE_RESOURCE_ID on INVITE(INVITE_UID);
    """)
    queryIgnoreAlreadyExists(db, """
        create index INVITE_HOME_RESOURCE_ID on INVITE(INVITE_UID);
    """)
    
    # Add NOTIFICATION_HOME index
    print "Create the NOTIFICATION_HOME_OWNER_UID index"
    queryIgnoreAlreadyExists(db, "create index NOTIFICATION_HOME_OWNER_UID on NOTIFICATION_HOME(OWNER_UID)")

    # Alter the NOTIFICATION table
    print "Alter the NOTIFICATION table and add indexes"
    queryIgnoreAlreadyExists(db, """
        alter table NOTIFICATION
        alter column
          XML_TYPE         TYPE varchar(255),
        alter column
          XML_DATA         TYPE text;
    """)
    queryIgnoreAlreadyExists(db, """
        create index NOTIFICATION_NOTIFICATION_HOME_RESOURCE_ID on
          NOTIFICATION(NOTIFICATION_HOME_RESOURCE_ID);
    """)
    queryIgnoreAlreadyExists(db, """
        create index NOTIFICATION_NOTIFICATION_UID on NOTIFICATION(NOTIFICATION_UID);
    """)
    
    # Add CALENDAR_BIND index
    print "Create indexes for CALENDAR_BIND table"
    queryIgnoreAlreadyExists(db, """
        create index CALENDAR_BIND_HOME_RESOURCE_ID on
          CALENDAR_BIND(CALENDAR_HOME_RESOURCE_ID);
    """)
    queryIgnoreAlreadyExists(db, """
        create index CALENDAR_BIND_RESOURCE_ID on
          CALENDAR_BIND(CALENDAR_RESOURCE_ID);
    """)
    
    # Alter the CALENDAR_OBJECT table and add columns
    print "Alter the CALENDAR_OBJECT table"
    queryIgnoreAlreadyExists(db, """
        alter table CALENDAR_OBJECT
            alter column
              ATTACHMENTS_MODE TYPE integer,
            alter column
              ATTACHMENTS_MODE set default 0,
            add column
              DROPBOX_ID       varchar(255),
            add column
              ACCESS           integer default 0 not null,
            add column
              SCHEDULE_OBJECT  boolean default false not null,
            add column
              SCHEDULE_TAG     varchar(36)  default null,
            add column
              SCHEDULE_ETAGS   text    default null,
            add column
              PRIVATE_COMMENTS boolean default false not null;
    """)
    queryIgnoreAlreadyExists(db, """
        create index CALENDAR_OBJECT_CALENDAR_RESOURCE_ID on
          CALENDAR_OBJECT(CALENDAR_RESOURCE_ID);
    """)
    queryIgnoreAlreadyExists(db, """
        create index CALENDAR_OBJECT_CALENDAR_RESOURCE_ID_AND_ICALENDAR_UID on
          CALENDAR_OBJECT(CALENDAR_RESOURCE_ID, ICALENDAR_UID);
    """)
    queryIgnoreAlreadyExists(db, """
        create index CALENDAR_OBJECT_CALENDAR_RESOURCE_ID_RECURRANCE_MAX on
          CALENDAR_OBJECT(CALENDAR_RESOURCE_ID, RECURRANCE_MAX);
    """)
    queryIgnoreAlreadyExists(db, """
        create index CALENDAR_OBJECT_ORGANIZER_OBJECT on
          CALENDAR_OBJECT(ORGANIZER_OBJECT);
    """)
    queryIgnoreAlreadyExists(db, """
        create index CALENDAR_OBJECT_DROPBOX_ID on
          CALENDAR_OBJECT(DROPBOX_ID);
    """)
    queryIgnoreAlreadyExists(db, """
        delete from CALENDAR_OBJECT_ATTACHMENTS_MODE;
        insert into CALENDAR_OBJECT_ATTACHMENTS_MODE values (0, 'none' );
        insert into CALENDAR_OBJECT_ATTACHMENTS_MODE values (1, 'read' );
        insert into CALENDAR_OBJECT_ATTACHMENTS_MODE values (2, 'write');
    """)
    queryIgnoreAlreadyExists(db, """
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
    
    # Add TIME_RANGE index
    print "Create indexes for TIME_RANGE table"
    queryIgnoreAlreadyExists(db, """
        create index TIME_RANGE_CALENDAR_RESOURCE_ID on
          TIME_RANGE(CALENDAR_RESOURCE_ID);
    """)
    queryIgnoreAlreadyExists(db, """
        create index TIME_RANGE_CALENDAR_OBJECT_RESOURCE_ID on
          TIME_RANGE(CALENDAR_OBJECT_RESOURCE_ID);
    """)
    
    # Add TRANSPARENCY index
    print "Create indexes for TRANSPARENCY table"
    queryIgnoreAlreadyExists(db, """
        create index TRANSPARENCY_TIME_RANGE_INSTANCE_ID on
          TRANSPARENCY(TIME_RANGE_INSTANCE_ID);
    """)
    
    # Alter the ATTACHMENT table
    print "Alter the ATTACHMENT table"
    queryExit(db, """
        delete from ATTACHMENT;
    """)
    queryIgnoreAlreadyExists(db, """
        alter table ATTACHMENT
            drop column if exists
              CALENDAR_OBJECT_RESOURCE_ID,
            add column
              CALENDAR_HOME_RESOURCE_ID   integer       not null references CALENDAR_HOME,
            add column
              DROPBOX_ID                  varchar(255)  not null,
            add
              unique(DROPBOX_ID, PATH);
    """)
    queryIgnoreAlreadyExists(db, """
        create index ATTACHMENT_DROPBOX_ID on ATTACHMENT(DROPBOX_ID);
    """)
    
    # Drop the ITIP_MESSAGE table
    print "Drop the ITIP_MESSAGE table"
    queryExit(db, """
        drop table if exists ITIP_MESSAGE;
    """)
    
    # Add ADDRESSBOOK_HOME index
    print "Create the ADDRESSBOOK_HOME_OWNER_UID index"
    queryIgnoreAlreadyExists(db, "create index ADDRESSBOOK_HOME_OWNER_UID on ADDRESSBOOK_HOME(OWNER_UID)")
    
    # Create the ADDRESSBOOK_HOME_METADATA table and provision with empty data
    print "Create the ADDRESSBOOK_HOME_METADATA table"
    queryIgnoreAlreadyExists(db, """
        --------------------------------
        -- AddressBook Home Meta-data --
        --------------------------------
        
        create table ADDRESSBOOK_HOME_METADATA (
          RESOURCE_ID      integer      not null references ADDRESSBOOK_HOME on delete cascade,
          QUOTA_USED_BYTES integer      default 0 not null
        );

        create index ADDRESSBOOK_HOME_METADATA_RESOURCE_ID
            on ADDRESSBOOK_HOME_METADATA(RESOURCE_ID);

        insert into ADDRESSBOOK_HOME_METADATA
            select RESOURCE_ID from ADDRESSBOOK_HOME
    """)
    
    # Add ADDRESSBOOK_BIND index
    print "Create indexes for ADDRESSBOOK_BIND table"
    queryIgnoreAlreadyExists(db, """
        create index ADDRESSBOOK_BIND_HOME_RESOURCE_ID on
          ADDRESSBOOK_BIND(ADDRESSBOOK_HOME_RESOURCE_ID);
    """)
    queryIgnoreAlreadyExists(db, """
        create index ADDRESSBOOK_BIND_RESOURCE_ID on
          ADDRESSBOOK_BIND(ADDRESSBOOK_RESOURCE_ID);
    """)
    
    # Add ADDRESSBOOK_OBJECT index
    print "Create indexes for ADDRESSBOOK_OBJECT table"
    queryIgnoreAlreadyExists(db, """
        create index ADDRESSBOOK_OBJECT_ADDRESSBOOK_RESOURCE_ID on
          ADDRESSBOOK_OBJECT(ADDRESSBOOK_RESOURCE_ID);
    """)
    
    # Alter the CALENDAR_OBJECT_REVISIONS table
    print "Alter the CALENDAR_OBJECT_REVISIONS table"
    queryExit(db, """
        alter table CALENDAR_OBJECT_REVISIONS
            alter column
              REVISION   set default nextval('REVISION_SEQ');
    """)
    queryIgnoreAlreadyExists(db, """
        create index CALENDAR_OBJECT_REVISIONS_HOME_RESOURCE_ID
          on CALENDAR_OBJECT_REVISIONS(CALENDAR_HOME_RESOURCE_ID);
    """)
    queryIgnoreAlreadyExists(db, """
        create index CALENDAR_OBJECT_REVISIONS_RESOURCE_ID
          on CALENDAR_OBJECT_REVISIONS(CALENDAR_RESOURCE_ID);
    """)
    
    # Alter the ADDRESSBOOK_OBJECT_REVISIONS table
    print "Alter the ADDRESSBOOK_OBJECT_REVISIONS table"
    queryExit(db, """
        alter table ADDRESSBOOK_OBJECT_REVISIONS
            alter column
              REVISION   set default nextval('REVISION_SEQ');
    """)
    queryIgnoreAlreadyExists(db, """
        create index ADDRESSBOOK_OBJECT_REVISIONS_HOME_RESOURCE_ID
          on ADDRESSBOOK_OBJECT_REVISIONS(ADDRESSBOOK_HOME_RESOURCE_ID);
    """)
    queryIgnoreAlreadyExists(db, """
        create index ADDRESSBOOK_OBJECT_REVISIONS_RESOURCE_ID
          on ADDRESSBOOK_OBJECT_REVISIONS(ADDRESSBOOK_RESOURCE_ID);
    """)
    
    # Alter the NOTIFICATION_OBJECT_REVISIONS table
    print "Alter the NOTIFICATION_OBJECT_REVISIONS table"
    queryExit(db, """
        alter table NOTIFICATION_OBJECT_REVISIONS
            alter column
              REVISION   set default nextval('REVISION_SEQ');
    """)
    queryIgnoreAlreadyExists(db, """
        create index NOTIFICATION_OBJECT_REVISIONS_HOME_RESOURCE_ID
          on NOTIFICATION_OBJECT_REVISIONS(NOTIFICATION_HOME_RESOURCE_ID);
    """)
    
    # Add CALENDARSERVER table
    print "Add the CALENDARSERVER table"
    queryIgnoreAlreadyExists(db, """
        --------------------
        -- Schema Version --
        --------------------
        
        create table CALENDARSERVER (
          NAME                          varchar(255),
          VALUE                         varchar(255),
          unique(NAME)
        );
        
        insert into CALENDARSERVER values ('VERSION', '3');
    """)
    

    
    
    
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
        mapped = {
            "":      "true",
            "true":  "true",
            "false": "false",
        }[str(prop)]
        query(db, """
            update CALENDAR_OBJECT
            set SCHEDULE_OBJECT = %s
            where RESOURCE_ID = %s
        """, (mapped, resource_id,)
        )
    removeProperty(TwistedSchedulingObjectResource)
    db.commit()
    
    # ScheduleTag - copy string value into column.
    print "Move ScheduleTag"
    for row in rowsForProperty(ScheduleTag):
        resource_id, value = row
        prop = WebDAVDocument.fromString(value).root_element
        query(db, """
            update CALENDAR_OBJECT
            set SCHEDULE_TAG = %s
            where RESOURCE_ID = %s
        """, (str(prop), resource_id,)
        )
    removeProperty(ScheduleTag)
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
    
    # Quota is now only calculated on attachments and we are removing attachments in this upgrade
    
    # TwistedQuotaUsedProperty - copy string value into column.
    print "Remove TwistedQuotaUsedProperty"
    removeProperty(TwistedQuotaUsedProperty)
    db.commit()
    
