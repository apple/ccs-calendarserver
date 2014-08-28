----
-- Copyright (c) 2012-2014 Apple Inc. All rights reserved.
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
-- Upgrade database schema from VERSION 47 to 48 --
---------------------------------------------------



-- Add pkey to PERUSER and remove old index
alter table PERUSER add primary key (TIME_RANGE_INSTANCE_ID, USER_ID);
drop index PERUSER_TIME_RANGE_INSTANCE_ID;

-- Add unique to CALENDAR_OBJECT_REVISIONS and remove old index
alter table CALENDAR_OBJECT_REVISIONS add unique(CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_ID, CALENDAR_NAME, RESOURCE_NAME);
drop index CALENDAR_OBJECT_REVISIONS_HOME_RESOURCE_ID_CALENDAR_RESOURCE_ID;

-- Add unique to ADDRESSBOOK_OBJECT_REVISIONS and remove old index
alter table ADDRESSBOOK_OBJECT_REVISIONS add unique(ADDRESSBOOK_HOME_RESOURCE_ID, OWNER_HOME_RESOURCE_ID, ADDRESSBOOK_NAME, RESOURCE_NAME);
drop index ADDRESSBOOK_OBJECT_REVISIONS_HOME_RESOURCE_ID_OWNER_HOME_RESOURCE_ID;


-- update the version
update CALENDARSERVER set VALUE = '48' where NAME = 'VERSION';
