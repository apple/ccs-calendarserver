# -*- test-case-name: twext.internet.test.test_sendfdport -*-
##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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
from errno import EAGAIN
from socket import socketpair, fromfd, error as SocketError, AF_INET, SOCK_STREAM

from twisted.python import log

from twisted.internet.abstract import FileDescriptor
from twisted.internet.protocol import Protocol, Factory

from twext.python.sendmsg import sendmsg, recvmsg
from twext.python.sendfd import sendfd, recvfd

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
        # actually I want to retrieve a child from a *pool* of potentially
        # available children.  i have to make that determination based on the
        # number of connections each child is currently handling.  which means
        # the logic shouldn't live here.  where should it live?  in this spot,
        # I just need an FD.
        self.factory.sendSocket(skt)



class InheritingProtocolFactory(Factory, object):
    """
    In the 'master' process, make one of these and hook it up to the sockets
    where you want to hear stuff.

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



class _AvailableConnection(FileDescriptor, object):
    """
    A socket in the master process pointing at a file descriptor that can be
    used to transmit sockets to a subprocess.

    @ivar skt: the UNIX socket used as the sendmsg() transport.

    @ivar outgoingSocketQueue: an outgoing queue of sockets to send to the
        subprocess.

    @ivar outgoingSocketQueue: a C{list} of 2-tuples of C{(socket-object, str)}

    @ivar status: a record of the last status message received (via recvmsg)
        from the subprocess: this is an application-specific indication of how
        ready this subprocess is to receive more connections.  A typical usage
        would be to count the open connections: this is what is passed to 

    @type status: C{str}
    """

    def __init__(self, reactor, skt):
        FileDescriptor.__init__(self, reactor)
        self.status = None
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
            data, flags, ancillary = recvmsg(self.fd)
        except SocketError:
            pass                # handle EAGAIN, etc
        else:
            self.status = data


    def doWrite(self):
        """
        Transmit as many queued pending file descriptors as we can.
        """
        while self.outgoingSocketQueue:
            skt, desc = self.outgoingSocketQueue.pop(0)
            try:
                sendfd(self.skt.fileno(), skt.fileno(), desc)
            except SocketError, se:
                if se.errno == EAGAIN:
                    self.outgoingSocketQueue.insert(0, (skt, desc))
                    return
                raise
        if not self.outgoingSocketQueue:
            self.stopWriting()



class InheritedSocketDispatcher(object):
    """
    Used by one or more L{InheritingProtocolFactory}s, this keeps track of a
    list of available sockets in subprocesses and sends inbound connections towards them.

    @ivar fitnessFunction: a function used to evaluate status messages received
        on available subprocess connections.  a 1-argument function which
        accepts a string - or C{None}, if no status has been reported - and
        returns something sortable.  this will be used to sort all available
        status messages; the lowest sorting result will be used to handle the
        new connection.
    """

    def __init__(self, fitnessFunction):
        """
        Create a socket dispatcher.
        """
        self.availableConnections = []
        self.fitnessFunction = fitnessFunction
        from twisted.internet import reactor
        self.reactor = reactor


    def sendFileDescriptor(self, skt, description):
        """
        A connection has been received.  Dispatch it.

        @param skt: a socket object

        @param description: some text to identify to the subprocess's
            L{InheritedPort} what type of transport to create for this socket.
        """
        self.availableConnections.sort(key=lambda conn:
                                           self.fitnessFunction(conn.status))


    def addSocket(self):
        """
        Add a C{sendmsg()}-oriented AF_UNIX socket to the pool of sockets being
        used for transmitting file descriptors to child processes.

        @return: a socket object for the receiving side; pass this object's
            C{fileno()} as part of the C{childFDs} argument to
            C{spawnProcess()}, then close it.
        """
        i, o = socketpair()
        a = _AvailableConnection(self.reactor, o)
        self.availableConnections.append(a)
        return i



class InheritedPort(FileDescriptor, object):
    """
    Create this in the 'slave' process to handle incoming connections
    dispatched via C{sendmsg}.
    """

    def __init__(self, fd, transportFactory, protocolFactory):
        """
        @param fd: a file descriptor

        @type fd: C{int}
        
        @param transportFactory: a 3-argument function that takes the socket
            object produced from the file descriptor, the (non-ancillary) data
            sent along with the incoming file descriptor, and the protocol
            built along with it, and returns an L{ITransport} provider.  Note
            that this should NOT call C{makeConnection} on the protocol that it
            produces, as this class will do that.

        @param protocolFactory: an L{IProtocolFactory}
        """
        FileDescriptor.__init__(self)
        self.fd = fd
        self.transportFactory = transportFactory
        self.protocolFactory = protocolFactory


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
                skt = fromfd(fd, AF_INET, SOCK_STREAM)
                # XXX it could be AF_UNIX, I guess?  or even something else?
                # should this be on the transportFactory's side of things?

                close(fd)       # fromfd() calls dup()
                peeraddr = skt.getpeername()
                protocol = self.protocolFactory.buildProtocol(peeraddr)
                transport = self.transportFactory(skt, description, protocol)
                protocol.makeConnection(transport)
            except:
                log.err()


    def doWrite(self):
        """
        Write some data.
        """
        while self.statusQueue:
            msg = self.statusQueue.pop(0)
            try:
                sendmsg(self.fd, msg, 0)
            except SocketError, se:
                if se.errno == EAGAIN:
                    self.statusQueue.insert(0, msg)
                    return
                raise
        self.stopWriting()


    def reportStatus(self, statusMessage):
        """
        Report a status message to the L{_AvailableConnection} monitoring this
        L{InheritedPort}'s health in the master process.
        """
        # XXX this has got to be invoked from 
        self.statusQueue.append(statusMessage)
        self.startWriting()
        
