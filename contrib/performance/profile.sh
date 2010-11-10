#!/bin/bash -x

. ./benchlib.sh

set -e # Break on error

sudo -v # Force up to date sudo token before the user walks away

REV=$1
LOGS=$2
RESULTS=$3

update_and_build $REV

DATE="`./svn-committime $SOURCE $REV`"
for backend in $BACKENDS; do
  setbackend $backend
  for benchmark in $BENCHMARKS; do
      pushd $SOURCE
      mkdir -p profiling/$backend/$benchmark
      start 0 -t Single -S profiling/$backend/$benchmark
      popd
      # Chances are sudo will throw out PYTHONPATH unless we tell it not to.
      sudo PYTHONPATH=$PYTHONPATH ./benchmark --label r$REV-$backend $benchmark
      pushd $SOURCE
      stop
      popd
  done
done
