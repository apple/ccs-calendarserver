##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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
Multiplexing control socket.  Currently used for messages related to queueing
and logging, but extensible to more.
"""

from zope.interface import implements

from twisted.internet.protocol import Factory
from twisted.protocols.amp import BinaryBoxProtocol, IBoxReceiver, IBoxSender
from twisted.application.service import Service

class DispatchingSender(object):
    implements(IBoxSender)

    def __init__(self, sender, route):
        self.sender = sender
        self.route = route


    def sendBox(self, box):
        box['_route'] = self.route
        self.sender.sendBox(box)


    def unhandledError(self, failure):
        self.sender.unhandledError(failure)



class DispatchingBoxReceiver(object):
    implements(IBoxReceiver)

    def __init__(self, receiverMap):
        self.receiverMap = receiverMap


    def startReceivingBoxes(self, boxSender):
        for key, receiver in self.receiverMap.items():
            receiver.startReceivingBoxes(DispatchingSender(boxSender, key))


    def ampBoxReceived(self, box):
        self.receiverMap[box['_route']].ampBoxReceived(box)


    def stopReceivingBoxes(self, reason):
        for receiver in self.receiverMap.values():
            receiver.stopReceivingBoxes(reason)



class ControlSocket(Factory, object):
    """
    An AMP control socket that aggregates other AMP factories.  This is the
    service that listens in the master process.
    """

    def __init__(self):
        """
        Initialize this L{ControlSocket}.
        """
        self._factoryMap = {}


    def addFactory(self, key, otherFactory):
        """
        Add another L{Factory} - one that returns L{AMP} instances - to this
        socket.
        """
        self._factoryMap[key] = otherFactory


    def buildProtocol(self, addr):
        """
        Build a thing that will multiplex AMP to all the relevant sockets.
        """
        receiverMap = {}
        for k, f  in self._factoryMap.items():
            receiverMap[k] = f.buildProtocol(addr)
        return BinaryBoxProtocol(DispatchingBoxReceiver(receiverMap))


    def doStart(self):
        """
        Relay start notification to all added factories.
        """
        for f in self._factoryMap.values():
            f.doStart()


    def doStop(self):
        """
        Relay stop notification to all added factories.
        """
        for f in self._factoryMap.values():
            f.doStop()



class ControlSocketConnectingService(Service, object):

    def __init__(self, endpointFactory, controlSocket):
        super(ControlSocketConnectingService, self).__init__()
        self.endpointFactory = endpointFactory
        self.controlSocket = controlSocket


    def privilegedStartService(self):
        from twisted.internet import reactor
        endpoint = self.endpointFactory(reactor)
        endpoint.connect(self.controlSocket)

