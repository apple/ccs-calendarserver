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
-- Upgrade database schema from VERSION 19 to 20 --
---------------------------------------------------

----------------
-- New Tables --
----------------

-----------------------------
-- Shared AddressBook Bind --
-----------------------------

-- Joins sharee ADDRESSBOOK_HOME and owner ADDRESSBOOK_HOME

create table SHARED_ADDRESSBOOK_BIND (
    "ADDRESSBOOK_HOME_RESOURCE_ID" integer not null references ADDRESSBOOK_HOME,
    "OWNER_HOME_RESOURCE_ID" integer not null references ADDRESSBOOK_HOME on delete cascade,
    "ADDRESSBOOK_RESOURCE_NAME" nvarchar2(255),
    "BIND_MODE" integer not null,
    "BIND_STATUS" integer not null,
    "BIND_REVISION" integer default 0 not null,
    "MESSAGE" nclob, 
    primary key("ADDRESSBOOK_HOME_RESOURCE_ID", "OWNER_HOME_RESOURCE_ID"), 
    unique("ADDRESSBOOK_HOME_RESOURCE_ID", "ADDRESSBOOK_RESOURCE_NAME")
);

create index SHARED_ADDRESSBOOK_BI_e9a2e6d4 on SHARED_ADDRESSBOOK_BIND (
    OWNER_HOME_RESOURCE_ID
);


-----------------------
-- Shared Group Bind --
-----------------------

-- Joins ADDRESSBOOK_HOME and ADDRESSBOOK_OBJECT (kind == group)

create table SHARED_GROUP_BIND (
    "ADDRESSBOOK_HOME_RESOURCE_ID" integer not null references ADDRESSBOOK_HOME,
    "GROUP_RESOURCE_ID" integer not null references ADDRESSBOOK_OBJECT on delete cascade,
    "GROUP_ADDRESSBOOK_NAME" nvarchar2(255),
    "BIND_MODE" integer not null,
    "BIND_STATUS" integer not null,
    "BIND_REVISION" integer default 0 not null,
    "MESSAGE" nclob, 
    primary key("ADDRESSBOOK_HOME_RESOURCE_ID", "GROUP_RESOURCE_ID"), 
    unique("ADDRESSBOOK_HOME_RESOURCE_ID", "GROUP_ADDRESSBOOK_NAME")
);

create index SHARED_GROUP_BIND_RES_cf52f95d on SHARED_GROUP_BIND (
    GROUP_RESOURCE_ID
);

  
-----------------------------
-- AddressBook Object kind --
-----------------------------

create table ADDRESSBOOK_OBJECT_KIND (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(16) unique
);

insert into ADDRESSBOOK_OBJECT_KIND (DESCRIPTION, ID) values ('person', 0);
insert into ADDRESSBOOK_OBJECT_KIND (DESCRIPTION, ID) values ('group', 1);
insert into ADDRESSBOOK_OBJECT_KIND (DESCRIPTION, ID) values ('resource', 2);
insert into ADDRESSBOOK_OBJECT_KIND (DESCRIPTION, ID) values ('location', 3);


---------------------------------
-- Address Book Object Members --
---------------------------------

create table ABO_MEMBERS (
    "GROUP_ID" integer not null references ADDRESSBOOK_OBJECT on delete cascade,
    "ADDRESSBOOK_ID" integer not null references ADDRESSBOOK_HOME on delete cascade,
    "MEMBER_ID" integer not null references ADDRESSBOOK_OBJECT, 
    primary key("GROUP_ID", "MEMBER_ID")
);


------------------------------------------
-- Address Book Object Foreign Members  --
------------------------------------------

create table ABO_FOREIGN_MEMBERS (
    "GROUP_ID" integer not null references ADDRESSBOOK_OBJECT on delete cascade,
    "ADDRESSBOOK_ID" integer not null references ADDRESSBOOK_HOME on delete cascade,
    "MEMBER_ADDRESS" nvarchar2(255), 
    primary key("GROUP_ID", "MEMBER_ADDRESS")
);



