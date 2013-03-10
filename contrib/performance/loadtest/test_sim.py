##
# Copyright (c) 2011-2013 Apple Inc. All rights reserved.
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
from cStringIO import StringIO

from twisted.python.log import msg
from twisted.python.usage import UsageError
from twisted.python.filepath import FilePath
from twisted.internet.defer import Deferred, succeed
from twisted.trial.unittest import TestCase

from twistedcaldav.directory.directory import DirectoryRecord

from contrib.performance.stats import NormalDistribution
from contrib.performance.loadtest.ical import OS_X_10_6
from contrib.performance.loadtest.profiles import Eventer, Inviter, Accepter
from contrib.performance.loadtest.population import (
    SmoothRampUp, ClientType, PopulationParameters, Populator, CalendarClientSimulator,
    ProfileType, SimpleStatistics)
from contrib.performance.loadtest.sim import (
    Arrival, SimOptions, LoadSimulator, LagTrackingReactor)

VALID_CONFIG = {
    'server': 'tcp:127.0.0.1:8008',
    'webadmin': {
        'enabled': True,
        'HTTPPort': 8080,
        },
    'arrival': {
        'factory': 'contrib.performance.loadtest.population.SmoothRampUp',
        'params': {
            'groups': 10,
            'groupSize': 1,
            'interval': 3,
            },
        },
    }

VALID_CONFIG_PLIST = writePlistToString(VALID_CONFIG)


class SimOptionsTests(TestCase):
    def test_defaultConfig(self):
        """
        If the I{config} option is not specified, the default config.plist in
        the source tree is used.
        """
        options = SimOptions()
        self.assertEqual(options['config'], FilePath(__file__).sibling('config.plist'))


    def test_configFileNotFound(self):
        """
        If the filename given to the I{config} option is not found,
        L{SimOptions.parseOptions} raises a L{UsageError} indicating
        this.
        """
        name = FilePath(self.mktemp())
        options = SimOptions()
        exc = self.assertRaises(
            UsageError, options.parseOptions, ['--config', name.path])
        self.assertEquals(
            str(exc), "--config %s: No such file or directory" % (name.path,))


    def test_configFileNotParseable(self):
        """
        If the contents of the file given to the I{config} option
        cannot be parsed by L{ConfigParser},
        L{SimOptions.parseOptions} raises a L{UsageError} indicating
        this.
        """
        config = FilePath(self.mktemp())
        config.setContent("some random junk")
        options = SimOptions()
        exc = self.assertRaises(
            UsageError, options.parseOptions, ['--config', config.path])
        self.assertEquals(
            str(exc),
            "--config %s: syntax error: line 1, column 0" % (config.path,))



