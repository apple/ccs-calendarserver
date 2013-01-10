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
-- Upgrade database schema from VERSION 4 to 5 --
-------------------------------------------------

-- We have changed the hashing schema for index names, so rename
-- all indexes first

-- Note that Oracle already suppressed some indexes because they were implicit or invalid

--implicit alter index IDX_0_CALENDAR_HOME_OWNER_UID rename to CALENDAR_HOME_OWNER_U_78016c63;
alter index IDX_1_CALENDAR_HOME_METADATA_R rename to CALENDAR_HOME_METADAT_35a84eec;
alter index IDX_2_INVITE_INVITE_UID rename to INVITE_INVITE_UID_9b0902ff;
--invalid alter index IDX_3_INVITE_RESOURCE_ID rename to INVITE_RESOURCE_ID_b36ddc23;
--invalid alter index IDX_4_INVITE_HOME_RESOURCE_ID rename to INVITE_HOME_RESOURCE__e9bdf77e;
--implicit alter index IDX_5_NOTIFICATION_HOME_OWNER_ rename to NOTIFICATION_HOME_OWN_401a6203;
alter index IDX_6_NOTIFICATION_NOTIFICATIO rename to NOTIFICATION_NOTIFICA_f891f5f9;
alter index IDX_7_NOTIFICATION_NOTIFICATIO rename to NOTIFICATION_NOTIFICA_62daf834;
alter index IDX_8_CALENDAR_BIND_HOME_RESOU rename to CALENDAR_BIND_HOME_RE_0d980be6;
alter index IDX_9_CALENDAR_BIND_RESOURCE_I rename to CALENDAR_BIND_RESOURC_e57964d4;
alter index IDX_10_CALENDAR_OBJECT_CALENDA rename to CALENDAR_OBJECT_CALEN_06694fd0;
alter index IDX_11_CALENDAR_OBJECT_CALENDA rename to CALENDAR_OBJECT_CALEN_a9a453a9;
alter index IDX_12_CALENDAR_OBJECT_CALENDA rename to CALENDAR_OBJECT_CALEN_96e83b73;
alter index IDX_13_CALENDAR_OBJECT_ORGANIZ rename to CALENDAR_OBJECT_ORGAN_7ce24750;
alter index IDX_14_CALENDAR_OBJECT_DROPBOX rename to CALENDAR_OBJECT_DROPB_de041d80;
alter index IDX_15_TIME_RANGE_CALENDAR_RES rename to TIME_RANGE_CALENDAR_R_beb6e7eb;
alter index IDX_16_TIME_RANGE_CALENDAR_OBJ rename to TIME_RANGE_CALENDAR_O_acf37bd1;
alter index IDX_17_TRANSPARENCY_TIME_RANGE rename to TRANSPARENCY_TIME_RAN_5f34467f;
alter index IDX_18_ATTACHMENT_DROPBOX_ID rename to ATTACHMENT_DROPBOX_ID_5073cf23;
--implicit alter index IDX_19_ADDRESSBOOK_HOME_OWNER_ rename to ADDRESSBOOK_HOME_OWNE_44f7f53b;
alter index IDX_20_ADDRESSBOOK_HOME_METADA rename to ADDRESSBOOK_HOME_META_cfe06701;
alter index IDX_21_ADDRESSBOOK_BIND_HOME_R rename to ADDRESSBOOK_BIND_HOME_6a6dc8ce;
alter index IDX_22_ADDRESSBOOK_BIND_RESOUR rename to ADDRESSBOOK_BIND_RESO_205aa75c;
alter index IDX_23_ADDRESSBOOK_OBJECT_ADDR rename to ADDRESSBOOK_OBJECT_AD_1540450d;
alter index IDX_24_CALENDAR_OBJECT_REVISIO rename to CALENDAR_OBJECT_REVIS_42be4d9e;
alter index IDX_25_CALENDAR_OBJECT_REVISIO rename to CALENDAR_OBJECT_REVIS_3e41b7f0;
alter index IDX_26_ADDRESSBOOK_OBJECT_REVI rename to ADDRESSBOOK_OBJECT_RE_5965a9e2;
alter index IDX_27_ADDRESSBOOK_OBJECT_REVI rename to ADDRESSBOOK_OBJECT_RE_2ab44f33;
alter index IDX_28_NOTIFICATION_OBJECT_REV rename to NOTIFICATION_OBJECT_R_47002cd8;

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
-- This constraint was not properly translated in original v4 schema
--alter table ATTACHMENT 
-- drop unique(DROPBOX_ID, PATH);
alter table ATTACHMENT
 add primary key(DROPBOX_ID, PATH);
create index ATTACHMENT_CALENDAR_H_0078845c on
  ATTACHMENT(CALENDAR_HOME_RESOURCE_ID);

--implicit drop index ADDRESSBOOK_HOME_OWNE_44f7f53b;
  
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

-- Changes to restore multi-column primary key and uniques lost in translation of v4
 
alter table NOTIFICATION
 add unique(NOTIFICATION_UID, NOTIFICATION_HOME_RESOURCE_ID);
 
alter table CALENDAR_BIND
 add primary key(CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_ID);
alter table CALENDAR_BIND
 add unique(CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_NAME);
 
alter table CALENDAR_OBJECT
 add unique(CALENDAR_RESOURCE_ID, RESOURCE_NAME);
 
--alter table ATTACHMENT
-- add primary key(DROPBOX_ID, PATH);
 
alter table RESOURCE_PROPERTY
 add primary key(RESOURCE_ID, NAME, VIEWER_UID);
 
alter table ADDRESSBOOK_BIND
 add primary key(ADDRESSBOOK_HOME_RESOURCE_ID, ADDRESSBOOK_RESOURCE_ID);
alter table ADDRESSBOOK_BIND
 add unique(ADDRESSBOOK_HOME_RESOURCE_ID, ADDRESSBOOK_RESOURCE_NAME);
 
alter table ADDRESSBOOK_OBJECT
 add unique(ADDRESSBOOK_RESOURCE_ID, RESOURCE_NAME);
alter table ADDRESSBOOK_OBJECT
 add unique(ADDRESSBOOK_RESOURCE_ID, VCARD_UID);
 
create index CALENDAR_OBJECT_REVIS_2643d556
  on CALENDAR_OBJECT_REVISIONS(CALENDAR_RESOURCE_ID, RESOURCE_NAME);
 
create index ADDRESSBOOK_OBJECT_RE_9a848f39
  on ADDRESSBOOK_OBJECT_REVISIONS(ADDRESSBOOK_RESOURCE_ID, RESOURCE_NAME);
 
alter table NOTIFICATION_OBJECT_REVISIONS
 add unique(NOTIFICATION_HOME_RESOURCE_ID, RESOURCE_NAME);
 

-- Now update the version
update CALENDARSERVER set VALUE = '5' where NAME = 'VERSION';

