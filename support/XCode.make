# -*- mode: Makefile; -*-
##
# XCode Makefile for CalendarServer
##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

default: build

#
# Run sed to suppress XCode's misguided attempts to interpret our output.
#
build::
	../run -s 2>&1 \
	  | sed \
	    -e 's|error|oops|' \
	    -e 's|warning|oopsie|' \
	    -e 's|^\(..*\):\([0-9][0-9]*\):\([0-9][0-9]*\): |\1-\2-\3: |';

clean::
	rm -rf ../.dependencies/ ../build/ ../data/ ../calendarserver/version.py;
	find .. -name '*.pyc' -o -name '*.so' -o -name dropin.cache -print0 | xargs -0 rm -f;
