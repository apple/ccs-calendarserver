#!/bin/bash -x

##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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

BENCHMARKS="event_move event_delete_attendee event_add_attendee event_change_date event_change_summary event_delete vfreebusy event"

for rev in 6446; do
for f in eighth-try/r$rev-*; do
    base=`basename $f`
    revision=${base:1:4}
    backend=${base:6:10}
    date="`./svn-committime ~/Projects/CalendarServer/trunk $revision`"
    for b in $BENCHMARKS; do
	for p in 1 9 81; do
	    for s in pagein pageout; do
		./upload \
		    --url http://localhost:8000/result/add/ \
		    --revision $revision --revision-date "$date" \
		    --environment nmosbuilder --backend $backend --statistic "$f,$b,$p,$s"
	    done
	done
    done
done
done
