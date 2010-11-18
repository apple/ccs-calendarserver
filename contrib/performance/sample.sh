#!/bin/bash -x

##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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

sudo -v # Force up to date sudo token before the user walks away

REV=$1
SOURCE_DIR=$2
RESULTS=$3

update_and_build $REV

DATE="`./svn-committime $SOURCE $REV`"
for backend in $BACKENDS; do
  setbackend $backend
  pushd $SOURCE
  stop
  rm -rf data/
  start 2
  popd
  sudo ./run.sh ./benchmark --label r$REV-$backend --source-directory $SOURCE_DIR $BENCHMARKS
  data=`echo -n r$REV-$backend*`
  ./run.sh ./massupload \
      --url $ADDURL --revision $REV \
      --revision-date "$DATE" --environment nmosbuilder \
      --backend $backend \
      --benchmarks "$BENCHMARKS" \
      --parameters "1 9 81" \
      --statistics "${STATISTICS[*]}" \
      $data
  mv $data $RESULTS
done
