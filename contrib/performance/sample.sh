#!/bin/bash -x

set -e

BACKENDS="filesystem postgresql"

SOURCE=~/Projects/CalendarServer/trunk
BENCHMARKS="vfreebusy event"
ADDURL=http://localhost:8000/result/add/
export PYTHONPATH=$PYTHONPATH:$SOURCE/../Twisted

REV=$1
RESULTS=$2

pushd $SOURCE
svn up -r$REV .
python setup.py build_ext -i
popd

for backend in $BACKENDS; do
  ./setbackend $SOURCE/conf/caldavd-test.plist $backend > $SOURCE/conf/caldavd-dev.plist
  pushd $SOURCE
  ./run -k || true
  sleep 5
  rm -rf data/
  ./run -d -n
  popd
  sleep 5
  ./benchmark --label r$REV-$backend $BENCHMARKS
  data=`echo -n r$REV-$backend*`
  for p in 1 9 81; do
    for b in $BENCHMARKS; do
      ./upload \
          --url $ADDURL --revision $REV \
          --revision-date "`./svn-committime $SOURCE`" --environment nmosbuilder \
          --backend $backend --statistic "$data,$b,$p,urlopen time"
    done
  done

  mv $data $RESULTS
done
