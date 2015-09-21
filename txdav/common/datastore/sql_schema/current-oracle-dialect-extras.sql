----
-- Copyright (c) 2010-2015 Apple Inc. All rights reserved.
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

create or replace function next_job_all(now timestamp)
  return integer is
  cursor c1 is
   select JOB_ID from JOB
   where ASSIGNED is NULL and PAUSE = 0 and NOT_BEFORE <= now
   order by PRIORITY desc
   for update skip locked;
  result integer;
begin
  open c1;
  fetch c1 into result;
  close c1;
  return result;
end;
/

create or replace function next_job_medium_high(now timestamp)
  return integer is
  cursor c1 is
    select JOB_ID from JOB
    where PRIORITY != 0 and ASSIGNED is NULL and PAUSE = 0 and NOT_BEFORE <= now
    order by PRIORITY desc
    for update skip locked;
  result integer;
begin
  open c1;
  fetch c1 into result;
  close c1;
  return result;
end;
/

create or replace function next_job_high(now timestamp)
  return integer is
  cursor c1 is
    select JOB_ID from JOB
    where PRIORITY = 2 and ASSIGNED is NULL and PAUSE = 0 and NOT_BEFORE <= now
    order by PRIORITY desc
    for update skip locked;
  result integer;
begin
  open c1;
  fetch c1 into result;
  close c1;
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
