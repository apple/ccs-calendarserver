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
-- Upgrade database schema from VERSION 39 to 40 --
---------------------------------------------------

alter table CALENDAR_OBJECT_ATTACHMENTS_MO rename to CALENDAR_OBJ_ATTACHMENTS_MODE;

alter table GROUP_ATTENDEE_RECONCILIATION_ rename to GROUP_ATTENDEE_RECONCILE_WORK;
alter index GROUP_ATTENDEE_RECONC_cd2d61b9 rename to GROUP_ATTENDEE_RECONC_da73d3c2;

alter table GROUP_MEMBERSHIP add
  primary key ("GROUP_ID", "MEMBER_UID");
drop index GROUP_MEMBERSHIP_GROU_9560a5e6;

alter table GROUP_ATTENDEE add
  primary key ("GROUP_ID", "RESOURCE_ID");
create index GROUP_ATTENDEE_RESOUR_855124dc on GROUP_ATTENDEE (
    RESOURCE_ID
);

create index DELEGATE_GROUPS_GROUP_25117446 on DELEGATE_GROUPS (
    GROUP_ID
);

alter table SCHEDULE_REFRESH_ATTENDEES add
  primary key ("RESOURCE_ID", "ATTENDEE");

-- update the version
update CALENDARSERVER set VALUE = '40' where NAME = 'VERSION';
