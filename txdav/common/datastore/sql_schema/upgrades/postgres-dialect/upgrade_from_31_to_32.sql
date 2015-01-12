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
-- Upgrade database schema from VERSION 31 to 32 --
---------------------------------------------------

-- Home related updates

alter table CALENDAR_HOME
 add column STATUS integer default 0 not null;

alter table NOTIFICATION_HOME
 add column STATUS integer default 0 not null;

alter table ADDRESSBOOK_HOME
 add column STATUS integer default 0 not null;

-- Enumeration of statuses

create table HOME_STATUS (
  ID          integer     primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into HOME_STATUS values (0, 'normal' );
insert into HOME_STATUS values (1, 'external');

-- Bind changes
alter table CALENDAR_BIND
 add column EXTERNAL_ID integer default null;

alter table SHARED_ADDRESSBOOK_BIND
 add column EXTERNAL_ID integer default null;

alter table SHARED_GROUP_BIND
 add column EXTERNAL_ID integer default null;


-- Now update the version
-- No data upgrades
update CALENDARSERVER set VALUE = '32' where NAME = 'VERSION';
