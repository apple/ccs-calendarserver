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
-- Upgrade database schema from VERSION 30 to 31 --
---------------------------------------------------

-- Add timestamp to revision tables --

alter table ABO_MEMBERS
  add column MODIFIED timestamp default timezone('UTC', CURRENT_TIMESTAMP);
alter table CALENDAR_OBJECT_REVISIONS
  add column MODIFIED timestamp default timezone('UTC', CURRENT_TIMESTAMP);
alter table ADDRESSBOOK_OBJECT_REVISIONS
  add column MODIFIED timestamp default timezone('UTC', CURRENT_TIMESTAMP);
alter table NOTIFICATION_OBJECT_REVISIONS
  add column MODIFIED timestamp default timezone('UTC', CURRENT_TIMESTAMP);

 -- Add cleanup work tables --
 
create table FIND_MIN_VALID_REVISION_WORK (
  WORK_ID integer primary key default nextval('WORKITEM_SEQ') not null,
  NOT_BEFORE timestamp default timezone('UTC', CURRENT_TIMESTAMP)
);
create table REVISION_CLEANUP_WORK (
  WORK_ID integer primary key default nextval('WORKITEM_SEQ') not null,
  NOT_BEFORE timestamp default timezone('UTC', CURRENT_TIMESTAMP)
);

-- add min revision

insert into CALENDARSERVER values ('MIN-VALID-REVISION', '1');

  
-- Update version --

update CALENDARSERVER set VALUE = '33' where NAME = 'VERSION';
