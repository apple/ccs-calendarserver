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

from twext.who.idirectory import RecordType
from twisted.protocols import amp
from twisted.internet.defer import succeed, inlineCallbacks, returnValue
from twext.python.log import Logger

log = Logger()


class DirectoryProxyAMPCommand(amp.Command):
    """
    A DirectoryProxy command
    """
    arguments = [('command', amp.String())]
    response = [('result', amp.String())]


class RecordWithShortNameCommand(amp.Command):
    arguments = [
        ('recordType', amp.String()),
        ('shortName', amp.String()),
    ]
    response = [
        ('fullNames', amp.ListOf(amp.String())),
        ('shortNames', amp.ListOf(amp.String())),
        ('emailAddresses', amp.ListOf(amp.String())),
    ]



class DirectoryProxyAMPProtocol(amp.AMP):
    """
    """

    def __init__(self, directory):
        """
        """
        amp.AMP.__init__(self)
        self._directory = directory


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


    @RecordWithShortNameCommand.responder
    @inlineCallbacks
    def recordWithShortName(self, recordType, shortName):
        log.debug("RecordWithShortName: {r} {n}", r=recordType, n=shortName)
        record = (yield self._directory.recordWithShortName(
            RecordType.lookupByName(recordType), shortName)
        )
        response = {
            "fullNames": [i.encode("utf-8") for i in record.fullNames],
            "shortNames": [i.encode("utf-8") for i in record.shortNames],
            "emailAddresses": [i.encode("utf-8") for i in record.emailAddresses],
        }
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


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
        import sys
        shortName = sys.argv[1]
        return ampProto.callRemote(
            RecordWithShortNameCommand,
            shortName=shortName,
            recordType=RecordType.user.description.encode("utf-8"))
    d.addCallback(connected)

    def gotResults(result):
        print('Done: %s' % (result,))
        reactor.stop()
    d.addCallback(gotResults)
    reactor.run()

if __name__ == '__main__':
    makeRequest()
