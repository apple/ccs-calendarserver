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

-- This is actually a noop for Oracle as we had some invalid names in the v20 schema that
-- were corrected in v20 (but not corrected in postgres which is being updated for v25).

-- Now update the version
-- No data upgrades
update CALENDARSERVER set VALUE = '25' where NAME = 'VERSION';
