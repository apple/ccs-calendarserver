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
  add column PAUSE integer default 0;

-- New tables
create table MIGRATION_CLEANUP_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ'), -- implicit index
  JOB_ID                        integer      references JOB not null,
  HOME_RESOURCE_ID              integer      not null references CALENDAR_HOME on delete cascade
);

create index MIGRATION_CLEANUP_WORK_JOB_ID on
  MIGRATION_CLEANUP_WORK(JOB_ID);
create index MIGRATION_CLEANUP_WORK_HOME_RESOURCE_ID on
  MIGRATION_CLEANUP_WORK(HOME_RESOURCE_ID);

  create table HOME_CLEANUP_WORK (
  WORK_ID          integer      primary key default nextval('WORKITEM_SEQ'), -- implicit index
  JOB_ID           integer      references JOB not null,
  OWNER_UID        varchar(255) not null
);

create index HOME_CLEANUP_WORK_JOB_ID on
  HOME_CLEANUP_WORK(JOB_ID);

create table MIGRATED_HOME_CLEANUP_WORK (
  WORK_ID          integer      primary key default nextval('WORKITEM_SEQ'), -- implicit index
  JOB_ID           integer      references JOB not null,
  OWNER_UID        varchar(255) not null
);

create index MIGRATED_HOME_CLEANUP_WORK_JOB_ID on
  MIGRATED_HOME_CLEANUP_WORK(JOB_ID);

-- update the version
update CALENDARSERVER set VALUE = '55' where NAME = 'VERSION';
