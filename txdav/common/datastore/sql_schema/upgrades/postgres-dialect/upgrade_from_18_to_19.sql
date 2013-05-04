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

----------------
-- New Tables --
----------------

-----------------------------
-- Shared AddressBook Bind --
-----------------------------

-- Joins sharee ADDRESSBOOK_HOME and owner ADDRESSBOOK_HOME

create table SHARED_ADDRESSBOOK_BIND (
  ADDRESSBOOK_HOME_RESOURCE_ID			integer			not null references ADDRESSBOOK_HOME,
  OWNER_ADDRESSBOOK_HOME_RESOURCE_ID    integer      	not null references ADDRESSBOOK_HOME on delete cascade,
  ADDRESSBOOK_RESOURCE_NAME    			varchar(255) 	not null,
  BIND_MODE                    			integer      	not null,	-- enum CALENDAR_BIND_MODE
  BIND_STATUS                  			integer      	not null,	-- enum CALENDAR_BIND_STATUS
  MESSAGE                      			text,                  		-- FIXME: xml?

  primary key (ADDRESSBOOK_HOME_RESOURCE_ID, OWNER_ADDRESSBOOK_HOME_RESOURCE_ID), -- implicit index
  unique (ADDRESSBOOK_HOME_RESOURCE_ID, ADDRESSBOOK_RESOURCE_NAME)     -- implicit index
);

create index SHARED_ADDRESSBOOK_BIND_RESOURCE_ID on
  SHARED_ADDRESSBOOK_BIND(OWNER_ADDRESSBOOK_HOME_RESOURCE_ID);


-----------------------
-- Shared Group Bind --
-----------------------

-- Joins ADDRESSBOOK_HOME and ADDRESSBOOK_OBJECT (kind == group)

create table SHARED_GROUP_BIND (	
  ADDRESSBOOK_HOME_RESOURCE_ID 		integer      not null references ADDRESSBOOK_HOME,
  GROUP_RESOURCE_ID      			integer      not null references ADDRESSBOOK_OBJECT on delete cascade,
  GROUP_ADDRESSBOOK_RESOURCE_NAME	varchar(255) not null,
  BIND_MODE                    		integer      not null, -- enum CALENDAR_BIND_MODE
  BIND_STATUS                  		integer      not null, -- enum CALENDAR_BIND_STATUS
  MESSAGE                      		text,                  -- FIXME: xml?

  primary key (ADDRESSBOOK_HOME_RESOURCE_ID, GROUP_RESOURCE_ID), -- implicit index
  unique (ADDRESSBOOK_HOME_RESOURCE_ID, GROUP_ADDRESSBOOK_RESOURCE_NAME)     -- implicit index
);

create index SHARED_GROUP_BIND_RESOURCE_ID on
  SHARED_GROUP_BIND(GROUP_RESOURCE_ID);

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
-- Alter  ADDRESSBOOK_HOME --
-----------------------------

alter table ADDRESSBOOK_HOME
	add column	ADDRESSBOOK_PROPERTY_STORE_ID	integer	default nextval('RESOURCE_ID_SEQ') not null;

update ADDRESSBOOK_HOME
	set	ADDRESSBOOK_PROPERTY_STORE_ID = (
		select ADDRESSBOOK_RESOURCE_ID
			from ADDRESSBOOK_BIND
		where 
			ADDRESSBOOK_BIND.ADDRESSBOOK_HOME_RESOURCE_ID = ADDRESSBOOK_HOME.RESOURCE_ID and
			ADDRESSBOOK_BIND.BIND_MODE = 0 and 	-- CALENDAR_BIND_MODE 'own'
			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_NAME = 'addressbook'
	)
	where exists (
		select *
			from ADDRESSBOOK_BIND
		where 
			ADDRESSBOOK_BIND.ADDRESSBOOK_HOME_RESOURCE_ID = ADDRESSBOOK_HOME.RESOURCE_ID and
			ADDRESSBOOK_BIND.BIND_MODE = 0 and 	-- CALENDAR_BIND_MODE 'own'
			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_NAME = 'addressbook'
  	);
	

