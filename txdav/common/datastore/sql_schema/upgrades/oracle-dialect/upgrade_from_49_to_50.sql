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
-- Upgrade database schema from VERSION 49 to 50 --
---------------------------------------------------


-- Update existing table
alter table SCHEDULE_REPLY_WORK drop column CHANGED_RIDS;
alter table SCHEDULE_REPLY_WORK add ("ITIP_MSG" nclob);

begin
    for i in (select constraint_name
              from   user_cons_columns
              where  table_name = 'SCHEDULE_REPLY_WORK' and
                     column_name = 'RESOURCE_ID' ) loop
        execute immediate 'alter table SCHEDULE_REPLY_WORK drop constraint '|| i.constraint_name;
    end loop;
end;
alter table SCHEDULE_REPLY_WORK modify ("RESOURCE_ID" null);

-- Copy over items from existing table about to be dropped
insert into SCHEDULE_REPLY_WORK
	(WORK_ID, HOME_RESOURCE_ID, RESOURCE_ID, ITIP_MSG)
	(select WORK_ID, HOME_RESOURCE_ID, null, ICALENDAR_TEXT from SCHEDULE_REPLY_CANCEL_WORK);

-- Delete existing table
drop table SCHEDULE_REPLY_CANCEL_WORK;


-- update the version
update CALENDARSERVER set VALUE = '50' where NAME = 'VERSION';
