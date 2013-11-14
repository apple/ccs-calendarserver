-- -*- test-case-name: txdav.caldav.datastore.test.test_sql,txdav.carddav.datastore.test.test_sql -*-

----
-- Copyright (c) 2010-2013 Apple Inc. All rights reserved.
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
-- http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.
----


-----------------
-- Resource ID --
-----------------

create sequence RESOURCE_ID_SEQ;


-------------------------
-- Cluster Bookkeeping --
-------------------------

-- Information about a process connected to this database.

-- Note that this must match the node info schema in twext.enterprise.queue.
create table NODE_INFO (
  HOSTNAME  varchar(255) not null,
  PID       integer      not null,
  PORT      integer      not null,
  TIME      timestamp    not null default timezone('UTC', CURRENT_TIMESTAMP),

  primary key (HOSTNAME, PORT)
);

-- Unique named locks.  This table should always be empty, but rows are
-- temporarily created in order to prevent undesirable concurrency.
create table NAMED_LOCK (
    LOCK_NAME varchar(255) primary key
);


-------------------
-- Calendar Home --
-------------------

create table CALENDAR_HOME (
  RESOURCE_ID      integer      primary key default nextval('RESOURCE_ID_SEQ'), -- implicit index
  OWNER_UID        varchar(255) not null unique,                                 -- implicit index
  DATAVERSION      integer      default 0 not null
);

--------------
-- Calendar --
--------------

create table CALENDAR (
  RESOURCE_ID integer   primary key default nextval('RESOURCE_ID_SEQ') -- implicit index
);

----------------------------
-- Calendar Home Metadata --
----------------------------

