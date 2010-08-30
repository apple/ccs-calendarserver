#!/bin/bash -x

set -e

BACKENDS="filesystem postgresql"

SOURCE=~/Projects/CalendarServer/trunk
BENCHMARKS="vfreebusy event"
STATISTICS=("urlopen time" execute)
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

for backend in $BACKENDS; do
  ./setbackend $SOURCE/conf/caldavd-test.plist $backend > $SOURCE/conf/caldavd-dev.plist
  pushd $SOURCE
  stop
  rm -rf data/
  ./run -d -n
  sleep 2
  echo "instance pid files" $SOURCE/data/Logs/*instance*
  popd
  sudo PYTHONPATH=$PYTHONPATH ./benchmark --label r$REV-$backend --log-directory $LOGS $BENCHMARKS
  data=`echo -n r$REV-$backend*`
  for p in 1 9 81; do
    for b in $BENCHMARKS; do
      for stat in "${STATISTICS[@]}"; do
        ./upload \
            --url $ADDURL --revision $REV \
            --revision-date "`./svn-committime $SOURCE`" --environment nmosbuilder \
            --backend $backend --statistic "$data,$b,$p,$stat"
      done
    done
  done

  mv $data $RESULTS
done
