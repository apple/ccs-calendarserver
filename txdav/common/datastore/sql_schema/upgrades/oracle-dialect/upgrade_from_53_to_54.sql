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
-- Upgrade database schema from VERSION 53 to 54 --
---------------------------------------------------

-- New columns
alter table CALENDAR_HOME_METADATA
  add ("TRASH" integer default null references CALENDAR on delete set null);

create index CALENDAR_HOME_METADAT_475de898 on CALENDAR_HOME_METADATA (
    TRASH
);

  
-- New columns
alter table CALENDAR_METADATA
  add ("CHILD_TYPE" integer default 0 not null)
  add ("TRASHED" timestamp default null)
  add ("IS_IN_TRASH" integer default 0 not null);

-- Enumeration of child type

create table CHILD_TYPE (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(16) unique
);

insert into CHILD_TYPE (DESCRIPTION, ID) values ('normal', 0);
insert into CHILD_TYPE (DESCRIPTION, ID) values ('inbox', 1);
insert into CHILD_TYPE (DESCRIPTION, ID) values ('trash', 2);


-- New columns
alter table CALENDAR_OBJECT
  add ("TRASHED" timestamp default null)
  add ("ORIGINAL_COLLECTION" integer default null);


-- New columns
alter table ADDRESSBOOK_OBJECT
  add ("TRASHED" timestamp default null)
  add ("IS_IN_TRASH" integer default 0 not null);


-- update the version
update CALENDARSERVER set VALUE = '54' where NAME = 'VERSION';
