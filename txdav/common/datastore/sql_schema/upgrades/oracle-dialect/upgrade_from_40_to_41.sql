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
-- Upgrade database schema from VERSION 40 to 41 --
---------------------------------------------------

insert into HOME_STATUS (DESCRIPTION, ID) values ('purging', 2);

--------------------------------
-- Principal Home Remove Work --
--------------------------------

create table PRINCIPAL_PURGE_HOME_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade
);

create index PRINCIPAL_PURGE_HOME__f35eea7a on PRINCIPAL_PURGE_HOME_WORK (
    JOB_ID
);
create index PRINCIPAL_PURGE_HOME__967e4480 on PRINCIPAL_PURGE_HOME_WORK (
    HOME_RESOURCE_ID
);

-- update the version
update CALENDARSERVER set VALUE = '41' where NAME = 'VERSION';
