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
-- Upgrade database schema from VERSION XX to YY --
---------------------------------------------------


-- Downgrade from hash partitioned indexes

-- CALENDAR_OBJECT Table

-- Disable the pkey and foreign key constraints
ALTER TABLE CALENDAR_OBJECT DISABLE CONSTRAINT SYS_C004279 CASCADE;

-- Hash partition the primary key index
ALTER TABLE CALENDAR_OBJECT ENABLE CONSTRAINT SYS_C004279 USING INDEX TABLESPACE DATA_TS;

-- Enable the foreign key constraints
ALTER TABLE TIME_RANGE ENABLE CONSTRAINT SYS_C004296;
ALTER TABLE ATTACHMENT_CALENDAR_OBJECT ENABLE CONSTRAINT SYS_C0065636;
ALTER TABLE CALENDAR_OBJECT_SPLITTER_WORK ENABLE CONSTRAINT SYS_C0089711;


-- TIME_RANGE Table

-- Disable the pkey and foreign key constraints
ALTER TABLE TIME_RANGE DISABLE CONSTRAINT SYS_C004294 CASCADE;

-- Hash partition the primary key index
ALTER TABLE TIME_RANGE ENABLE CONSTRAINT SYS_C004294 USING INDEX TABLESPACE DATA_TS;

-- Enable the foreign key constraints
ALTER TABLE TRANSPARENCY ENABLE CONSTRAINT SYS_C004301;


-- PUSH_NOTIFICATION_WORK Table

-- Hash partition the primary key index
ALTER TABLE PUSH_NOTIFICATION_WORK DISABLE CONSTRAINT SYS_C0013546 CASCADE;
ALTER TABLE PUSH_NOTIFICATION_WORK ENABLE CONSTRAINT SYS_C0013546 USING INDEX TABLESPACE DATA_TS;
