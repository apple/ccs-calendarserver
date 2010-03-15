# Copyright (c) 2001-2008 Twisted Matrix Laboratories.
# See LICENSE for details.


"""
A kqueue()/kevent() based implementation of the Twisted main loop.

To install the event loop (and you should do this before any connections,
listeners or connectors are added)::

    | from twisted.internet import kqreactor
    | kqreactor.install()


Maintainer: U{Itamar Shtull-Trauring<mailto:twisted@itamarst.org>}
"""


import errno, sys

try:
    from select import KQ_FILTER_READ, KQ_FILTER_WRITE, KQ_EV_DELETE, KQ_EV_ADD
    from select import kqueue, kevent, KQ_EV_ENABLE, KQ_EV_DISABLE, KQ_EV_EOF
except ImportError:
    from select26 import KQ_FILTER_READ, KQ_FILTER_WRITE, KQ_EV_DELETE, KQ_EV_ADD
    from select26 import kqueue, kevent, KQ_EV_ENABLE, KQ_EV_DISABLE, KQ_EV_EOF

from zope.interface import implements

from twisted.python import log
from twisted.internet import main, posixbase
from twisted.internet.interfaces import IReactorFDSet



class KQueueReactor(posixbase.PosixReactorBase):
    """
    A reactor that uses kqueue(2)/kevent(2).

    @ivar _kq: A L{kqueue} which will be used to check for I/O readiness.

    @ivar _selectables: A dictionary mapping integer file descriptors to
        instances of L{FileDescriptor} which have been registered with the
        reactor.  All L{FileDescriptors} which are currently receiving read or
        write readiness notifications will be present as values in this
        dictionary.

    @ivar _reads: A set storing integer file descriptors.  These values will be
        registered with C{_kq} for read readiness notifications which will be
        dispatched to the corresponding L{FileDescriptor} instances in
        C{_selectables}.

    @ivar _writes: A set storing integer file descriptors.  These values will
        be registered with C{_kq} for write readiness notifications which will
        be dispatched to the corresponding L{FileDescriptor} instances in
        C{_selectables}.
    """
    implements(IReactorFDSet)

    def __init__(self):
        """
        Initialize kqueue object, file descriptor tracking sets, and the base
        class.
        """
        self._kq = kqueue()
        self._reads = set()
        self._writes = set()
        self._selectables = {}
        posixbase.PosixReactorBase.__init__(self)


    def _updateRegistration(self, fd, filter, flags):
        ev = kevent(fd, filter, flags)
        self._kq.control([ev], 0, 0)


    def addReader(self, reader):
        """
        Add a FileDescriptor for notification of data available to read.
        """
        fd = reader.fileno()
        if fd not in self._reads:
            if fd not in self._selectables:
                self._updateRegistration(fd, KQ_FILTER_READ, KQ_EV_ADD|KQ_EV_ENABLE)
                self._updateRegistration(fd, KQ_FILTER_WRITE, KQ_EV_ADD|KQ_EV_DISABLE)
                self._selectables[fd] = reader
            else:
                self._updateRegistration(fd, KQ_FILTER_READ, KQ_EV_ENABLE)
            self._reads.add(fd)


    def addWriter(self, writer):
        """
        Add a FileDescriptor for notification of data available to write.
        """
        fd = writer.fileno()
        if fd not in self._writes:
            if fd not in self._selectables:
                self._updateRegistration(fd, KQ_FILTER_WRITE, KQ_EV_ADD|KQ_EV_ENABLE)
                self._updateRegistration(fd, KQ_FILTER_READ, KQ_EV_ADD|KQ_EV_DISABLE)
                self._selectables[fd] = writer
            else:
                self._updateRegistration(fd, KQ_FILTER_WRITE, KQ_EV_ENABLE)
            self._writes.add(fd)


    def removeReader(self, reader):
        """
        Remove a Selectable for notification of data available to read.
        """
        fd = reader.fileno()
        if fd == -1:
            for fd, fdes in self._selectables.iteritems():
                if reader is fdes:
                    break
            else:
                return
        if fd in self._reads:
            self._reads.discard(fd)
            if fd not in self._writes:
                del self._selectables[fd]
            self._updateRegistration(fd, KQ_FILTER_READ, KQ_EV_DISABLE)


    def removeWriter(self, writer):
        """
        Remove a Selectable for notification of data available to write.
        """
        fd = writer.fileno()
        if fd == -1:
            for fd, fdes in self._selectables.iteritems():
                if writer is fdes:
                    break
            else:
                return
        if fd in self._writes:
            self._writes.discard(fd)
            if fd not in self._reads:
                del self._selectables[fd]
            self._updateRegistration(fd, KQ_FILTER_WRITE, KQ_EV_DISABLE)


    def removeAll(self):
        """
        Remove all selectables, and return a list of them.
        """
        if self.waker is not None:
            self.removeReader(self.waker)
        result = self._selectables.values()
        for fd in self._reads:
            self._updateRegistration(fd, KQ_FILTER_READ, KQ_EV_DELETE)
        for fd in self._writes:
            self._updateRegistration(fd, KQ_FILTER_WRITE, KQ_EV_DELETE)
        self._reads.clear()
        self._writes.clear()
        self._selectables.clear()
        if self.waker is not None:
            self.addReader(self.waker)
        return result


    def getReaders(self):
        return [self._selectables[fd] for fd in self._reads]


    def getWriters(self):
        return [self._selectables[fd] for fd in self._writes]


    def doKEvent(self, timeout):
        """
        Poll the kqueue for new events.
        """
        if timeout is None:
            timeout = 1

        try:
            l = self._kq.control([], len(self._selectables), timeout)
        except OSError, e:
            if e[0] == errno.EINTR:
                return
            else:
                raise
        _drdw = self._doWriteOrRead
        for event in l:
            fd = event.ident
            try:
                selectable = self._selectables[fd]
            except KeyError:
                # Handles the infrequent case where one selectable's
                # handler disconnects another.
                continue
            log.callWithLogger(selectable, _drdw, selectable, fd, event)


    def _doWriteOrRead(self, selectable, fd, event):
        why = None
        inRead = False
        filter, flags, data, fflags = event.filter, event.flags, event.data, event.fflags
        if flags & KQ_EV_EOF and data and fflags:
            why = main.CONNECTION_LOST
        else:
            try:
                if filter == KQ_FILTER_READ:
                    inRead = True
                    why = selectable.doRead()
                if filter == KQ_FILTER_WRITE:
                    inRead = False
                    why = selectable.doWrite()
                if not selectable.fileno() == fd:
                    inRead = False
                    why = main.CONNECTION_LOST
            except:
                log.err()
                why = sys.exc_info()[1]

        if why:
            self._disconnectSelectable(selectable, why, inRead)

    doIteration = doKEvent


def install():
    k = KQueueReactor()
    main.installReactor(k)


__all__ = ["KQueueReactor", "install"]
