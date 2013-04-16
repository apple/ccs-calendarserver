----
-- Copyright (c) 2011-2013 Apple Inc. All rights reserved.
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
-- Upgrade database schema from VERSION 17 to 18 --
---------------------------------------------------


-----------------
-- GroupCacher --
-----------------



create table GROUP_CACHER_POLLING_WORK (
  "WORK_ID" integer primary key not null,
  "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);


-- Now update the version
update CALENDARSERVER set VALUE = '18' where NAME = 'VERSION';
