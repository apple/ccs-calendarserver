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
-- Upgrade database schema from VERSION 25 to 26 --
---------------------------------------------------

-- New tables

create table SCHEDULE_REFRESH_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "ICALENDAR_UID" nvarchar2(255),
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade,
    "RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade
);

create index SCHEDULE_REFRESH_WORK_26084c7b on SCHEDULE_REFRESH_WORK (
    HOME_RESOURCE_ID
);

create index SCHEDULE_REFRESH_WORK_989efe54 on SCHEDULE_REFRESH_WORK (
    RESOURCE_ID
);

create table SCHEDULE_REFRESH_ATTENDEES (
    "RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade,
    "ATTENDEE" nvarchar2(255)
);

create index SCHEDULE_REFRESH_ATTE_83053b91 on SCHEDULE_REFRESH_ATTENDEES (
    RESOURCE_ID,
    ATTENDEE
);

create table SCHEDULE_AUTO_REPLY_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "ICALENDAR_UID" nvarchar2(255),
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

create table SCHEDULE_REPLY_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "ICALENDAR_UID" nvarchar2(255),
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

create table SCHEDULE_REPLY_CANCEL_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "ICALENDAR_UID" nvarchar2(255),
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade,
    "ICALENDAR_TEXT" nclob
);

create index SCHEDULE_REPLY_CANCEL_dab513ef on SCHEDULE_REPLY_CANCEL_WORK (
    HOME_RESOURCE_ID
);


-- Now update the version
-- No data upgrades
update CALENDARSERVER set VALUE = '26' where NAME = 'VERSION';
