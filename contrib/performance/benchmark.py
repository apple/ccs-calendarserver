import sys

from signal import SIGINT
from pickle import dump

from datetime import datetime
from StringIO import StringIO

from twisted.internet.protocol import ProcessProtocol
from twisted.internet.defer import (
    Deferred, inlineCallbacks, gatherResults)
from twisted.internet import reactor

from stats import SQLDuration, Bytes
import vfreebusy


class DTraceBug(Exception):
    """
    Represents some kind of problem related to a shortcoming in dtrace
    itself.
    """



class IOMeasureConsumer(ProcessProtocol):
    def __init__(self, started, done):
        self.started = started
        self.done = done


    def connectionMade(self):
        self.out = StringIO()
        self._out = ''
        self._err = ''


    def errReceived(self, bytes):
        self._err += bytes
        if 'Interrupted system call' in self._err:
            started = self.started
            self.started = None
            started.errback(DTraceBug(self._err))


    def outReceived(self, bytes):
        if self.started is None:
            self.out.write(bytes)
        else:
            self._out += bytes
            if self._out == 'READY\n':
                started = self.started
                self.started = None
                started.callback(None)


    def processEnded(self, reason):
        if self.started is None:
            self.done.callback(self.out.getvalue())
        else:
            self.started.errback(RuntimeError("Exited too soon"))


class DTraceCollector(object):
    def __init__(self, pids):
        self.pids = pids
        self._read = []
        self._write = []
        self._execute = []
        self._iternext = []


    def stats(self):
        return {
            Bytes('read'): self._read,
            Bytes('write'): self._write,
            SQLDuration('execute'): self._execute,
            SQLDuration('iternext'): self._iternext,
            }


    def _parse(self, dtrace):
        file('dtrace.log', 'a').write(dtrace)

        self.sql = self.start = None
        for L in dtrace.split('\n\1'):

            # dtrace puts some extra newlines in the output sometimes.  Get rid of them.
            L = L.strip()
            if not L:
                continue

            op, rest = L.split(None, 1)
            getattr(self, '_op_' + op)(op, rest)
        self.sql = self.start = None


    def _op_EXECUTE(self, cmd, rest):
        which, when = rest.split(None, 1)
        if which == 'SQL':
            self.sql = when
            return

        when = int(when)
        if which == 'ENTRY':
            self.start = when
        elif which == 'RETURN':
            if self.start is None:
                print 'return without entry at', when, 'in', cmd
            else:
                diff = when - self.start
                if diff < 0:
                    print 'Completely bogus EXECUTE', self.start, when
                else:        
                    if cmd == 'EXECUTE':
                        accum = self._execute
                    elif cmd == 'ITERNEXT':
                        accum = self._iternext

                    accum.append((self.sql, diff))
                self.start = None

    _op_ITERNEXT = _op_EXECUTE

    def _op_B_READ(self, cmd, rest):
        self._read.append(int(rest))


    def _op_B_WRITE(self, cmd, rest):
        self._write.append(int(rest))


    def start(self):
        ready = []
        self.finished = []
        self.dtraces = {}
        for p in self.pids:
            started, stopped = self._startDTrace(p)
            ready.append(started)
            self.finished.append(stopped)
        return gatherResults(ready)


    def _startDTrace(self, pid):
        started = Deferred()
        stopped = Deferred()
        self.dtraces[pid] = reactor.spawnProcess(
            IOMeasureConsumer(started, stopped),
            "/usr/sbin/dtrace",
            ["/usr/sbin/dtrace", "-q", "-p", str(pid), "-s",
             "io_measure.d"])
        def eintr(reason):
            reason.trap(DTraceBug)
            print 'Dtrace startup failed (', reason.getErrorMessage(), '), retrying.'
            return self._startDTrace(pid)
        started.addErrback(eintr)
        stopped.addCallback(self._cleanup, pid)
        stopped.addCallback(self._parse)
        return started, stopped


    def _cleanup(self, passthrough, pid):
        del self.dtraces[pid]
        return passthrough


    def stop(self):
        for proc in self.dtraces.itervalues():
            proc.signalProcess(SIGINT)
        d = gatherResults(self.finished)
        d.addCallback(lambda ign: self.stats())
        return d



@inlineCallbacks
def benchmark(argv):
    # Figure out which pids we are benchmarking.
    pids = map(int, argv)

    parameters = [1, 10, 100]
    stuff = [
        ('vfreebusy', vfreebusy.measure, parameters),
        ]

    statistics = {}

    for stat, survey, parameter in stuff:
        print 'Surveying', stat
        for p in parameter:
            print 'Parameter at', p
            dtrace = DTraceCollector(pids)
            data = yield survey(dtrace, p, 100)
            statistics[stat] = data

    fObj = file(datetime.now().isoformat(), 'w')
    dump(statistics, fObj, 2)
    fObj.close()


def main():
    from twisted.python.log import err
    from twisted.python.failure import startDebugMode
    startDebugMode()
    d = benchmark(sys.argv[1:])
    d.addErrback(err)
    d.addCallback(lambda ign: reactor.stop())
    reactor.run()