create table CALENDAR_HOME_METADATA (
  RESOURCE_ID              integer     primary key references CALENDAR_HOME on delete cascade, -- implicit index
  QUOTA_USED_BYTES         integer     default 0 not null,
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

create index CALENDAR_HOME_METADATA_DEFAULT_EVENTS on
	CALENDAR_HOME_METADATA(DEFAULT_EVENTS);
create index CALENDAR_HOME_METADATA_DEFAULT_TASKS on
	CALENDAR_HOME_METADATA(DEFAULT_TASKS);
create index CALENDAR_HOME_METADATA_DEFAULT_POLLS on
	CALENDAR_HOME_METADATA(DEFAULT_POLLS);

-----------------------
-- Calendar Metadata --
-----------------------

create table CALENDAR_METADATA (
  RESOURCE_ID           integer      primary key references CALENDAR on delete cascade, -- implicit index
  SUPPORTED_COMPONENTS  varchar(255) default null,
  CREATED               timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED              timestamp    default timezone('UTC', CURRENT_TIMESTAMP)
);


---------------------------
-- Sharing Notifications --
---------------------------

create table NOTIFICATION_HOME (
  RESOURCE_ID integer      primary key default nextval('RESOURCE_ID_SEQ'), -- implicit index
  OWNER_UID   varchar(255) not null unique                                 -- implicit index
);

create table NOTIFICATION (
  RESOURCE_ID                   integer      primary key default nextval('RESOURCE_ID_SEQ'), -- implicit index
  NOTIFICATION_HOME_RESOURCE_ID integer      not null references NOTIFICATION_HOME,
  NOTIFICATION_UID              varchar(255) not null,
  XML_TYPE                      varchar(255) not null,
  XML_DATA                      text         not null,
  MD5                           char(32)     not null,
  CREATED                       timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED                      timestamp    default timezone('UTC', CURRENT_TIMESTAMP),

  unique(NOTIFICATION_UID, NOTIFICATION_HOME_RESOURCE_ID) -- implicit index
);

create index NOTIFICATION_NOTIFICATION_HOME_RESOURCE_ID on
	NOTIFICATION(NOTIFICATION_HOME_RESOURCE_ID);


-------------------
-- Calendar Bind --
-------------------

-- Joins CALENDAR_HOME and CALENDAR

create table CALENDAR_BIND (
  CALENDAR_HOME_RESOURCE_ID integer      not null references CALENDAR_HOME,
  CALENDAR_RESOURCE_ID      integer      not null references CALENDAR on delete cascade,
  CALENDAR_RESOURCE_NAME    varchar(255) not null,
  BIND_MODE                 integer      not null, -- enum CALENDAR_BIND_MODE
  BIND_STATUS               integer      not null, -- enum CALENDAR_BIND_STATUS
  BIND_REVISION				integer      default 0 not null,
  MESSAGE                   text,
  TRANSP                    integer      default 0 not null, -- enum CALENDAR_TRANSP
  ALARM_VEVENT_TIMED        text         default null,
  ALARM_VEVENT_ALLDAY       text         default null,
  ALARM_VTODO_TIMED         text         default null,
  ALARM_VTODO_ALLDAY        text         default null,
  TIMEZONE                  text         default null,

  primary key(CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_ID), -- implicit index
  unique(CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_NAME)     -- implicit index
);

create index CALENDAR_BIND_RESOURCE_ID on
	CALENDAR_BIND(CALENDAR_RESOURCE_ID);

-- Enumeration of calendar bind modes

create table CALENDAR_BIND_MODE (
  ID          integer     primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into CALENDAR_BIND_MODE values (0, 'own'  );
insert into CALENDAR_BIND_MODE values (1, 'read' );
insert into CALENDAR_BIND_MODE values (2, 'write');
insert into CALENDAR_BIND_MODE values (3, 'direct');

-- Enumeration of statuses

create table CALENDAR_BIND_STATUS (
  ID          integer     primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into CALENDAR_BIND_STATUS values (0, 'invited' );
insert into CALENDAR_BIND_STATUS values (1, 'accepted');
insert into CALENDAR_BIND_STATUS values (2, 'declined');
insert into CALENDAR_BIND_STATUS values (3, 'invalid');


-- Enumeration of transparency

create table CALENDAR_TRANSP (
  ID          integer     primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into CALENDAR_TRANSP values (0, 'opaque' );
insert into CALENDAR_TRANSP values (1, 'transparent');


---------------------
-- Calendar Object --
---------------------

create table CALENDAR_OBJECT (
  RESOURCE_ID          integer      primary key default nextval('RESOURCE_ID_SEQ'), -- implicit index
  CALENDAR_RESOURCE_ID integer      not null references CALENDAR on delete cascade,
  RESOURCE_NAME        varchar(255) not null,
  ICALENDAR_TEXT       text         not null,
  ICALENDAR_UID        varchar(255) not null,
  ICALENDAR_TYPE       varchar(255) not null,
  ATTACHMENTS_MODE     integer      default 0 not null, -- enum CALENDAR_OBJECT_ATTACHMENTS_MODE
  DROPBOX_ID           varchar(255),
  ORGANIZER            varchar(255),
  RECURRANCE_MIN       date,        -- minimum date that recurrences have been expanded to.
  RECURRANCE_MAX       date,        -- maximum date that recurrences have been expanded to.
  ACCESS               integer      default 0 not null,
  SCHEDULE_OBJECT      boolean      default false,
  SCHEDULE_TAG         varchar(36)  default null,
  SCHEDULE_ETAGS       text         default null,
  PRIVATE_COMMENTS     boolean      default false not null,
  MD5                  char(32)     not null,
  CREATED              timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED             timestamp    default timezone('UTC', CURRENT_TIMESTAMP),

  unique (CALENDAR_RESOURCE_ID, RESOURCE_NAME) -- implicit index

  -- since the 'inbox' is a 'calendar resource' for the purpose of storing
  -- calendar objects, this constraint has to be selectively enforced by the
  -- application layer.

  -- unique(CALENDAR_RESOURCE_ID, ICALENDAR_UID)
);

create index CALENDAR_OBJECT_CALENDAR_RESOURCE_ID_AND_ICALENDAR_UID on
  CALENDAR_OBJECT(CALENDAR_RESOURCE_ID, ICALENDAR_UID);

create index CALENDAR_OBJECT_CALENDAR_RESOURCE_ID_RECURRANCE_MAX on
  CALENDAR_OBJECT(CALENDAR_RESOURCE_ID, RECURRANCE_MAX);

create index CALENDAR_OBJECT_ICALENDAR_UID on
  CALENDAR_OBJECT(ICALENDAR_UID);

create index CALENDAR_OBJECT_DROPBOX_ID on
  CALENDAR_OBJECT(DROPBOX_ID);

-- Enumeration of attachment modes

create table CALENDAR_OBJECT_ATTACHMENTS_MODE (
  ID          integer     primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into CALENDAR_OBJECT_ATTACHMENTS_MODE values (0, 'none' );
insert into CALENDAR_OBJECT_ATTACHMENTS_MODE values (1, 'read' );
insert into CALENDAR_OBJECT_ATTACHMENTS_MODE values (2, 'write');


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


-----------------
-- Instance ID --
-----------------

create sequence INSTANCE_ID_SEQ;


----------------
-- Time Range --
----------------

create table TIME_RANGE (
  INSTANCE_ID                 integer        primary key default nextval('INSTANCE_ID_SEQ'), -- implicit index
  CALENDAR_RESOURCE_ID        integer        not null references CALENDAR on delete cascade,
  CALENDAR_OBJECT_RESOURCE_ID integer        not null references CALENDAR_OBJECT on delete cascade,
  FLOATING                    boolean        not null,
  START_DATE                  timestamp      not null,
  END_DATE                    timestamp      not null,
  FBTYPE                      integer        not null,
  TRANSPARENT                 boolean        not null
);

create index TIME_RANGE_CALENDAR_RESOURCE_ID on
  TIME_RANGE(CALENDAR_RESOURCE_ID);
create index TIME_RANGE_CALENDAR_OBJECT_RESOURCE_ID on
  TIME_RANGE(CALENDAR_OBJECT_RESOURCE_ID);


-- Enumeration of free/busy types

create table FREE_BUSY_TYPE (
  ID          integer     primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into FREE_BUSY_TYPE values (0, 'unknown'         );
insert into FREE_BUSY_TYPE values (1, 'free'            );
insert into FREE_BUSY_TYPE values (2, 'busy'            );
insert into FREE_BUSY_TYPE values (3, 'busy-unavailable');
insert into FREE_BUSY_TYPE values (4, 'busy-tentative'  );


------------------
-- Transparency --
------------------

create table TRANSPARENCY (
  TIME_RANGE_INSTANCE_ID      integer      not null references TIME_RANGE on delete cascade,
  USER_ID                     varchar(255) not null,
  TRANSPARENT                 boolean      not null
);

create index TRANSPARENCY_TIME_RANGE_INSTANCE_ID on
  TRANSPARENCY(TIME_RANGE_INSTANCE_ID);


----------------
-- Attachment --
----------------

create sequence ATTACHMENT_ID_SEQ;

create table ATTACHMENT (
  ATTACHMENT_ID               integer           primary key default nextval('ATTACHMENT_ID_SEQ'), -- implicit index
  CALENDAR_HOME_RESOURCE_ID   integer           not null references CALENDAR_HOME,
  DROPBOX_ID                  varchar(255),
  CONTENT_TYPE                varchar(255)      not null,
  SIZE                        integer           not null,
  MD5                         char(32)          not null,
  CREATED                     timestamp default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED                    timestamp default timezone('UTC', CURRENT_TIMESTAMP),
  PATH                        varchar(1024)     not null
);

create index ATTACHMENT_CALENDAR_HOME_RESOURCE_ID on
  ATTACHMENT(CALENDAR_HOME_RESOURCE_ID);

-- Many-to-many relationship between attachments and calendar objects
create table ATTACHMENT_CALENDAR_OBJECT (
  ATTACHMENT_ID                  integer      not null references ATTACHMENT on delete cascade,
  MANAGED_ID                     varchar(255) not null,
  CALENDAR_OBJECT_RESOURCE_ID    integer      not null references CALENDAR_OBJECT on delete cascade,

  primary key (ATTACHMENT_ID, CALENDAR_OBJECT_RESOURCE_ID), -- implicit index
  unique (MANAGED_ID, CALENDAR_OBJECT_RESOURCE_ID) --implicit index
);

create index ATTACHMENT_CALENDAR_OBJECT_CALENDAR_OBJECT_RESOURCE_ID on
	ATTACHMENT_CALENDAR_OBJECT(CALENDAR_OBJECT_RESOURCE_ID);

-----------------------
-- Resource Property --
-----------------------

create table RESOURCE_PROPERTY (
  RESOURCE_ID integer      not null, -- foreign key: *.RESOURCE_ID
  NAME        varchar(255) not null,
  VALUE       text         not null, -- FIXME: xml?
  VIEWER_UID  varchar(255),

  primary key (RESOURCE_ID, NAME, VIEWER_UID) -- implicit index
);


----------------------
-- AddressBook Home --
----------------------

create table ADDRESSBOOK_HOME (
  RESOURCE_ID      				integer			primary key default nextval('RESOURCE_ID_SEQ'), -- implicit index
  ADDRESSBOOK_PROPERTY_STORE_ID	integer      	default nextval('RESOURCE_ID_SEQ') not null, 	-- implicit index
  OWNER_UID        				varchar(255) 	not null unique,                                -- implicit index
  DATAVERSION      				integer      	default 0 not null
);


-------------------------------
-- AddressBook Home Metadata --
-------------------------------

create table ADDRESSBOOK_HOME_METADATA (
  RESOURCE_ID      integer      primary key references ADDRESSBOOK_HOME on delete cascade, -- implicit index
  QUOTA_USED_BYTES integer      default 0 not null,
  CREATED          timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED         timestamp    default timezone('UTC', CURRENT_TIMESTAMP)
);


-----------------------------
-- Shared AddressBook Bind --
-----------------------------

-- Joins sharee ADDRESSBOOK_HOME and owner ADDRESSBOOK_HOME

create table SHARED_ADDRESSBOOK_BIND (
  ADDRESSBOOK_HOME_RESOURCE_ID			integer			not null references ADDRESSBOOK_HOME,
  OWNER_HOME_RESOURCE_ID    			integer      	not null references ADDRESSBOOK_HOME on delete cascade,
  ADDRESSBOOK_RESOURCE_NAME    			varchar(255) 	not null,
  BIND_MODE                    			integer      	not null,	-- enum CALENDAR_BIND_MODE
  BIND_STATUS                  			integer      	not null,	-- enum CALENDAR_BIND_STATUS
  BIND_REVISION				   			integer      	default 0 not null,
  MESSAGE                      			text,                  		-- FIXME: xml?

  primary key (ADDRESSBOOK_HOME_RESOURCE_ID, OWNER_HOME_RESOURCE_ID), -- implicit index
  unique (ADDRESSBOOK_HOME_RESOURCE_ID, ADDRESSBOOK_RESOURCE_NAME)     -- implicit index
);

create index SHARED_ADDRESSBOOK_BIND_RESOURCE_ID on
  SHARED_ADDRESSBOOK_BIND(OWNER_HOME_RESOURCE_ID);


------------------------
-- AddressBook Object --
------------------------

create table ADDRESSBOOK_OBJECT (
  RESOURCE_ID             		integer   		primary key default nextval('RESOURCE_ID_SEQ'),    -- implicit index
  ADDRESSBOOK_HOME_RESOURCE_ID 	integer      	not null references ADDRESSBOOK_HOME on delete cascade,
  RESOURCE_NAME           		varchar(255) 	not null,
  VCARD_TEXT              		text         	not null,
  VCARD_UID               		varchar(255) 	not null,
  KIND 			  		  		integer      	not null,  -- enum ADDRESSBOOK_OBJECT_KIND
  MD5                     		char(32)     	not null,
  CREATED                 		timestamp    	default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED                		timestamp    	default timezone('UTC', CURRENT_TIMESTAMP),

  unique (ADDRESSBOOK_HOME_RESOURCE_ID, RESOURCE_NAME), -- implicit index
  unique (ADDRESSBOOK_HOME_RESOURCE_ID, VCARD_UID)      -- implicit index
);


-----------------------------
-- AddressBook Object kind --
-----------------------------

create table ADDRESSBOOK_OBJECT_KIND (
  ID          integer     primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into ADDRESSBOOK_OBJECT_KIND values (0, 'person');
insert into ADDRESSBOOK_OBJECT_KIND values (1, 'group' );
insert into ADDRESSBOOK_OBJECT_KIND values (2, 'resource');
insert into ADDRESSBOOK_OBJECT_KIND values (3, 'location');


---------------------------------
-- Address Book Object Members --
---------------------------------

create table ABO_MEMBERS (
    GROUP_ID              integer      not null references ADDRESSBOOK_OBJECT on delete cascade,	-- AddressBook Object's (kind=='group') RESOURCE_ID
 	ADDRESSBOOK_ID		  integer      not null references ADDRESSBOOK_HOME on delete cascade,
    MEMBER_ID             integer      not null references ADDRESSBOOK_OBJECT,						-- member AddressBook Object's RESOURCE_ID

    primary key (GROUP_ID, MEMBER_ID) -- implicit index
);

create index ABO_MEMBERS_ADDRESSBOOK_ID on
	ABO_MEMBERS(ADDRESSBOOK_ID);
create index ABO_MEMBERS_MEMBER_ID on
	ABO_MEMBERS(MEMBER_ID);

------------------------------------------
-- Address Book Object Foreign Members  --
------------------------------------------

create table ABO_FOREIGN_MEMBERS (
    GROUP_ID              integer      not null references ADDRESSBOOK_OBJECT on delete cascade,	-- AddressBook Object's (kind=='group') RESOURCE_ID
 	ADDRESSBOOK_ID		  integer      not null references ADDRESSBOOK_HOME on delete cascade,
    MEMBER_ADDRESS  	  varchar(255) not null, 													-- member AddressBook Object's 'calendar' address

    primary key (GROUP_ID, MEMBER_ADDRESS) -- implicit index
);

create index ABO_FOREIGN_MEMBERS_ADDRESSBOOK_ID on
	ABO_FOREIGN_MEMBERS(ADDRESSBOOK_ID);

-----------------------
-- Shared Group Bind --
-----------------------

-- Joins ADDRESSBOOK_HOME and ADDRESSBOOK_OBJECT (kind == group)

create table SHARED_GROUP_BIND (	
  ADDRESSBOOK_HOME_RESOURCE_ID 		integer      not null references ADDRESSBOOK_HOME,
  GROUP_RESOURCE_ID      			integer      not null references ADDRESSBOOK_OBJECT on delete cascade,
  GROUP_ADDRESSBOOK_NAME			varchar(255) not null,
  BIND_MODE                    		integer      not null, -- enum CALENDAR_BIND_MODE
  BIND_STATUS                  		integer      not null, -- enum CALENDAR_BIND_STATUS
  BIND_REVISION				   		integer      default 0 not null,
  MESSAGE                      		text,                  -- FIXME: xml?

  primary key (ADDRESSBOOK_HOME_RESOURCE_ID, GROUP_RESOURCE_ID), -- implicit index
  unique (ADDRESSBOOK_HOME_RESOURCE_ID, GROUP_ADDRESSBOOK_NAME)     -- implicit index
);

create index SHARED_GROUP_BIND_RESOURCE_ID on
  SHARED_GROUP_BIND(GROUP_RESOURCE_ID);


---------------
-- Revisions --
---------------

create sequence REVISION_SEQ;


-------------------------------
-- Calendar Object Revisions --
-------------------------------

create table CALENDAR_OBJECT_REVISIONS (
  CALENDAR_HOME_RESOURCE_ID integer      not null references CALENDAR_HOME,
  CALENDAR_RESOURCE_ID      integer      references CALENDAR,
  CALENDAR_NAME             varchar(255) default null,
  RESOURCE_NAME             varchar(255),
  REVISION                  integer      default nextval('REVISION_SEQ') not null,
  DELETED                   boolean      not null
);

create index CALENDAR_OBJECT_REVISIONS_HOME_RESOURCE_ID_CALENDAR_RESOURCE_ID
  on CALENDAR_OBJECT_REVISIONS(CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_ID);

create index CALENDAR_OBJECT_REVISIONS_RESOURCE_ID_RESOURCE_NAME_DELETED_REVISION
  on CALENDAR_OBJECT_REVISIONS(CALENDAR_RESOURCE_ID, RESOURCE_NAME, DELETED, REVISION);

create index CALENDAR_OBJECT_REVISIONS_RESOURCE_ID_REVISION
  on CALENDAR_OBJECT_REVISIONS(CALENDAR_RESOURCE_ID, REVISION);


----------------------------------
-- AddressBook Object Revisions --
----------------------------------

create table ADDRESSBOOK_OBJECT_REVISIONS (
  ADDRESSBOOK_HOME_RESOURCE_ID 			integer			not null references ADDRESSBOOK_HOME,
  OWNER_HOME_RESOURCE_ID    			integer     	references ADDRESSBOOK_HOME,
  ADDRESSBOOK_NAME             			varchar(255) 	default null,
  RESOURCE_NAME                			varchar(255),
  REVISION                     			integer     	default nextval('REVISION_SEQ') not null,
  DELETED                      			boolean      	not null
);

create index ADDRESSBOOK_OBJECT_REVISIONS_HOME_RESOURCE_ID_OWNER_HOME_RESOURCE_ID
  on ADDRESSBOOK_OBJECT_REVISIONS(ADDRESSBOOK_HOME_RESOURCE_ID, OWNER_HOME_RESOURCE_ID);

create index ADDRESSBOOK_OBJECT_REVISIONS_OWNER_HOME_RESOURCE_ID_RESOURCE_NAME_DELETED_REVISION
  on ADDRESSBOOK_OBJECT_REVISIONS(OWNER_HOME_RESOURCE_ID, RESOURCE_NAME, DELETED, REVISION);

create index ADDRESSBOOK_OBJECT_REVISIONS_OWNER_HOME_RESOURCE_ID_REVISION
  on ADDRESSBOOK_OBJECT_REVISIONS(OWNER_HOME_RESOURCE_ID, REVISION);


-----------------------------------
-- Notification Object Revisions --
-----------------------------------

create table NOTIFICATION_OBJECT_REVISIONS (
  NOTIFICATION_HOME_RESOURCE_ID integer      not null references NOTIFICATION_HOME on delete cascade,
  RESOURCE_NAME                 varchar(255),
  REVISION                      integer      default nextval('REVISION_SEQ') not null,
  DELETED                       boolean      not null,

  unique(NOTIFICATION_HOME_RESOURCE_ID, RESOURCE_NAME) -- implicit index
);

create index NOTIFICATION_OBJECT_REVISIONS_RESOURCE_ID_REVISION
  on NOTIFICATION_OBJECT_REVISIONS(NOTIFICATION_HOME_RESOURCE_ID, REVISION);


-------------------------------------------
-- Apple Push Notification Subscriptions --
-------------------------------------------

create table APN_SUBSCRIPTIONS (
  TOKEN                         varchar(255) not null,
  RESOURCE_KEY                  varchar(255) not null,
  MODIFIED                      integer      not null,
  SUBSCRIBER_GUID               varchar(255) not null,
  USER_AGENT                    varchar(255) default null,
  IP_ADDR                       varchar(255) default null,

  primary key (TOKEN, RESOURCE_KEY) -- implicit index
);

create index APN_SUBSCRIPTIONS_RESOURCE_KEY
   on APN_SUBSCRIPTIONS(RESOURCE_KEY);

   
-----------------
-- IMIP Tokens --
-----------------

create table IMIP_TOKENS (
  TOKEN                         varchar(255) not null,
  ORGANIZER                     varchar(255) not null,
  ATTENDEE                      varchar(255) not null,
  ICALUID                       varchar(255) not null,
  ACCESSED                      timestamp    default timezone('UTC', CURRENT_TIMESTAMP),

  primary key (ORGANIZER, ATTENDEE, ICALUID) -- implicit index
);

create index IMIP_TOKENS_TOKEN
   on IMIP_TOKENS(TOKEN);

   
----------------
-- Work Items --
----------------

create sequence WORKITEM_SEQ;


---------------------------
-- IMIP Inivitation Work --
---------------------------

create table IMIP_INVITATION_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  FROM_ADDR                     varchar(255) not null,
  TO_ADDR                       varchar(255) not null,
  ICALENDAR_TEXT                text         not null
);


-----------------------
-- IMIP Polling Work --
-----------------------

create table IMIP_POLLING_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP)
);


---------------------
-- IMIP Reply Work --
---------------------

create table IMIP_REPLY_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  ORGANIZER                     varchar(255) not null,
  ATTENDEE                      varchar(255) not null,
  ICALENDAR_TEXT                text         not null
);


------------------------
-- Push Notifications --
------------------------

create table PUSH_NOTIFICATION_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  PUSH_ID                       varchar(255) not null,
  PRIORITY                      integer      not null -- 1:low 5:medium 10:high
);

-----------------
-- GroupCacher --
-----------------

create table GROUP_CACHER_POLLING_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP)
);


--------------------------
-- Object Splitter Work --
--------------------------

create table CALENDAR_OBJECT_SPLITTER_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  RESOURCE_ID                   integer      not null references CALENDAR_OBJECT on delete cascade
);

create index CALENDAR_OBJECT_SPLITTER_WORK_RESOURCE_ID on
	CALENDAR_OBJECT_SPLITTER_WORK(RESOURCE_ID);

--------------------
-- Schema Version --
--------------------

create table CALENDARSERVER (
  NAME                          varchar(255) primary key, -- implicit index
  VALUE                         varchar(255)
);

insert into CALENDARSERVER values ('VERSION', '28');
insert into CALENDARSERVER values ('CALENDAR-DATAVERSION', '5');
insert into CALENDARSERVER values ('ADDRESSBOOK-DATAVERSION', '2');
