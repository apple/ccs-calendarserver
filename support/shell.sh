#!/usr/bin/env bash
##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

# Use this file as: "source support/shell.sh", in order to produce a shell
# environment like the one that './run' uses.  This can be useful to interact
# with dependencies such as PostGreSQL from the command line, if they have been
# set up by the CalendarServer run script and are not otherwise installed on
# your system.

if [ -z "${wd}" ]; then
    wd="$(pwd)";
fi;

source "${wd}/support/build.sh";
do_setup=false;
do_get=false;
do_run=false;
dependencies 2>&1 > /dev/null;

