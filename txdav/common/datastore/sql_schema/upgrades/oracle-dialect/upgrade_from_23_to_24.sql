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
-- Upgrade database schema from VERSION 23 to 24 --
---------------------------------------------------

-- Missing index fix
create index CALENDAR_HOME_METADAT_3cb9049e on CALENDAR_HOME_METADATA (
    DEFAULT_EVENTS
);
create index CALENDAR_HOME_METADAT_d55e5548 on CALENDAR_HOME_METADATA (
    DEFAULT_TASKS
);

create index ATTACHMENT_CALENDAR_O_81508484 on ATTACHMENT_CALENDAR_OBJECT (
    CALENDAR_OBJECT_RESOURCE_ID
);

create index ABO_MEMBERS_ADDRESSBO_4effa879 on ABO_MEMBERS (
    ADDRESSBOOK_ID
);
create index ABO_MEMBERS_MEMBER_ID_8d66adcf on ABO_MEMBERS (
    MEMBER_ID
);

create index ABO_FOREIGN_MEMBERS_A_1fd2c5e9 on ABO_FOREIGN_MEMBERS (
    ADDRESSBOOK_ID
);

create index CALENDAR_OBJECT_SPLIT_af71dcda on CALENDAR_OBJECT_SPLITTER_WORK (
    RESOURCE_ID
);

-- Now update the version
-- No data upgrades
update CALENDARSERVER set VALUE = '24' where NAME = 'VERSION';
