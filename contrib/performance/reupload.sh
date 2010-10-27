#!/bin/bash -x

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
