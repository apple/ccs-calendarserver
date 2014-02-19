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
 add ("MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC');
alter table CALENDAR_OBJECT_REVISIONS
 add ("MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC');
alter table ADDRESSBOOK_OBJECT_REVISIONS
 add ("MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC');
alter table NOTIFICATION_OBJECT_REVISIONS
 add ("MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC');

 -- Add cleanup work tables --
 
create table FIND_MIN_VALID_REVISION_WORK (
  "WORK_ID" integer primary key not null,
  "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);
create table REVISION_CLEANUP_WORK (
  "WORK_ID" integer primary key not null,
  "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);
 
-- add min revision

insert into CALENDARSERVER values ('MIN-VALID-REVISION', '1');


-- Update version --

update CALENDARSERVER set VALUE = '31' where NAME = 'VERSION';
