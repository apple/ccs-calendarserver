##
# Copyright (c) 2007-2010 Apple Inc. All rights reserved.
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

import sys
import os
import stat
import grp

from os.path import dirname, abspath

from zope.interface import implements

from twisted.python.threadable import isInIOThread
from twisted.internet.reactor import callFromThread
from twisted.python.usage import Options, UsageError
from twisted.python.reflect import namedAny
from twisted.python import log
from twisted.python.procutils import which

from twisted.internet.interfaces import IProcessTransport, IReactorProcess
from twisted.internet.protocol import ServerFactory
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet.task import Clock
from twisted.internet import reactor

from twisted.application.service import IService, IServiceCollection
from twisted.application import internet

from twext.web2.dav import auth
from twext.web2.log import LogWrapperResource
from twext.python.filepath import CachingFilePath as FilePath

from twext.python.plistlib import writePlist #@UnresolvedImport
from twext.internet.tcp import MaxAcceptTCPServer, MaxAcceptSSLServer

from twistedcaldav.config import config, ConfigDict
from twistedcaldav.stdconfig import DEFAULT_CONFIG

from twistedcaldav.directory.aggregate import AggregateDirectoryService
from twistedcaldav.directory.calendar import DirectoryCalendarHomeProvisioningResource
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource

from twistedcaldav.test.util import TestCase, CapturingProcessProtocol

from calendarserver.tap.caldav import (
    CalDAVOptions, CalDAVServiceMaker, CalDAVService, GroupOwnedUNIXServer,
    DelayedStartupProcessMonitor, DelayedStartupLineLogger, TwistdSlaveProcess,
    _CONTROL_SERVICE_NAME
)
from calendarserver.provision.root import RootResource
from StringIO import StringIO


# Points to top of source tree.
sourceRoot = dirname(dirname(dirname(dirname(abspath(__file__)))))


class NotAProcessTransport(object):
    """
    Simple L{IProcessTransport} stub.
    """
    implements(IProcessTransport)

    def __init__(self, processProtocol, executable, args, env, path,
                 uid, gid, usePTY, childFDs):
        """
        Hold on to all the attributes passed to spawnProcess.
        """
        self.processProtocol = processProtocol
        self.executable = executable
        self.args = args
        self.env = env
        self.path = path
        self.uid = uid
        self.gid = gid
        self.usePTY = usePTY
        self.childFDs = childFDs


class InMemoryProcessSpawner(Clock):
    """
    Stub out L{IReactorProcess} and L{IReactorClock} so that we can examine the
    interaction of L{DelayedStartupProcessMonitor} and the reactor.
    """
    implements(IReactorProcess)

    def __init__(self):
        """
        Create some storage to hold on to all the fake processes spawned.
        """
        super(InMemoryProcessSpawner, self).__init__()
        self.processTransports = []
        self.waiting = []


    def waitForOneProcess(self, amount=10.0):
        """
        Wait for an L{IProcessTransport} to be created by advancing the clock.
        If none are created in the specified amount of time, raise an
        AssertionError.
        """
        self.advance(amount)
        if self.processTransports:
            return self.processTransports.pop(0)
        else:
            raise AssertionError(
                "There were no process transports available.  Calls: " +
                repr(self.calls)
            )


    def spawnProcess(self, processProtocol, executable, args=(), env={},
                     path=None, uid=None, gid=None, usePTY=0,
                     childFDs=None):

        transport = NotAProcessTransport(
            processProtocol, executable, args, env, path, uid, gid, usePTY,
            childFDs
        )
        transport.startedAt = self.seconds()
        self.processTransports.append(transport)
        if self.waiting:
            self.waiting.pop(0).callback(transport)
        return transport



class TestCalDAVOptions (CalDAVOptions):
    """
    A fake implementation of CalDAVOptions that provides
    empty implementations of checkDirectory and checkFile.
    """
    def checkDirectory(self, *args, **kwargs):
        pass

    def checkFile(self, *args, **kwargs):
        pass


    def loadConfiguration(self):
        """
        Simple wrapper to avoid printing during test runs.
        """
        oldout = sys.stdout
        newout = sys.stdout = StringIO()
        try:
            return CalDAVOptions.loadConfiguration(self)
        finally:
            sys.stdout = oldout
            log.msg(
                "load configuration console output: %s" % newout.getvalue()
            )


