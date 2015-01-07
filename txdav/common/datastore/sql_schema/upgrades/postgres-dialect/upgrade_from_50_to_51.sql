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
-- Upgrade database schema from VERSION 50 to 51 --
---------------------------------------------------

-- New table
create table CALENDAR_OBJECT_UPGRADE_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ'), -- implicit index
  JOB_ID                        integer      references JOB not null,
  RESOURCE_ID                   integer      not null references CALENDAR_OBJECT on delete cascade
);

create index CALENDAR_OBJECT_UPGRADE_WORK_RESOURCE_ID on
  CALENDAR_OBJECT_UPGRADE_WORK(RESOURCE_ID);
create index CALENDAR_OBJECT_UPGRADE_WORK_JOB_ID on
  CALENDAR_OBJECT_UPGRADE_WORK(JOB_ID);


-- update the version
update CALENDARSERVER set VALUE = '51' where NAME = 'VERSION';
