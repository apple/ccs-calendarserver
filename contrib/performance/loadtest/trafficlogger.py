##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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
#
##

"""
This module implements a reactor wrapper which will cause all traffic on
connections set up using that reactor to be logged.
"""

__all__ = ['loggedReactor']

from StringIO import StringIO

from zope.interface import providedBy

from twisted.python.components import proxyForInterface
from twisted.internet.interfaces import IReactorCore, IReactorTime, IReactorTCP
from twisted.protocols.policies import WrappingFactory, TrafficLoggingProtocol

def loggedReactor(reactor):
    """
    Construct and return a wrapper around the given C{reactor} which provides
    all of the same interfaces, but which will log all traffic over outgoing
    TCP connections it establishes.
    """
    bases = []
    for iface in providedBy(reactor):
        if iface is IReactorTCP:
            bases.append(_TCPTrafficLoggingReactor)
        else:
            bases.append(proxyForInterface(iface, '_reactor'))
    if bases:
        return type('(Logged Reactor)', tuple(bases), {})(reactor)
    return reactor


class _TCPTrafficLoggingReactor(proxyForInterface(IReactorTCP, '_reactor')):
    """
    A mixin for a reactor wrapper which defines C{connectTCP} so as to cause
    traffic to be logged.
    """
    def connectTCP(self, host, port, factory):
        return self._reactor.connectTCP(
            host, port, _TrafficLoggingFactory(factory))


class _TrafficLoggingFactory(WrappingFactory):
    """
    A wrapping factory which applies L{TrafficLoggingProtocolWrapper}.
    """
    LOGFILE_LIMIT = 20

    protocol = TrafficLoggingProtocol

    def __init__(self, wrappedFactory):
        WrappingFactory.__init__(self, wrappedFactory)
        self.logs = []
        self.finishedLogs = []


    def unregisterProtocol(self, protocol):
        WrappingFactory.unregisterProtocol(self, protocol)
        self.logs.remove(protocol.logfile)
        self.finishedLogs.append(protocol.logfile)
        del self.finishedLogs[:-self.LOGFILE_LIMIT]


    def buildProtocol(self, addr):
        logfile = StringIO()
        self.logs.append(logfile)
        return self.protocol(
            self, self.wrappedFactory.buildProtocol(addr), logfile, None, 0)
