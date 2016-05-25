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
-- Upgrade database schema from VERSION 61 to 62 --
---------------------------------------------------

-------------------------------------
-- Apple Push Notification Purging --
-------------------------------------

create table APN_PURGING_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ'), -- implicit index
  JOB_ID                        integer      references JOB not null
);

create index APN_PURGING_WORK_JOB_ID on
  APN_PURGING_WORK(JOB_ID);

-- update the version
update CALENDARSERVER set VALUE = '62' where NAME = 'VERSION';
