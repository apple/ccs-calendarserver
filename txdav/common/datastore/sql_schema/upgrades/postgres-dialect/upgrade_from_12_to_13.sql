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
-- Upgrade database schema from VERSION 12 to 13 --
---------------------------------------------------


-- Attachment related updates

create sequence ATTACHMENT_ID_SEQ;


alter table ATTACHMENT
 drop constraint ATTACHMENT_PKEY,
 alter column DROPBOX_ID drop not null,
 add column ATTACHMENT_ID integer primary key default nextval('ATTACHMENT_ID_SEQ');

create table ATTACHMENT_CALENDAR_OBJECT (
  ATTACHMENT_ID                  integer      not null references ATTACHMENT on delete cascade,
  MANAGED_ID                     varchar(255) not null,
  CALENDAR_OBJECT_RESOURCE_ID    integer      not null references CALENDAR_OBJECT on delete cascade,

  primary key (ATTACHMENT_ID, CALENDAR_OBJECT_RESOURCE_ID), -- implicit index
  unique (MANAGED_ID, CALENDAR_OBJECT_RESOURCE_ID) --implicit index
);


-- Now update the version
-- No data upgrades
update CALENDARSERVER set VALUE = '13' where NAME = 'VERSION';
