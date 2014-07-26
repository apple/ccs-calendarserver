##
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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
    def runmain():
        import traceback
        try:
            __import__("twext")
            from twisted.python.log import startLogging
            from sys import exit, stderr

            startLogging(stderr)

            from twisted.internet import reactor
            from twisted.internet.stdio import StandardIO

            from contrib.performance.loadtest.ampsim import Worker # @UnresolvedImport
            from contrib.performance.loadtest.sim import LagTrackingReactor

            StandardIO(Worker(LagTrackingReactor(reactor)))
            reactor.run()
        except:
            traceback.print_exc()
            exit(1)
        else:
            exit(0)
    runmain()


from copy import deepcopy

from plistlib import writePlistToString, readPlistFromString

from twisted.python.log import msg, addObserver
from twisted.protocols.amp import AMP, Command, String, Unicode

from twext.enterprise.adbapi2 import Pickle

from contrib.performance.loadtest.sim import _DirectoryRecord, LoadSimulator

class Configure(Command):
    """
    Configure this worker process with the text of an XML property list.
    """
    arguments = [("plist", String())]
    # Pass OSError exceptions through, presenting the exception message to the user.
    errors = {OSError: 'OSError'}



class LogMessage(Command):
    """
    This message represents an observed log message being relayed from a worker
    process to the manager process.
    """
    arguments = [("event", Pickle())]



class Account(Command):
    """
    This message represents a L{_DirectoryRecord} loaded by the manager process
    being relayed to a worker.
    """
    arguments = [
        ("uid", Unicode()),
        ("password", Unicode()),
        ("commonName", Unicode()),
        ("email", Unicode()),
        ("guid", Unicode()),
    ]



class Worker(AMP):
    """
    Protocol to be run in the worker process, to handle messages from its
    manager.
    """

    def __init__(self, reactor):
        super(Worker, self).__init__()
        self.reactor = reactor
        self.records = []


    @Account.responder
    def account(self, **kw):
        self.records.append(_DirectoryRecord(**kw))
        return {}


    @Configure.responder
    def config(self, plist):
        from sys import stderr
        cfg = readPlistFromString(plist)
        addObserver(self.emit)
        sim = LoadSimulator.fromConfig(cfg)
        sim.records = self.records
        sim.attachServices(stderr)
        return {}


    def emit(self, eventDict):
        if 'type' in eventDict:
            self.reactor.callFromThread(
                self.callRemote, LogMessage, event=eventDict
            )


    def connectionLost(self, reason):
        super(Worker, self).connectionLost(reason)
        msg("Standard IO connection lost.")
        self.reactor.stop()



class Manager(AMP):
    """
    Protocol to be run in the coordinating process, to respond to messages from
    a single worker.
    """

    def __init__(self, loadsim, whichWorker, numWorkers, output):
        super(Manager, self).__init__()
        self.loadsim = loadsim
        self.whichWorker = whichWorker
        self.numWorkers = numWorkers
        self.output = output


    def connectionMade(self):
        super(Manager, self).connectionMade()

        for record in self.loadsim.records:
            self.callRemote(Account,
                            uid=record.uid,
                            password=record.password,
                            commonName=record.commonName,
                            email=record.email,
                            guid=record.guid)

        workerConfig = deepcopy(self.loadsim.configTemplate)
        # The list of workers is for the manager only; the workers themselves
        # know they're workers because they _don't_ receive this list.
        del workerConfig["workers"]
        # The manager loads the accounts via the configured loader, then sends
        # them out to the workers (right above), which look at the state at an
        # instance level and therefore don't need a globally-named directory
        # record loader.
        del workerConfig["accounts"]

        workerConfig["workerID"] = self.whichWorker
        workerConfig["workerCount"] = self.numWorkers
        workerConfig["observers"] = []
        workerConfig.pop("accounts", None)

        plist = writePlistToString(workerConfig)
        self.output.write("Initiating worker configuration\n")
        def completed(x):
            self.output.write("Worker configuration complete.\n")
        self.callRemote(Configure, plist=plist).addCallback(completed)


    @LogMessage.responder
    def observed(self, event):
        # from pprint import pformat
        # self.output.write(pformat(event)+"\n")
        msg(**event)
        return {}
