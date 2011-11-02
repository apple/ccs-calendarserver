# -*- test-case-name: contrib.performance.loadtest.test_sim -*-
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

from xml.parsers.expat import ExpatError
from sys import argv, stdout
from random import Random
from plistlib import readPlist
from collections import namedtuple

from twisted.python import context
from twisted.python.filepath import FilePath
from twisted.python.log import startLogging, addObserver, removeObserver
from twisted.python.usage import UsageError, Options
from twisted.python.reflect import namedAny

from twisted.application.service import Service
from twisted.application.service import MultiService

from contrib.performance.loadtest.ical import SnowLeopard
from contrib.performance.loadtest.profiles import Eventer, Inviter, Accepter
from contrib.performance.loadtest.population import (
    Populator, ProfileType, ClientType, PopulationParameters, SmoothRampUp,
    CalendarClientSimulator)


class _DirectoryRecord(object):
    def __init__(self, uid, password, commonName, email):
        self.uid = uid
        self.password = password
        self.commonName = commonName
        self.email = email


def generateRecords(count, uidPattern="user%d", passwordPattern="user%d",
    namePattern="User %d", emailPattern="user%d@example.com"):
    for i in xrange(count):
        i += 1
        uid = uidPattern % (i,)
        password = passwordPattern % (i,)
        name = namePattern % (i,)
        email = emailPattern % (i,)
        yield _DirectoryRecord(uid, password, name, email)


def recordsFromCSVFile(path):
    if path:
        pathObj = FilePath(path)
    else:
        pathObj = FilePath(__file__).sibling("accounts.csv")
    return [
        _DirectoryRecord(*line.decode('utf-8').split(u','))
        for line
        in pathObj.getContent().splitlines()]


class LagTrackingReactor(object):
    """
    This reactor wraps another reactor and proxies all attribute
    access (including method calls).  It only changes the behavior of
    L{IReactorTime.callLater} to insert a C{"lag"} key into the
    context which delayed function calls are invoked with.  This key
    has a float value which gives the difference in time between when
    the call was original scheduled and when the call actually took
    place.
    """
    def __init__(self, reactor):
        self._reactor = reactor

    def __getattr__(self, name):
        return getattr(self._reactor, name)

    def callLater(self, delay, function, *args, **kwargs):
        expected = self._reactor.seconds() + delay
        def modifyContext():
            now = self._reactor.seconds()
            context.call({'lag': now - expected}, function, *args, **kwargs)
        return self._reactor.callLater(delay, modifyContext)


class SimOptions(Options):
    """
    Command line configuration options for the load simulator.
    """
    config = None
    _defaultConfig = FilePath(__file__).sibling("config.plist")

    optParameters = [
        ("runtime", "t", None,
         "Specify the limit (seconds) on the time to run the simulation.",
         int),
        ("config", None, _defaultConfig,
         "Configuration plist file name from which to read simulation parameters.",
         FilePath),
        ]


    def opt_logfile(self, filename):
        """
        Enable normal logging to some file.  - for stdout.
        """
        if filename == "-":
            fObj = stdout
        else:
            fObj = file(filename, "a")
        startLogging(fObj, setStdout=False)


    def opt_debug(self):
        """
        Enable Deferred and Failure debugging.
        """
        self.opt_debug_deferred()
        self.opt_debug_failure()


    def opt_debug_deferred(self):
        """
        Enable Deferred debugging.
        """
        from twisted.internet.defer import setDebugging
        setDebugging(True)


    def opt_debug_failure(self):
        """
        Enable Failure debugging.
        """
        from twisted.python.failure import startDebugMode
        startDebugMode()


    def postOptions(self):
        try:
            configFile = self['config'].open()
        except IOError, e:
            raise UsageError("--config %s: %s" % (
                    self['config'].path, e.strerror))
        try:
            try:
                self.config = readPlist(configFile)
            except ExpatError, e:
                raise UsageError("--config %s: %s" % (self['config'].path, e)) 
        finally:
            configFile.close()


Arrival = namedtuple('Arrival', 'factory parameters')


