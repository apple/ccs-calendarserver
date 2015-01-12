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
-- Upgrade database schema from VERSION 48 to 49 --
---------------------------------------------------


-- Update index
drop index CALENDAR_OBJECT_CALEN_96e83b73;
create index CALENDAR_OBJECT_CALEN_c4dc619c on CALENDAR_OBJECT (
    CALENDAR_RESOURCE_ID,
    RECURRANCE_MAX,
    RECURRANCE_MIN
);

-- New indexes

create index CALENDAR_OBJECT_REVIS_550b1c56 on CALENDAR_OBJECT_REVISIONS (
    CALENDAR_HOME_RESOURCE_ID,
    REVISION
);

create index PUSH_NOTIFICATION_WOR_3a3ee588 on PUSH_NOTIFICATION_WORK (
    PUSH_ID
);

create index GROUP_REFRESH_WORK_GR_0325f3a8 on GROUP_REFRESH_WORK (
    GROUP_UID
);

create index GROUP_DELEGATE_CHANGE_d8f7af69 on GROUP_DELEGATE_CHANGES_WORK (
    DELEGATOR_UID
);

create index PRINCIPAL_PURGE_CHECK_198388a5 on PRINCIPAL_PURGE_CHECK_WORK (
    UID
);

create index PRINCIPAL_PURGE_WORK__db35cfdc on PRINCIPAL_PURGE_WORK (
    UID
);


-- update the version
update CALENDARSERVER set VALUE = '49' where NAME = 'VERSION';
