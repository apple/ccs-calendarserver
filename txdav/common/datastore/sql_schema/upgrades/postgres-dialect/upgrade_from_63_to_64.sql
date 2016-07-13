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
-- Upgrade database schema from VERSION 63 to 64 --
---------------------------------------------------

-- JOB table changes
alter table JOB add column IS_ASSIGNED integer default 0 not null;
alter table JOB alter column PRIORITY set not null;
alter table JOB alter column WEIGHT set not null;
alter table JOB alter column FAILED set not null;
alter table JOB alter column PAUSE set not null;

drop index JOB_PRIORITY_ASSIGNED_PAUSE_NOT_BEFORE;
create index JOB_PRIORITY_IS_ASSIGNED_PAUSE_NOT_BEFORE_JOB_ID on
  JOB(PRIORITY, IS_ASSIGNED, PAUSE, NOT_BEFORE, JOB_ID);

drop index JOB_ASSIGNED_OVERDUE;
create index JOB_IS_ASSIGNED_OVERDUE_JOB_ID on
  JOB(IS_ASSIGNED, OVERDUE, JOB_ID);


-- update the version
update CALENDARSERVER set VALUE = '64' where NAME = 'VERSION';