-----------------------------
-- Alter  ADDRESSBOOK_HOME --
-----------------------------

alter table ADDRESSBOOK_HOME
	add ("ADDRESSBOOK_PROPERTY_STORE_ID" integer not null);

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
	add ("KIND"	integer)  -- enum ADDRESSBOOK_OBJECT_KIND
	add ("ADDRESSBOOK_HOME_RESOURCE_ID"	integer	references ADDRESSBOOK_HOME on delete cascade);

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

-- delete rows for shared and non-default address books
delete 
	from ADDRESSBOOK_OBJECT
	where exists (
		select *
			from ADDRESSBOOK_BIND
		where 
			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_ID = ADDRESSBOOK_OBJECT.ADDRESSBOOK_RESOURCE_ID and (
				ADDRESSBOOK_BIND.BIND_MODE != 0 or 	-- not CALENDAR_BIND_MODE 'own'
	 			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_NAME != 'addressbook'
	 		)
  	);
  	
-- add non null constraints after update and delete are complete
alter table ADDRESSBOOK_OBJECT
	modify ("KIND" not null,
            "ADDRESSBOOK_HOME_RESOURCE_ID" not null)
	drop ("ADDRESSBOOK_RESOURCE_ID");


alter table ADDRESSBOOK_OBJECT
	add unique ("ADDRESSBOOK_HOME_RESOURCE_ID", "RESOURCE_NAME")
	    unique ("ADDRESSBOOK_HOME_RESOURCE_ID", "VCARD_UID");

------------------------------------------
-- change  ADDRESSBOOK_OBJECT_REVISIONS --
------------------------------------------

alter table ADDRESSBOOK_OBJECT_REVISIONS
	add ("OWNER_HOME_RESOURCE_ID"	integer	references ADDRESSBOOK_HOME);

update ADDRESSBOOK_OBJECT_REVISIONS
	set	OWNER_HOME_RESOURCE_ID = (
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

-- delete rows for shared and non-default address books
delete 
	from ADDRESSBOOK_OBJECT_REVISIONS
	where exists (
		select *
			from ADDRESSBOOK_BIND
		where 
			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_ID = ADDRESSBOOK_OBJECT_REVISIONS.ADDRESSBOOK_RESOURCE_ID and (
				ADDRESSBOOK_BIND.BIND_MODE != 0 or 	-- not CALENDAR_BIND_MODE 'own'
	 			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_NAME != 'addressbook'
	 		)
  	);

alter table ADDRESSBOOK_OBJECT_REVISIONS
	drop ("ADDRESSBOOK_RESOURCE_ID");

-- New indexes
create index ADDRESSBOOK_OBJECT_RE_40cc2d73 on ADDRESSBOOK_OBJECT_REVISIONS (
    ADDRESSBOOK_HOME_RESOURCE_ID,
    OWNER_HOME_RESOURCE_ID
);

create index ADDRESSBOOK_OBJECT_RE_980b9872 on ADDRESSBOOK_OBJECT_REVISIONS (
    OWNER_HOME_RESOURCE_ID,
    RESOURCE_NAME
);

create index ADDRESSBOOK_OBJECT_RE_45004780 on ADDRESSBOOK_OBJECT_REVISIONS (
    OWNER_HOME_RESOURCE_ID,
    REVISION
);


-------------------------------
-- change  RESOURCE_PROPERTY --
-------------------------------

-- delete rows for shared and non-default address books
delete 
	from RESOURCE_PROPERTY
	where exists (
		select *
			from ADDRESSBOOK_BIND
		where 
			ADDRESSBOOK_BIND.ADDRESSBOOK_RESOURCE_ID = RESOURCE_PROPERTY.RESOURCE_ID and (
				ADDRESSBOOK_BIND.BIND_MODE != 0 or 	-- not CALENDAR_BIND_MODE 'own'
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
update CALENDARSERVER set VALUE = '20' where NAME = 'VERSION';
