----
-- Copyright (c) 2011-2013 Apple Inc. All rights reserved.
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
-- Upgrade database schema from VERSION 15 to 16 --
-------------------------------------------------


-----------------
-- IMIP Tokens --
-----------------

create table IMIP_TOKENS (
  TOKEN                         varchar(255) not null,
  ORGANIZER                     varchar(255) not null,
  ATTENDEE                      varchar(255) not null,
  ICALUID                       varchar(255) not null,
  ACCESSED                      timestamp default timezone('UTC', CURRENT_TIMESTAMP),

  primary key (ORGANIZER, ATTENDEE, ICALUID) -- implicit index
);

create index IMIP_TOKENS_TOKEN
   on IMIP_TOKENS(TOKEN);

----------------
-- Work Items --
----------------

create sequence WORKITEM_SEQ;

---------------------------
-- IMIP Inivitation Work --
---------------------------

create table IMIP_INVITATION_WORK (
  WORK_ID                       integer primary key default nextval('WORKITEM_SEQ') not null,
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  FROM_ADDR                     varchar(255) not null,
  TO_ADDR                       varchar(255) not null,
  ICALENDAR_TEXT                text         not null
);

-----------------------
-- IMIP Polling Work --
-----------------------

create table IMIP_POLLING_WORK (
  WORK_ID                       integer primary key default nextval('WORKITEM_SEQ') not null,
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP)
);

---------------------
-- IMIP Reply Work --
---------------------

create table IMIP_REPLY_WORK (
  WORK_ID                       integer primary key default nextval('WORKITEM_SEQ') not null,
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  ORGANIZER                     varchar(255) not null,
  ATTENDEE                      varchar(255) not null,
  ICALENDAR_TEXT                text         not null
);

------------------------
-- Push Notifications --
------------------------

create table PUSH_NOTIFICATION_WORK (
  WORK_ID                       integer primary key default nextval('WORKITEM_SEQ') not null,
  NOT_BEFORE                    timestamp    default timezone('UTC', CURRENT_TIMESTAMP),
  PUSH_ID                       varchar(255) not null
);


-- Now update the version
update CALENDARSERVER set VALUE = '16' where NAME = 'VERSION';

