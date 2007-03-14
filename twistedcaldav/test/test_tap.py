##
# Copyright (c) 2007 Apple Inc. All rights reserved.
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
# DRI: David Reid, dreid@apple.com
##

import os
from copy import deepcopy

from twisted.trial import unittest

from twisted.python.usage import Options, UsageError
from twisted.python.util import sibpath
from twisted.python.reflect import namedAny
from twisted.application.service import IService
from twisted.application import internet

from twisted.web2.dav import auth
from twisted.web2.log import LogWrapperResource

from twistedcaldav.tap import CalDAVOptions, CalDAVServiceMaker
from twistedcaldav import tap

from twistedcaldav.config import config
from twistedcaldav import config as config_mod
from twistedcaldav.py.plistlib import writePlist

from twistedcaldav.directory.aggregate import AggregateDirectoryService
from twistedcaldav.directory.sudo import SudoDirectoryService
from twistedcaldav.directory.directory import UnknownRecordTypeError


class TestCalDAVOptions(CalDAVOptions):
    """
    A fake implementation of CalDAVOptions that provides
    empty implementations of checkDirectory and checkFile.
    """

    def checkDirectory(*args, **kwargs):
        pass

    def checkFile(*args, **kwargs):
        pass


class CalDAVOptionsTest(unittest.TestCase):
    """
    Test various parameters of our usage.Options subclass
    """

    def setUp(self):
        """
        Set up our options object, giving it a parent, and forcing the
        global config to be loaded from defaults.
        """

        self.config = TestCalDAVOptions()
        self.config.parent = Options()
        self.config.parent['uid'] = 0
        self.config.parent['gid'] = 0
        self.config.parent['nodaemon'] = False

    def tearDown(self):
        config.loadConfig(None)
        config.setDefaults(config_mod.defaultConfig)
        config.reload()

    def test_overridesConfig(self):
        """
        Test that values on the command line's -o and --option options
        overide the config file
        """

        argv = ['-o', 'EnableSACLs',
                '-o', 'HTTPPort=80',
                '-o', 'BindAddresses=127.0.0.1,127.0.0.2,127.0.0.3',
                '-o', 'DocumentRoot=/dev/null',
                '-o', 'UserName=None',
                '-o', 'EnableProxyPrincipals=False']

        self.config.parseOptions(argv)

        self.assertEquals(config.EnableSACLs, True)
        self.assertEquals(config.HTTPPort, 80)
        self.assertEquals(config.BindAddresses, ['127.0.0.1',
                                               '127.0.0.2',
                                               '127.0.0.3'])
        self.assertEquals(config.DocumentRoot, '/dev/null')
        self.assertEquals(config.UserName, None)
        self.assertEquals(config.EnableProxyPrincipals, False)

        argv = ['-o', 'Authentication=This Doesn\'t Matter']

        self.assertRaises(UsageError, self.config.parseOptions, argv)

    def test_setsParent(self):
        """
        Test that certain values are set on the parent (i.e. twistd's
        Option's object)
        """

        argv = ['-o', 'ErrorLogFile=/dev/null',
                '-o', 'PIDFile=/dev/null']

        self.config.parseOptions(argv)

        self.assertEquals(self.config.parent['logfile'], '/dev/null')

        self.assertEquals(self.config.parent['pidfile'], '/dev/null')

    def test_specifyConfigFile(self):
        """
        Test that specifying a config file from the command line
        loads the global config with those values properly.
        """

        myConfig = deepcopy(config_mod.defaultConfig)

        myConfig['Authentication']['Basic']['Enabled'] = False

        myConfig['MultiProcess']['LoadBalancer']['Enabled'] = False

        myConfig['HTTPPort'] = 80

        myConfig['ServerHostName'] = 'calendar.calenderserver.org'

        myConfigFile = self.mktemp()
        writePlist(myConfig, myConfigFile)

        args = ['-f', myConfigFile]

        self.config.parseOptions(args)

        self.assertEquals(config.ServerHostName, myConfig['ServerHostName'])

        self.assertEquals(config.MultiProcess['LoadBalancer']['Enabled'],
                          myConfig['MultiProcess']['LoadBalancer']['Enabled'])

        self.assertEquals(config.HTTPPort, myConfig['HTTPPort'])

        self.assertEquals(config.Authentication['Basic']['Enabled'],
                          myConfig['Authentication']['Basic']['Enabled'])


class BaseServiceMakerTests(unittest.TestCase):
    """
    Utility class for ServiceMaker tests.
    """

    def setUp(self):
        self.options = TestCalDAVOptions()
        self.options.parent = Options()
        self.options.parent['gid'] = None
        self.options.parent['uid'] = None
        self.options.parent['nodaemon'] = None

        self.config = deepcopy(config_mod.defaultConfig)

        accountsFile = sibpath(os.path.dirname(__file__),
                               'directory/test/accounts.xml')

        self.config['DirectoryService'] = {
            'params': {'xmlFile': accountsFile},
            'type': 'twistedcaldav.directory.xmlfile.XMLDirectoryService'
            }

        self.config['DocumentRoot'] = self.mktemp()

        self.config['SSLPrivateKey'] = sibpath(__file__, 'data/server.pem')
        self.config['SSLCertificate'] = sibpath(__file__, 'data/server.pem')

        self.config['SudoersFile'] = ''

        os.mkdir(self.config['DocumentRoot'])

        self.configFile = self.mktemp()

        self.writeConfig()

    def tearDown(self):
        config.loadConfig(None)
        config.setDefaults(config_mod.defaultConfig)
        config.reload()

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

        self.options.parseOptions(['-f', self.configFile])

        return CalDAVServiceMaker().makeService(self.options)

    def getSite(self):
        """
        Get the server.Site from the service by finding the HTTPFactory
        """

        service = self.makeService()

        return service.services[0].args[1].protocolArgs['requestFactory']


