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
-- Upgrade database schema from VERSION 51 to 52 --
---------------------------------------------------

-- New status value
insert into HOME_STATUS (DESCRIPTION, ID) values ('migrating', 3);

-- New table
create table CALENDAR_MIGRATION_STATE (
    "CALENDAR_HOME_RESOURCE_ID" integer references CALENDAR_HOME on delete cascade,
    "REMOTE_RESOURCE_ID" integer not null,
    "CALENDAR_RESOURCE_ID" integer references CALENDAR on delete cascade,
    "LAST_SYNC_TOKEN" nvarchar2(255), 
    primary key ("CALENDAR_HOME_RESOURCE_ID", "REMOTE_RESOURCE_ID")
);

create index CALENDAR_MIGRATION_ST_57f40e9a on CALENDAR_MIGRATION_STATE (
    CALENDAR_RESOURCE_ID
);


-- update the version
update CALENDARSERVER set VALUE = '52' where NAME = 'VERSION';
