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
-- Upgrade database schema from VERSION 31 to 32 --
---------------------------------------------------

-- Home related updates

alter table CALENDAR_HOME
 add ("STATUS" integer default 0 not null);

alter table NOTIFICATION_HOME
 add ("STATUS" integer default 0 not null);

alter table ADDRESSBOOK_HOME
 add ("STATUS" integer default 0 not null);

create table HOME_STATUS (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(16) unique
);

insert into HOME_STATUS (DESCRIPTION, ID) values ('normal', 0);
insert into HOME_STATUS (DESCRIPTION, ID) values ('external', 1);

-- Bind changes
alter table CALENDAR_BIND
 add ("EXTERNAL_ID" integer default null);

alter table SHARED_ADDRESSBOOK_BIND
 add ("EXTERNAL_ID" integer default null);

alter table SHARED_GROUP_BIND
 add ("EXTERNAL_ID" integer default null);


-- Now update the version
-- No data upgrades
update CALENDARSERVER set VALUE = '32' where NAME = 'VERSION';
