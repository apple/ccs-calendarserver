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
-- Upgrade database schema from VERSION 45 to 46 --
---------------------------------------------------


-- delete data and add contraint to GROUP_ATTENDEE_RECONCILE_WORK

drop table GROUP_ATTENDEE_RECONCILE_WORK;

create table GROUP_ATTENDEE_RECONCILE_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade,
    "GROUP_ID" integer not null references GROUPS on delete cascade
);

create index GROUP_ATTENDEE_RECONC_da73d3c2 on GROUP_ATTENDEE_RECONCILE_WORK (
    JOB_ID
);

create index GROUP_ATTENDEE_RECONC_b894ee7a on GROUP_ATTENDEE_RECONCILE_WORK (
    RESOURCE_ID
);

create index GROUP_ATTENDEE_RECONC_5eabc549 on GROUP_ATTENDEE_RECONCILE_WORK (
    GROUP_ID
);

  
-- schema for group sharees

insert into CALENDAR_BIND_MODE (DESCRIPTION, ID) values ('group', 5);
insert into CALENDAR_BIND_MODE (DESCRIPTION, ID) values ('group_read', 6);
insert into CALENDAR_BIND_MODE (DESCRIPTION, ID) values ('group_write', 7);


create table GROUP_SHAREE_RECONCILE_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "CALENDAR_ID" integer not null references CALENDAR on delete cascade,
    "GROUP_ID" integer not null references GROUPS on delete cascade
);

create index GROUP_SHAREE_RECONCIL_9aad0858 on GROUP_SHAREE_RECONCILE_WORK (
    JOB_ID
);

create index GROUP_SHAREE_RECONCIL_4dc60f78 on GROUP_SHAREE_RECONCILE_WORK (
    CALENDAR_ID
);

create index GROUP_SHAREE_RECONCIL_1d14c921 on GROUP_SHAREE_RECONCILE_WORK (
    GROUP_ID
);


create table GROUP_SHAREE (
    "GROUP_ID" integer not null references GROUPS on delete cascade,
    "CALENDAR_ID" integer not null references CALENDAR on delete cascade,
    "GROUP_BIND_MODE" integer not null,
    "MEMBERSHIP_HASH" nvarchar2(255), 
    primary key ("GROUP_ID", "CALENDAR_ID")
);

create index GROUP_SHAREE_CALENDAR_28a88850 on GROUP_SHAREE (
    CALENDAR_ID
);


-- update the version
update CALENDARSERVER set VALUE = '46' where NAME = 'VERSION';
