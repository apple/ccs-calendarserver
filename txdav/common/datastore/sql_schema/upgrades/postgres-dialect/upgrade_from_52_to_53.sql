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
-- Upgrade database schema from VERSION 52 to 53 --
---------------------------------------------------

-- New status value
insert into HOME_STATUS values (3, 'migrating');
insert into HOME_STATUS values (4, 'disabled');

-- Home constraints
alter table CALENDAR_HOME
	drop constraint CALENDAR_HOME_OWNER_UID_KEY,
	add unique (OWNER_UID, STATUS);

alter table ADDRESSBOOK_HOME
	drop constraint ADDRESSBOOK_HOME_OWNER_UID_KEY,
	add unique (OWNER_UID, STATUS);

alter table NOTIFICATION_HOME
	drop constraint NOTIFICATION_HOME_OWNER_UID_KEY,
	add unique (OWNER_UID, STATUS);

-- Change columns
alter table CALENDAR_BIND
	drop column EXTERNAL_ID,
	add column BIND_UID varchar(36) default null;

alter table SHARED_ADDRESSBOOK_BIND
	drop column EXTERNAL_ID,
	add column BIND_UID varchar(36) default null;

alter table SHARED_GROUP_BIND
	drop column EXTERNAL_ID,
	add column BIND_UID varchar(36) default null;


-- New table
create table CALENDAR_MIGRATION (
  CALENDAR_HOME_RESOURCE_ID		integer references CALENDAR_HOME on delete cascade,
  REMOTE_RESOURCE_ID			integer not null,
  LOCAL_RESOURCE_ID				integer	references CALENDAR on delete cascade,
  LAST_SYNC_TOKEN				varchar(255),
   
  primary key (CALENDAR_HOME_RESOURCE_ID, REMOTE_RESOURCE_ID) -- implicit index
);

create index CALENDAR_MIGRATION_LOCAL_RESOURCE_ID on
  CALENDAR_MIGRATION(LOCAL_RESOURCE_ID);

  
-- New table
create table CALENDAR_OBJECT_MIGRATION (
  CALENDAR_HOME_RESOURCE_ID		integer references CALENDAR_HOME on delete cascade,
  REMOTE_RESOURCE_ID			integer not null,
  LOCAL_RESOURCE_ID				integer	references CALENDAR_OBJECT on delete cascade,
   
  primary key (CALENDAR_HOME_RESOURCE_ID, REMOTE_RESOURCE_ID) -- implicit index
);

create index CALENDAR_OBJECT_MIGRATION_HOME_LOCAL on
  CALENDAR_OBJECT_MIGRATION(CALENDAR_HOME_RESOURCE_ID, LOCAL_RESOURCE_ID);
create index CALENDAR_OBJECT_MIGRATION_LOCAL_RESOURCE_ID on
  CALENDAR_OBJECT_MIGRATION(LOCAL_RESOURCE_ID);

  
-- New table
create table ATTACHMENT_MIGRATION (
  CALENDAR_HOME_RESOURCE_ID		integer references CALENDAR_HOME on delete cascade,
  REMOTE_RESOURCE_ID			integer not null,
  LOCAL_RESOURCE_ID				integer	references ATTACHMENT on delete cascade,
   
  primary key (CALENDAR_HOME_RESOURCE_ID, REMOTE_RESOURCE_ID) -- implicit index
);

create index ATTACHMENT_MIGRATION_HOME_LOCAL on
  ATTACHMENT_MIGRATION(CALENDAR_HOME_RESOURCE_ID, LOCAL_RESOURCE_ID);
create index ATTACHMENT_MIGRATION_LOCAL_RESOURCE_ID on
  ATTACHMENT_MIGRATION(LOCAL_RESOURCE_ID);


-- update the version
update CALENDARSERVER set VALUE = '53' where NAME = 'VERSION';
