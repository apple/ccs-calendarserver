-- -*- test-case-name: txdav.caldav.datastore.test.test_sql,txdav.carddav.datastore.test.test_sql -*-

----
-- Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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
  PID       integer not null,
  PORT      integer not null,
  TIME      timestamp not null default timezone('UTC', CURRENT_TIMESTAMP),

  primary key(HOSTNAME, PORT)
);


-------------------
-- Calendar Home --
-------------------

create table CALENDAR_HOME (
  RESOURCE_ID      integer      primary key default nextval('RESOURCE_ID_SEQ'), -- implicit index
  OWNER_UID        varchar(255) not null unique,                                 -- implicit index
  DATAVERSION	   integer      default 0 not null
);

----------------------------
-- Calendar Home Metadata --
----------------------------

create table CALENDAR_HOME_METADATA (
  RESOURCE_ID      integer      primary key references CALENDAR_HOME on delete cascade, -- implicit index
  QUOTA_USED_BYTES integer      default 0 not null,
  CREATED          timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED         timestamp    default timezone('UTC', CURRENT_TIMESTAMP)
);

--------------
-- Calendar --
--------------

create table CALENDAR (
  RESOURCE_ID integer   primary key default nextval('RESOURCE_ID_SEQ') -- implicit index
);


-----------------------
-- Calendar Metadata --
-----------------------

create table CALENDAR_METADATA (
  RESOURCE_ID           integer   primary key references CALENDAR on delete cascade, -- implicit index
  SUPPORTED_COMPONENTS  varchar(255) default null,
  CREATED               timestamp default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED              timestamp default timezone('UTC', CURRENT_TIMESTAMP)
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
  CREATED                       timestamp default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED                      timestamp default timezone('UTC', CURRENT_TIMESTAMP),

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
  MESSAGE                   text,

  primary key(CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_ID), -- implicit index
  unique(CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_NAME)     -- implicit index
);

create index CALENDAR_BIND_RESOURCE_ID on CALENDAR_BIND(CALENDAR_RESOURCE_ID);

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
  ORGANIZER_OBJECT     integer      references CALENDAR_OBJECT,
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

  unique(CALENDAR_RESOURCE_ID, RESOURCE_NAME) -- implicit index

  -- since the 'inbox' is a 'calendar resource' for the purpose of storing
  -- calendar objects, this constraint has to be selectively enforced by the
  -- application layer.

  -- unique(CALENDAR_RESOURCE_ID, ICALENDAR_UID)
);

create index CALENDAR_OBJECT_CALENDAR_RESOURCE_ID_AND_ICALENDAR_UID on
  CALENDAR_OBJECT(CALENDAR_RESOURCE_ID, ICALENDAR_UID);

create index CALENDAR_OBJECT_CALENDAR_RESOURCE_ID_RECURRANCE_MAX on
  CALENDAR_OBJECT(CALENDAR_RESOURCE_ID, RECURRANCE_MAX);

create index CALENDAR_OBJECT_ORGANIZER_OBJECT on
  CALENDAR_OBJECT(ORGANIZER_OBJECT);

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

create table ATTACHMENT (
  CALENDAR_HOME_RESOURCE_ID   integer       not null references CALENDAR_HOME,
  DROPBOX_ID                  varchar(255)  not null,
  CONTENT_TYPE                varchar(255)  not null,
  SIZE                        integer       not null,
  MD5                         char(32)      not null,
  CREATED                     timestamp default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED                    timestamp default timezone('UTC', CURRENT_TIMESTAMP),
  PATH                        varchar(1024) not null,

  primary key(DROPBOX_ID, PATH) --implicit index
);

create index ATTACHMENT_CALENDAR_HOME_RESOURCE_ID on
  ATTACHMENT(CALENDAR_HOME_RESOURCE_ID);

-----------------------
-- Resource Property --
-----------------------

create table RESOURCE_PROPERTY (
  RESOURCE_ID integer      not null, -- foreign key: *.RESOURCE_ID
  NAME        varchar(255) not null,
  VALUE       text         not null, -- FIXME: xml?
  VIEWER_UID  varchar(255),

  primary key(RESOURCE_ID, NAME, VIEWER_UID) -- implicit index
);


----------------------
-- AddressBook Home --
----------------------

