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
-- Upgrade database schema from VERSION 39 to 40 --
---------------------------------------------------

alter table CALENDAR_OBJECT_ATTACHMENTS_MODE rename to CALENDAR_OBJ_ATTACHMENTS_MODE;

alter table GROUP_ATTENDEE_RECONCILIATION_WORK rename to GROUP_ATTENDEE_RECONCILE_WORK;
alter index GROUP_ATTENDEE_RECONCILIATION_WORK_JOB_ID rename to GROUP_ATTENDEE_RECONCILE_WORK_JOB_ID;

alter table GROUP_MEMBERSHIP add
  primary key (GROUP_ID, MEMBER_UID);
drop index GROUP_MEMBERSHIP_GROUP;

alter table GROUP_ATTENDEE add
  primary key (GROUP_ID, RESOURCE_ID);
create index GROUP_ATTENDEE_RESOURCE_ID on
  GROUP_ATTENDEE(RESOURCE_ID);

create index DELEGATE_GROUPS_GROUP_ID on
  DELEGATE_GROUPS(GROUP_ID);

alter table SCHEDULE_REFRESH_ATTENDEES add
  primary key(RESOURCE_ID, ATTENDEE);

-- update the version
update CALENDARSERVER set VALUE = '40' where NAME = 'VERSION';