class CalDAVOptionsTest (TestCase):
    """
    Test various parameters of our usage.Options subclass
    """
    def setUp(self):
        """
        Set up our options object, giving it a parent, and forcing the
        global config to be loaded from defaults.
        """
        TestCase.setUp(self)
        self.config = TestCalDAVOptions()
        self.config.parent = Options()
        self.config.parent["uid"] = 0
        self.config.parent["gid"] = 0
        self.config.parent["nodaemon"] = False

    def tearDown(self):
        config.setDefaults(DEFAULT_CONFIG)
        config.reload()

    def test_overridesConfig(self):
        """
        Test that values on the command line's -o and --option options
        overide the config file
        """
        myConfig = ConfigDict(DEFAULT_CONFIG)
        myConfigFile = self.mktemp()
        writePlist(myConfig, myConfigFile)

        argv = [
            "-f", myConfigFile,
            "-o", "EnableSACLs",
            "-o", "HTTPPort=80",
            "-o", "BindAddresses=127.0.0.1,127.0.0.2,127.0.0.3",
            "-o", "DocumentRoot=/dev/null",
            "-o", "UserName=None",
            "-o", "EnableProxyPrincipals=False",
        ]

        self.config.parseOptions(argv)

        self.assertEquals(config.EnableSACLs, True)
        self.assertEquals(config.HTTPPort, 80)
        self.assertEquals(config.BindAddresses,
                          ["127.0.0.1", "127.0.0.2", "127.0.0.3"])
        self.assertEquals(config.DocumentRoot, "/dev/null")
        self.assertEquals(config.UserName, None)
        self.assertEquals(config.EnableProxyPrincipals, False)

        argv = ["-o", "Authentication=This Doesn't Matter"]

        self.assertRaises(UsageError, self.config.parseOptions, argv)

    def test_setsParent(self):
        """
        Test that certain values are set on the parent (i.e. twistd's
        Option's object)
        """
        myConfig = ConfigDict(DEFAULT_CONFIG)
        myConfigFile = self.mktemp()
        writePlist(myConfig, myConfigFile)

        argv = [
            "-f", myConfigFile,
            "-o", "PIDFile=/dev/null",
        ]

        self.config.parseOptions(argv)

        self.assertEquals(self.config.parent["pidfile"], "/dev/null")

    def test_specifyConfigFile(self):
        """
        Test that specifying a config file from the command line
        loads the global config with those values properly.
        """
        myConfig = ConfigDict(DEFAULT_CONFIG)

        myConfig.Authentication.Basic.Enabled = False
        myConfig.HTTPPort = 80
        myConfig.ServerHostName = "calendar.calenderserver.org"

        myConfigFile = self.mktemp()
        writePlist(myConfig, myConfigFile)

        args = ["-f", myConfigFile]

        self.config.parseOptions(args)

        self.assertEquals(config.ServerHostName, myConfig["ServerHostName"])
        self.assertEquals(config.HTTPPort, myConfig.HTTPPort)
        self.assertEquals(
            config.Authentication.Basic.Enabled,
            myConfig.Authentication.Basic.Enabled
        )

    def test_specifyDictPath(self):
        """
        Test that we can specify command line overrides to leafs using
        a "/" seperated path.  Such as "-o MultiProcess/ProcessCount=1"
        """
        myConfig = ConfigDict(DEFAULT_CONFIG)
        myConfigFile = self.mktemp()
        writePlist(myConfig, myConfigFile)

        argv = [
            "-o", "MultiProcess/ProcessCount=102",
            "-f", myConfigFile,
        ]

        self.config.parseOptions(argv)

        self.assertEquals(config.MultiProcess["ProcessCount"], 102)

