----
-- Copyright (c) 2011 Apple Inc. All rights reserved.
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
-- Upgrade database schema from VERSION 5 to 6 --
-------------------------------------------------

-- Just need to add one column
alter table CALENDAR_HOME
 add column DATAVERSION integer default 1 null;
 
-- Just need to add one column
alter table CALENDAR
 add column SUPPORTED_COMPONENTS varchar(255) default null;

-- Just need to add one column
alter table ADDRESSBOOK_HOME
 add column DATAVERSION integer default 1 null;
 
-- Now update the version
update CALENDARSERVER set VALUE = '6' where NAME = 'VERSION';

-- Also insert the initial data version which we will use in the data upgrade
insert into CALENDARSERVER values ('CALENDAR-DATAVERSION', '1');
insert into CALENDARSERVER values ('ADDRESSBOOK-DATAVERSION', '1');
