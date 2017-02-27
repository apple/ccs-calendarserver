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
-- Upgrade database schema from VERSION 63 to 64 --
---------------------------------------------------

-- JOB table changes
alter table JOB add ("IS_ASSIGNED" integer default 0 not null);
alter table JOB modify ("PRIORITY" not null);
alter table JOB modify ("WEIGHT" not null);
alter table JOB modify ("FAILED" not null);
alter table JOB modify ("PAUSE" not null);

drop index JOB_PRIORITY_ASSIGNED_6d49a082;
create index JOB_PRIORITY_IS_ASSIG_48985bfd on
  JOB(PRIORITY, IS_ASSIGNED, PAUSE, NOT_BEFORE, JOB_ID);

drop index JOB_ASSIGNED_OVERDUE_e88f7afc;
create index JOB_IS_ASSIGNED_OVERD_4a40c3f3 on
  JOB(IS_ASSIGNED, OVERDUE, JOB_ID);

-- Updated stored procedures
create or replace function next_job(now in timestamp, min_priority in integer, row_limit in integer)
  return integer is
  cursor c (priority number) is
    select JOB_ID from JOB
      where PRIORITY = priority AND IS_ASSIGNED = 0 and PAUSE = 0 and NOT_BEFORE <= now and ROWNUM <= row_limit
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

create or replace function overdue_job(now timestamp, row_limit in integer)
  return integer is
  cursor c is
   select JOB_ID from JOB
   where IS_ASSIGNED = 0 and OVERDUE <= now and ROWNUM <= row_limit
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
update CALENDARSERVER set VALUE = '64' where NAME = 'VERSION';
