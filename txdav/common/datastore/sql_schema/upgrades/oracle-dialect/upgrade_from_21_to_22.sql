----
-- Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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
-- Upgrade database schema from VERSION 21 to 22 --
---------------------------------------------------
  
-- Calendar home related updates

alter table CALENDAR_HOME_METADATA
 add ("AVAILABILITY" nclob default null);

 	  
-- Calendar related updates

alter table CALENDAR_BIND
 add ("TIMEZONE" nclob default null);


-- update schema version
update CALENDARSERVER set VALUE = '22' where NAME = 'VERSION';
