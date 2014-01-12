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

-------------------------------------------------
-- Upgrade database schema from VERSION 8 to 9 --
-------------------------------------------------

-- Drop one index and create a new one for both primary revisions tables
drop index CALENDAR_OBJECT_REVISIONS_HOME_RESOURCE_ID;
create index CALENDAR_OBJECT_REVISIONS_HOME_RESOURCE_ID_CALENDAR_RESOURCE_ID
  on CALENDAR_OBJECT_REVISIONS(CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_ID);

drop index ADDRESSBOOK_OBJECT_REVISIONS_HOME_RESOURCE_ID;
create index ADDRESSBOOK_OBJECT_REVISIONS_HOME_RESOURCE_ID_ADDRESSBOOK_RESOURCE_ID
  on ADDRESSBOOK_OBJECT_REVISIONS(ADDRESSBOOK_HOME_RESOURCE_ID, ADDRESSBOOK_RESOURCE_ID);

-- Now update the version
-- No data upgrades
update CALENDARSERVER set VALUE = '9' where NAME = 'VERSION';