class LoadSimulator(object):
    """
    A L{LoadSimulator} simulates some configuration of calendar
    clients.

    @type server: C{str}
    @type arrival: L{Arrival}
    @type parameters: L{PopulationParameters}

    @ivar records: A C{list} of L{DirectoryRecord} instances giving
        user information about the accounts on the server being put
        under load.
    """
    def __init__(self, server, arrival, parameters, observers=None,
                 records=None, reactor=None, runtime=None):
        if reactor is None:
            from twisted.internet import reactor
        self.server = server
        self.arrival = arrival
        self.parameters = parameters
        self.observers = observers
        self.records = records
        self.reactor = LagTrackingReactor(reactor)
        self.runtime = runtime


    @classmethod
    def fromCommandLine(cls, args=None, output=stdout):
        if args is None:
            args = argv[1:]

        options = SimOptions()
        try:
            options.parseOptions(args)
        except UsageError, e:
            raise SystemExit(str(e))

        return cls.fromConfig(options.config, options['runtime'], output)


    @classmethod
    def fromConfig(cls, config, runtime=None, output=stdout):
        """
        Create a L{LoadSimulator} from a parsed instance of a configuration
        property list.
        """

        server = 'http://127.0.0.1:8008/'
        if 'server' in config:
            server = config['server']

        if 'arrival' in config:
            arrival = Arrival(
                namedAny(config['arrival']['factory']), 
                config['arrival']['params'])
        else:
            arrival = Arrival(
                SmoothRampUp, dict(groups=10, groupSize=1, interval=3))

        parameters = PopulationParameters()
        if 'clients' in config:
            for clientConfig in config['clients']:
                parameters.addClient(
                    clientConfig["weight"],
                    ClientType(
                        namedAny(clientConfig["software"]),
                        cls._convertParams(clientConfig["params"]),
                        [ProfileType(
                                namedAny(profile["class"]),
                                cls._convertParams(profile["params"]))
                         for profile in clientConfig["profiles"]]))
        if not parameters.clients:
            parameters.addClient(
                1, ClientType(SnowLeopard, {}, [Eventer, Inviter, Accepter]))

        observers = []
        if 'observers' in config:
            for observerName in config['observers']:
                observers.append(namedAny(observerName)())

        records = []
        if 'accounts' in config:
            loader = config['accounts']['loader']
            params = config['accounts']['params']
            records.extend(namedAny(loader)(**params))
            output.write("Loaded {0} accounts.\n".format(len(records)))

        return cls(server, arrival, parameters,
                   observers=observers, records=records,
                   runtime=runtime)


    @classmethod
    def _convertParams(cls, params):
        """
        Find parameter values which should be more structured than plistlib is
        capable of constructing and replace them with the more structured form.

        Specifically, find keys that end with C{"Distribution"} and convert
        them into some kind of distribution object using the associated
        dictionary of keyword arguments.
        """
        for k, v in params.iteritems():
            if k.endswith('Distribution'):
                params[k] = cls._convertDistribution(v)
        return params


    @classmethod
    def _convertDistribution(cls, value):
        """
        Construct and return a new distribution object using the type and
        params specified by C{value}.
        """
        return namedAny(value['type'])(**value['params'])


    @classmethod
    def main(cls, args=None):
        simulator = cls.fromCommandLine(args)
        raise SystemExit(simulator.run())


    def createSimulator(self):
        populator = Populator(Random())
        return CalendarClientSimulator(
            self.records, populator, self.parameters, self.reactor, self.server)


    def createArrivalPolicy(self):
        return self.arrival.factory(self.reactor, **self.arrival.parameters)


    def run(self, output=stdout):
        ms = MultiService()
        for svcclass in [
                ObserverService,
                SimulatorService,
                ReporterService,
            ]:
            svcclass(self, output).setServiceParent(ms)

        attachService(self.reactor, ms)

        if self.runtime is not None:
            self.reactor.callLater(self.runtime, self.reactor.stop)

        self.reactor.run()



def attachService(reactor, service):
    """
    Attach a given L{IService} provider to the given L{IReactorCore}; cause it
    to be started when the reactor starts, and stopped when the reactor stops.
    """
    reactor.callWhenRunning(service.startService)
    reactor.addSystemEventTrigger('before', 'shutdown', service.stopService)



class SimService(Service, object):
    """
    Base class for services associated with the L{LoadSimulator}.
    """

    def __init__(self, loadsim, output):
        super(SimService, self).__init__()
        self.loadsim = loadsim
        self.output = output



class ObserverService(SimService):
    """
    A service that adds and removes a L{LoadSimulator}'s set of observers at
    start and stop time.
    """

    def startService(self):
        """
        Start observing.
        """
        super(ObserverService, self).startService()
        for obs in self.loadsim.observers:
            addObserver(obs.observe)


    def stopService(self):
        super(ObserverService, self).startService()
        for obs in self.loadsim.observers:
            removeObserver(obs.observe)



class SimulatorService(SimService):
    """
    A service that starts the L{CalendarClientSimulator} associated with the
    L{LoadSimulator} and stops it at shutdown.
    """

    def startService(self):
        super(SimulatorService, self).startService()
        self.clientsim = self.loadsim.createSimulator()
        arrivalPolicy = self.loadsim.createArrivalPolicy()
        arrivalPolicy.run(self.clientsim)


    def stopService(self):
        super(SimulatorService, self).stopService()
        return self.clientsim.stop()



class ReporterService(SimService):
    """
    A service which reports all the results from all the observers on a load
    simulator when it is stopped.
    """

    def stopService(self):
        super(ReporterService, self).stopService()
        failures = []
        for obs in self.loadsim.observers:
            obs.report()
            failures.extend(obs.failures())
        if failures:
            self.output.write('FAIL\n')
            self.output.write('\n'.join(failures))
            self.output.write('\n')
        else:
            self.output.write('PASS\n')


main = LoadSimulator.main



if __name__ == '__main__':
    main()
