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
-- Upgrade database schema from VERSION 36 to 37 --
---------------------------------------------------

------------------------
-- Inbox Cleanup Work --
------------------------

create sequence JOB_SEQ;

create table JOB (
  JOB_ID      integer primary key default nextval('JOB_SEQ') not null, --implicit index
  WORK_TYPE   varchar(255) not null,
  PRIORITY    integer default 0,
  WEIGHT      integer default 0,
  NOT_BEFORE  timestamp default null,
  NOT_AFTER   timestamp default null
);

create or replace function next_job() returns integer as $$
declare
  result integer;
begin
  select ID into result from JOB where pg_try_advisory_xact_lock(ID) limit 1 for update;
  return result;
end
$$ LANGUAGE plpgsql;


-- IMIP_INVITATION_WORK --
alter table IMIP_INVITATION_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'IMIP_INVITATION_WORK', NOT_BEFORE from IMIP_INVITATION_WORK);

alter table IMIP_INVITATION_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index IMIP_INVITATION_WORK_JOB_ID on
  IMIP_INVITATION_WORK(JOB_ID);


-- IMIP_POLLING_WORK --
alter table IMIP_POLLING_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'IMIP_POLLING_WORK', NOT_BEFORE from IMIP_POLLING_WORK);

alter table IMIP_POLLING_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index IMIP_POLLING_WORK_JOB_ID on
  IMIP_POLLING_WORK(JOB_ID);


-- IMIP_REPLY_WORK --
alter table IMIP_REPLY_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'IMIP_REPLY_WORK', NOT_BEFORE from IMIP_REPLY_WORK);

alter table IMIP_REPLY_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index IMIP_REPLY_WORK_JOB_ID on
  IMIP_REPLY_WORK(JOB_ID);


-- PUSH_NOTIFICATION_WORK --
alter table PUSH_NOTIFICATION_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;
alter table PUSH_NOTIFICATION_WORK
    rename PRIORITY to PUSH_PRIORITY;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'PUSH_NOTIFICATION_WORK', NOT_BEFORE from PUSH_NOTIFICATION_WORK);

alter table PUSH_NOTIFICATION_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index PUSH_NOTIFICATION_WORK_JOB_ID on
  PUSH_NOTIFICATION_WORK(JOB_ID);


-- GROUP_CACHER_POLLING_WORK --
alter table GROUP_CACHER_POLLING_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'GROUP_CACHER_POLLING_WORK', NOT_BEFORE from GROUP_CACHER_POLLING_WORK);

alter table GROUP_CACHER_POLLING_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index GROUP_CACHER_POLLING_WORK_JOB_ID on
  GROUP_CACHER_POLLING_WORK(JOB_ID);


-- GROUP_REFRESH_WORK --
alter table GROUP_REFRESH_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'GROUP_REFRESH_WORK', NOT_BEFORE from GROUP_REFRESH_WORK);

alter table GROUP_REFRESH_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index GROUP_REFRESH_WORK_JOB_ID on
  GROUP_REFRESH_WORK(JOB_ID);


-- GROUP_ATTENDEE_RECONCILIATION_WORK --
alter table GROUP_ATTENDEE_RECONCILIATION_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'GROUP_ATTENDEE_RECONCILIATION_WORK', NOT_BEFORE from GROUP_ATTENDEE_RECONCILIATION_WORK);

alter table GROUP_ATTENDEE_RECONCILIATION_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index GROUP_ATTENDEE_RECONCILIATION_WORK_JOB_ID on
  GROUP_ATTENDEE_RECONCILIATION_WORK(JOB_ID);


-- CALENDAR_OBJECT_SPLITTER_WORK --
alter table CALENDAR_OBJECT_SPLITTER_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'CALENDAR_OBJECT_SPLITTER_WORK', NOT_BEFORE from CALENDAR_OBJECT_SPLITTER_WORK);

alter table CALENDAR_OBJECT_SPLITTER_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index CALENDAR_OBJECT_SPLITTER_WORK_JOB_ID on
  CALENDAR_OBJECT_SPLITTER_WORK(JOB_ID);


