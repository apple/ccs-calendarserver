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
-- Upgrade database schema from VERSION 4 to 5 --
-------------------------------------------------

-- Changes related to primary key and index optimizations

drop index CALENDAR_HOME_OWNER_UID;

drop index CALENDAR_HOME_METADATA_RESOURCE_ID;
alter table CALENDAR_HOME_METADATA
 add primary key(RESOURCE_ID);

drop index INVITE_RESOURCE_ID;
create index INVITE_RESOURCE_ID on INVITE(RESOURCE_ID);

drop index INVITE_HOME_RESOURCE_ID;
create index INVITE_HOME_RESOURCE_ID on INVITE(HOME_RESOURCE_ID);

drop index NOTIFICATION_HOME_OWNER_UID;

drop index NOTIFICATION_NOTIFICATION_UID;

drop index CALENDAR_BIND_HOME_RESOURCE_ID;

drop index CALENDAR_OBJECT_CALENDAR_RESOURCE_ID;

drop index ATTACHMENT_DROPBOX_ID;
alter table ATTACHMENT
 drop constraint ATTACHMENT_DROPBOX_ID_PATH_KEY,
 add primary key(DROPBOX_ID, PATH);
create index ATTACHMENT_CALENDAR_HOME_RESOURCE_ID on
  ATTACHMENT(CALENDAR_HOME_RESOURCE_ID);

drop index ADDRESSBOOK_HOME_OWNER_UID;
  
drop index ADDRESSBOOK_HOME_METADATA_RESOURCE_ID;
alter table ADDRESSBOOK_HOME_METADATA
 add primary key(RESOURCE_ID);

drop index ADDRESSBOOK_BIND_HOME_RESOURCE_ID;

drop index ADDRESSBOOK_OBJECT_ADDRESSBOOK_RESOURCE_ID;

drop index CALENDAR_OBJECT_REVISIONS_RESOURCE_ID;
alter table CALENDAR_OBJECT_REVISIONS
 drop constraint CALENDAR_OBJECT_REVISIONS_CALENDAR_RESOURCE_ID_RESOURCE_NAM_KEY;
create index CALENDAR_OBJECT_REVISIONS_RESOURCE_ID_RESOURCE_NAME
  on CALENDAR_OBJECT_REVISIONS(CALENDAR_RESOURCE_ID, RESOURCE_NAME);

drop index ADDRESSBOOK_OBJECT_REVISIONS_RESOURCE_ID;
alter table ADDRESSBOOK_OBJECT_REVISIONS
 drop constraint ADDRESSBOOK_OBJECT_REVISIONS_ADDRESSBOOK_RESOURCE_ID_RESOUR_KEY;
create index ADDRESSBOOK_OBJECT_REVISIONS_RESOURCE_ID_RESOURCE_NAME
  on ADDRESSBOOK_OBJECT_REVISIONS(ADDRESSBOOK_RESOURCE_ID, RESOURCE_NAME);

drop index NOTIFICATION_OBJECT_REVISIONS_HOME_RESOURCE_ID;

alter table CALENDARSERVER
 drop constraint CALENDARSERVER_NAME_KEY,
 add primary key(NAME);

-- Now update the version
update CALENDARSERVER set VALUE = '5' where NAME = 'VERSION';