class CalDAVServiceMakerTests(BaseServiceMakerTests):
    """
    Test the service maker's behavior
    """

    def test_makeServiceDispatcher(self):
        """
        Test the default options of the dispatching makeService
        """
        validServices = ['Slave', 'Master', 'Combined']

        for service in validServices:
            self.config['ServerType'] = service
            self.writeConfig()
            self.makeService()

        self.config['ServerType'] = 'Unknown Service'
        self.writeConfig()
        self.assertRaises(UsageError, self.makeService)


class SlaveServiceTest(BaseServiceMakerTests):
    """
    Test various configurations of the Slave service
    """

    def test_defaultService(self):
        """
        Test the value of a Slave service in it's simplest
        configuration.
        """
        self.config['HTTPPort'] = 8008
        self.config['SSLPort'] = 8443
        self.writeConfig()

        service = self.makeService()

        self.failUnless(IService(service),
                        "%s does not provide IService" % (service,))

        self.failUnless(service.services,
                        "No services configured")

        self.failUnless(isinstance(service, tap.CalDAVService),
                        "%s is not a tap.CalDAVService" % (service,))

    def test_defaultListeners(self):
        """
        Test that the Slave service has sub services with the
        default TCP and SSL configuration
        """
        self.config['HTTPPort'] = 8008
        self.config['SSLPort'] = 8443
        self.writeConfig()

        service = self.makeService()

        expectedSubServices = ((internet.TCPServer, self.config['HTTPPort']),
                               (internet.SSLServer, self.config['SSLPort']))

        configuredSubServices = [(s.__class__, s.args)
                                 for s in service.services]

        for serviceClass, serviceArgs in configuredSubServices:
            self.failUnless(
                serviceClass in (s[0] for s in expectedSubServices))

            self.assertEquals(serviceArgs[0],
                              dict(expectedSubServices)[serviceClass])

    def test_SSLKeyConfiguration(self):
        """
        Test that the configuration of the SSLServer reflect the config file's
        SSL Private Key and SSL Certificate
        """
        self.config['SSLPort'] = 8443
        self.writeConfig()

        service = self.makeService()

        sslService = None
        for s in service.services:
            if isinstance(s, internet.SSLServer):
                sslService = s
                break

        self.failIf(sslService is None, "No SSL Service found")

        context = sslService.args[2]

        self.assertEquals(self.config['SSLPrivateKey'],
                          context.privateKeyFileName)

        self.assertEquals(self.config['SSLCertificate'],
                          context.certificateFileName)

    def test_noSSL(self):
        """
        Test the single service to make sure there is no SSL Service when SSL
        is disabled
        """
        service = self.makeService()

        self.assertNotIn(
            internet.SSLServer, [s.__class__ for s in service.services])

    def test_noHTTP(self):
        """
        Test the single service to make sure there is no TCPServer when
        HTTPPort is not configured
        """
        service = self.makeService()

        self.assertNotIn(
            internet.TCPServer, [s.__class__ for s in service.services])

    def test_singleBindAddresses(self):
        """
        Test that the TCPServer and SSLServers are bound to the proper address
        """
        self.config['SSLPort'] = 8443
        self.config['HTTPPort'] = 8008

        self.config['BindAddresses'] = ['127.0.0.1']
        self.writeConfig()
        service = self.makeService()

        for s in service.services:
            self.assertEquals(s.kwargs['interface'], '127.0.0.1')

    def test_multipleBindAddresses(self):
        """
        Test that the TCPServer and SSLServers are bound to the proper
        addresses.
        """
        self.config['SSLPort'] = 8443
        self.config['HTTPPort'] = 8008

        self.config['BindAddresses'] = ['127.0.0.1', '10.0.0.2', '172.53.13.123']
        self.writeConfig()
        service = self.makeService()

        tcpServers = []
        sslServers = []

        for s in service.services:
            if isinstance(s, internet.TCPServer):
                tcpServers.append(s)
            elif isinstance(s, internet.SSLServer):
                sslServers.append(s)

        self.assertEquals(len(tcpServers), len(self.config['BindAddresses']))
        self.assertEquals(len(sslServers), len(self.config['BindAddresses']))

        for addr in self.config['BindAddresses']:
            for s in tcpServers:
                if s.kwargs['interface'] == addr:
                    tcpServers.remove(s)

            for s in sslServers:
                if s.kwargs['interface'] == addr:
                    sslServers.remove(s)

        self.assertEquals(len(tcpServers), 0)
        self.assertEquals(len(sslServers), 0)
