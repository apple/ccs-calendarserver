#!/usr/bin/env python

##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
from __future__ import print_function

import cStringIO
import socket
from twext.python.plistlib import readPlistFromString, writePlistToString
from calendarserver.tap.util import getRootResource
from twisted.application.internet import StreamServerEndpointService
from twisted.internet.endpoints import AdoptedStreamServerEndpoint
from twisted.protocols import amp
from twisted.internet.protocol import Factory
from twisted.internet.defer import inlineCallbacks, returnValue

# TODO, implement this:
# from launchd import getLaunchdSocketFds

# For the sample client, below:
from twisted.internet import reactor
from twisted.internet.protocol import ClientCreator

from twext.python.log import Logger
log = Logger()

"""
A service spawned on-demand by launchd, meant to handle configuration requests
from Server.app.  When a request comes in on the socket specified in the launchd
agent.plist, launchd will run "caldavd -t Agent" which ends up creating this
service.  AMP protocol commands sent to this socket are passed to gateway.Runner.
"""

class GatewayAMPCommand(amp.Command):
    """
    A command to be executed by gateway.Runner 
    """
    arguments = [('command', amp.String())]
    response = [('result', amp.String())]


class GatewayAMPProtocol(amp.AMP):
    """
    Passes commands to gateway.Runner and returns the results
    """

    def __init__(self, store, davRootResource, directory):
        """
        @param store: an already opened store
        @param davRootResource: the root resource, required for principal
            operations
        @param directory: a directory service
        """
        amp.AMP.__init__(self)
        self.store = store
        self.davRootResource = davRootResource
        self.directory = directory


    @GatewayAMPCommand.responder
    @inlineCallbacks
    def gatewayCommandReceived(self, command):
        """
        Process a command via gateway.Runner

        @param command: GatewayAMPCommand
        @returns: a deferred returning a dict
        """
        command = readPlistFromString(command)
        output = cStringIO.StringIO()
        from calendarserver.tools.gateway import Runner
        runner = Runner(self.davRootResource, self.directory, self.store,
            [command], output=output)

        try:
            yield runner.run()
            result = output.getvalue()
            output.close()
        except Exception as e:
            error = {
                "Error" : str(e),
            }
            result = writePlistToString(error)

        output.close()
        returnValue(dict(result=result))


class GatewayAMPFactory(Factory):
    """
    Builds GatewayAMPProtocols
    """
    protocol = GatewayAMPProtocol

    def __init__(self, store):
        """
        @param store: an already opened store
        """
        self.store = store
        from twistedcaldav.config import config
        self.davRootResource = getRootResource(config, self.store)
        self.directory = self.davRootResource.getDirectory()

    def buildProtocol(self, addr):
        return GatewayAMPProtocol(self.store, self.davRootResource,
            self.directory)


def makeAgentService(store):
    """
    Returns a service which will process GatewayAMPCommands, using a socket
    file descripter acquired by launchd

    @param store: an already opened store
    @returns: service
    """
    from twisted.internet import reactor

    # TODO: remove this
    def getLaunchdSocketFds():
        return {}

    # TODO: implement this
    sockets = getLaunchdSocketFds() 
    fd = sockets["AgentSocket"][0]
    
    # TODO: use UNIX socket
    family = socket.AF_INET
    endpoint = AdoptedStreamServerEndpoint(reactor, fd, family)
    return StreamServerEndpointService(endpoint, GatewayAMPFactory(store))



#
# A test client
#

command = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>getLocationAndResourceList</string>
</dict>
</plist>"""

def getList():
    creator = ClientCreator(reactor, amp.AMP)
    # TODO: use UNIX socket
    d = creator.connectTCP('127.0.0.1', 12345)

    def connected(ampProto):
        return ampProto.callRemote(GatewayAMPCommand, command=command)
    d.addCallback(connected)

    def resulted(result):
        return result['result']
    d.addCallback(resulted)

    def done(result):
        print('Done: %s' % (result,))
        reactor.stop()
    d.addCallback(done)

if __name__ == '__main__':
    getList()
    reactor.run()
