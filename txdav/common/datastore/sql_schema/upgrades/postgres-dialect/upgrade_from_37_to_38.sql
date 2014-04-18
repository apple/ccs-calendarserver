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
-- Upgrade database schema from VERSION 37 to 38 --
---------------------------------------------------

-------------------
-- Per-user data --
-------------------

alter table TRANSPARENCY
  rename to PERUSER;

alter table PERUSER
  add column ADJUSTED_START_DATE timestamp default null,
  add column ADJUSTED_END_DATE timestamp default null;

alter index TRANSPARENCY_TIME_RANGE_INSTANCE_ID
  rename to PERUSER_TIME_RANGE_INSTANCE_ID;

----------------------------------
-- Principal Purge Polling Work --
----------------------------------

create table PRINCIPAL_PURGE_POLLING_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  JOB_ID                        integer      references JOB not null
);

create index PRINCIPAL_PURGE_POLLING_WORK_JOB_ID on
  PRINCIPAL_PURGE_POLLING_WORK(JOB_ID);

--------------------------------
-- Principal Purge Check Work --
--------------------------------

create table PRINCIPAL_PURGE_CHECK_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  JOB_ID                        integer      references JOB not null,
  UID                           varchar(255) not null
);

create index PRINCIPAL_PURGE_CHECK_WORK_JOB_ID on
  PRINCIPAL_PURGE_CHECK_WORK(JOB_ID);

--------------------------
-- Principal Purge Work --
--------------------------

create table PRINCIPAL_PURGE_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  JOB_ID                        integer      references JOB not null,
  UID                           varchar(255) not null
);

create index PRINCIPAL_PURGE_WORK_JOB_ID on
  PRINCIPAL_PURGE_WORK(JOB_ID);


-- update the version
update CALENDARSERVER set VALUE = '38' where NAME = 'VERSION';