class CalendarClientSimulatorTests(TestCase):
    """
    Tests for L{CalendarClientSimulator} which adds running clients to
    a simulation.
    """
    realmName = 'stub'

    def _user(self, name):
        record = DirectoryRecord(self, 'user', name, (name,))
        record.password = 'password-' + name
        return record


    def test_createUser(self):
        """
        Subsequent calls to L{CalendarClientSimulator._createUser}
        with different user numbers return user details from different
        directory records.
        """
        calsim = CalendarClientSimulator(
            [self._user('alice'), self._user('bob'), self._user('carol')],
            Populator(None), None, None, 'http://example.org:1234/', None, None)
        users = sorted([
                calsim._createUser(0)[0],
                calsim._createUser(1)[0],
                calsim._createUser(2)[0],
                ])
        self.assertEqual(['alice', 'bob', 'carol'], users)


    def test_createUserAuthInfo(self):
        """
        The auth handler returned by L{CalendarClientSimulator._createUser}
        includes the password taken from user's directory record.
        """
        calsim = CalendarClientSimulator(
            [self._user('alice')],
            Populator(None), None, None, 'http://example.org:1234/', None, None)
        user, auth = calsim._createUser(0)
        self.assertEqual(
            auth['basic'].passwd.find_user_password('Test Realm', 'http://example.org:1234/')[1],
            'password-' + user)
        self.assertEqual(
            auth['digest'].passwd.find_user_password('Test Realm', 'http://example.org:1234/')[1],
            'password-' + user)


    def test_stop(self):
        """
        After L{CalendarClientSimulator.stop} is called, failed clients and
        profiles are not logged.
        """
        class BrokenClient(object):
            def __init__(self, reactor, serverAddress, principalPathTemplate, serializationPath, userInfo, auth, runResult):
                self._runResult = runResult

            def run(self):
                return self._runResult

            def stop(self):
                return succeed(None)
                
        class BrokenProfile(object):
            def __init__(self, reactor, simulator, client, userNumber, runResult):
                self._runResult = runResult
                self.enabled = True

            def run(self):
                return self._runResult

        clientRunResult = Deferred()
        profileRunResult = Deferred()

        params = PopulationParameters()
        params.addClient(1, ClientType(
                BrokenClient, {'runResult': clientRunResult},
                [ProfileType(BrokenProfile, {'runResult': profileRunResult})]))
        sim = CalendarClientSimulator(
            [self._user('alice')], Populator(None), params, None, 'http://example.com:1234/', None, None)
        sim.add(1, 1)
        sim.stop()
        clientRunResult.errback(RuntimeError("Some fictional client problem"))
        profileRunResult.errback(RuntimeError("Some fictional profile problem"))

        self.assertEqual([], self.flushLoggedErrors())



class Reactor(object):
    message = "some event to be observed"

    def __init__(self):
        self._triggers = []
        self._whenRunning = []


    def run(self):
        for thunk in self._whenRunning:
            thunk()
        msg(self.message)
        for _ignore_phase, event, thunk in self._triggers:
            if event == 'shutdown':
                thunk()


    def callWhenRunning(self, thunk):
        self._whenRunning.append(thunk)


    def addSystemEventTrigger(self, phase, event, thunk):
        self._triggers.append((phase, event, thunk))


