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
-- Upgrade database schema from VERSION 45 to 46 --
---------------------------------------------------

insert into CALENDAR_BIND_MODE (DESCRIPTION, ID) values ('group', 5);

create table GROUP_SHAREE_RECONCILE_WORK (
  WORK_ID                       integer primary key default nextval('WORKITEM_SEQ') not null, -- implicit index
  JOB_ID                        integer not null references JOB,
  CALENDAR_ID                   integer	not null references CALENDAR on delete cascade,
  GROUP_ID                      integer not null references GROUPS on delete cascade
);

create index GROUP_SHAREE_RECONCILE_WORK_JOB_ID on GROUP_SHAREE_RECONCILE_WORK(
	JOB_ID
);


create table GROUP_SHAREE (
  GROUP_ID                      integer not null references GROUPS on delete cascade,
  CALENDAR_HOME_ID 				integer not null references CALENDAR_HOME on delete cascade,
  CALENDAR_ID      				integer not null references CALENDAR on delete cascade,
  GROUP_BIND_MODE               integer not null, -- enum CALENDAR_BIND_MODE
  MEMBERSHIP_HASH               varchar(255) not null,
  
  primary key (GROUP_ID, CALENDAR_HOME_ID, CALENDAR_ID) -- implicit index
);

create index GROUP_SHAREE_CALENDAR_ID on GROUP_SHAREE(
	CALENDAR_ID
);

-- update the version
update CALENDARSERVER set VALUE = '46' where NAME = 'VERSION';