class BaseServiceMakerTests(TestCase):
    """
    Utility class for ServiceMaker tests.
    """
    configOptions = None

    def setUp(self):
        TestCase.setUp(self)
        self.options = TestCalDAVOptions()
        self.options.parent = Options()
        self.options.parent["gid"] = None
        self.options.parent["uid"] = None
        self.options.parent["nodaemon"] = None

        self.config = ConfigDict(DEFAULT_CONFIG)

        accountsFile = os.path.join(sourceRoot, "twistedcaldav/directory/test/accounts.xml")
        resourcesFile = os.path.join(sourceRoot, "twistedcaldav/directory/test/resources.xml")
        augmentsFile = os.path.join(sourceRoot, "twistedcaldav/directory/test/augments.xml")
        pemFile = os.path.join(sourceRoot, "twistedcaldav/test/data/server.pem")

        self.config["DirectoryService"] = {
            "params": {"xmlFile": accountsFile},
            "type": "twistedcaldav.directory.xmlfile.XMLDirectoryService"
        }

        self.config["ResourceService"] = {
            "params": {"xmlFile": resourcesFile},
        }

        self.config["AugmentService"] = {
            "params": {"xmlFiles": [augmentsFile]},
            "type": "twistedcaldav.directory.augment.AugmentXMLDB"
        }

        self.config.UseDatabase    = False
        self.config.ServerRoot     = self.mktemp()
        self.config.ConfigRoot     = "config"
        self.config.ProcessType    = "Single"
        self.config.SSLPrivateKey  = pemFile
        self.config.SSLCertificate = pemFile
        self.config.EnableSSL      = True
        self.config.Memcached.Pools.Default.ClientEnabled = False
        self.config.Memcached.Pools.Default.ServerEnabled = False
        self.config.DirectoryAddressBook.Enabled = False

        self.config.SudoersFile = ""

        if self.configOptions:
            self.config.update(self.configOptions)

        os.mkdir(self.config.ServerRoot)
        os.mkdir(os.path.join(self.config.ServerRoot, self.config.DocumentRoot))
        os.mkdir(os.path.join(self.config.ServerRoot, self.config.DataRoot))
        os.mkdir(os.path.join(self.config.ServerRoot, self.config.ConfigRoot))

        self.configFile = self.mktemp()

        self.writeConfig()


    def tearDown(self):
        config.setDefaults(DEFAULT_CONFIG)
        config.reset()


    def writeConfig(self):
        """
        Flush self.config out to self.configFile
        """
        writePlist(self.config, self.configFile)


    def makeService(self):
        """
        Create a service by calling into CalDAVServiceMaker with
        self.configFile
        """
        self.options.parseOptions(["-f", self.configFile])

        return CalDAVServiceMaker().makeService(self.options)


    def getSite(self):
        """
        Get the server.Site from the service by finding the HTTPFactory.
        """
        service = self.makeService()
        for listeningService in inServiceHierarchy(
                service,
                # FIXME: need a better predicate for 'is this really an HTTP
                # factory' but this works for now.
                # NOTE: in a database 'single' configuration, PostgresService
                # will prevent the HTTP services from actually getting added to
                # the hierarchy until the hierarchy has started.
                lambda x: hasattr(x, 'args')
            ):
            return listeningService.args[1].protocolArgs['requestFactory']
        raise RuntimeError("No site found.")



def inServiceHierarchy(svc, predicate):
    """
    Find services in the service collection which satisfy the given predicate.
    """
    for subsvc in svc.services:
        if IServiceCollection.providedBy(subsvc):
            for value in inServiceHierarchy(subsvc, predicate):
                yield value
        if predicate(subsvc):
            yield subsvc



def determineAppropriateGroupID():
    """
    Determine a secondary group ID which can be used for testing.
    """
    return os.getgroups()[1]



class SocketGroupOwnership(TestCase):
    """
    Tests for L{GroupOwnedUNIXServer}.
    """

    def test_groupOwnedUNIXSocket(self):
        """
        When a L{GroupOwnedUNIXServer} is started, it will change the group of
        its socket.
        """
        alternateGroup = determineAppropriateGroupID()
        socketName = self.mktemp()
        gous = GroupOwnedUNIXServer(alternateGroup, socketName, ServerFactory(), mode=0660)
        gous.privilegedStartService()
        self.addCleanup(gous.stopService)
        filestat = os.stat(socketName)
        self.assertTrue(stat.S_ISSOCK(filestat.st_mode))
        self.assertEquals(filestat.st_gid, alternateGroup)
        self.assertEquals(filestat.st_uid, os.getuid())



