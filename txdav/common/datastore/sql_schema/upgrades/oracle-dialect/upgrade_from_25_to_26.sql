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
-- Upgrade database schema from VERSION 25 to 26 --
---------------------------------------------------

-- Replace index

drop index CALENDAR_OBJECT_REVIS_2643d556;
create index CALENDAR_OBJECT_REVIS_6d9d929c on CALENDAR_OBJECT_REVISIONS (
    CALENDAR_RESOURCE_ID,
    RESOURCE_NAME,
    DELETED,
    REVISION
);


drop index ADDRESSBOOK_OBJECT_RE_980b9872;
create index ADDRESSBOOK_OBJECT_RE_00fe8288 on ADDRESSBOOK_OBJECT_REVISIONS (
    OWNER_HOME_RESOURCE_ID,
    RESOURCE_NAME,
    DELETED,
    REVISION
);


-- Now update the version
-- No data upgrades
update CALENDARSERVER set VALUE = '26' where NAME = 'VERSION';
