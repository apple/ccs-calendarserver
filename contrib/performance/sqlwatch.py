
import sys, os, signal, time
from pprint import pprint

from twisted.python.failure import Failure
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet import reactor

from benchmark import DTraceCollector


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
def collect(pids):
    while True:
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
    pids = []
    for pidfile in os.listdir(sys.argv[1]):
        if pidfile.startswith('caldav-instance-'):
            pidpath = os.path.join(sys.argv[1], pidfile)
            pidtext = file(pidpath).read()
            pid = int(pidtext)
            pids.append(pid)
    d = collect(pids)
    d.addBoth(lambda ign: reactor.stop())
    reactor.run(installSignalHandlers=False)
