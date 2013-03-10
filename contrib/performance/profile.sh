#!/bin/bash -x

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

. ./benchlib.sh

set -e # Break on error

sudo -v # Force up to date sudo token before the user walks away

REV_SPEC="$1"

update_and_build "$REV_SPEC"

REV="$(./svn-revno "$SOURCE_DIR")"

DATE="`./svn-committime $SOURCE $REV`"
for backend in ${BACKENDS[*]}; do
  setbackend $backend
  for benchmark in $BENCHMARKS; do
      pushd $SOURCE
      mkdir -p profiling/$backend/$benchmark
      start 0 -t Single -S profiling/$backend/$benchmark
      popd
      # Chances are sudo will throw out PYTHONPATH unless we tell it not to.
      sudo ./run.sh ./benchmark --label r$REV-$backend $benchmark
      pushd $SOURCE
      stop
      popd
  done
done
