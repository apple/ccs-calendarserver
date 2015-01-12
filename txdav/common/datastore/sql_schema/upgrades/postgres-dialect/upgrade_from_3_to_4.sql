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

-------------------------------------------------
-- Upgrade database schema from VERSION 3 to 4 --
-------------------------------------------------

-- Just need to modify one column
alter table CALENDAR_OBJECT
 alter column SCHEDULE_OBJECT drop not null;

-- Now update the version
update CALENDARSERVER set VALUE = '4' where NAME = 'VERSION';

