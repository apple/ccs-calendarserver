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
