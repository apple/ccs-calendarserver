--
-- Copyright (c) 2010-2014 Apple Inc. All rights reserved.
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.
--

-- Set the units of all of the benchmarks to what they really are.

update codespeed_benchmark set units_title = 'Statements' where name like '%-SQLcount';
update codespeed_benchmark set units_title = 'Bytes' where name like '%-read';
update codespeed_benchmark set units_title = 'Bytes' where name like '%-write';
update codespeed_benchmark set units_title = 'Pages' where name like '%-pagein';
update codespeed_benchmark set units_title = 'Pages' where name like '%-pageout';

update codespeed_benchmark set units = 'statements' where name like '%-SQLcount';
update codespeed_benchmark set units = 'bytes' where name like '%-read'; 
update codespeed_benchmark set units = 'bytes' where name like '%-write';
update codespeed_benchmark set units = 'pages' where name like '%-pagein';
update codespeed_benchmark set units = 'pages' where name like '%-pageout';
