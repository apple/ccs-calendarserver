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

-------------------------------------------------
-- Upgrade database schema from VERSION 5 to 6 --
-------------------------------------------------

---------------------------------------------------------
-- New table for Apple Push Notification Subscriptions --
---------------------------------------------------------

create table APN_SUBSCRIPTIONS (
  "TOKEN"                       nvarchar2(255),
  "RESOURCE_KEY"                nvarchar2(255),
  "MODIFIED"                    integer not null,
  "SUBSCRIBER_GUID"             nvarchar2(255), 
  unique(TOKEN, RESOURCE_KEY) -- implicit index
);

create index APN_SUBSCRIPTIONS_RES_9610d78e
  on APN_SUBSCRIPTIONS(RESOURCE_KEY);

-- Now update the version
update CALENDARSERVER set VALUE = '6' where NAME = 'VERSION';