class CalDAVServiceMakerTests(BaseServiceMakerTests):
    """
    Test the service maker's behavior
    """

    def test_makeServiceDispatcher(self):
        """
        Test the default options of the dispatching makeService
        """
        validServices = ["Slave", "Combined"]

        self.config["HTTPPort"] = 0

        for service in validServices:
            self.config["ProcessType"] = service
            self.writeConfig()
            self.makeService()

        self.config["ProcessType"] = "Unknown Service"
        self.writeConfig()
        self.assertRaises(UsageError, self.makeService)


    def test_modesOnUNIXSockets(self):
        """
        The logging and stats UNIX sockets that are bound as part of the
        'Combined' service hierarchy should have a secure mode specified: only
        the executing user should be able to open and send to them.
        """

        self.config["HTTPPort"] = 0 # Don't conflict with the test above.
        alternateGroup = determineAppropriateGroupID()
        self.config.GroupName = grp.getgrgid(alternateGroup).gr_name

        self.config["ProcessType"] = "Combined"
        self.writeConfig()
        svc = self.makeService()
        for serviceName in [_CONTROL_SERVICE_NAME]:
            socketService = svc.getServiceNamed(serviceName)
            self.assertIsInstance(socketService, GroupOwnedUNIXServer)
            m = socketService.kwargs.get("mode", 0666)
            self.assertEquals(
                m, int("660", 8),
                "Wrong mode on %s: %s" % (serviceName, oct(m))
            )
            self.assertEquals(socketService.gid, alternateGroup)
        for serviceName in ["stats"]:
            socketService = svc.getServiceNamed(serviceName)
            self.assertIsInstance(socketService, GroupOwnedUNIXServer)
            m = socketService.kwargs.get("mode", 0666)
            self.assertEquals(
                m, int("660", 8),
                "Wrong mode on %s: %s" % (serviceName, oct(m))
            )
            self.assertEquals(socketService.gid, alternateGroup)


    def test_processMonitor(self):
        """
        In the master, there should be exactly one
        L{DelayedStartupProcessMonitor} in the service hierarchy so that it
        will be started by startup.
        """
        self.config["ProcessType"] = "Combined"
        self.writeConfig()
        self.assertEquals(
            1,
            len(
                list(inServiceHierarchy(
                    self.makeService(),
                    lambda x: isinstance(x, DelayedStartupProcessMonitor)))
            )
        )




