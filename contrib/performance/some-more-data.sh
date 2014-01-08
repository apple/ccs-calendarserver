#!/bin/bash -x
##
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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

SOURCE_DIR="$1"
RESULTS="$2"

NOW="$(date +%s)"

WHEN=($((60*60*24*7)) $((60*60*24*31)) $((60*60*24*31*3)))
for when in ${WHEN[*]}; do
    THEN=$(($NOW-$when))
    REV_SPEC="{$(date -r "$THEN" +"%Y-%m-%d")}"
    ./sample.sh "$REV_SPEC" "$SOURCE_DIR" "$RESULTS"
done