--------------------------------
-- change  ADDRESSBOOK_OBJECT --
--------------------------------

alter table ADDRESSBOOK_OBJECT
	add column	KIND	integer	not null;  -- enum ADDRESSBOOK_OBJECT_KIND

alter table ADDRESSBOOK_OBJECT
	add column	ADDRESSBOOK_HOME_RESOURCE_ID	integer	not null references ADDRESSBOOK_HOME on delete cascade;

update ADDRESSBOOK_OBJECT
	set	ADDRESSBOOK_HOME_RESOURCE_ID = (
		select ADDRESSBOOK_HOME_RESOURCE_ID
			from ADDRESSBOOK_BIND
		where 
			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_ID = ADDRESSBOOK_OBJECT.ADDRESSBOOK_RESOURCE_ID and
			ADDRESSBOOK_BIND.BIND_MODE = 0 and 	-- CALENDAR_BIND_MODE 'own'
			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_NAME = 'addressbook'
	), KIND = 0 -- ADDRESSBOOK_OBJECT_KIND 'person'
	where exists (
		select *
			from ADDRESSBOOK_BIND
		where 
			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_ID = ADDRESSBOOK_OBJECT.ADDRESSBOOK_RESOURCE_ID and
			ADDRESSBOOK_BIND.BIND_MODE = 0 and 	-- CALENDAR_BIND_MODE 'own'
			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_NAME = 'addressbook'
  	);

alter table ADDRESSBOOK_OBJECT
	drop column	ADDRESSBOOK_RESOURCE_ID;

	
------------------------------------------
-- change  ADDRESSBOOK_OBJECT_REVISIONS --
------------------------------------------

alter table ADDRESSBOOK_OBJECT_REVISIONS
	add column	OWNER_ADDRESSBOOK_HOME_RESOURCE_ID	integer	not null references ADDRESSBOOK_HOME on delete cascade;

update ADDRESSBOOK_OBJECT_REVISIONS
	set	OWNER_ADDRESSBOOK_HOME_RESOURCE_ID = (
		select ADDRESSBOOK_HOME_RESOURCE_ID
			from ADDRESSBOOK_BIND
		where 
			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_ID = ADDRESSBOOK_OBJECT_REVISIONS.ADDRESSBOOK_RESOURCE_ID and
			ADDRESSBOOK_BIND.BIND_MODE = 0 and 	-- CALENDAR_BIND_MODE 'own'
			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_NAME = 'addressbook'
	)
	where exists (
		select *
			from ADDRESSBOOK_BIND
		where 
			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_ID = ADDRESSBOOK_OBJECT_REVISIONS.ADDRESSBOOK_RESOURCE_ID and
			ADDRESSBOOK_BIND.BIND_MODE = 0 and 	-- CALENDAR_BIND_MODE 'own'
			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_NAME = 'addressbook'
  	);

alter table ADDRESSBOOK_OBJECT_REVISIONS
	drop column	ADDRESSBOOK_RESOURCE_ID;

----------------------------------------------------------------------------
-- delete RESOURCE_PROPERTY rows for shared and non-default address books --
----------------------------------------------------------------------------

delete 
	from RESOURCE_PROPERTY
	where exists (
		select *
			from ADDRESSBOOK_BIND
		where 
			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_ID = RESOURCE_PROPERTY.RESOURCE_ID and (
				ADDRESSBOOK_BIND.BIND_MODE != 0 or 	-- CALENDAR_BIND_MODE 'own'
	 			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_NAME != 'addressbook'
	 		)
  	);

	
-------------------------------------
-- Drop ADDRESSBOOK related tables --
-------------------------------------

drop table ADDRESSBOOK_METADATA;
drop table ADDRESSBOOK_BIND;
drop table ADDRESSBOOK;
  
-- update schema version
update CALENDARSERVER set VALUE = '19' where NAME = 'VERSION';