class SlaveServiceTest(BaseServiceMakerTests):
    """
    Test various configurations of the Slave service
    """

    configOptions = {
        "HTTPPort": 8008,
        "SSLPort": 8443,
    }

    def test_defaultService(self):
        """
        Test the value of a Slave service in it's simplest
        configuration.
        """
        service = self.makeService()

        self.failUnless(
            IService(service),
            "%s does not provide IService" % (service,)
        )
        self.failUnless(
            service.services,
            "No services configured"
        )
        self.failUnless(
            isinstance(service, CalDAVService),
            "%s is not a CalDAVService" % (service,)
        )

    def test_defaultListeners(self):
        """
        Test that the Slave service has sub services with the
        default TCP and SSL configuration
        """
        service = self.makeService()

        expectedSubServices = dict((
            (MaxAcceptTCPServer, self.config["HTTPPort"]),
            (MaxAcceptSSLServer, self.config["SSLPort"]),
        ))

        configuredSubServices = [(s.__class__, getattr(s, 'args', None))
                                 for s in service.services]
        checked = 0
        for serviceClass, serviceArgs in configuredSubServices:
            if serviceClass in expectedSubServices:
                checked += 1
                self.assertEquals(
                    serviceArgs[0],
                    dict(expectedSubServices)[serviceClass]
                )
        # TCP+SSL services for IPv4, TCP+SSL services for IPv6.
        self.assertEquals(checked, 4)


    def test_SSLKeyConfiguration(self):
        """
        Test that the configuration of the SSLServer reflect the config file's
        SSL Private Key and SSL Certificate
        """
        service = self.makeService()

        sslService = None
        for s in service.services:
            if isinstance(s, internet.SSLServer):
                sslService = s
                break

        self.failIf(sslService is None, "No SSL Service found")

        context = sslService.args[2]

        self.assertEquals(
            self.config["SSLPrivateKey"],
            context.privateKeyFileName
        )
        self.assertEquals(
            self.config["SSLCertificate"],
            context.certificateFileName,
        )

    def test_noSSL(self):
        """
        Test the single service to make sure there is no SSL Service when SSL
        is disabled
        """
        del self.config["SSLPort"]
        self.writeConfig()

        service = self.makeService()

        self.assertNotIn(
            internet.SSLServer,
            [s.__class__ for s in service.services]
        )

    def test_noHTTP(self):
        """
        Test the single service to make sure there is no TCPServer when
        HTTPPort is not configured
        """
        del self.config["HTTPPort"]
        self.writeConfig()

        service = self.makeService()

        self.assertNotIn(
            internet.TCPServer,
            [s.__class__ for s in service.services]
        )

    def test_singleBindAddresses(self):
        """
        Test that the TCPServer and SSLServers are bound to the proper address
        """
        self.config.BindAddresses = ["127.0.0.1"]
        self.writeConfig()

        service = self.makeService()

        for s in service.services:
            if isinstance(s, (internet.TCPServer, internet.SSLServer)):
                self.assertEquals(s.kwargs["interface"], "127.0.0.1")

    def test_multipleBindAddresses(self):
        """
        Test that the TCPServer and SSLServers are bound to the proper
        addresses.
        """
        self.config.BindAddresses = [
            "127.0.0.1",
            "10.0.0.2",
            "172.53.13.123",
        ]

        self.writeConfig()
        service = self.makeService()

        tcpServers = []
        sslServers = []

        for s in service.services:
            if isinstance(s, internet.TCPServer):
                tcpServers.append(s)
            elif isinstance(s, internet.SSLServer):
                sslServers.append(s)

        self.assertEquals(len(tcpServers), len(self.config.BindAddresses))
        self.assertEquals(len(sslServers), len(self.config.BindAddresses))

        for addr in self.config.BindAddresses:
            for s in tcpServers:
                if s.kwargs["interface"] == addr:
                    tcpServers.remove(s)

            for s in sslServers:
                if s.kwargs["interface"] == addr:
                    sslServers.remove(s)

        self.assertEquals(len(tcpServers), 0)
        self.assertEquals(len(sslServers), 0)

    def test_listenBacklog(self):
        """
        Test that the backlog arguments is set in TCPServer and SSLServers
        """
        self.config.ListenBacklog = 1024
        self.writeConfig()
        service = self.makeService()

        for s in service.services:
            if isinstance(s, (internet.TCPServer, internet.SSLServer)):
                self.assertEquals(s.kwargs["backlog"], 1024)


class ServiceHTTPFactoryTests(BaseServiceMakerTests):
    """
    Test the configuration of the initial resource hierarchy of the
    single service
    """
    configOptions = {"HTTPPort": 8008}

    def test_AuthWrapperAllEnabled(self):
        """
        Test the configuration of the authentication wrapper
        when all schemes are enabled.
        """
        self.config.Authentication.Digest.Enabled = True
        self.config.Authentication.Kerberos.Enabled = True
        self.config.Authentication.Kerberos.ServicePrincipal = "http/hello@bob"
        self.config.Authentication.Basic.Enabled = True

        self.writeConfig()
        site = self.getSite()

        self.failUnless(isinstance(
                site.resource.resource,
                auth.AuthenticationWrapper))

        authWrapper = site.resource.resource

        expectedSchemes = ["negotiate", "digest", "basic"]

        for scheme in authWrapper.credentialFactories:
            self.failUnless(scheme in expectedSchemes)

        self.assertEquals(len(expectedSchemes),
                          len(authWrapper.credentialFactories))

    def test_servicePrincipalNone(self):
        """
        Test that the Kerberos principal look is attempted if the principal is empty.
        """
        self.config.Authentication.Kerberos.ServicePrincipal = ""
        self.config.Authentication.Kerberos.Enabled = True
        self.writeConfig()
        site = self.getSite()

        authWrapper = site.resource.resource

        self.assertFalse(authWrapper.credentialFactories.has_key("negotiate"))

    def test_servicePrincipal(self):
        """
        Test that the kerberos realm is the realm portion of a principal
        in the form proto/host@realm
        """
        self.config.Authentication.Kerberos.ServicePrincipal = "http/hello@bob"
        self.config.Authentication.Kerberos.Enabled = True
        self.writeConfig()
        site = self.getSite()

        authWrapper = site.resource.resource
        ncf = authWrapper.credentialFactories["negotiate"]

        self.assertEquals(ncf.service, "http@HELLO")
        self.assertEquals(ncf.realm, "bob")

    def test_AuthWrapperPartialEnabled(self):
        """
        Test that the expected credential factories exist when
        only a partial set of authentication schemes is
        enabled.
        """

        self.config.Authentication.Basic.Enabled    = False
        self.config.Authentication.Kerberos.Enabled = False

        self.writeConfig()
        site = self.getSite()

        authWrapper = site.resource.resource

        expectedSchemes = ["digest"]

        for scheme in authWrapper.credentialFactories:
            self.failUnless(scheme in expectedSchemes)

        self.assertEquals(
            len(expectedSchemes),
            len(authWrapper.credentialFactories)
        )

    def test_LogWrapper(self):
        """
        Test the configuration of the log wrapper
        """
        site = self.getSite()

        self.failUnless(isinstance(
                site.resource,
                LogWrapperResource))

    def test_rootResource(self):
        """
        Test the root resource
        """
        site = self.getSite()
        root = site.resource.resource.resource

        self.failUnless(isinstance(root, RootResource))

    def test_principalResource(self):
        """
        Test the principal resource
        """
        site = self.getSite()
        root = site.resource.resource.resource

        self.failUnless(isinstance(
            root.getChild("principals"),
            DirectoryPrincipalProvisioningResource
        ))

    def test_calendarResource(self):
        """
        Test the calendar resource
        """
        site = self.getSite()
        root = site.resource.resource.resource

        self.failUnless(isinstance(
            root.getChild("calendars"),
            DirectoryCalendarHomeProvisioningResource
        ))


