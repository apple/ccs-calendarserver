----
-- Copyright (c) 2011-2015 Apple Inc. All rights reserved.
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
-- Upgrade database schema from VERSION 20 to 21 --
---------------------------------------------------

--------------------------
-- Update CALENDAR_BIND --
--------------------------

update CALENDAR_BIND set MESSAGE = 'shared' where BIND_MODE = 0 and CALENDAR_RESOURCE_ID in (select CALENDAR_RESOURCE_ID from CALENDAR_BIND group by CALENDAR_RESOURCE_ID having count(CALENDAR_RESOURCE_ID) > 1);

-- update schema version
update CALENDARSERVER set VALUE = '21' where NAME = 'VERSION';
