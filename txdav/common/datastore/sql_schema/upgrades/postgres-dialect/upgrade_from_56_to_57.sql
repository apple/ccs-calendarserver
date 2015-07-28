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
-- Upgrade database schema from VERSION 56 to 57 --
---------------------------------------------------

-- pre-delete any that would conflict during the update
delete from IMIP_TOKENS where (ORGANIZER, ATTENDEE, ICALUID) in (select concat('urn:uuid:', substr(ORGANIZER, 11)), ATTENDEE, ICALUID from IMIP_TOKENS where substr(ORGANIZER, 1, 10) = 'urn:x-uid:');

-- convert the old-style urn:uuid: CUAs to new style urn:x-uid:
update IMIP_TOKENS set ORGANIZER = concat('urn:x-uid:', substr(ORGANIZER, 10)) where substr(ORGANIZER, 1, 9) = 'urn:uuid:';

-- update the version
update CALENDARSERVER set VALUE = '57' where NAME = 'VERSION';
