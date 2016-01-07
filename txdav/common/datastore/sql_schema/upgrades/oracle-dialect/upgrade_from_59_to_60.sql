----
-- Copyright (c) 2012-2016 Apple Inc. All rights reserved.
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
-- Upgrade database schema from VERSION 59 to 60 --
---------------------------------------------------

-- For IS&T: remove the modify - now done in upgrade_from_32_to_33

-- Modified columns
--Not for IS&T: alter table CALENDAR_OBJECT_REVISIONS
--Not for IS&T:     modify ("MODIFIED" not null);

--Not for IS&T: alter table ADDRESSBOOK_OBJECT_REVISIONS
--Not for IS&T:     modify ("MODIFIED" not null);

--Not for IS&T: alter table NOTIFICATION_OBJECT_REVISIONS
--Not for IS&T:     modify ("MODIFIED" not null);

-- update the version
update CALENDARSERVER set VALUE = '60' where NAME = 'VERSION';
