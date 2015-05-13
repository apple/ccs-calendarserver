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
-- Upgrade database schema from VERSION 54 to 55 --
---------------------------------------------------

-- New columns
alter table JOB
  add ("PAUSE" integer default 0);

-- New tables
create table MIGRATION_CLEANUP_WORK (
    "WORK_ID" integer primary key,
    "JOB_ID" integer not null references JOB,
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade
);

create index MIGRATION_CLEANUP_WOR_8c23cc35 on MIGRATION_CLEANUP_WORK (
    "JOB_ID"
);
create index MIGRATION_CLEANUP_WOR_86181cb8 on MIGRATION_CLEANUP_WORK (
    "HOME_RESOURCE_ID"
);

create table HOME_CLEANUP_WORK (
    "WORK_ID" integer primary key,
    "JOB_ID" integer not null references JOB,
    "OWNER_UID" nvarchar2(255)
);

create index HOME_CLEANUP_WORK_JOB_9631dfb0 on HOME_CLEANUP_WORK (
    "JOB_ID"
);

create table MIGRATED_HOME_CLEANUP_WORK (
    "WORK_ID" integer primary key,
    "JOB_ID" integer not null references JOB,
    "OWNER_UID" nvarchar2(255)
);

create index MIGRATED_HOME_CLEANUP_4c714fd4 on MIGRATED_HOME_CLEANUP_WORK (
    "JOB_ID"
);

-- update the version
update CALENDARSERVER set VALUE = '55' where NAME = 'VERSION';
