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
-- Upgrade database schema from VERSION 6 to 7 --
-------------------------------------------------

-- Just need to add one column
alter table CALENDAR_HOME
 add column DATAVERSION integer default 1 null;
 
-- Need to add timestamp columns
alter table CALENDAR_HOME_METADATA
 add column CREATED  timestamp  default timezone('UTC', CURRENT_TIMESTAMP),
 add column MODIFIED timestamp  default timezone('UTC', CURRENT_TIMESTAMP);
 
-- Just need to add one column
alter table CALENDAR
 add column SUPPORTED_COMPONENTS  varchar(255) default null;

-- Just need to add one column
alter table ADDRESSBOOK_HOME
 add column DATAVERSION integer default 1 null;
 
-- Need to add timestamp columns
alter table ADDRESSBOOK_HOME_METADATA
 add column CREATED  timestamp  default timezone('UTC', CURRENT_TIMESTAMP),
 add column MODIFIED timestamp  default timezone('UTC', CURRENT_TIMESTAMP);

-- Add an index
create index CALENDAR_OBJECT_REVISIONS_RESOURCE_ID_REVISION
  on CALENDAR_OBJECT_REVISIONS(CALENDAR_RESOURCE_ID, REVISION);

-- Add an index
create index ADDRESSBOOK_OBJECT_REVISIONS_RESOURCE_ID_REVISION
  on ADDRESSBOOK_OBJECT_REVISIONS(ADDRESSBOOK_RESOURCE_ID, REVISION);

-- Add an index
create index NOTIFICATION_OBJECT_REVISIONS_RESOURCE_ID_REVISION
  on NOTIFICATION_OBJECT_REVISIONS(NOTIFICATION_HOME_RESOURCE_ID, REVISION);

-- Change a constraint
alter table APN_SUBSCRIPTIONS
 drop constraint APN_SUBSCRIPTIONS_TOKEN_RESOURCE_KEY_KEY,
 add primary key(TOKEN, RESOURCE_KEY);

-- Now update the version
update CALENDARSERVER set VALUE = '7' where NAME = 'VERSION';

-- Also insert the initial data version which we will use in the data upgrade
insert into CALENDARSERVER values ('CALENDAR-DATAVERSION', '1');
insert into CALENDARSERVER values ('ADDRESSBOOK-DATAVERSION', '1');
