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
drop index JOB_ASSIGNED_PAUSE_NO_b2540b3b;
create index JOB_IS_ASSIGNED_PAUSE_1769af63 on JOB (
    "IS_ASSIGNED",
    "PAUSE",
    "NOT_BEFORE",
    "JOB_ID"
);

-- Updated stored procedures
create or replace function next_job(now in timestamp, min_priority in integer, row_limit in integer)
  return integer is
  cursor c (test_priority number) is
    select JOB_ID from JOB
      where PRIORITY = test_priority and IS_ASSIGNED = 0 and PAUSE = 0 and NOT_BEFORE <= now and ROWNUM <= row_limit
      for update skip locked;
  result integer;
begin
  open c(2);
  fetch c into result;
  close c;
  if result is null and min_priority != 2 then
    open c(1);
    fetch c into result;
    close c;
    if result is null and min_priority = 0 then
      open c(0);
      fetch c into result;
      close c;
    end if;
  end if;
  return result;
end;
/

create or replace function overdue_job(now in timestamp, row_limit in integer)
  return integer is
  cursor c is
   select JOB_ID from JOB
     where IS_ASSIGNED = 1 and OVERDUE <= now and ROWNUM <= row_limit
     for update skip locked;
  result integer;
begin
  open c;
  fetch c into result;
  close c;
  return result;
end;
/

-- update the version
update CALENDARSERVER set VALUE = '65' where NAME = 'VERSION';
