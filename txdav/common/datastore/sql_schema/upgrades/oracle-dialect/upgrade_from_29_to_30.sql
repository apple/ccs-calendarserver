----
-- Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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
-- Upgrade database schema from VERSION 29 to 30 --
---------------------------------------------------

----------------------------------------
-- Change Address Book Object Members --
----------------------------------------

begin
for i in (select constraint_name from user_cons_columns where column_name = 'MEMBER_ID' or column_name = 'GROUP_ID')
loop
execute immediate 'alter table abo_members drop constraint' || i.constraint_name;
end loop;
end;

alter table ABO_MEMBERS
	add ("REVISION" integer default nextval('REVISION_SEQ') not null);
alter table ABO_MEMBERS
	add ("REMOVED" boolean default false not null);
alter table ABO_MEMBERS
	 drop primary key;
alter table ABO_MEMBERS
	 add primary key ("GROUP_ID", "MEMBER_ID", "REVISION");

------------------------------------------
-- Change Address Book Object Revisions --
------------------------------------------
	
alter table ADDRESSBOOK_OBJECT_REVISIONS
	add ("OBJECT_RESOURCE_ID" integer default 0);

--------------------
-- Update version --
--------------------

update CALENDARSERVER set VALUE = '30' where NAME = 'VERSION';