create table ADDRESSBOOK_HOME (
  RESOURCE_ID      integer      primary key default nextval('RESOURCE_ID_SEQ'), -- implicit index
  OWNER_UID        varchar(255) not null unique,                                -- implicit index
  DATAVERSION	   integer      default 0 not null
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
-- AddressBook Object --
-----------------------------


  create table ADDRESSBOOK_OBJECT (
  RESOURCE_ID             integer      primary key default nextval('RESOURCE_ID_SEQ'),	-- implicit index
  ADDRESSBOOK_RESOURCE_ID integer      references ADDRESSBOOK_OBJECT on delete cascade,	-- ### could add non-null, but ab would reference itself
  RESOURCE_NAME           varchar(255) not null,
  VCARD_TEXT              text         not null,
  VCARD_UID               varchar(255) not null,
  MD5                     char(32)     not null,
  CREATED                 timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED                timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  KIND 			  		  integer      not null, -- enum OBJECT_KIND 
  
  unique(ADDRESSBOOK_RESOURCE_ID, RESOURCE_NAME), -- implicit index
  unique(ADDRESSBOOK_RESOURCE_ID, VCARD_UID)      -- implicit index
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
 	ADDRESSBOOK_ID		  integer      not null references ADDRESSBOOK_OBJECT on delete cascade,	-- only used on insert and whole address book delete
    MEMBER_ID             integer      not null references ADDRESSBOOK_OBJECT,						-- member AddressBook Object's RESOURCE_ID
    primary key(GROUP_ID, MEMBER_ID) -- implicit index
);

------------------------------------------
-- Address Book Object Foreign Members  --
------------------------------------------

create table ABO_FOREIGN_MEMBERS (
    GROUP_ID              integer      not null references ADDRESSBOOK_OBJECT on delete cascade,	-- AddressBook Object's (kind=='group') RESOURCE_ID
 	ADDRESSBOOK_ID		  integer      not null references ADDRESSBOOK_OBJECT on delete cascade,	-- only used on insert and whole address book delete
    MEMBER_ADDRESS  	  varchar(255) not null, 													-- member AddressBook Object's 'calendar' address
    primary key(GROUP_ID, MEMBER_ADDRESS) -- implicit index
);

-- #### TODO: DELETE, USE CREATED and MODIFIED in ADDRESSS_BOOK_OBJECT instead ####
--------------------------
-- AddressBook Metadata --
--------------------------

create table ADDRESSBOOK_METADATA (
  RESOURCE_ID integer   primary key references ADDRESSBOOK_OBJECT on delete cascade, -- implicit index
  CREATED     timestamp default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED    timestamp default timezone('UTC', CURRENT_TIMESTAMP)
);


----------------------
-- AddressBook Bind --
----------------------

-- Joins ADDRESSBOOK_HOME and ADDRESSBOOK_OBJECT (acting as Address Book)

create table ADDRESSBOOK_BIND (	
  ADDRESSBOOK_HOME_RESOURCE_ID 		integer      not null references ADDRESSBOOK_HOME,
  ADDRESSBOOK_RESOURCE_ID     		integer      not null references ADDRESSBOOK_OBJECT on delete cascade,
  ADDRESSBOOK_RESOURCE_NAME    		varchar(255) not null,
  BIND_MODE                    		integer      not null, 	-- enum CALENDAR_BIND_MODE
  BIND_STATUS                  		integer      not null, 	-- enum CALENDAR_BIND_STATUS
  MESSAGE                      		text,        			-- FIXME: xml?

  primary key(ADDRESSBOOK_HOME_RESOURCE_ID, ADDRESSBOOK_RESOURCE_ID), -- implicit index
  unique(ADDRESSBOOK_HOME_RESOURCE_ID, ADDRESSBOOK_RESOURCE_NAME)     -- implicit index
);

create index ADDRESSBOOK_BIND_RESOURCE_ID on
  ADDRESSBOOK_BIND(ADDRESSBOOK_RESOURCE_ID);

---------------
-- Revisions --
---------------

create sequence REVISION_SEQ;

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

create index CALENDAR_OBJECT_REVISIONS_RESOURCE_ID_RESOURCE_NAME
  on CALENDAR_OBJECT_REVISIONS(CALENDAR_RESOURCE_ID, RESOURCE_NAME);

create index CALENDAR_OBJECT_REVISIONS_RESOURCE_ID_REVISION
  on CALENDAR_OBJECT_REVISIONS(CALENDAR_RESOURCE_ID, REVISION);

----------------------------------
-- AddressBook Object Revisions --
----------------------------------

create table ADDRESSBOOK_OBJECT_REVISIONS (
  ADDRESSBOOK_HOME_RESOURCE_ID integer      not null references ADDRESSBOOK_HOME,
  ADDRESSBOOK_RESOURCE_ID      integer      references ADDRESSBOOK_OBJECT,
  ADDRESSBOOK_NAME             varchar(255) default null,
  RESOURCE_NAME                varchar(255),
  REVISION                     integer      default nextval('REVISION_SEQ') not null,
  DELETED                      boolean      not null
);

create index ADDRESSBOOK_OBJECT_REVISIONS_HOME_RESOURCE_ID_ADDRESSBOOK_RESOURCE_ID
  on ADDRESSBOOK_OBJECT_REVISIONS(ADDRESSBOOK_HOME_RESOURCE_ID, ADDRESSBOOK_RESOURCE_ID);

create index ADDRESSBOOK_OBJECT_REVISIONS_RESOURCE_ID_RESOURCE_NAME
  on ADDRESSBOOK_OBJECT_REVISIONS(ADDRESSBOOK_RESOURCE_ID, RESOURCE_NAME);

create index ADDRESSBOOK_OBJECT_REVISIONS_RESOURCE_ID_REVISION
  on ADDRESSBOOK_OBJECT_REVISIONS(ADDRESSBOOK_RESOURCE_ID, REVISION);

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
  MODIFIED                      integer not null,
  SUBSCRIBER_GUID               varchar(255) not null,
  USER_AGENT                    varchar(255) default null,
  IP_ADDR                       varchar(255) default null,

  primary key(TOKEN, RESOURCE_KEY) -- implicit index
);

create index APN_SUBSCRIPTIONS_RESOURCE_KEY
   on APN_SUBSCRIPTIONS(RESOURCE_KEY);


--------------------
-- Schema Version --
--------------------

create table CALENDARSERVER (
  NAME                          varchar(255) primary key, -- implicit index
  VALUE                         varchar(255)
);

insert into CALENDARSERVER values ('VERSION', '12');
insert into CALENDARSERVER values ('CALENDAR-DATAVERSION', '3');
insert into CALENDARSERVER values ('ADDRESSBOOK-DATAVERSION', '1');
