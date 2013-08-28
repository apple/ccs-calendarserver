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
-- Upgrade database schema from VERSION 24 to 25 --
---------------------------------------------------

----------------------------------------
-- Change Address Book Object Members --
----------------------------------------

alter table ABO_MEMBERS
	drop constraint	abo_members_member_id_fkey,
	drop constraint	abo_members_group_id_fkey,
	add column	RESOURCE_NAME	varchar(255),
	add column	REVISION		integer      default nextval('REVISION_SEQ') not null,
	add column	REMOVED         boolean      default false not null;
		
--------------------
-- Update version --
--------------------

update CALENDARSERVER set VALUE = '25' where NAME = 'VERSION';
