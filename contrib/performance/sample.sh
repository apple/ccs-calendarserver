#!/bin/bash -x

set -e # Break on error
shopt -s nullglob # Expand foo* to nothing if nothing matches

sudo -v # Force up to date sudo token before the user walks away

BACKENDS="filesystem postgresql"

SOURCE=~/Projects/CalendarServer/trunk
NUM_INSTANCES=2
BENCHMARKS="event_move event_delete_attendee event_add_attendee event_change_date event_change_summary event_delete vfreebusy event"
STATISTICS=(HTTP SQL read write pagein pageout)
ADDURL=http://localhost:8000/result/add/
export PYTHONPATH=$PYTHONPATH:$SOURCE/../Twisted

REV=$1
LOGS=$2
RESULTS=$3

function stop() {
  ./run -k || true
  while [ -e ./data/Logs/caldavd.pid ]; do
    echo "Waiting for server to exit..."
    sleep 1
  done
}

pushd $SOURCE
stop
svn st --no-ignore | grep '^[?I]' | cut -c9- | xargs rm -r
svn up -r$REV .
python setup.py build_ext -i
popd

DATE="`./svn-committime $SOURCE $REV`"
for backend in $BACKENDS; do
  ./setbackend $SOURCE/conf/caldavd-test.plist $backend > $SOURCE/conf/caldavd-dev.plist
  pushd $SOURCE
  stop
  rm -rf data/
  ./run -d -n
  while :; do
    instances=($SOURCE/data/Logs/*instance*)
    if [ "${#instances[*]}" -ne "$NUM_INSTANCES" ]; then
      sleep 2
    else
      break
    fi
  done
  echo "instance pid files: ${instances[*]}"
  popd
  sudo PYTHONPATH=$PYTHONPATH ./benchmark --label r$REV-$backend --log-directory $LOGS $BENCHMARKS
  data=`echo -n r$REV-$backend*`
  ./massupload \
      --url $ADDURL --revision $REV \
      --revision-date "$DATE" --environment nmosbuilder \
      --backend $backend \
      --benchmarks "$BENCHMARKS" \
      --parameters "1 9 81" \
      --statistics "${STATISTICS[*]}" \
      $data
  mv $data $RESULTS
done