class Observer(object):
    def __init__(self):
        self.reported = False
        self.events = []


    def observe(self, event):
        self.events.append(event)


    def report(self, output):
        self.reported = True


    def failures(self):
        return []


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
            exc.args, (StubSimulator(None, None, None, None, None, None).run(),))


    def test_createSimulator(self):
        """
        L{LoadSimulator.createSimulator} creates a L{CalendarClientSimulator}
        with its own reactor and host and port information from the
        configuration file.
        """
        server = 'http://127.0.0.7:1243/'
        reactor = object()
        sim = LoadSimulator(server, None, None, None, None, None, reactor=reactor)
        calsim = sim.createSimulator()
        self.assertIsInstance(calsim, CalendarClientSimulator)
        self.assertIsInstance(calsim.reactor, LagTrackingReactor)
        self.assertIdentical(calsim.reactor._reactor, reactor)
        self.assertEquals(calsim.server, server)


    def test_loadAccountsFromFile(self):
        """
        L{LoadSimulator.fromCommandLine} takes an account loader from the
        config file and uses it to create user records for use in the
        simulation.
        """
        accounts = FilePath(self.mktemp())
        accounts.setContent("foo,bar,baz,quux\nfoo2,bar2,baz2,quux2\n")
        config = VALID_CONFIG.copy()
        config["accounts"] = {
            "loader": "contrib.performance.loadtest.sim.recordsFromCSVFile",
            "params": {
                "path": accounts.path},
            }
        configpath = FilePath(self.mktemp())
        configpath.setContent(writePlistToString(config))
        io = StringIO()
        sim = LoadSimulator.fromCommandLine(['--config', configpath.path], io)
        self.assertEquals(io.getvalue(), "Loaded 2 accounts.\n")
        self.assertEqual(2, len(sim.records))
        self.assertEqual(sim.records[0].uid, 'foo')
        self.assertEqual(sim.records[0].password, 'bar')
        self.assertEqual(sim.records[0].commonName, 'baz')
        self.assertEqual(sim.records[0].email, 'quux')
        self.assertEqual(sim.records[1].uid, 'foo2')
        self.assertEqual(sim.records[1].password, 'bar2')
        self.assertEqual(sim.records[1].commonName, 'baz2')
        self.assertEqual(sim.records[1].email, 'quux2')


    def test_loadDefaultAccountsFromFile(self):
        """
        L{LoadSimulator.fromCommandLine} takes an account loader (with
        empty path)from the config file and uses it to create user
        records for use in the simulation.
        """
        config = VALID_CONFIG.copy()
        config["accounts"] = {
            "loader": "contrib.performance.loadtest.sim.recordsFromCSVFile",
            "params": {
                "path": ""},
            }
        configpath = FilePath(self.mktemp())
        configpath.setContent(writePlistToString(config))
        sim = LoadSimulator.fromCommandLine(['--config', configpath.path],
                                            StringIO())
        self.assertEqual(99, len(sim.records))
        self.assertEqual(sim.records[0].uid, 'user01')
        self.assertEqual(sim.records[0].password, 'user01')
        self.assertEqual(sim.records[0].commonName, 'User 01')
        self.assertEqual(sim.records[0].email, 'user01@example.com')
        self.assertEqual(sim.records[98].uid, 'user99')
        self.assertEqual(sim.records[98].password, 'user99')
        self.assertEqual(sim.records[98].commonName, 'User 99')
        self.assertEqual(sim.records[98].email, 'user99@example.com')

    def test_generateRecordsDefaultPatterns(self):
        """
        L{LoadSimulator.fromCommandLine} takes an account loader from the
        config file and uses it to generate user records for use in the
        simulation.
        """
        config = VALID_CONFIG.copy()
        config["accounts"] = {
            "loader": "contrib.performance.loadtest.sim.generateRecords",
            "params": {
                "count": 2
            },
        }
        configpath = FilePath(self.mktemp())
        configpath.setContent(writePlistToString(config))
        sim = LoadSimulator.fromCommandLine(['--config', configpath.path],
                                            StringIO())
        self.assertEqual(2, len(sim.records))
        self.assertEqual(sim.records[0].uid, 'user1')
        self.assertEqual(sim.records[0].password, 'user1')
        self.assertEqual(sim.records[0].commonName, 'User 1')
        self.assertEqual(sim.records[0].email, 'user1@example.com')
        self.assertEqual(sim.records[1].uid, 'user2')
        self.assertEqual(sim.records[1].password, 'user2')
        self.assertEqual(sim.records[1].commonName, 'User 2')
        self.assertEqual(sim.records[1].email, 'user2@example.com')

    def test_generateRecordsNonDefaultPatterns(self):
        """
        L{LoadSimulator.fromCommandLine} takes an account loader from the
        config file and uses it to generate user records for use in the
        simulation.
        """
        config = VALID_CONFIG.copy()
        config["accounts"] = {
            "loader": "contrib.performance.loadtest.sim.generateRecords",
            "params": {
                "count": 3,
                "uidPattern": "USER%03d",
                "passwordPattern": "PASSWORD%03d",
                "namePattern": "Test User %03d",
                "emailPattern": "USER%03d@example2.com",
            },
        }
        configpath = FilePath(self.mktemp())
        configpath.setContent(writePlistToString(config))
        sim = LoadSimulator.fromCommandLine(['--config', configpath.path],
                                            StringIO())
        self.assertEqual(3, len(sim.records))
        self.assertEqual(sim.records[0].uid, 'USER001')
        self.assertEqual(sim.records[0].password, 'PASSWORD001')
        self.assertEqual(sim.records[0].commonName, 'Test User 001')
        self.assertEqual(sim.records[0].email, 'USER001@example2.com')
        self.assertEqual(sim.records[2].uid, 'USER003')
        self.assertEqual(sim.records[2].password, 'PASSWORD003')
        self.assertEqual(sim.records[2].commonName, 'Test User 003')
        self.assertEqual(sim.records[2].email, 'USER003@example2.com')

    def test_specifyRuntime(self):
        """
        L{LoadSimulator.fromCommandLine} recognizes the I{--runtime} option to
        specify a limit on how long the simulation will run.
        """
        config = FilePath(self.mktemp())
        config.setContent(VALID_CONFIG_PLIST)
        sim = LoadSimulator.fromCommandLine(['--config', config.path, '--runtime', '123'])
        self.assertEqual(123, sim.runtime)


    def test_loadServerConfig(self):
        """
        The Calendar Server host and port are loaded from the [server]
        section of the configuration file specified.
        """
        config = FilePath(self.mktemp())
        config.setContent(writePlistToString({
                    "server": "https://127.0.0.3:8432/"}))
        sim = LoadSimulator.fromCommandLine(['--config', config.path])
        self.assertEquals(sim.server, "https://127.0.0.3:8432/")


    def test_loadArrivalConfig(self):
        """
        The arrival policy type and arguments are loaded from the
        [arrival] section of the configuration file specified.
        """
        config = FilePath(self.mktemp())
        config.setContent(writePlistToString({
                    "arrival": {
                        "factory": "contrib.performance.loadtest.population.SmoothRampUp",
                        "params": {
                            "groups": 10,
                            "groupSize": 1,
                            "interval": 3,
                            },
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
            None, None, None, None, Arrival(FakeArrival, {'x': 3, 'y': 2}), None, reactor=reactor)
        arrival = sim.createArrivalPolicy()
        self.assertIsInstance(arrival, FakeArrival)
        self.assertIdentical(arrival.reactor, sim.reactor)
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
                            "software": "contrib.performance.loadtest.ical.OS_X_10_6",
                            "params": {"foo": "bar"},
                            "profiles": [{
                                    "params": {
                                        "interval": 25,
                                        "eventStartDistribution": {
                                            "type": "contrib.performance.stats.NormalDistribution",
                                            "params": {
                                                "mu": 123,
                                                "sigma": 456,
                                                }}},
                                    "class": "contrib.performance.loadtest.profiles.Eventer"}],
                            "weight": 3,
                            }]}))
                            
        sim = LoadSimulator.fromCommandLine(['--config', config.path])
        expectedParameters = PopulationParameters()
        expectedParameters.addClient(
            3, ClientType(OS_X_10_6, {"foo": "bar"}, [ProfileType(Eventer, {
                            "interval": 25,
                            "eventStartDistribution": NormalDistribution(123, 456)})]))
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
            1, ClientType(OS_X_10_6, {}, [Eventer, Inviter, Accepter]))
        self.assertEquals(sim.parameters, expectedParameters)


    def test_loadLogObservers(self):
        """
        Log observers specified in the [observers] section of the
        configuration file are added to the logging system.
        """
        config = FilePath(self.mktemp())
        config.setContent(writePlistToString({
            "observers": [{"type":"contrib.performance.loadtest.population.SimpleStatistics", "params":{},},]
        }))
        sim = LoadSimulator.fromCommandLine(['--config', config.path])
        self.assertEquals(len(sim.observers), 1)
        self.assertIsInstance(sim.observers[0], SimpleStatistics)


    def test_observeRunReport(self):
        """
        Each log observer is added to the log publisher before the
        simulation run is started and has its C{report} method called
        after the simulation run completes.
        """
        observers = [Observer()]
        sim = LoadSimulator(
            "http://example.com:123/",
            "/principals/users/%s/",
            None,
            None,
            Arrival(lambda reactor: NullArrival(), {}),
            None, observers, reactor=Reactor())
        io = StringIO()
        sim.run(io)
        self.assertEquals(io.getvalue(), "\n*** PASS\n")
        self.assertTrue(observers[0].reported)
        self.assertEquals(
            observers[0].events[0]['message'], (Reactor.message,))

