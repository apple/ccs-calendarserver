
import sys, signal, time

from twisted.python.log import err
from twisted.python.failure import Failure
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet import reactor

from benchmark import DTraceCollector, instancePIDs


class Stop(Exception):
    pass


interrupted = 0.0
def waitForInterrupt():
    if signal.getsignal(signal.SIGINT) != signal.default_int_handler:
        raise RuntimeError("Already waiting")

    d = Deferred()
    def fire(*ignored):
        global interrupted
        signal.signal(signal.SIGINT, signal.default_int_handler)
        now = time.time()
        if now - interrupted < 4:
            reactor.callFromThread(lambda: d.errback(Failure(Stop())))
        else:
            interrupted = now
            reactor.callFromThread(d.callback, None)
    signal.signal(signal.SIGINT, fire)
    return d


@inlineCallbacks
def collect(directory):
    while True:
        pids = instancePIDs(directory)
        dtrace = DTraceCollector("sql_measure.d", pids)
        print 'Starting'
        yield dtrace.start()
        print 'Started'
        try:
            yield waitForInterrupt()
        except Stop:
            yield dtrace.stop()
            break
        print 'Stopping'
        stats = yield dtrace.stop()
        for s in stats:
            if s.name == 'execute':
                s.statements(stats[s])
        print 'Stopped'


def main():
    from twisted.python.failure import startDebugMode
    startDebugMode()
    d = collect(sys.argv[1])
    d.addErrback(err, "Problem collecting SQL")
    d.addBoth(lambda ign: reactor.stop())
    reactor.run(installSignalHandlers=False)
