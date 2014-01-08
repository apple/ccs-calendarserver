##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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

set -e # Break on error
shopt -s nullglob # Expand foo* to nothing if nothing matches

# Names of database backends that can be benchmarked.
BACKENDS=(filesystem postgresql)

# Location of the CalendarServer source.  Will automatically be
# updated to the appropriate version, config edited to use the right
# backend, and PID files will be discovered beneath it.
SOURCE=~/Projects/CalendarServer/trunk

# The plist the server will respect.
CONF=$SOURCE/conf/caldavd-dev.plist

# Names of benchmarks we can run.  Since ordering makes a difference to how
# benchmarks are split across multiple hosts, new benchmarks should be appended
# to this list, not inserted earlier on.
BENCHMARKS="find_calendars find_events event_move event_delete_attendee event_add_attendee event_change_date event_change_summary event_delete vfreebusy event bounded_recurrence unbounded_recurrence event_autoaccept bounded_recurrence_autoaccept unbounded_recurrence_autoaccept vfreebusy_vary_attendees"

# Custom scaling parameters for benchmarks that merit it.  Be careful
# not to exceed the 99 user limit for benchmarks where the scaling
# parameter represents a number of users!
SCALE_PARAMETERS="--parameters find_events:1,10,100,1000,10000 --parameters vfreebusy_vary_attendees:1,9,30"

# Names of metrics we can collect.
STATISTICS=(HTTP SQL read write pagein pageout)

# Codespeed add-result location.
ADDURL=http://localhost:8000/result/add/

EXTRACT=$(PWD)/extractconf

# Change the config beneath $SOURCE to use a particular database backend.
function setbackend() {
  ./setbackend $SOURCE/conf/caldavd-test.plist $1 > $CONF
}

# Clean up $SOURCE, update to the specified revision, and build the
# extensions (in-place).
function update_and_build() {
  pushd $SOURCE
  stop
  svn st --no-ignore | grep '^[?I]' | cut -c9- | xargs rm -r
  svn up -r$1 .
  python setup.py build_ext -i
  popd
}

# Ensure that the required configuration file is present, exit if not.
function check_conf() {
  if [ ! -e $CONF ]; then
    echo "Configuration file $CONF is missing."
    exit 1
  fi
}

# Start a CalendarServer in the current directory.  Only return after
# the specified number of slave processes have written their PID files
# (which is only a weak metric for "the server is ready to use").
function start() {
  NUM_INSTANCES=$1
  check_conf
  PIDDIR=$SOURCE/$($EXTRACT $CONF ServerRoot)/$($EXTRACT $CONF RunRoot)

  shift
  ./run -d $*
  while sleep 2; do
    instances=($PIDDIR/*instance*)
    if [ "${#instances[*]}" -eq "$NUM_INSTANCES" ]; then
      echo "instance pid files: ${instances[*]}"
      break
    fi
  done
}

# Stop the CalendarServer in the current directory.  Only return after
# it has exited.
function stop() {
  if [ ! -e $CONF ]; then
    return
  fi
  PIDFILE=$SOURCE/$($EXTRACT $CONF ServerRoot)/$($EXTRACT $CONF RunRoot)/$($EXTRACT $CONF PIDFile)
  ./run -k || true
  while :; do
      pid=$(cat $PIDFILE 2>/dev/null || true)
      if [ ! -e $PIDFILE ]; then
	  break
      fi
      if ! $(kill -0 $pid); then
	  break
      fi
    echo "Waiting for server to exit..."
    sleep 1
  done
}
