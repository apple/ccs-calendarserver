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

from operator import setitem
from plistlib import writePlistToString

from twisted.python.log import LogPublisher, theLogPublisher
from twisted.python.usage import UsageError
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase
from twisted.internet.defer import succeed
from twisted.internet.task import Clock

from loadtest.ical import SnowLeopard
from loadtest.profiles import Eventer, Inviter, Accepter
from loadtest.population import (
    SmoothRampUp, ClientType, PopulationParameters, CalendarClientSimulator,
    SimpleStatistics)
from loadtest.sim import Server, Arrival, SimOptions, LoadSimulator, main

VALID_CONFIG = {
    'server': {
        'host': '127.0.0.1',
        'port': 8008,
        },
    'arrival': {
        'factory': 'loadtest.population.SmoothRampUp',
        'groups': 10,
        'groupSize': 1,
        'interval': 3,
        },
    }

VALID_CONFIG_PLIST = writePlistToString(VALID_CONFIG)


class SimOptionsTests(TestCase):
    def test_missingConfig(self):
        """
        If the I{config} option is not specified,
        L{SimOptions.parseOptions} raises a L{UsageError} indicating
        it is required.
        """
        options = SimOptions()
        exc = self.assertRaises(UsageError, options.parseOptions, [])
        self.assertEquals(
            str(exc), "Specify a configuration file using --config <path>")


    def test_configFileNotFound(self):
        """
        If the filename given to the I{config} option is not found,
        L{SimOptions.parseOptions} raises a L{UsageError} indicating
        this.
        """
        name = self.mktemp()
        options = SimOptions()
        exc = self.assertRaises(
            UsageError, options.parseOptions, ['--config', name])
        self.assertEquals(
            str(exc), "--config %s: No such file or directory" % (name,))


    def test_configFileNotParseable(self):
        """
        If the contents of the file given to the I{config} option
        cannot be parsed by L{ConfigParser},
        L{SimOptions.parseOptions} raises a L{UsageError} indicating
        this.
        """
        config = self.mktemp()
        FilePath(config).setContent("some random junk")
        options = SimOptions()
        exc = self.assertRaises(
            UsageError, options.parseOptions, ['--config', config])
        self.assertEquals(
            str(exc),
            "--config %s: syntax error: line 1, column 0" % (config,))



class Reactor(object):
    def run(self):
        pass


class Observer(object):
    def __init__(self):
        self.reported = False
        self.events = []


    def observe(self, event):
        self.events.append(event)


    def report(self):
        self.reported = True



class NullArrival(object):
    def run(self, sim):
        pass



class StubSimulator(LoadSimulator):
    def run(self):
        return 3



