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
-- Upgrade database schema from VERSION 41 to 42 --
---------------------------------------------------

-----------------
-- Job Changes --
-----------------

alter table JOB
  alter column NOT_BEFORE drop default,
  alter column NOT_BEFORE set not null,
  add column FAILED integer default 0;

alter table JOB
  rename column NOT_AFTER to ASSIGNED;

-- update the version
update CALENDARSERVER set VALUE = '42' where NAME = 'VERSION';
