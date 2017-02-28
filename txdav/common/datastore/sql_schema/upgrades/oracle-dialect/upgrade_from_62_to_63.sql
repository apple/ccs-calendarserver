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
-- Upgrade database schema from VERSION 62 to 63 --
---------------------------------------------------

create index CALENDAR_OBJECT_ORIGI_53447b73 on CALENDAR_OBJECT (
    "ORIGINAL_COLLECTION",
    "TRASHED"
);

-- Replace three stored procedures with one new one
drop function next_job_all;
drop function next_job_medium_high;
drop function next_job_high;

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

-- update the version
update CALENDARSERVER set VALUE = '63' where NAME = 'VERSION';
