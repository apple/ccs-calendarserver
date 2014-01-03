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

-------------------------------------------------
-- Upgrade database schema from VERSION 7 to 8 --
-------------------------------------------------

-- Add new table populated from existing one
create table CALENDAR_METADATA (
  RESOURCE_ID integer   primary key references CALENDAR on delete cascade, -- implicit index
  SUPPORTED_COMPONENTS  varchar(255) default null,
  CREATED               timestamp default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED              timestamp default timezone('UTC', CURRENT_TIMESTAMP)
);
insert into CALENDAR_METADATA
 select RESOURCE_ID, SUPPORTED_COMPONENTS, CREATED, MODIFIED from CALENDAR;

-- Alter existing table to drop columns moved to new one
alter table CALENDAR
 drop column SUPPORTED_COMPONENTS,
 drop column CREATED,
 drop column MODIFIED;

-- Add new table populated from existing one
create table ADDRESSBOOK_METADATA (
  RESOURCE_ID integer   primary key references ADDRESSBOOK on delete cascade, -- implicit index
  CREATED     timestamp default timezone('UTC', CURRENT_TIMESTAMP),
  MODIFIED    timestamp default timezone('UTC', CURRENT_TIMESTAMP)
);
insert into ADDRESSBOOK_METADATA
 select RESOURCE_ID, CREATED, MODIFIED from ADDRESSBOOK;

-- Alter existing table to drop columns moved to new one
alter table ADDRESSBOOK
 drop column CREATED,
 drop column MODIFIED;

-- Now update the version
-- No data upgrades
update CALENDARSERVER set VALUE = '8' where NAME = 'VERSION';
