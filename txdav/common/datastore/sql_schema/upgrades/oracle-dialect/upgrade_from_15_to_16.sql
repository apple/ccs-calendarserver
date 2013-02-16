----
-- Copyright (c) 2011-2013 Apple Inc. All rights reserved.
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

-------------------------------------------------
-- Upgrade database schema from VERSION 15 to 16 --
-------------------------------------------------


create sequence WORKITEM_SEQ;

create table IMIP_TOKENS (
    "TOKEN" nvarchar2(255),
    "ORGANIZER" nvarchar2(255),
    "ATTENDEE" nvarchar2(255),
    "ICALUID" nvarchar2(255),
    "ACCESSED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    primary key("ORGANIZER", "ATTENDEE", "ICALUID")
);

create table IMIP_INVITATION_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "FROM_ADDR" nvarchar2(255),
    "TO_ADDR" nvarchar2(255),
    "ICALENDAR_TEXT" nclob
);

create table IMIP_POLLING_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);

create table IMIP_REPLY_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "ORGANIZER" nvarchar2(255),
    "ATTENDEE" nvarchar2(255),
    "ICALENDAR_TEXT" nclob
);

create table PUSH_NOTIFICATION_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "PUSH_ID" nvarchar2(255)
);


-- Now update the version
update CALENDARSERVER set VALUE = '16' where NAME = 'VERSION';

