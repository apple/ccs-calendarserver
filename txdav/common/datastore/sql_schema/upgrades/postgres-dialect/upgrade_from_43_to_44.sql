----
-- Copyright (c) 2012-2015 Apple Inc. All rights reserved.
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
-- Upgrade database schema from VERSION 43 to 44 --
---------------------------------------------------

-----------------
-- Job Changes --
-----------------

drop function next_job();

-- The scheduling work schema has changed a lot - to avoid a complex migration process this
-- script just drops all the existing tables and adds back the new set

-------------------
-- Schedule Work --
-------------------

create table SCHEDULE_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  JOB_ID                        integer      references JOB not null,
  ICALENDAR_UID                 varchar(255) not null,
  WORK_TYPE                     varchar(255) not null
);

create index SCHEDULE_WORK_JOB_ID on
  SCHEDULE_WORK(JOB_ID);
create index SCHEDULE_WORK_ICALENDAR_UID on
  SCHEDULE_WORK(ICALENDAR_UID);

---------------------------
-- Schedule Refresh Work --
---------------------------

drop table SCHEDULE_REFRESH_WORK;

create table SCHEDULE_REFRESH_WORK (
  WORK_ID                       integer      primary key references SCHEDULE_WORK on delete cascade, -- implicit index
  HOME_RESOURCE_ID              integer      not null references CALENDAR_HOME on delete cascade,
  RESOURCE_ID                   integer      not null references CALENDAR_OBJECT on delete cascade,
  ATTENDEE_COUNT                integer
);

create index SCHEDULE_REFRESH_WORK_HOME_RESOURCE_ID on
  SCHEDULE_REFRESH_WORK(HOME_RESOURCE_ID);
create index SCHEDULE_REFRESH_WORK_RESOURCE_ID on
  SCHEDULE_REFRESH_WORK(RESOURCE_ID);

------------------------------
-- Schedule Auto Reply Work --
------------------------------

drop table SCHEDULE_AUTO_REPLY_WORK;

create table SCHEDULE_AUTO_REPLY_WORK (
  WORK_ID                       integer      primary key references SCHEDULE_WORK on delete cascade, -- implicit index
  HOME_RESOURCE_ID              integer      not null references CALENDAR_HOME on delete cascade,
  RESOURCE_ID                   integer      not null references CALENDAR_OBJECT on delete cascade,
  PARTSTAT                      varchar(255) not null
);

create index SCHEDULE_AUTO_REPLY_WORK_HOME_RESOURCE_ID on
  SCHEDULE_AUTO_REPLY_WORK(HOME_RESOURCE_ID);
create index SCHEDULE_AUTO_REPLY_WORK_RESOURCE_ID on
  SCHEDULE_AUTO_REPLY_WORK(RESOURCE_ID);

-----------------------------
-- Schedule Organizer Work --
-----------------------------

drop table SCHEDULE_ORGANIZER_WORK;

create table SCHEDULE_ORGANIZER_WORK (
  WORK_ID                       integer      primary key references SCHEDULE_WORK on delete cascade, -- implicit index
  SCHEDULE_ACTION               integer      not null, -- Enum SCHEDULE_ACTION
  HOME_RESOURCE_ID              integer      not null references CALENDAR_HOME on delete cascade,
  RESOURCE_ID                   integer,     -- this references a possibly non-existent CALENDR_OBJECT
  ICALENDAR_TEXT_OLD            text,
  ICALENDAR_TEXT_NEW            text,
  ATTENDEE_COUNT                integer,
  SMART_MERGE                   boolean
);

create index SCHEDULE_ORGANIZER_WORK_HOME_RESOURCE_ID on
  SCHEDULE_ORGANIZER_WORK(HOME_RESOURCE_ID);
create index SCHEDULE_ORGANIZER_WORK_RESOURCE_ID on
  SCHEDULE_ORGANIZER_WORK(RESOURCE_ID);

----------------------------------
-- Schedule Organizer Send Work --
----------------------------------

create table SCHEDULE_ORGANIZER_SEND_WORK (
  WORK_ID                       integer      primary key references SCHEDULE_WORK on delete cascade, -- implicit index
  SCHEDULE_ACTION               integer      not null, -- Enum SCHEDULE_ACTION
  HOME_RESOURCE_ID              integer      not null references CALENDAR_HOME on delete cascade,
  RESOURCE_ID                   integer,     -- this references a possibly non-existent CALENDAR_OBJECT
  ATTENDEE                      varchar(255) not null,
  ITIP_MSG                      text,
  NO_REFRESH                    boolean
);

create index SCHEDULE_ORGANIZER_SEND_WORK_HOME_RESOURCE_ID on
  SCHEDULE_ORGANIZER_SEND_WORK(HOME_RESOURCE_ID);
create index SCHEDULE_ORGANIZER_SEND_WORK_RESOURCE_ID on
  SCHEDULE_ORGANIZER_SEND_WORK(RESOURCE_ID);

-------------------------
-- Schedule Reply Work --
-------------------------

drop table SCHEDULE_REPLY_WORK;

create table SCHEDULE_REPLY_WORK (
  WORK_ID                       integer      primary key references SCHEDULE_WORK on delete cascade, -- implicit index
  HOME_RESOURCE_ID              integer      not null references CALENDAR_HOME on delete cascade,
  RESOURCE_ID                   integer      not null references CALENDAR_OBJECT on delete cascade,
  CHANGED_RIDS                  text
);

create index SCHEDULE_REPLY_WORK_HOME_RESOURCE_ID on
  SCHEDULE_REPLY_WORK(HOME_RESOURCE_ID);
create index SCHEDULE_REPLY_WORK_RESOURCE_ID on
  SCHEDULE_REPLY_WORK(RESOURCE_ID);

--------------------------------
-- Schedule Reply Cancel Work --
--------------------------------

drop table SCHEDULE_REPLY_CANCEL_WORK;

create table SCHEDULE_REPLY_CANCEL_WORK (
  WORK_ID                       integer      primary key references SCHEDULE_WORK on delete cascade, -- implicit index
  HOME_RESOURCE_ID              integer      not null references CALENDAR_HOME on delete cascade,
  ICALENDAR_TEXT                text         not null
);

create index SCHEDULE_REPLY_CANCEL_WORK_HOME_RESOURCE_ID on
  SCHEDULE_REPLY_CANCEL_WORK(HOME_RESOURCE_ID);

-- update the version
update CALENDARSERVER set VALUE = '44' where NAME = 'VERSION';
