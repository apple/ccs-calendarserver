##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

import sys
from Queue import Queue


from twisted.python.failure import Failure
from twisted.internet.defer import Deferred


_DONE = object()

_STATE_STOPPED = 'STOPPED'
_STATE_RUNNING = 'RUNNING'
_STATE_STOPPING = 'STOPPING'

class ThreadHolder(object):
    """
    A queue which will hold a reactor threadpool thread open until all of the
    work in that queue is done.
    """

    def __init__(self, reactor):
        self._reactor = reactor
        self._state = _STATE_STOPPED
        self._stopper = None
        self._q = None


    def _run(self):
        """
        Worker function which runs in a non-reactor thread.
        """
        while self._qpull():
            pass


    def _qpull(self):
        """
        Pull one item off the queue and react appropriately.

        Return whether or not to keep going.
        """
        work = self._q.get()
        if work is _DONE:
            def finishStopping():
                self._state = _STATE_STOPPED
                self._q = None
                s = self._stopper
                self._stopper = None
                s.callback(None)
            self._reactor.callFromThread(finishStopping)
            return False
        self._oneWorkUnit(*work)
        return True


    def _oneWorkUnit(self, deferred, instruction):
        try:
            result = instruction()
        except:
            etype, evalue, etb = sys.exc_info()
            def relayFailure():
                f = Failure(evalue, etype, etb)
                deferred.errback(f)
            self._reactor.callFromThread(relayFailure)
        else:
            self._reactor.callFromThread(deferred.callback, result)


    def submit(self, work):
        """
        Submit some work to be run.

        @param work: a 0-argument callable, which will be run in a thread.

        @return: L{Deferred} that fires with the result of L{work}
        """
        if self._state != _STATE_RUNNING:
            raise RuntimeError("not running")
        d = Deferred()
        self._q.put((d, work))
        return d


    def start(self):
        """
        Start this thing, if it's stopped.
        """
        if self._state != _STATE_STOPPED:
            raise RuntimeError("Not stopped.")
        self._state = _STATE_RUNNING
        self._q = Queue(0)
        self._reactor.callInThread(self._run)


    def stop(self):
        """
        Stop this thing and release its thread, if it's running.
        """
        if self._state != _STATE_RUNNING:
            raise RuntimeError("Not running.")
        s = self._stopper = Deferred()
        self._state = _STATE_STOPPING
        self._q.put(_DONE)
        return s



