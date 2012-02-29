----
-- Copyright (c) 2012 Apple Inc. All rights reserved.
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

update CALENDAR_HOME set OWNER_UID = lower(OWNER_UID);

alter table CALENDAR_HOME
add constraint CALENDAR_HOME_CASE check(OWNER_UID = lower(OWNER_UID));

update ADDRESSBOOK_HOME set OWNER_UID = lower(OWNER_UID);

alter table ADDRESSBOOK_HOME
add constraint ADDRESSBOOK_HOME_CASE check(OWNER_UID = lower(OWNER_UID));

update NOTIFICATION_HOME set OWNER_UID = lower(OWNER_UID);

alter table NOTIFICATION_HOME
add constraint NOTIFICATION_HOME_CASE check(OWNER_UID = lower(OWNER_UID));

update CALENDARSERVER set VALUE = '9' where NAME = 'VERSION';
