----
-- Copyright (c) 2015-2016 Apple Inc. All rights reserved.
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

-------------------------------------------
-- Upgrade database schema at VERSION 28 --
-------------------------------------------

-- Missing index rename
alter index ADDRESSBOOK_OBJECT_RE_40cc2d73 rename to ADDRESSBOOK_OBJECT_RE_2bfcf757;

-- Missing index
create index IMIP_TOKENS_TOKEN_e94b918f on IMIP_TOKENS (
    TOKEN
);

alter table PUSH_NOTIFICATION_WORK
    modify ("PRIORITY" integer default null);

alter table CALENDAR_HOME
    modify ("DATAVERSION" integer default 0 not null);

alter table ADDRESSBOOK_HOME
    modify ("DATAVERSION" integer default 0 not null);
