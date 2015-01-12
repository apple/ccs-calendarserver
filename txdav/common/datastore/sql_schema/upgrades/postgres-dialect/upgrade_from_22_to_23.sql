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
-- Upgrade database schema from VERSION 22 to 23 --
---------------------------------------------------

-- Object Splitter Work --

create table CALENDAR_OBJECT_SPLITTER_WORK (
  WORK_ID                       integer      primary key default nextval('WORKITEM_SEQ') not null,
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  RESOURCE_ID                   integer      not null references CALENDAR_OBJECT on delete cascade
);


 -- update schema version
update CALENDARSERVER set VALUE = '23' where NAME = 'VERSION';
