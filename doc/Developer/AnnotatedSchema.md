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

# CALENDAR

```sql
create table CALENDAR (
  RESOURCE_ID integer   primary key default nextval('RESOURCE_ID_SEQ')
);
```

This table represents a calendar - basically a container for calendar objects. The `CALENDAR_OBJECT` table has a single `CALENDAR` reference for each entry - i.e., there is a one-to-many relationship between `CALENDAR` and `CALENDAR_OBJECT` entries. However, the relationship between calendars and calendar homes is more complicated: typically a calendar will be owned by a specific user, so that represents a one-to-many relationship between calendar homes and calendars. However, calendars can also be shared to other users such that they appear in those other users' calendar homes. So that gives rise to a many-to-many relationship between calendar homes and calendars. That many-to-many relationship is managed via the `CALENDAR_BIND` table, described below. Each row in that table defines a relationship between one calendar home and one calendar.

# CALENDAR\_METADATA

```sql
create table CALENDAR_METADATA (
  RESOURCE_ID           integer      primary key references CALENDAR on delete cascade,
  SUPPORTED_COMPONENTS  varchar(255) default null,
  CHILD_TYPE            integer      default 0 not null,
  TRASHED               timestamp    default null,
  IS_IN_TRASH           boolean      default false not null, -- collection is in the trash
  CREATED               timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED              timestamp    default timezone('UTC', CURRENT_TIMESTAMP)
);
```

This table plays a similar role to `CALENDAR_HOME_METADATA` in that it maintains mutable state for calendars, again separated from the main table in order to reduce lock contention issues.

# CALENDAR\_BIND

```sql
create table CALENDAR_BIND (
  CALENDAR_HOME_RESOURCE_ID integer      not null references CALENDAR_HOME,
  CALENDAR_RESOURCE_ID      integer      not null references CALENDAR on delete cascade,
  CALENDAR_RESOURCE_NAME    varchar(255) not null,
  BIND_MODE                 integer      not null,
  BIND_STATUS               integer      not null,
  BIND_REVISION             integer      default 0 not null,
  BIND_UID                  varchar(36)  default null,
  MESSAGE                   text,
  TRANSP                    integer      default 0 not null,
  ALARM_VEVENT_TIMED        text         default null,
  ALARM_VEVENT_ALLDAY       text         default null,
  ALARM_VTODO_TIMED         text         default null,
  ALARM_VTODO_ALLDAY        text         default null,
  TIMEZONE                  text         default null,

  primary key (CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_ID),
  unique (CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_NAME)
);
```

This table maintains the mapping between a calendar and the calendar home it is meant to appear in. Each row has a column for the referenced calendar home and calendar entry defining the "bind". The type of "bind" is defined by the `BIND_MODE` column. There are several values for `BIND_MODE` but the primary purpose is to distinguish between "owned" and "shared" calendars. For any pair of calendar home and calendar, there can (must be) only one owned calendar: `BIND_MODE == 0`, but there can be many shared calendars in various states (invited, accepted, declined etc) as indicated by the `BIND_STATUS` value.

This table also maintains per-user calendar state, such as alarms and associated time zone, which may differ between the various users who have access to the calendar.

# CALENDAR\_OBJECT

```sql
create table CALENDAR_OBJECT (
  RESOURCE_ID          integer      primary key default nextval('RESOURCE_ID_SEQ'),
  CALENDAR_RESOURCE_ID integer      not null references CALENDAR on delete cascade,
  RESOURCE_NAME        varchar(255) not null,
  ICALENDAR_TEXT       text         not null,
  ICALENDAR_UID        varchar(255) not null,
  ICALENDAR_TYPE       varchar(255) not null,
  ATTACHMENTS_MODE     integer      default 0 not null,
  DROPBOX_ID           varchar(255),
  ORGANIZER            varchar(255),
  RECURRANCE_MIN       date,
  RECURRANCE_MAX       date,
  ACCESS               integer      default 0 not null,
  SCHEDULE_OBJECT      boolean      default false,
  SCHEDULE_TAG         varchar(36)  default null,
  SCHEDULE_ETAGS       text         default null,
  PRIVATE_COMMENTS     boolean      default false not null,
  MD5                  char(32)     not null,
  TRASHED              timestamp    default null,
  ORIGINAL_COLLECTION  integer      default null,
  CREATED              timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED             timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  DATAVERSION          integer      default 0 not null
);
```

