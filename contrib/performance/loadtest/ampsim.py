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
AMP-based simulator.
"""

if __name__ == '__main__':
    # When run as a script, this is the worker process, receiving commands over
    # stdin.
    import traceback
    try:
        from twisted.python.log import startLogging
        from sys import stderr, exit

        startLogging(stderr)

        from twisted.internet import reactor
        from twisted.internet.stdio import StandardIO

        from contrib.performance.loadtest.ampsim import Worker

        StandardIO(Worker(reactor))
        reactor.run()
    except:
        traceback.print_exc()
        exit(1)
    else:
        exit(0)


from copy import deepcopy

from plistlib import writePlistToString
from twisted.protocols.amp import AMP, Command, String
from twext.enterprise.adbapi2 import Pickle

from twisted.python.log import msg, addObserver


class Configure(Command):
    """
    Configure this worker process with the text of an XML property list.
    """
    arguments = [("plist", String())]



class LogMessage(Command):
    """
    A log message was received.
    """
    arguments = [("event", Pickle())]



class Worker(AMP):
    """
    Protocol to be run in the worker process, to handle messages from its
    manager.
    """

    def __init__(self, reactor):
        super(Worker, self).__init__()
        self.reactor = reactor


    @Configure.responder
    def config(self, plist):
        from plistlib import readPlistFromString
        from contrib.performance.loadtest.sim import LoadSimulator
        cfg = readPlistFromString(plist)
        addObserver(self.emit)
        sim = LoadSimulator.fromConfig(cfg)
        sim.attachServices()
        return {}


    def emit(self, eventDict):
        self.reactor.callFromThread(
            self.callRemote, LogMessage, event=eventDict
        )



class Manager(AMP):
    """
    Protocol to be run in the coordinating process, to respond to messages from
    a single worker.
    """

    def __init__(self, loadsim, whichWorker, numWorkers):
        super(Manager, self).__init__()
        self.loadsim = loadsim
        self.whichWorker = whichWorker
        self.numWorkers = numWorkers


    def connectionMade(self):
        super(Manager, self).connectionMade()
        workerConfig = deepcopy(self.loadsim.configTemplate)
        del workerConfig["workers"]
        workerConfig["workerID"] = self.whichWorker
        workerConfig["workerCount"] = self.numWorkers
        self.callRemote(Configure, plist=writePlistToString(workerConfig))


    @LogMessage.responder
    def observed(self, event):
        msg(**event)
        return {}


