CalendarServer: Annotated Schema
================================

# Introduction

This document serves as a description of the [CalendarServer SQL schema](https://github.com/apple/ccs-calendarserver/blob/master/txdav/common/datastore/sql_schema/current.sql). The goal is to document the tables, their relationships, how they map to app-layer (CalDAV) actions, how they interact with the directory system, and how they are used for scheduling and other internal operations. This document will concentrate on the calendaring specific schema elements and skip discussion of the contacts elements, but the contacts schema is a simplified version of calendar, so the same basic concepts apply.

The CalendarServer database stores the calendaring data associated with a user. The actual details of a user are not stored in the database, instead they are assumed to come from the directory service configured for use with CalendarServer. To relate data in the database to directory users, the directory service GUID or UUID record entry for each calendar user is used as a "key" in the database. The directory service is assumed to be read-only, but some user-specific data can be modified on the server - in particular calendaring delegate relationships - and we do maintain separate tables in the database for that. Additionally, the server needs to detect changes to group membership so group membership information is also cached in the database.

Each key piece of data in the database will have an associated unique-id, derived from a database `SEQUENCE` value, and these are used for the foreign key relationships between tables.
 
# CALENDAR\_HOME

```sql
create table CALENDAR_HOME (
  RESOURCE_ID      integer      primary key default nextval('RESOURCE_ID_SEQ'),
  OWNER_UID        varchar(255) not null,
  STATUS           integer      default 0 not null,
  DATAVERSION      integer      default 0 not null
);
```

This table provides the main mapping between a directory record GUID/UUID and the calendar data associated with a user. The `OWNER_UID` column is the directory record GUID/UUID value. The `RESOURCE_ID` is used as the foreign key in other tables to define ownership of calendar and calendar object data. A `CALENDAR_HOME` table entry is provisioned the first time a calendar user logs in and makes a CalDAV request, or the first time a calendar user is referred to as an attendee of an event or a sharee of a calendar. The server always checks the directory record first to ensure a calendar user exists and is active before creating the `CALENDAR_HOME` entry for that user.

The `STATUS` column is used to represent different internal modes for the corresponding associated calendar data. Details TBD.

The `DATAVERSION` column is used to support on-demand data upgrades. In some cases it may be necessary to upgrade data on the server - that could be either calendar data or database related metadata. Rather than lock the database and upgrade all the data at once, we have the option to upgrade data on demand or in the background. The `DATAVERSION` column is used to track the status of that. The value is an integer representing the current version of the data. If that version is less than the expected version, then an upgrade is needed and the appropriate tools can key of that to initiate background or on-demand processing.

# CALENDAR\_HOME\_METADATA

```sql
create table CALENDAR_HOME_METADATA (
  RESOURCE_ID              integer     primary key references CALENDAR_HOME on delete cascade,
  QUOTA_USED_BYTES         integer     default 0 not null,
  TRASH                    integer     default null references CALENDAR on delete set null,
  DEFAULT_EVENTS           integer     default null references CALENDAR on delete set null,
  DEFAULT_TASKS            integer     default null references CALENDAR on delete set null,
  DEFAULT_POLLS            integer     default null references CALENDAR on delete set null,
  ALARM_VEVENT_TIMED       text        default null,
  ALARM_VEVENT_ALLDAY      text        default null,
  ALARM_VTODO_TIMED        text        default null,
  ALARM_VTODO_ALLDAY       text        default null,
  AVAILABILITY             text        default null,
  CREATED                  timestamp   default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED                 timestamp   default timezone('UTC', CURRENT_TIMESTAMP)
);
```

This table has one row for every row in `CALENDAR_HOME`. It maintains data about a user's calendar home that changes, potentially fairly frequently. Rather than store that in the `CALENDAR_HOME` table, it was found to be better to have an associated table to maintain the data - primarily to avoid lock contention issues. Data is this table can change as a direct result of a user action (e.g., a `PROPPATCH` of properties on the user's calendar home resource), or as the side-effect of other changes (e.g., the `QUOTA_USED_BYTES` is changed each time an attachment is added, changed, or removed).
 