-- FIND_MIN_VALID_REVISION_WORK --
alter table FIND_MIN_VALID_REVISION_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'FIND_MIN_VALID_REVISION_WORK', NOT_BEFORE from FIND_MIN_VALID_REVISION_WORK);

alter table FIND_MIN_VALID_REVISION_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index FIND_MIN_VALID_REVISION_WORK_JOB_ID on
  FIND_MIN_VALID_REVISION_WORK(JOB_ID);


-- REVISION_CLEANUP_WORK --
alter table REVISION_CLEANUP_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'REVISION_CLEANUP_WORK', NOT_BEFORE from REVISION_CLEANUP_WORK);

alter table REVISION_CLEANUP_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index REVISION_CLEANUP_WORK_JOB_ID on
  REVISION_CLEANUP_WORK(JOB_ID);


-- INBOX_CLEANUP_WORK --
alter table INBOX_CLEANUP_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'INBOX_CLEANUP_WORK', NOT_BEFORE from INBOX_CLEANUP_WORK);

alter table INBOX_CLEANUP_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index INBOX_CLEANUP_WORK_JOB_ID on
  INBOX_CLEANUP_WORK(JOB_ID);


-- CLEANUP_ONE_INBOX_WORK --
alter table CLEANUP_ONE_INBOX_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'CLEANUP_ONE_INBOX_WORK', NOT_BEFORE from CLEANUP_ONE_INBOX_WORK);

alter table CLEANUP_ONE_INBOX_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index CLEANUP_ONE_INBOX_WORK_JOB_ID on
  CLEANUP_ONE_INBOX_WORK(JOB_ID);


-- SCHEDULE_REFRESH_WORK --
alter table SCHEDULE_REFRESH_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'SCHEDULE_REFRESH_WORK', NOT_BEFORE from SCHEDULE_REFRESH_WORK);

alter table SCHEDULE_REFRESH_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index SCHEDULE_REFRESH_WORK_JOB_ID on
  SCHEDULE_REFRESH_WORK(JOB_ID);


-- SCHEDULE_AUTO_REPLY_WORK --
alter table SCHEDULE_AUTO_REPLY_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'SCHEDULE_AUTO_REPLY_WORK', NOT_BEFORE from SCHEDULE_AUTO_REPLY_WORK);

alter table SCHEDULE_AUTO_REPLY_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index SCHEDULE_AUTO_REPLY_WORK_JOB_ID on
  SCHEDULE_AUTO_REPLY_WORK(JOB_ID);


-- SCHEDULE_ORGANIZER_WORK --
alter table SCHEDULE_ORGANIZER_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'SCHEDULE_ORGANIZER_WORK', NOT_BEFORE from SCHEDULE_ORGANIZER_WORK);

alter table SCHEDULE_ORGANIZER_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index SCHEDULE_ORGANIZER_WORK_JOB_ID on
  SCHEDULE_ORGANIZER_WORK(JOB_ID);


-- SCHEDULE_REPLY_WORK --
alter table SCHEDULE_REPLY_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'SCHEDULE_REPLY_WORK', NOT_BEFORE from SCHEDULE_REPLY_WORK);

alter table SCHEDULE_REPLY_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index SCHEDULE_REPLY_WORK_JOB_ID on
  SCHEDULE_REPLY_WORK(JOB_ID);


-- SCHEDULE_REPLY_CANCEL_WORK --
alter table SCHEDULE_REPLY_CANCEL_WORK
    add JOB_ID  integer default nextval('JOB_SEQ') not null;

insert into JOB
  (JOB_ID, WORK_TYPE, NOT_BEFORE)
  (select JOB_ID, 'SCHEDULE_REPLY_CANCEL_WORK', NOT_BEFORE from SCHEDULE_REPLY_CANCEL_WORK);

alter table SCHEDULE_REPLY_CANCEL_WORK
    drop column NOT_BEFORE,
    add foreign key (JOB_ID) references JOB;

create index SCHEDULE_REPLY_CANCEL_WORK_JOB_ID on
  SCHEDULE_REPLY_CANCEL_WORK(JOB_ID);

  
-- update the version
update CALENDARSERVER set VALUE = '37' where NAME = 'VERSION';
