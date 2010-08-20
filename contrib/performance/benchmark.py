import sys, os
from os.path import dirname

from signal import SIGINT
from pickle import dump

from datetime import datetime

from twisted.python.reflect import namedAny
from twisted.internet.protocol import ProcessProtocol
from twisted.protocols.basic import LineReceiver
from twisted.internet.defer import (
    Deferred, inlineCallbacks, gatherResults)
from twisted.internet import reactor

from stats import SQLDuration, Bytes


class DTraceBug(Exception):
    """
    Represents some kind of problem related to a shortcoming in dtrace
    itself.
    """



class IOMeasureConsumer(ProcessProtocol):
    def __init__(self, started, done, parser):
        self.started = started
        self.done = done
        self.parser = parser


    def connectionMade(self):
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
            self.parser.dataReceived(bytes)
        else:
            self._out += bytes
            if self._out.startswith('READY\n'):
                self.parser.dataReceived(self._out[len('READY\n'):])
                del self._out
                started = self.started
                self.started = None
                started.callback(None)


    def processEnded(self, reason):
        if self.started is None:
            self.done.callback(None)
        else:
            self.started.errback(RuntimeError("Exited too soon"))


def instancePIDs(directory):
    pids = []
    for pidfile in os.listdir(directory):
        if pidfile.startswith('caldav-instance-'):
            pidpath = os.path.join(directory, pidfile)
            pidtext = file(pidpath).read()
            pid = int(pidtext)
            pids.append(pid)
    return pids


class _DTraceParser(LineReceiver):
    delimiter = '\n\1'

    sql = None
    start = None

    def __init__(self, collector):
        self.collector = collector


    def lineReceived(self, dtrace):
        # dtrace puts some extra newlines in the output sometimes.  Get rid of them.
        dtrace = dtrace.strip()
        if dtrace:
            op, rest = dtrace.split(None, 1)
            getattr(self, '_op_' + op)(op, rest)


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
                        accum = self.collector._execute
                    elif cmd == 'ITERNEXT':
                        accum = self.collector._iternext

                    accum.append((self.sql, diff))
                self.start = None

    _op_ITERNEXT = _op_EXECUTE

    def _op_B_READ(self, cmd, rest):
        self.collector._read.append(int(rest))


    def _op_B_WRITE(self, cmd, rest):
        self.collector._write.append(int(rest))



class DTraceCollector(object):
    def __init__(self, script, pids):
        self._dScript = script
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
        process = reactor.spawnProcess(
            IOMeasureConsumer(started, stopped, _DTraceParser(self)),
            "/usr/sbin/dtrace",
            ["/usr/sbin/dtrace", 
             # process preprocessor macros
             "-C",
             # search for include targets in the source directory containing this file
             "-I", dirname(__file__),
             # suppress most implicitly generated output (which would mess up our parser)
             "-q",
             # make this pid the target
             "-p", str(pid),
             # load this script
             "-s", self._dScript])
        def eintr(reason):
            reason.trap(DTraceBug)
            print 'Dtrace startup failed (', reason.getErrorMessage().strip(), '), retrying.'
            return self._startDTrace(pid)
        def ready(passthrough):
            # Once the dtrace process is ready, save the state and
            # have the stopped Deferred deal with the results.  We
            # don't want to do either of these for failed dtrace
            # processes.
            self.dtraces[pid] = process
            stopped.addCallback(self._cleanup, pid)
            return passthrough
        started.addCallbacks(ready, eintr)
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
def benchmark(directory, label, benchmarks):
    # Figure out which pids we are benchmarking.
    pids = instancePIDs(directory)

    parameters = [1, 9, 81]
    samples = 100

    statistics = {}

    for (name, measure) in benchmarks:
        statistics[name] = {}
        for p in parameters:
            print 'Parameter at', p
            dtrace = DTraceCollector("io_measure.d", pids)
            data = yield measure(dtrace, p, samples)
            statistics[name][p] = data

    fObj = file(
        '%s-%s' % (label, datetime.now().isoformat()), 'w')
    dump(statistics, fObj, 2)
    fObj.close()


def main():
    from twisted.python.log import err
    from twisted.python.failure import startDebugMode
    startDebugMode()
    d = benchmark(
        sys.argv[1], sys.argv[2],
        [(arg, namedAny(arg).measure) for arg in sys.argv[3:]])
    d.addErrback(err)
    d.addCallback(lambda ign: reactor.stop())
    reactor.run()
