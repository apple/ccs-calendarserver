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
-- Upgrade database schema from VERSION 34 to 35 --
---------------------------------------------------

----------------------
-- Group membership --
----------------------

create table GROUP_REFRESH_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  GROUP_GUID                    varchar(255) not null
);

create table GROUP_ATTENDEE_RECONCILIATION_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  RESOURCE_ID                   integer,
  GROUP_ID                      integer
);

create table GROUPS (
  GROUP_ID                      integer      primary key default nextval('RESOURCE_ID_SEQ'),    -- implicit index
  NAME                          varchar(255) not null,
  GROUP_GUID                    varchar(255) not null,
  MEMBERSHIP_HASH               varchar(255) not null,
  EXTANT                        integer default 1,
  CREATED                       timestamp default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED                      timestamp default timezone('UTC', CURRENT_TIMESTAMP)
);
create index GROUPS_GROUP_GUID on GROUPS(GROUP_GUID);

create table GROUP_MEMBERSHIP (
  GROUP_ID                      integer,
  MEMBER_GUID                   varchar(255) not null
);
create index GROUP_MEMBERSHIP_GROUP on GROUP_MEMBERSHIP(GROUP_ID);
create index GROUP_MEMBERSHIP_MEMBER on GROUP_MEMBERSHIP(MEMBER_GUID);

create table GROUP_ATTENDEE (
  GROUP_ID                      integer,
  RESOURCE_ID                   integer,
  MEMBERSHIP_HASH               varchar(255) not null
);

---------------
-- Delegates --
---------------

create table DELEGATES (
  DELEGATOR                     varchar(255) not null,
  DELEGATE                      varchar(255) not null,
  READ_WRITE                    integer      not null -- 1 = ReadWrite, 0 = ReadOnly
);

create table DELEGATE_GROUPS (
  DELEGATOR                     varchar(255) not null,
  GROUP_ID                      integer      not null,
  READ_WRITE                    integer      not null, -- 1 = ReadWrite, 0 = ReadOnly
  IS_EXTERNAL                   integer      not null -- 1 = ReadWrite, 0 = ReadOnly
);

create table EXTERNAL_DELEGATE_GROUPS (
  DELEGATOR                     varchar(255) not null,
  GROUP_GUID_READ               varchar(255),
  GROUP_GUID_WRITE              varchar(255)
);

-- Now update the version
-- No data upgrades
update CALENDARSERVER set VALUE = '35' where NAME = 'VERSION';
