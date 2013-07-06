# -*- test-case-name: twext.internet.test.test_sendfdport -*-
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

"""
Implementation of a TCP/SSL port that uses sendmsg/recvmsg as implemented by
L{twext.python.sendfd}.
"""

from os import close
from errno import EAGAIN, ENOBUFS
from socket import (socketpair, fromfd, error as SocketError, AF_UNIX,
                    SOCK_STREAM, SOCK_DGRAM)

from twisted.internet.abstract import FileDescriptor
from twisted.internet.protocol import Protocol, Factory

from twext.python.log import Logger
from twext.python.sendmsg import sendmsg, recvmsg
from twext.python.sendfd import sendfd, recvfd
from twext.python.sendmsg import getsockfam

log = Logger()



class InheritingProtocol(Protocol, object):
    """
    When a connection comes in on this protocol, stop reading and writing, and
    dispatch the socket to another process via its factory.
    """

    def connectionMade(self):
        """
        A connection was received; transmit the file descriptor to another
        process via L{InheritingProtocolFactory} and remove my transport from
        the reactor.
        """
        self.transport.stopReading()
        self.transport.stopWriting()
        skt = self.transport.getHandle()
        self.factory.sendSocket(skt)



class InheritingProtocolFactory(Factory, object):
    """
    An L{InheritingProtocolFactory} is a protocol factory which listens for
    incoming connections in a I{master process}, then sends those connections
    off to be inherited by a I{worker process} via an
    L{InheritedSocketDispatcher}.

    L{InheritingProtocolFactory} is instantiated in the master process.

    @ivar dispatcher: an L{InheritedSocketDispatcher} to use to dispatch
        incoming connections to an appropriate subprocess.

    @ivar description: the string to send along with connections received on
        this factory.
    """

    protocol = InheritingProtocol

    def __init__(self, dispatcher, description):
        self.dispatcher = dispatcher
        self.description = description


    def sendSocket(self, socketObject):
        """
        Send the given socket object on to my dispatcher.
        """
        self.dispatcher.sendFileDescriptor(socketObject, self.description)



class _SubprocessSocket(FileDescriptor, object):
    """
    A socket in the master process pointing at a file descriptor that can be
    used to transmit sockets to a subprocess.

    @ivar skt: the UNIX socket used as the sendmsg() transport.

    @ivar outgoingSocketQueue: an outgoing queue of sockets to send to the
        subprocess, along with their descriptions (strings describing their
        protocol so that the subprocess knows how to handle them; as of this
        writing, either C{"TCP"} or C{"SSL"})
    @ivar outgoingSocketQueue: a C{list} of 2-tuples of C{(socket-object,
        bytes)}

    @ivar status: a record of the last status message received (via recvmsg)
        from the subprocess: this is an application-specific indication of how
        ready this subprocess is to receive more connections.  A typical usage
        would be to count the open connections: this is what is passed to
    @type status: C{str}
    """

    def __init__(self, dispatcher, skt):
        FileDescriptor.__init__(self, dispatcher.reactor)
        self.status = None
        self.dispatcher = dispatcher
        self.skt = skt          # XXX needs to be set non-blocking by somebody
        self.fileno = skt.fileno
        self.outgoingSocketQueue = []


    def sendSocketToPeer(self, skt, description):
        """
        Enqueue a socket to send to the subprocess.
        """
        self.outgoingSocketQueue.append((skt, description))
        self.startWriting()


    def doRead(self):
        """
        Receive a status / health message and record it.
        """
        try:
            data, _ignore_flags, _ignore_ancillary = recvmsg(self.skt.fileno())
        except SocketError, se:
            if se.errno not in (EAGAIN, ENOBUFS):
                raise
        else:
            self.dispatcher.statusMessage(self, data)


    def doWrite(self):
        """
        Transmit as many queued pending file descriptors as we can.
        """
        while self.outgoingSocketQueue:
            skt, desc = self.outgoingSocketQueue.pop(0)
            try:
                sendfd(self.skt.fileno(), skt.fileno(), desc)
            except SocketError, se:
                if se.errno in (EAGAIN, ENOBUFS):
                    self.outgoingSocketQueue.insert(0, (skt, desc))
                    return
                raise
        if not self.outgoingSocketQueue:
            self.stopWriting()



