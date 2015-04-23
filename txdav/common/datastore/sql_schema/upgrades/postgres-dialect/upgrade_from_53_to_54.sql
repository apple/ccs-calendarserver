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
  add column TRASH integer default null references CALENDAR on delete set null;

create index CALENDAR_HOME_METADATA_TRASH on
  CALENDAR_HOME_METADATA(TRASH);

  
-- New columns
alter table CALENDAR_METADATA
  add column CHILD_TYPE     integer      default 0 not null,
  add column TRASHED        timestamp    default null,
  add column IS_IN_TRASH    boolean      default false not null;

-- Enumeration of child type

create table CHILD_TYPE (
  ID          integer     primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into CHILD_TYPE values (0, 'normal');
insert into CHILD_TYPE values (1, 'inbox');
insert into CHILD_TYPE values (2, 'trash');


-- New columns
alter table CALENDAR_OBJECT
  add column TRASHED              timestamp    default null,
  add column ORIGINAL_COLLECTION  integer      default null;


-- New columns
alter table ADDRESSBOOK_OBJECT
  add column TRASHED       timestamp    default null,
  add column IS_IN_TRASH   boolean      default false not null;



-- update the version
update CALENDARSERVER set VALUE = '54' where NAME = 'VERSION';