class LoadSimulatorTests(TestCase):
    def test_main(self):
        """
        L{LoadSimulator.main} raises L{SystemExit} with the result of
        L{LoadSimulator.run}.
        """
        config = FilePath(self.mktemp())
        config.setContent(VALID_CONFIG_PLIST)

        exc = self.assertRaises(
            SystemExit, StubSimulator.main, ['--config', config.path])
        self.assertEquals(
            exc.args, (StubSimulator(None, None, None).run(),))


    def test_createSimulator(self):
        """
        L{LoadSimulator.createSimulator} creates a
        L{CalendarClientSimulator} with its own reactor and host and
        port information from the configuration file.
        """
        host = '127.0.0.7'
        port = 1243
        reactor = object()
        sim = LoadSimulator(Server(host, port), None, None, reactor=reactor)
        calsim = sim.createSimulator()
        self.assertIsInstance(calsim, CalendarClientSimulator)
        self.assertIdentical(calsim.reactor, reactor)
        self.assertEquals(calsim.host, host)
        self.assertEquals(calsim.port, port)


    def test_loadServerConfig(self):
        """
        The Calendar Server host and port are loaded from the [server]
        section of the configuration file specified.
        """
        config = FilePath(self.mktemp())
        config.setContent(writePlistToString({
                    "server": {
                        "host": "127.0.0.1",
                        "port": 1234,
                        },
                    }))
        sim = LoadSimulator.fromCommandLine(['--config', config.path])
        self.assertEquals(sim.server, Server("127.0.0.1", 1234))


    def test_loadArrivalConfig(self):
        """
        The arrival policy type and arguments are loaded from the
        [arrival] section of the configuration file specified.
        """
        config = FilePath(self.mktemp())
        config.setContent(writePlistToString({
                    "arrival": {
                        "factory": "loadtest.population.SmoothRampUp",
                        "groups": 10,
                        "groupSize": 1,
                        "interval": 3,
                        },
                    }))
        sim = LoadSimulator.fromCommandLine(['--config', config.path])
        self.assertEquals(
            sim.arrival,
            Arrival(SmoothRampUp, dict(groups=10, groupSize=1, interval=3)))


    def test_createArrivalPolicy(self):
        """
        L{LoadSimulator.createArrivalPolicy} creates an arrival
        policy based on the L{Arrival} passed to its initializer.
        """
        class FakeArrival(object):
            def __init__(self, reactor, x, y):
                self.reactor = reactor
                self.x = x
                self.y = y

        reactor = object()
        sim = LoadSimulator(
            None, Arrival(FakeArrival, {'x': 3, 'y': 2}), None, reactor=reactor)
        arrival = sim.createArrivalPolicy()
        self.assertIsInstance(arrival, FakeArrival)
        self.assertIdentical(arrival.reactor, reactor)
        self.assertEquals(arrival.x, 3)
        self.assertEquals(arrival.y, 2)


    def test_loadPopulationParameters(self):
        """
        Client weights and profiles are loaded from the [clients]
        section of the configuration file specified.
        """
        config = FilePath(self.mktemp())
        config.setContent(writePlistToString({
                    "clients": [{
                            "software": "loadtest.ical.SnowLeopard",
                            "profiles": ["loadtest.profiles.Eventer"],
                            "weight": 3,
                            }]}))
        sim = LoadSimulator.fromCommandLine(['--config', config.path])
        expectedParameters = PopulationParameters()
        expectedParameters.addClient(3, ClientType(SnowLeopard, [Eventer]))
        self.assertEquals(sim.parameters, expectedParameters)

        
    def test_requireClient(self):
        """
        At least one client is required, so if a configuration with an
        empty clients array is specified, a single default client type
        is used.
        """
        config = FilePath(self.mktemp())
        config.setContent(writePlistToString({"clients": []}))
        sim = LoadSimulator.fromCommandLine(['--config', config.path])
        expectedParameters = PopulationParameters()
        expectedParameters.addClient(
            1, ClientType(SnowLeopard, [Eventer, Inviter, Accepter]))
        self.assertEquals(sim.parameters, expectedParameters)


    def test_loadLogObservers(self):
        """
        Log observers specified in the [observers] section of the
        configuration file are added to the logging system.
        """
        config = FilePath(self.mktemp())
        config.setContent(writePlistToString({
                    "observers": ["loadtest.population.SimpleStatistics"]}))
        sim = LoadSimulator.fromCommandLine(['--config', config.path])
        self.assertEquals(len(sim.observers), 1)
        self.assertIsInstance(sim.observers[0], SimpleStatistics)

    def test_observeBeforeRun(self):
        """
        Each log observer is added to the log publisher before the
        simulation run is started.
        """
        self.fail("implement me")


    def test_reportAfterRun(self):
        """
        Each log observer also has its C{report} method called after
        the simulation run completes.
        """
        observers = [Observer()]
        sim = LoadSimulator(
            Server('example.com', 123), 
            Arrival(lambda reactor: NullArrival(), {}),
            None, observers, Reactor())
        sim.run()
        self.assertTrue(observers[0].reported)

