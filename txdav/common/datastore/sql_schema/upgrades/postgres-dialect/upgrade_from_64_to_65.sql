----
-- Copyright (c) 2012-2017 Apple Inc. All rights reserved.
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
-- Upgrade database schema from VERSION 64 to 65 --
---------------------------------------------------

-- JOB table changes
drop index JOB_ASSIGNED_PAUSE_NOT_BEFORE;
create index JOB_IS_ASSIGNED_PAUSE_NOT_BEFORE on
  JOB(IS_ASSIGNED, PAUSE, NOT_BEFORE, JOB_ID);


-- update the version
update CALENDARSERVER set VALUE = '65' where NAME = 'VERSION';