This table maintains the data and metadata for calendar objects. Each entry references a single calendar, in which the calendar object is meant to appear. The actual iCalendar data is stored as text in the `ICALENDAR_TEXT` column. The other columns maintain associated metadata used by the business logic for various purposes. The `DATAVERSION` column is used in a similar manner to the column with the same name on the `CALENDAR_HOME` to support incremental, or on-demand, data upgrades. `RECURRANCE_MIN` and `RECURRANCE_MAX` are used to define the range of validity for expanded time range instance data for the calendar object, as stored in the `TIME_RANGE` table, and used during time range and freebusy queries. Other columns such as `ICALENDAR_UID`, `ACCESS`, and `PRIVATE_COMMENTS`, provide quick access to frequently used data that would otherwise have to be read and parsed from the actual iCalendar data.

# TIME\_RANGE

```sql
create table TIME_RANGE (
  INSTANCE_ID                 integer        primary key default nextval('INSTANCE_ID_SEQ'),
  CALENDAR_RESOURCE_ID        integer        not null references CALENDAR on delete cascade,
  CALENDAR_OBJECT_RESOURCE_ID integer        not null references CALENDAR_OBJECT on delete cascade,
  FLOATING                    boolean        not null,
  START_DATE                  timestamp      not null,
  END_DATE                    timestamp      not null,
  FBTYPE                      integer        not null,
  TRANSPARENT                 boolean        not null
);
```

This table maintains a list of expanded recurrence instances for the associated calendar object. We want time range and freebusy queries to be fast, which means we don't want to have to read, parse, and carry out recurrence expansion on every calendar object in a calendar each time one of those queries is done (since they happen frequently). Instead, we do the instance expansion once and cache the result in the `TIME_RANGE` table so that the queries can directly target those tables to return results. However, this is an on-demand cache, so typically we don't expand the instances when the calendar object is created or updated, but instead wait for the first time range or freebusy query to occur and then do the expansion. The reason for that is that sometimes a calendar object can be updated multiple times in rapid succession, without a time range or freebusy query occurring in between, so the time range expansion work would be wasted for all but the last update. Also, the server does not cache all instances of an event, but instead only caches over a period of past/future time to limit the amount of data that needs to be stored since some recurring events can be unbounded or long lived, yet most time range or freebusy queries are done over short periods of time centered on the current time.

# PERUSER

```sql
create table PERUSER (
  TIME_RANGE_INSTANCE_ID      integer      not null references TIME_RANGE on delete cascade,
  USER_ID                     varchar(255) not null,
  TRANSPARENT                 boolean      not null,
  ADJUSTED_START_DATE         timestamp    default null,
  ADJUSTED_END_DATE           timestamp    default null
);
```

Another aspect of time range data is that there is a per-user component to it: specifically, a single calendar object appears in a single calendar, but that calendar could be shared with multiple users, each of which can set their own travel time and transparency status on the event. As a result, we need to maintain the per-user data in such a way that we can pick the appropriate items to use for a time range of freebusy query depending on which user is carrying out the query request. The `PERUSER` table is used for that purpose. If a user with access to a calendar object has per-user data that differs from the default for any instance of the data, then they will have an associated entry in the `PERUSER` table that relates their directory GUID/UUID - via the `USER_ID` column - to the specific instance in the `TIME_RANGE` table. The time range and freebusy queries then include this table as a join to ensure the required information is extracted.

# ATTACHMENT

```sql
create table ATTACHMENT (
  ATTACHMENT_ID               integer           primary key default nextval('ATTACHMENT_ID_SEQ'),
  CALENDAR_HOME_RESOURCE_ID   integer           not null references CALENDAR_HOME,
  DROPBOX_ID                  varchar(255),
  CONTENT_TYPE                varchar(255)      not null,
  SIZE                        integer           not null,
  MD5                         char(32)          not null,
  CREATED                     timestamp default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED                    timestamp default timezone('UTC', CURRENT_TIMESTAMP),
  PATH                        varchar(1024)     not null
);
```

This table maintains information about attachments stored on the server. Each attachment has a specific user as its owner (identified by the `CALENDAR_HOME_RESOURCE_ID` column). That is the user whose quota will be impacted by the attachment. The attachment data is stored as a file on disk - not in the database.

