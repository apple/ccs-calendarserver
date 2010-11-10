
set -e # Break on error
shopt -s nullglob # Expand foo* to nothing if nothing matches

BACKENDS="filesystem postgresql"

SOURCE=~/Projects/CalendarServer/trunk
BENCHMARKS="event_move event_delete_attendee event_add_attendee event_change_date event_change_summary event_delete vfreebusy event"
STATISTICS=(HTTP SQL read write pagein pageout)
ADDURL=http://boson.:8000/result/add/

function setbackend() {
  ./setbackend $SOURCE/conf/caldavd-test.plist $1 > $SOURCE/conf/caldavd-dev.plist
}

function update_and_build() {
  pushd $SOURCE
  stop
  svn st --no-ignore | grep '^[?I]' | cut -c9- | xargs rm -r
  svn up -r$1 .
  python setup.py build_ext -i
  popd
}

function start() {
  NUM_INSTANCES=$1
  shift
  ./run -d -n $*
  while :; do
    instances=($SOURCE/data/Logs/*instance*)
    if [ "${#instances[*]}" -ne "$NUM_INSTANCES" ]; then
      sleep 2
    else
      break
    fi
  done
}

function stop() {
  ./run -k || true
  while [ -e ./data/Logs/caldavd.pid ]; do
    echo "Waiting for server to exit..."
    sleep 1
  done
}
