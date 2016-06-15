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
-- Upgrade database schema from VERSION 62 to 63 --
---------------------------------------------------

create index CALENDAR_OBJECT_ORIGI_a3d15cf2 on CALENDAR_OBJECT (
    "ORIGINAL_COLLECTION"
);

-- update the version
update CALENDARSERVER set VALUE = '63' where NAME = 'VERSION';
