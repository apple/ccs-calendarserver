----
-- Copyright (c) 2012-2014 Apple Inc. All rights reserved.
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

drop function next_job;

-- The scheduling work schema has changed a lot - to avoid a complex migration process this
-- script just drops all the existing tables and adds back the new set

-------------------
-- Schedule Work --
-------------------

create table SCHEDULE_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "ICALENDAR_UID" nvarchar2(255),
    "WORK_TYPE" nvarchar2(255)
);

create index SCHEDULE_WORK_JOB_ID_65e810ee on SCHEDULE_WORK (
    JOB_ID
);
create index SCHEDULE_WORK_ICALEND_089f33dc on SCHEDULE_WORK (
    ICALENDAR_UID
);

---------------------------
-- Schedule Refresh Work --
---------------------------

drop table SCHEDULE_REFRESH_WORK;

create table SCHEDULE_REFRESH_WORK (
    "WORK_ID" integer primary key references SCHEDULE_WORK on delete cascade,
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade,
    "RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade,
    "ATTENDEE_COUNT" integer
);

create index SCHEDULE_REFRESH_WORK_26084c7b on SCHEDULE_REFRESH_WORK (
    HOME_RESOURCE_ID
);
create index SCHEDULE_REFRESH_WORK_989efe54 on SCHEDULE_REFRESH_WORK (
    RESOURCE_ID
);

------------------------------
-- Schedule Auto Reply Work --
------------------------------

drop table SCHEDULE_AUTO_REPLY_WORK;

create table SCHEDULE_AUTO_REPLY_WORK (
    "WORK_ID" integer primary key references SCHEDULE_WORK on delete cascade,
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade,
    "RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade,
    "PARTSTAT" nvarchar2(255)
);

create index SCHEDULE_AUTO_REPLY_W_0256478d on SCHEDULE_AUTO_REPLY_WORK (
    HOME_RESOURCE_ID
);
create index SCHEDULE_AUTO_REPLY_W_0755e754 on SCHEDULE_AUTO_REPLY_WORK (
    RESOURCE_ID
);

-----------------------------
-- Schedule Organizer Work --
-----------------------------

drop table SCHEDULE_ORGANIZER_WORK;

create table SCHEDULE_ORGANIZER_WORK (
    "WORK_ID" integer primary key references SCHEDULE_WORK on delete cascade,
    "SCHEDULE_ACTION" integer not null,
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade,
    "RESOURCE_ID" integer,
    "ICALENDAR_TEXT_OLD" nclob,
    "ICALENDAR_TEXT_NEW" nclob,
    "ATTENDEE_COUNT" integer,
    "SMART_MERGE" integer
);

create index SCHEDULE_ORGANIZER_WO_18ce4edd on SCHEDULE_ORGANIZER_WORK (
    HOME_RESOURCE_ID
);
create index SCHEDULE_ORGANIZER_WO_14702035 on SCHEDULE_ORGANIZER_WORK (
    RESOURCE_ID
);

----------------------------------
-- Schedule Organizer Send Work --
----------------------------------

create table SCHEDULE_ORGANIZER_SEND_WORK (
    "WORK_ID" integer primary key references SCHEDULE_WORK on delete cascade,
    "SCHEDULE_ACTION" integer not null,
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade,
    "RESOURCE_ID" integer,
    "ATTENDEE" nvarchar2(255),
    "ITIP_MSG" nclob,
    "NO_REFRESH" integer
);

create index SCHEDULE_ORGANIZER_SE_9ec9f827 on SCHEDULE_ORGANIZER_SEND_WORK (
    HOME_RESOURCE_ID
);
create index SCHEDULE_ORGANIZER_SE_699fefc4 on SCHEDULE_ORGANIZER_SEND_WORK (
    RESOURCE_ID
);

-------------------------
-- Schedule Reply Work --
-------------------------

drop table SCHEDULE_REPLY_WORK;

create table SCHEDULE_REPLY_WORK (
    "WORK_ID" integer primary key references SCHEDULE_WORK on delete cascade,
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade,
    "RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade,
    "CHANGED_RIDS" nclob
);

create index SCHEDULE_REPLY_WORK_H_745af8cf on SCHEDULE_REPLY_WORK (
    HOME_RESOURCE_ID
);
create index SCHEDULE_REPLY_WORK_R_11bd3fbb on SCHEDULE_REPLY_WORK (
    RESOURCE_ID
);

--------------------------------
-- Schedule Reply Cancel Work --
--------------------------------

drop table SCHEDULE_REPLY_CANCEL_WORK;

create table SCHEDULE_REPLY_CANCEL_WORK (
    "WORK_ID" integer primary key references SCHEDULE_WORK on delete cascade,
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade,
    "ICALENDAR_TEXT" nclob
);

create index SCHEDULE_REPLY_CANCEL_dab513ef on SCHEDULE_REPLY_CANCEL_WORK (
    HOME_RESOURCE_ID
);

-- update the version
update CALENDARSERVER set VALUE = '44' where NAME = 'VERSION';
