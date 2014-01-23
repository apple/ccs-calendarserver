----
-- Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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

---------------------------------------------------
-- Upgrade database schema from VERSION 33 to 34 --
---------------------------------------------------

-- New tables

---------------------------
-- Schedule Refresh Work --
---------------------------

create table SCHEDULE_REFRESH_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  ICALENDAR_UID        			varchar(255) not null,
  HOME_RESOURCE_ID              integer      not null references CALENDAR_HOME on delete cascade,
  RESOURCE_ID                   integer      not null references CALENDAR_OBJECT on delete cascade
);

create index SCHEDULE_REFRESH_WORK_HOME_RESOURCE_ID on
	SCHEDULE_REFRESH_WORK(HOME_RESOURCE_ID);
create index SCHEDULE_REFRESH_WORK_RESOURCE_ID on
	SCHEDULE_REFRESH_WORK(RESOURCE_ID);

create table SCHEDULE_REFRESH_ATTENDEES (
  RESOURCE_ID                   integer      not null references CALENDAR_OBJECT on delete cascade,
  ATTENDEE			            varchar(255) not null
);

create index SCHEDULE_REFRESH_ATTENDEES_RESOURCE_ID_ATTENDEE on
	SCHEDULE_REFRESH_ATTENDEES(RESOURCE_ID, ATTENDEE);

------------------------------
-- Schedule Auto Reply Work --
------------------------------

create table SCHEDULE_AUTO_REPLY_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  ICALENDAR_UID        			varchar(255) not null,
  HOME_RESOURCE_ID              integer      not null references CALENDAR_HOME on delete cascade,
  RESOURCE_ID                   integer      not null references CALENDAR_OBJECT on delete cascade,
  PARTSTAT						varchar(255) not null
);

create index SCHEDULE_AUTO_REPLY_WORK_HOME_RESOURCE_ID on
	SCHEDULE_AUTO_REPLY_WORK(HOME_RESOURCE_ID);
create index SCHEDULE_AUTO_REPLY_WORK_RESOURCE_ID on
	SCHEDULE_AUTO_REPLY_WORK(RESOURCE_ID);

-----------------------------
-- Schedule Organizer Work --
-----------------------------

create table SCHEDULE_ORGANIZER_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  ICALENDAR_UID        			varchar(255) not null,
  SCHEDULE_ACTION				integer		 not null, -- Enum SCHEDULE_ACTION
  HOME_RESOURCE_ID              integer      not null references CALENDAR_HOME on delete cascade,
  RESOURCE_ID                   integer,	 -- this references a possibly non-existent CALENDR_OBJECT
  ICALENDAR_TEXT				text,
  SMART_MERGE					boolean
);

create index SCHEDULE_ORGANIZER_WORK_HOME_RESOURCE_ID on
	SCHEDULE_ORGANIZER_WORK(HOME_RESOURCE_ID);
create index SCHEDULE_ORGANIZER_WORK_RESOURCE_ID on
	SCHEDULE_ORGANIZER_WORK(RESOURCE_ID);

-- Enumeration of schedule actions

create table SCHEDULE_ACTION (
  ID          integer     primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into SCHEDULE_ACTION values (0, 'create');
insert into SCHEDULE_ACTION values (1, 'modify');
insert into SCHEDULE_ACTION values (2, 'remove');

-------------------------
-- Schedule Reply Work --
-------------------------

create table SCHEDULE_REPLY_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  ICALENDAR_UID        			varchar(255) not null,
  HOME_RESOURCE_ID              integer      not null references CALENDAR_HOME on delete cascade,
  RESOURCE_ID                   integer      not null references CALENDAR_OBJECT on delete cascade,
  CHANGED_RIDS       			text
);

create index SCHEDULE_REPLY_WORK_HOME_RESOURCE_ID on
	SCHEDULE_REPLY_WORK(HOME_RESOURCE_ID);
create index SCHEDULE_REPLY_WORK_RESOURCE_ID on
	SCHEDULE_REPLY_WORK(RESOURCE_ID);

--------------------------------
-- Schedule Reply Cancel Work --
--------------------------------

create table SCHEDULE_REPLY_CANCEL_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  ICALENDAR_UID        			varchar(255) not null,
  HOME_RESOURCE_ID              integer      not null references CALENDAR_HOME on delete cascade,
  ICALENDAR_TEXT       			text         not null
);

create index SCHEDULE_REPLY_CANCEL_WORK_HOME_RESOURCE_ID on
	SCHEDULE_REPLY_CANCEL_WORK(HOME_RESOURCE_ID);


-- Now update the version
-- No data upgrades
update CALENDARSERVER set VALUE = '34' where NAME = 'VERSION';
