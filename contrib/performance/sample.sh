#!/bin/bash

set -e # Break on error
shopt -s nullglob # Expand foo* to nothing if nothing matches

sudo -v # Force up to date sudo token before the user walks away

BACKENDS="filesystem postgresql"

SOURCE=~/Projects/CalendarServer/trunk
NUM_INSTANCES=2
BENCHMARKS="vfreebusy event"
STATISTICS=("urlopen time" execute read write)
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
  echo "instance pid files: $instances"
  popd
  sudo PYTHONPATH=$PYTHONPATH ./benchmark --label r$REV-$backend --log-directory $LOGS $BENCHMARKS
  data=`echo -n r$REV-$backend*`
  for p in 1 9 81; do
    for b in $BENCHMARKS; do
      for stat in "${STATISTICS[@]}"; do
        sudo -v # Bump timestamp again
        ./upload \
            --url $ADDURL --revision $REV \
            --revision-date "$DATE" --environment nmosbuilder \
            --backend $backend --statistic "$data,$b,$p,$stat"
      done
    done
  done

  mv $data $RESULTS
done
