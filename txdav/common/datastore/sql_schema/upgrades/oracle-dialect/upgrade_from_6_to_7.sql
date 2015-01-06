----
-- Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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
 add ("DATAVERSION" integer default 1 not null);
 
-- Need to add timestamp columns
alter table CALENDAR_HOME_METADATA
 add ("CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC');
alter table CALENDAR_HOME_METADATA
 add ("MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC');

 -- Just need to modify one column
alter table CALENDAR
 add ("SUPPORTED_COMPONENTS" nvarchar2(255) default null);

-- Just need to add one column
alter table ADDRESSBOOK_HOME
 add ("DATAVERSION" integer default 1 not null);
 
-- Need to add timestamp columns
alter table ADDRESSBOOK_HOME_METADATA
 add ("CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC');
alter table ADDRESSBOOK_HOME_METADATA
 add ("MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC');

-- Add an index
create index CALENDAR_OBJECT_REVIS_265c8acf
  on CALENDAR_OBJECT_REVISIONS(CALENDAR_RESOURCE_ID, REVISION);

-- Add an index
create index ADDRESSBOOK_OBJECT_RE_cb101e6b
  on ADDRESSBOOK_OBJECT_REVISIONS(ADDRESSBOOK_RESOURCE_ID, REVISION);

-- Add an index
create index NOTIFICATION_OBJECT_R_036a9cee
  on NOTIFICATION_OBJECT_REVISIONS(NOTIFICATION_HOME_RESOURCE_ID, REVISION);

-- Change a constraint
alter table APN_SUBSCRIPTIONS
 drop unique(TOKEN, RESOURCE_KEY);
alter table APN_SUBSCRIPTIONS
 add primary key(TOKEN, RESOURCE_KEY);

-- Now update the version
update CALENDARSERVER set VALUE = '7' where NAME = 'VERSION';

-- Also insert the initial data version which we will use in the data upgrade
insert into CALENDARSERVER values ('CALENDAR-DATAVERSION', '1');
insert into CALENDARSERVER values ('ADDRESSBOOK-DATAVERSION', '1');
