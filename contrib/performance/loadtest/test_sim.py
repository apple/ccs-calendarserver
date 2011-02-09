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

from plistlib import writePlistToString

from twisted.python.usage import UsageError
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase
from twisted.internet.defer import succeed
from twisted.internet.task import Clock

from loadtest.sim import Server, Arrival, SimOptions, LoadSimulator, main
from loadtest.population import SmoothRampUp, CalendarClientSimulator

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
        self.assertEquals(exc.args, (StubSimulator(None, None).run(),))


    def test_createSimulator(self):
        """
        L{LoadSimulator.createSimulator} creates a
        L{CalendarClientSimulator} with its own reactor and host and
        port information from the configuration file.
        """
        host = '127.0.0.7'
        port = 1243
        reactor = object()
        sim = LoadSimulator(Server(host, port), None, reactor)
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
        policy.
        """
        reactor = object()
        sim = LoadSimulator(None, None, reactor)
        arrival = sim.createArrivalPolicy()
        self.assertIsInstance(arrival, SmoothRampUp)
        self.assertIdentical(arrival.reactor, reactor)
