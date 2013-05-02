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


---------------------------------------------------
-- Upgrade database schema from VERSION 18 to 19 --
---------------------------------------------------

alter table ADDRESSBOOK_HOME
 add column PROPERTY_STORE_ID	integer      	default nextval('RESOURCE_ID_SEQ') not null;

alter table ADDRESSBOOK_BIND
 alter column   ADDRESSBOOK_RESOURCE_ID			  integer;
alter table ADDRESSBOOK_BIND
 add column OWNER_ADDRESSBOOK_HOME_RESOURCE_ID    integer      	not null references ADDRESSBOOK_HOME on delete cascade;

alter table ADDRESSBOOK_BIND
 alter column ADDRESSBOOK_RESOURCE_ID
  drop contraint;

----------------
-- New Tables --
----------------

-----------------------------
-- AddressBook Object kind --
-----------------------------

create table ADDRESSBOOK_OBJECT_KIND (
  ID          integer     primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into ADDRESSBOOK_OBJECT_KIND values (0, 'person');
insert into ADDRESSBOOK_OBJECT_KIND values (1, 'group' );
insert into ADDRESSBOOK_OBJECT_KIND values (2, 'resource');
insert into ADDRESSBOOK_OBJECT_KIND values (3, 'location');


---------------------------------
-- Address Book Object Members --
---------------------------------

create table ABO_MEMBERS (
    GROUP_ID              integer      not null references ADDRESSBOOK_OBJECT on delete cascade,	-- AddressBook Object's (kind=='group') RESOURCE_ID
 	ADDRESSBOOK_ID		  integer      not null references ADDRESSBOOK_HOME on delete cascade,
    MEMBER_ID             integer      not null references ADDRESSBOOK_OBJECT,						-- member AddressBook Object's RESOURCE_ID
    primary key (GROUP_ID, MEMBER_ID) -- implicit index
);


------------------------------------------
-- Address Book Object Foreign Members  --
------------------------------------------

create table ABO_FOREIGN_MEMBERS (
    GROUP_ID              integer      not null references ADDRESSBOOK_OBJECT on delete cascade,	-- AddressBook Object's (kind=='group') RESOURCE_ID
 	ADDRESSBOOK_ID		  integer      not null references ADDRESSBOOK_HOME on delete cascade,
    MEMBER_ADDRESS  	  varchar(255) not null, 													-- member AddressBook Object's 'calendar' address
    primary key (GROUP_ID, MEMBER_ADDRESS) -- implicit index
);


-----------------------------
-- Group Address Book Bind --
-----------------------------

-- Joins ADDRESSBOOK_HOME and ADDRESSBOOK_OBJECT (acting as Address Book)

create table GROUP_ADDRESSBOOK_BIND (	
  ADDRESSBOOK_HOME_RESOURCE_ID 		integer      not null references ADDRESSBOOK_HOME,
  GROUP_RESOURCE_ID      			integer      not null references ADDRESSBOOK_OBJECT on delete cascade,
  GROUP_ADDRESSBOOK_RESOURCE_NAME	varchar(255) not null,
  BIND_MODE                    		integer      not null, -- enum CALENDAR_BIND_MODE
  BIND_STATUS                  		integer      not null, -- enum CALENDAR_BIND_STATUS
  MESSAGE                      		text,                  -- FIXME: xml?

  primary key (ADDRESSBOOK_HOME_RESOURCE_ID, GROUP_RESOURCE_ID), -- implicit index
  unique (ADDRESSBOOK_HOME_RESOURCE_ID, GROUP_ADDRESSBOOK_RESOURCE_NAME)     -- implicit index
);

create index GROUP_ADDRESSBOOK_BIND_RESOURCE_ID on
  GROUP_ADDRESSBOOK_BIND(GROUP_RESOURCE_ID);
  
  
-- Now update the version
update CALENDARSERVER set VALUE = '19' where NAME = 'VERSION';
