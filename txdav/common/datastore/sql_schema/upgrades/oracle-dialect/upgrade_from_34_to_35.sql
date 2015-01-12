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
-- Upgrade database schema from VERSION 34 to 35 --
---------------------------------------------------

create table GROUP_REFRESH_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "GROUP_UID" nvarchar2(255)
);

create table GROUP_ATTENDEE_RECONCILIATION_ (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "RESOURCE_ID" integer,
    "GROUP_ID" integer
);

create table GROUPS (
    "GROUP_ID" integer primary key,
    "NAME" nvarchar2(255),
    "GROUP_UID" nvarchar2(255),
    "MEMBERSHIP_HASH" nvarchar2(255),
    "EXTANT" integer default 1,
    "CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);

create table GROUP_MEMBERSHIP (
    "GROUP_ID" integer,
    "MEMBER_UID" nvarchar2(255)
);

create table GROUP_ATTENDEE (
    "GROUP_ID" integer,
    "RESOURCE_ID" integer,
    "MEMBERSHIP_HASH" nvarchar2(255)
);

create table DELEGATES (
    "DELEGATOR" nvarchar2(255),
    "DELEGATE" nvarchar2(255),
    "READ_WRITE" integer not null,
    primary key("DELEGATOR", "READ_WRITE", "DELEGATE")
);

create table DELEGATE_GROUPS (
    "DELEGATOR" nvarchar2(255),
    "GROUP_ID" integer not null,
    "READ_WRITE" integer not null,
    "IS_EXTERNAL" integer not null,
    primary key("DELEGATOR", "READ_WRITE", "GROUP_ID")
);

create table EXTERNAL_DELEGATE_GROUPS (
    "DELEGATOR" nvarchar2(255) primary key,
    "GROUP_UID_READ" nvarchar2(255),
    "GROUP_UID_WRITE" nvarchar2(255)
);


create index GROUPS_GROUP_UID_b35cce23 on GROUPS (
    GROUP_UID
);

create index GROUP_MEMBERSHIP_GROU_9560a5e6 on GROUP_MEMBERSHIP (
    GROUP_ID
);

create index GROUP_MEMBERSHIP_MEMB_0ca508e8 on GROUP_MEMBERSHIP (
    MEMBER_UID
);

create index DELEGATE_TO_DELEGATOR_5e149b11 on DELEGATES (
    DELEGATE,
    READ_WRITE,
    DELEGATOR
);


-- Now update the version
-- No data upgrades
update CALENDARSERVER set VALUE = '35' where NAME = 'VERSION';


