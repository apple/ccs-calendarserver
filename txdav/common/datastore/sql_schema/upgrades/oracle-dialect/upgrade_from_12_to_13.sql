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
-- Upgrade database schema from VERSION 12 to 13 --
---------------------------------------------------

-- Attachment related updates

create sequence ATTACHMENT_ID_SEQ;

alter table ATTACHMENT
 drop primary key;

-- not needed; DROPBOX_ID becomes nullable after dropping primary key above
-- alter table ATTACHMENT
--  modify (DROPBOX_ID null);

-- We want ATTACHMENT_ID as a pkey, but can't yet since it needs unique values,
-- and oracle can't set a default column value from a sequence
alter table ATTACHMENT
 add ("ATTACHMENT_ID" integer);

-- fill in ATTACHMENT_ID with unique values from the sequence
update ATTACHMENT set ATTACHMENT_ID = ATTACHMENT_ID_SEQ.nextval;

-- now set ATTACHMENT_ID as primary key, which implies unique and not null
alter table ATTACHMENT
 add primary key(ATTACHMENT_ID);

create table ATTACHMENT_CALENDAR_OBJECT (
    "ATTACHMENT_ID" integer not null references ATTACHMENT on delete cascade,
    "MANAGED_ID" nvarchar2(255),
    "CALENDAR_OBJECT_RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade, 
    primary key ("ATTACHMENT_ID", "CALENDAR_OBJECT_RESOURCE_ID"), 
    unique ("MANAGED_ID", "CALENDAR_OBJECT_RESOURCE_ID")
);


-- Now update the version
-- No data upgrades
update CALENDARSERVER set VALUE = '13' where NAME = 'VERSION';
