#!/bin/bash

for i in `python -c "for i in range($START, $STOP, $STEP): print i,"`; do
    ./sample.sh $i ~/Projects/CalendarServer/trunk/data/Logs "$1"
done
