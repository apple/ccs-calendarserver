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
-- Upgrade database schema from VERSION 29 to 30 --
---------------------------------------------------

-- Sharing notification related updates

alter table NOTIFICATION_HOME
 add ("DATAVERSION" integer default 0 not null);

alter table NOTIFICATION
  rename column XML_TYPE to NOTIFICATION_TYPE;
alter table NOTIFICATION
  rename column XML_DATA to NOTIFICATION_DATA;

  -- Sharing enumeration updates
insert into CALENDAR_BIND_MODE (DESCRIPTION, ID) values ('indirect', 4);

insert into CALENDAR_BIND_STATUS (DESCRIPTION, ID) values ('deleted', 4);

-- Now update the version
update CALENDARSERVER set VALUE = '30' where NAME = 'VERSION';
insert into CALENDARSERVER (NAME, VALUE) values ('NOTIFICATION-DATAVERSION', '1');
