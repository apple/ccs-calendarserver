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
-- Upgrade database schema from VERSION 24 to 25 --
---------------------------------------------------

-- Rename columns and indexes
alter table SHARED_ADDRESSBOOK_BIND
	rename column OWNER_ADDRESSBOOK_HOME_RESOURCE_ID to OWNER_HOME_RESOURCE_ID;

alter table SHARED_GROUP_BIND
	rename column GROUP_ADDRESSBOOK_RESOURCE_NAME to GROUP_ADDRESSBOOK_NAME;

alter table ADDRESSBOOK_OBJECT_REVISIONS
	rename column OWNER_ADDRESSBOOK_HOME_RESOURCE_ID to OWNER_HOME_RESOURCE_ID;

alter index ADDRESSBOOK_OBJECT_REVISIONS_HOME_RESOURCE_ID_OWNER_ADDRESSBOOK_HOME_RESOURCE_ID rename to ADDRESSBOOK_OBJECT_REVISIONS_HOME_RESOURCE_ID_OWNER_HOME_RESOURCE_ID;

-- Now update the version
-- No data upgrades
update CALENDARSERVER set VALUE = '25' where NAME = 'VERSION';
