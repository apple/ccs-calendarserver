##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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

# import twext.who
from twisted.protocols import amp
from twisted.internet.defer import succeed
from twext.python.log import Logger

log = Logger()


class DirectoryProxyAMPCommand(amp.Command):
    """
    A DirectoryProxy command
    """
    arguments = [('command', amp.String())]
    response = [('result', amp.String())]



class DirectoryProxyAMPProtocol(amp.AMP):
    """
    """

    def __init__(self):
        """
        """
        amp.AMP.__init__(self)


    @DirectoryProxyAMPCommand.responder
    # @inlineCallbacks
    def testCommandReceived(self, command):
        """
        Process a command

        @param command: DirectoryProxyAMPCommand
        @returns: a deferred returning a dict
        """
        # command = readPlistFromString(command)
        log.debug("Command arrived: {cmd}", cmd=command)
        response = {"result": "plugh", "command": command}
        log.debug("Responding with: {response}", response=response)
        # returnValue(dict(result=result))
        return succeed(response)


#
# A test AMP client
#

command = "xyzzy"


def makeRequest():
    from twisted.internet import reactor
    from twisted.internet.protocol import ClientCreator

    creator = ClientCreator(reactor, amp.AMP)
    d = creator.connectUNIX("data/Logs/state/directory-proxy.sock")

    def connected(ampProto):
        return ampProto.callRemote(DirectoryProxyAMPCommand, command=command)
    d.addCallback(connected)

    def resulted(result):
        return result['result']
    d.addCallback(resulted)

    def done(result):
        print('Done: %s' % (result,))
        reactor.stop()
    d.addCallback(done)
    reactor.run()

if __name__ == '__main__':
    makeRequest()

