----
-- Copyright (c) 2012-2016 Apple Inc. All rights reserved.
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
-- Upgrade database schema from VERSION 60 to 61 --
---------------------------------------------------

-- Create indexes
create index CALENDAR_OBJECT_REVIS_fa21ef83 on CALENDAR_OBJECT_REVISIONS (
    "REVISION"
);

create index ADDRESSBOOK_OBJECT_RE_0900cfdf on ADDRESSBOOK_OBJECT_REVISIONS (
    "REVISION"
);

create index NOTIFICATION_OBJECT_R_c251f0fd on NOTIFICATION_OBJECT_REVISIONS (
    "REVISION"
);

-- New table
create table INBOX_REMOVE_WORK (
    "WORK_ID" integer primary key,
    "JOB_ID" integer not null references JOB,
    "HOME_ID" integer not null references CALENDAR_HOME on delete cascade,
    "RESOURCE_NAME" nvarchar2(255), 
    unique ("HOME_ID", "RESOURCE_NAME")
);

create index INBOX_REMOVE_WORK_JOB_4b627f1e on INBOX_REMOVE_WORK (
    "JOB_ID"
);

-- update the version
update CALENDARSERVER set VALUE = '61' where NAME = 'VERSION';
