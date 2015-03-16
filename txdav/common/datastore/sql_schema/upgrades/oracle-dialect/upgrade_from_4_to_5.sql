----
-- Copyright (c) 2011-2015 Apple Inc. All rights reserved.
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

--implicit drop index CALENDAR_HOME_OWNER_U_78016c63;

drop index CALENDAR_HOME_METADAT_35a84eec;
alter table CALENDAR_HOME_METADATA
 add primary key(RESOURCE_ID);

--invalid drop index INVITE_RESOURCE_ID_b36ddc23;
create index INVITE_RESOURCE_ID_b36ddc23 on INVITE(RESOURCE_ID);

--invalid drop index INVITE_HOME_RESOURCE__e9bdf77e;
create index INVITE_HOME_RESOURCE__e9bdf77e on INVITE(HOME_RESOURCE_ID);

--implicit drop index NOTIFICATION_HOME_OWN_401a6203;

drop index NOTIFICATION_NOTIFICA_62daf834;

drop index CALENDAR_BIND_HOME_RE_0d980be6;

drop index CALENDAR_OBJECT_CALEN_06694fd0;

drop index ATTACHMENT_DROPBOX_ID_5073cf23;

alter table ATTACHMENT 
 drop unique(DROPBOX_ID, PATH);
alter table ATTACHMENT
 add primary key(DROPBOX_ID, PATH);

 create index ATTACHMENT_CALENDAR_H_0078845c on
  ATTACHMENT(CALENDAR_HOME_RESOURCE_ID);
  
drop index ADDRESSBOOK_HOME_META_cfe06701;
alter table ADDRESSBOOK_HOME_METADATA
 add primary key(RESOURCE_ID);

drop index ADDRESSBOOK_BIND_HOME_6a6dc8ce;

drop index ADDRESSBOOK_OBJECT_AD_1540450d;

drop index CALENDAR_OBJECT_REVIS_3e41b7f0;

drop index ADDRESSBOOK_OBJECT_RE_2ab44f33;

drop index NOTIFICATION_OBJECT_R_47002cd8;

alter table CALENDARSERVER
 drop unique(NAME);
alter table CALENDARSERVER
 add primary key(NAME);

alter table CALENDAR_OBJECT_REVISIONS 
 drop unique(CALENDAR_RESOURCE_ID, RESOURCE_NAME);
create index CALENDAR_OBJECT_REVIS_2643d556 on CALENDAR_OBJECT_REVISIONS (
    CALENDAR_RESOURCE_ID,
    RESOURCE_NAME
);

alter table ADDRESSBOOK_OBJECT_REVISIONS 
 drop unique(ADDRESSBOOK_RESOURCE_ID, RESOURCE_NAME);
create index ADDRESSBOOK_OBJECT_RE_9a848f39 on ADDRESSBOOK_OBJECT_REVISIONS (
    ADDRESSBOOK_RESOURCE_ID,
    RESOURCE_NAME
);

-- Now update the version
update CALENDARSERVER set VALUE = '5' where NAME = 'VERSION';