# ATTACHMENT\_CALENDAR\_OBJECT

This table maintains a mapping between attachments and calendar objects and is needed because a single attachment can appear in multiple calendar objects.

# RESOURCE\_PROPERTY

```sql
create table RESOURCE_PROPERTY (
  RESOURCE_ID integer      not null,
  NAME        varchar(255) not null,
  VALUE       text         not null,
  VIEWER_UID  varchar(255)
);
```

Each WebDAV resource at the application layer can have associated WebDAV "properties", which can be server or user defined metadata. Server specific metadata is usually stored in specific columns in the relevant calendar home, calendar, or calendar object data. User defined properties might be stored in those tables if we need fast access to the data, or it will be stored in the `RESOURCE_PROPERTY` table, with the value being the XML "blob" used by WebDAV.

# CALENDAR\_OBJECT\_REVISIONS

```sql
create table CALENDAR_OBJECT_REVISIONS (
  CALENDAR_HOME_RESOURCE_ID integer      not null references CALENDAR_HOME,
  CALENDAR_RESOURCE_ID      integer      references CALENDAR,
  CALENDAR_NAME             varchar(255) default null,
  RESOURCE_NAME             varchar(255),
  REVISION                  integer      default nextval('REVISION_SEQ') not null,
  DELETED                   boolean      not null,
  MODIFIED                  timestamp    default timezone('UTC', CURRENT_TIMESTAMP) not null
);
```

To allow clients to incrementally update their cache of data from the server, the server supports a WebDAV "sync" REPORT. In order to carry out that query the server needs to track changes and deletions of all resources: calendars and calendar objects. The `CALENDAR_OBJECT_REVISIONS` table is used to track that state and to provide results for the sync query, by tracking the changes to both calendars and calendar objects in one place (so that a single query can be scoped to just or calendar or an entire calendar home). When a calendar or calendar object is deleted, its entry in the `CALENDAR_BIND` or `CALENDAR_OBJECT` table is removed, however the sync query needs to still maintain at least the name of that resource to report the deletion back to the client, so this table needs to maintain such "tomb stones".

# APN\_SUBSCRIPTIONS

```sql
create table APN_SUBSCRIPTIONS (
  TOKEN                         varchar(255) not null,
  RESOURCE_KEY                  varchar(255) not null,
  MODIFIED                      integer      not null,
  SUBSCRIBER_GUID               varchar(255) not null,
  USER_AGENT                    varchar(255) default null,
  IP_ADDR                       varchar(255) default null
);
```

This table tracks client subscriptions to APNS push notifications, so that when a change on the server occurs, the server can determine which clients need to be sent push notifications. We store MODIFIED (seconds since the Epoch) because we purge subscriptions older than config.SubscriptionPurgeSeconds.  Clients are expected to re-subscribe at least every config.SubscriptionRefreshIntervalSeconds.  SUBSCRIBER_GUID, USER_AGENT, and IP_ADDR are used purely for diagnosing problems via the push command utility.

# IMIP\_TOKENS

```sql
create table IMIP_TOKENS (
  TOKEN                         varchar(255) not null,
  ORGANIZER                     varchar(255) not null,
  ATTENDEE                      varchar(255) not null,
  ICALUID                       varchar(255) not null,
  ACCESSED                      timestamp    default timezone('UTC', CURRENT_TIMESTAMP)
);
```

When scheduling messages are sent via email to calendar users not hosted on the server, the server needs a way to be able to track replies coming back from the attendees based on information in the iCalendar reply message. This table is used to track sufficient information for the server to be able to relate the iCalendar data in an email reply with the calendar object that generated the original request.

# *\_MIGRATION

The set of tables with the `_MIGRATION` suffix are used by the incremental cross-pod migration process to track the status of migrating data.

# CALENDARSERVER

```sql
create table CALENDARSERVER (
  NAME                          varchar(255) primary key, -- implicit index
  VALUE                         varchar(255)
);
```

This table maintains global state about the overall database using a "key-value" data mode. The `VERSION` key represents the current SQL schema version present in the database, and is checked on server startup to determine whether a schema upgrade is needed. Other `*-DATAVERSION` keys are used to determine whether data upgrades are needed.