sudoersFile = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>users</key>
    <array>
       	<dict>
            <key>password</key>
            <string>superuser</string>
            <key>username</key>
            <string>superuser</string>
        </dict>
    </array>
</dict>
</plist>
"""

class DirectoryServiceTest(BaseServiceMakerTests):
    """
    Tests of the directory service
    """

    configOptions = {"HTTPPort": 8008}

    def test_sameDirectory(self):
        """
        Test that the principal hierarchy has a reference
        to the same DirectoryService as the calendar hierarchy
        """
        site = self.getSite()
        principals = site.resource.resource.resource.getChild("principals")
        calendars = site.resource.resource.resource.getChild("calendars")

        self.assertEquals(principals.directory, calendars.directory)

    def test_aggregateDirectory(self):
        """
        Assert that the base directory service is actually
        an AggregateDirectoryService
        """
        site = self.getSite()
        principals = site.resource.resource.resource.getChild("principals")
        directory = principals.directory

        self.failUnless(isinstance(directory, AggregateDirectoryService))


    def test_configuredDirectoryService(self):
        """
        Test that the real directory service is the directory service
        set in the configuration file.
        """
        site = self.getSite()
        principals = site.resource.resource.resource.getChild("principals")
        directory = principals.directory

        realDirectory = directory.serviceForRecordType("users")

        configuredDirectory = namedAny(self.config.DirectoryService.type)

        self.failUnless(isinstance(realDirectory, configuredDirectory))



class DummyProcessObject(object):
    """
    Simple stub for Process Object API which just has an executable and some
    arguments.

    This is a stand in for L{TwistdSlaveProcess}.
    """

    def __init__(self, scriptname, *args):
        self.scriptname = scriptname
        self.args = args


    def getCommandLine(self):
        """
        Simple command line.
        """
        return [self.scriptname] + list(self.args)


    def getFileDescriptors(self):
        """
        Return a dummy, empty mapping of file descriptors.
        """
        return {}


    def getName(self):
        """
        Get a dummy name.
        """
        return 'Dummy'


class ScriptProcessObject(DummyProcessObject):
    """
    Simple stub for the Process Object API that will run a test script.
    """

    def getCommandLine(self):
        """
        Get the command line to invoke this script.
        """
        return [
            sys.executable,
            FilePath(__file__).sibling(self.scriptname).path
        ] + list(self.args)





class DelayedStartupProcessMonitorTests(TestCase):
    """
    Test cases for L{DelayedStartupProcessMonitor}.
    """

    def test_lineAfterLongLine(self):
        """
        A "long" line of output from a monitored process (longer than
        L{LineReceiver.MAX_LENGTH}) should be logged in chunks rather than all
        at once, to avoid resource exhaustion.
        """
        dspm = DelayedStartupProcessMonitor()
        dspm.addProcessObject(ScriptProcessObject(
                'longlines.py', str(DelayedStartupLineLogger.MAX_LENGTH)),
                          os.environ)
        dspm.startService()
        self.addCleanup(dspm.stopService)

        logged = []

        def tempObserver(event):
            # Probably won't be a problem, but let's not have any intermittent
            # test issues that stem from multi-threaded log messages randomly
            # going off...
            if not isInIOThread():
                callFromThread(tempObserver, event)
                return
            if event.get('isError'):
                d.errback()
            m = event.get('message')[0]
            if m.startswith('[Dummy] '):
                logged.append(event)
                if m == '[Dummy] z':
                    d.callback("done")

        log.addObserver(tempObserver)
        self.addCleanup(log.removeObserver, tempObserver)
        d = Deferred()
        def assertions(result):
            self.assertEquals(["[Dummy] x",
                               "[Dummy] y",
                               "[Dummy] y", # final segment
                               "[Dummy] z"],
                              [''.join(evt['message'])[:len('[Dummy]') + 2]
                               for evt in logged])
            self.assertEquals([" (truncated, continued)",
                               " (truncated, continued)",
                               "[Dummy] y",
                               "[Dummy] z"],
                              [''.join(evt['message'])[-len(" (truncated, continued)"):]
                               for evt in logged])
        d.addCallback(assertions)
        return d


    def test_breakLineIntoSegments(self):
        """
        Exercise the line-breaking logic with various key lengths
        """
        testLogger = DelayedStartupLineLogger()
        testLogger.MAX_LENGTH = 10
        for input, output in [
            ("", []),
            ("a", ["a"]),
            ("abcde", ["abcde"]),
            ("abcdefghij", ["abcdefghij"]),
            ("abcdefghijk",
                ["abcdefghij (truncated, continued)",
                 "k"
                ]
            ),
            ("abcdefghijklmnopqrst",
                ["abcdefghij (truncated, continued)",
                 "klmnopqrst"
                ]
            ),
            ("abcdefghijklmnopqrstuv",
                ["abcdefghij (truncated, continued)",
                 "klmnopqrst (truncated, continued)",
                 "uv"]
            ),
        ]:
            self.assertEquals(output, testLogger._breakLineIntoSegments(input))


    def test_acceptDescriptorInheritance(self):
        """
        If a L{TwistdSlaveProcess} specifies some file descriptors to be
        inherited, they should be inherited by the subprocess.
        """
        imps = InMemoryProcessSpawner()
        dspm = DelayedStartupProcessMonitor(imps)

        # Most arguments here will be ignored, so these are bogus values.
        slave = TwistdSlaveProcess(
            twistd        = "bleh",
            tapname       = "caldav",
            configFile    = "/does/not/exist",
            id            = 10,
            interfaces    = '127.0.0.1',
            inheritFDs    = [3, 7],
            inheritSSLFDs = [19, 25],
        )

        dspm.addProcessObject(slave, {})
        dspm.startService()
        # We can easily stub out spawnProcess, because caldav calls it, but a
        # bunch of callLater calls are buried in procmon itself, so we need to
        # use the real clock.
        oneProcessTransport = imps.waitForOneProcess()
        self.assertEquals(oneProcessTransport.childFDs,
                          {0: 'w', 1: 'r', 2: 'r',
                           3: 3, 7: 7,
                           19: 19, 25: 25})


    def test_changedArgumentEachSpawn(self):
        """
        If the result of C{getCommandLine} changes on subsequent calls,
        subsequent calls should result in different arguments being passed to
        C{spawnProcess} each time.
        """
        imps = InMemoryProcessSpawner()
        dspm = DelayedStartupProcessMonitor(imps)
        slave = DummyProcessObject('scriptname', 'first')
        dspm.addProcessObject(slave, {})
        dspm.startService()
        oneProcessTransport = imps.waitForOneProcess()
        self.assertEquals(oneProcessTransport.args,
                          ['scriptname', 'first'])
        slave.args = ['second']
        oneProcessTransport.processProtocol.processEnded(None)
        twoProcessTransport = imps.waitForOneProcess()
        self.assertEquals(twoProcessTransport.args,
                          ['scriptname', 'second'])


    def test_metaDescriptorInheritance(self):
        """
        If a L{TwistdSlaveProcess} specifies a meta-file-descriptor to be
        inherited, it should be inherited by the subprocess, and a
        configuration argument should be passed that indicates to the
        subprocess.
        """
        imps = InMemoryProcessSpawner()
        dspm = DelayedStartupProcessMonitor(imps)
        # Most arguments here will be ignored, so these are bogus values.
        slave = TwistdSlaveProcess(
            twistd     = "bleh",
            tapname    = "caldav",
            configFile = "/does/not/exist",
            id         = 10,
            interfaces = '127.0.0.1',
            metaSocket = FakeDispatcher().addSocket()
        )

        dspm.addProcessObject(slave, {})
        dspm.startService()
        oneProcessTransport = imps.waitForOneProcess()
        self.assertIn("MetaFD=4", oneProcessTransport.args)
        self.assertEquals(
            oneProcessTransport.args[oneProcessTransport.args.index("MetaFD=4")-1],
            '-o',
            "MetaFD argument was not passed as an option"
        )
        self.assertEquals(oneProcessTransport.childFDs,
                          {0: 'w', 1: 'r', 2: 'r',
                           4: 4})


    def test_startServiceDelay(self):
        """
        Starting a L{DelayedStartupProcessMonitor} should result in the process
        objects that have been added to it being started once per
        delayInterval.
        """
        imps = InMemoryProcessSpawner()
        dspm = DelayedStartupProcessMonitor(imps)
        dspm.delayInterval = 3.0
        sampleCounter = range(0, 5)
        for counter in sampleCounter:
            slave = TwistdSlaveProcess(
                twistd     = "bleh",
                tapname    = "caldav",
                configFile = "/does/not/exist",
                id         = counter * 10,
                interfaces = '127.0.0.1',
                metaSocket = FakeDispatcher().addSocket()
            )
            dspm.addProcessObject(slave, {"SAMPLE_ENV_COUNTER": str(counter)})
        dspm.startService()

        # Advance the clock a bunch of times, allowing us to time things with a
        # comprehensible resolution.
        imps.pump([0] + [dspm.delayInterval / 2.0] * len(sampleCounter) * 3)
        expectedValues = [dspm.delayInterval * n for n in sampleCounter]
        self.assertEquals([x.startedAt for x in imps.processTransports],
                          expectedValues)



class FakeFD(object):

    def __init__(self, n):
        self.fd = n

    
    def fileno(self):
        return self.fd



class FakeDispatcher(object):
    n = 3

    def addSocket(self):
        self.n += 1
        return FakeFD(self.n)



class TwistdSlaveProcessTests(TestCase):
    """
    Tests for L{TwistdSlaveProcess}.
    """
    def test_pidfile(self):
        """
        The result of L{TwistdSlaveProcess.getCommandLine} includes an option
        setting the name of the pidfile to something including the instance id.
        """
        slave = TwistdSlaveProcess("/path/to/twistd", "something", "config", 7, [])
        commandLine = slave.getCommandLine()

        option = 'PIDFile=something-instance-7.pid'
        self.assertIn(option, commandLine)
        self.assertEquals(commandLine[commandLine.index(option) - 1], '-o')






class ReExecServiceTests(TestCase):

    @inlineCallbacks
    def test_reExecService(self):
        """
        Verify that sending a HUP to the test reexec.tac causes startService
        and stopService to be called again by counting the number of times
        START and STOP appear in the process output.
        """
        tacFilePath = os.path.join(os.path.dirname(__file__), "reexec.tac")
        twistd = which("twistd")[0]
        deferred = Deferred()
        proc = reactor.spawnProcess(
            CapturingProcessProtocol(deferred, None), twistd,
                [twistd, '-n', '-y', tacFilePath],
                env=os.environ
        )
        reactor.callLater(3, proc.signalProcess, "HUP")
        reactor.callLater(6, proc.signalProcess, "TERM")
        output = yield deferred
        self.assertEquals(output.count("START"), 2)
        self.assertEquals(output.count("STOP"), 2)