class InheritedSocketDispatcher(object):
    """
    Used by one or more L{InheritingProtocolFactory}s, this keeps track of a
    list of available sockets that connect to I{worker process}es and sends
    inbound connections to be inherited over those sockets, by those processes.

    L{InheritedSocketDispatcher} is therefore insantiated in the I{master
    process}.

    @ivar statusWatcher: An object that tracks the I{status messages} reported
        by the worker processes over their control sockets, and computes
        internal I{status values} for those messages.  The I{messages} are
        individual octets, representing one of three operations.  C{0} meaning
        "a new worker process has started, with zero connections being
        processed", C{+} meaning "I have received and am processing your
        request; I am confirming that my requests-being-processed count has
        gone up by one", and C{-} meaning "I have completed processing a
        request, my requests-being-processed count has gone down by one".  The
        I{status value} tracked by L{_SubprocessSocket.status} is an integer,
        indicating the current requests-being-processed value.  (FIXME: the
        intended design here is actually just that all I{this} object knows
        about is that L{_SubprocessSocket.status} is an orderable value, and
        that this C{statusWatcher} will compute appropriate values so the
        status that I{sorts the least} is the socket to which new connections
        should be directed; also, the format of the status messages is only
        known / understood by the C{statusWatcher}, not the
        L{InheritedSocketDispatcher}.  It's hard to explain it in that manner
        though.)
    @type statusWatcher: L{twext.web2.metafd.ConnectionLimiter} (FIXME: this
        should be a bit more abstract; declared in an interface or something,
        since we may in principle want to throttle connections from more than
        just HTTP.)
    """

    def __init__(self, statusWatcher):
        """
        Create a socket dispatcher.
        """
        self._subprocessSockets = []
        self.statusWatcher = statusWatcher
        from twisted.internet import reactor
        self.reactor = reactor
        self._isDispatching = False


    @property
    def statuses(self):
        """
        Yield the current status of all subprocess sockets.
        """
        for subsocket in self._subprocessSockets:
            yield subsocket.status


    def statusMessage(self, subsocket, message):
        """
        The status of a connection has changed; update all registered status
        change listeners.
        """
        subsocket.status = self.statusWatcher.statusFromMessage(
            subsocket.status, message
        )


    def sendFileDescriptor(self, skt, description):
        """
        A connection has been received.  Dispatch it.

        @param skt: the I{connection socket} (i.e.: not the listening socket)
        @type skt: L{socket.socket}

        @param description: some text to identify to the subprocess's
            L{InheritedPort} what type of transport to create for this socket.
        @type description: C{bytes}
        """
        # We want None to sort after 0 and before 1, so coerce to 0.5 - this
        # allows the master to first schedule all child process that are up but
        # not yet busy ahead of those that are still starting up.
        def sortKey(conn):
            if conn.status is None:
                return 0.5
            else:
                return conn.status
        self._subprocessSockets.sort(key=sortKey)
        selectedSocket = self._subprocessSockets[0]
        selectedSocket.sendSocketToPeer(skt, description)
        # XXX Maybe want to send along 'description' or 'skt' or some
        # properties thereof? -glyph
        selectedSocket.status = self.statusWatcher.newConnectionStatus(
           selectedSocket.status
        )


    def startDispatching(self):
        """
        Start listening on all subprocess sockets.
        """
        self._isDispatching = True
        for subSocket in self._subprocessSockets:
            subSocket.startReading()


    def addSocket(self):
        """
        Add a C{sendmsg()}-oriented AF_UNIX socket to the pool of sockets being
        used for transmitting file descriptors to child processes.

        @return: a socket object for the receiving side; pass this object's
            C{fileno()} as part of the C{childFDs} argument to
            C{spawnProcess()}, then close it.
        """
        i, o = socketpair(AF_UNIX, SOCK_DGRAM)
        i.setblocking(False)
        o.setblocking(False)
        a = _SubprocessSocket(self, o)
        self._subprocessSockets.append(a)
        if self._isDispatching:
            a.startReading()
        return i



class InheritedPort(FileDescriptor, object):
    """
    An L{InheritedPort} is an L{IReadDescriptor}/L{IWriteDescriptor} created in
    the I{worker process} to handle incoming connections dispatched via
    C{sendmsg}.
    """

    def __init__(self, fd, transportFactory, protocolFactory):
        """
        @param fd: the file descriptor representing a UNIX socket connected to
            a I{master process}.  We will call C{recvmsg} on this socket to
            receive file descriptors.
        @type fd: C{int}

        @param transportFactory: a 4-argument function that takes the socket
            object produced from the file descriptor, the peer address of that
            socket, the (non-ancillary) data sent along with the incoming file
            descriptor, and the protocol built along with it, and returns an
            L{ITransport} provider.  Note that this should NOT call
            C{makeConnection} on the protocol that it produces, as this class
            will do that.

        @param protocolFactory: an L{IProtocolFactory}
        """
        FileDescriptor.__init__(self)
        self.fd = fd
        self.transportFactory = transportFactory
        self.protocolFactory = protocolFactory
        self.statusQueue = []


    def fileno(self):
        """
        Get the FD number for this socket.
        """
        return self.fd


    def doRead(self):
        """
        A message is ready to read.  Receive a file descriptor from our parent
        process.
        """
        try:
            fd, description = recvfd(self.fd)
        except SocketError, se:
            if se.errno != EAGAIN:
                raise
        else:
            try:
                skt = fromfd(fd, getsockfam(fd), SOCK_STREAM)
                close(fd)       # fromfd() calls dup()
                try:
                    peeraddr = skt.getpeername()
                except SocketError:
                    peeraddr = ('0.0.0.0', 0)
                protocol = self.protocolFactory.buildProtocol(peeraddr)
                transport = self.transportFactory(skt, peeraddr,
                                                  description, protocol)
                protocol.makeConnection(transport)
            except:
                log.failure("doRead()")


    def doWrite(self):
        """
        Write some data.
        """
        while self.statusQueue:
            msg = self.statusQueue.pop(0)
            try:
                sendmsg(self.fd, msg, 0)
            except SocketError, se:
                if se.errno in (EAGAIN, ENOBUFS):
                    self.statusQueue.insert(0, msg)
                    return
                raise
        self.stopWriting()


    def reportStatus(self, statusMessage):
        """
        Report a status message to the L{_SubprocessSocket} monitoring this
        L{InheritedPort}'s health in the master process.
        """
        self.statusQueue.append(statusMessage)
        self.startWriting()

