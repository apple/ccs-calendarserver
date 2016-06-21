----
-- Copyright (c) 2010-2016 Apple Inc. All rights reserved.
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

-- Extra schema to add to current-oracle-dialect.sql

create or replace function next_job(now in timestamp, min_priority in integer)
  return integer is
  cursor c (priority number) is
    select JOB_ID from JOB
      where PRIORITY = priority AND ASSIGNED is NULL and PAUSE = 0 and NOT_BEFORE <= now
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

create or replace function overdue_job(now timestamp)
  return integer is
  cursor c1 is
   select JOB_ID from JOB
   where ASSIGNED is not NULL and OVERDUE <= now
   for update skip locked;
  result integer;
begin
  open c1;
  fetch c1 into result;
  close c1;
  return result;
end;
/
