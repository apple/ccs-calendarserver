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

        argv = ['-f', 'No-Such-File',
                '-o', 'EnableSACLs',
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

        argv = ['-f', 'No-Such-File',
                '-o', 'ErrorLogFile=/dev/null',
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

    def test_specifyDictPath(self):
        """
        Test that we can specify command line overrides to leafs using
        a '/' seperated path.  Such as '-o MultiProcess/ProcessCount=1'
        """

        argv = ['-o', 'MultiProcess/ProcessCount=102']
        self.config.parseOptions(argv)

        self.assertEquals(config.MultiProcess['ProcessCount'], 102)

class BaseServiceMakerTests(unittest.TestCase):
    """
    Utility class for ServiceMaker tests.
    """

    configOptions = None

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
        self.config['DataRoot'] = self.mktemp()
        self.config['ProcessType'] = 'Slave'
        self.config['SSLPrivateKey'] = sibpath(__file__, 'data/server.pem')
        self.config['SSLCertificate'] = sibpath(__file__, 'data/server.pem')

        self.config['SudoersFile'] = ''

        if self.configOptions:
            config_mod._mergeData(self.config, self.configOptions)

        os.mkdir(self.config['DocumentRoot'])
        os.mkdir(self.config['DataRoot'])

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

        self.config['HTTPPort'] = 80

        for service in validServices:
            self.config['ProcessType'] = service
            self.writeConfig()
            self.makeService()

        self.config['ProcessType'] = 'Unknown Service'
        self.writeConfig()
        self.assertRaises(UsageError, self.makeService)


class SlaveServiceTest(BaseServiceMakerTests):
    """
    Test various configurations of the Slave service
    """

    configOptions = {'HTTPPort': 8008,
                     'SSLPort': 8443}

    def test_defaultService(self):
        """
        Test the value of a Slave service in it's simplest
        configuration.
        """
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
        del self.config['SSLPort']
        self.writeConfig()

        service = self.makeService()

        self.assertNotIn(
            internet.SSLServer, [s.__class__ for s in service.services])

    def test_noHTTP(self):
        """
        Test the single service to make sure there is no TCPServer when
        HTTPPort is not configured
        """
        del self.config['HTTPPort']
        self.writeConfig()

        service = self.makeService()

        self.assertNotIn(
            internet.TCPServer, [s.__class__ for s in service.services])

    def test_singleBindAddresses(self):
        """
        Test that the TCPServer and SSLServers are bound to the proper address
        """
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
        self.config['BindAddresses'] = ['127.0.0.1',
                                        '10.0.0.2',
                                        '172.53.13.123']
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

    def test_listenBacklog(self):
        """
        Test that the backlog arguments is set in TCPServer and SSLServers
        """
        self.config['ListenBacklog'] = 1024
        self.writeConfig()
        service = self.makeService()

        for s in service.services:
            self.assertEquals(s.kwargs['backlog'], 1024)


class ServiceHTTPFactoryTests(BaseServiceMakerTests):
    """
    Test the configuration of the initial resource hierarchy of the
    single service
    """

    configOptions = {'HTTPPort': 8008}

    def test_AuthWrapperAllEnabled(self):
        """
        Test the configuration of the authentication wrapper
        when all schemes are enabled.
        """
        self.config['Authentication']['Digest']['Enabled'] = True
        self.config['Authentication']['Kerberos']['Enabled'] = True
        self.config['Authentication']['Kerberos']['ServicePrincipal'] = 'http/hello@bob'
        self.config['Authentication']['Basic']['Enabled'] = True

        self.writeConfig()
        site = self.getSite()

        self.failUnless(isinstance(
                site.resource.resource,
                auth.AuthenticationWrapper))

        authWrapper = site.resource.resource

        expectedSchemes = ['negotiate', 'digest', 'basic']

        for scheme in authWrapper.credentialFactories:
            self.failUnless(scheme in expectedSchemes)

        self.assertEquals(len(expectedSchemes),
                          len(authWrapper.credentialFactories))

    def test_servicePrincipalNone(self):
        """
        Test that the Kerberos principal look is attempted if the principal is empty.
        """
        self.config['Authentication']['Kerberos']['ServicePrincipal'] = ''
        self.config['Authentication']['Kerberos']['Enabled'] = True
        self.writeConfig()
        site = self.getSite()

        authWrapper = site.resource.resource

        self.assertFalse(authWrapper.credentialFactories.has_key('negotiate'))

    def test_servicePrincipal(self):
        """
        Test that the kerberos realm is the realm portion of a principal
        in the form proto/host@realm
        """
        self.config['Authentication']['Kerberos']['ServicePrincipal'] = 'http/hello@bob'
        self.config['Authentication']['Kerberos']['Enabled'] = True
        self.writeConfig()
        site = self.getSite()

        authWrapper = site.resource.resource

        ncf = authWrapper.credentialFactories['negotiate']
        self.assertEquals(ncf.service, 'http@HELLO')
        self.assertEquals(ncf.realm, 'bob')

    def test_AuthWrapperPartialEnabled(self):
        """
        Test that the expected credential factories exist when
        only a partial set of authentication schemes is
        enabled.
        """

        self.config['Authentication']['Basic']['Enabled'] = False
        self.config['Authentication']['Kerberos']['Enabled'] = False

        self.writeConfig()
        site = self.getSite()

        authWrapper = site.resource.resource

        expectedSchemes = ['digest']

        for scheme in authWrapper.credentialFactories:
            self.failUnless(scheme in expectedSchemes)

        self.assertEquals(len(expectedSchemes),
                          len(authWrapper.credentialFactories))

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

        self.failUnless(isinstance(root, CalDAVServiceMaker.rootResourceClass))

    def test_principalResource(self):
        """
        Test the principal resource
        """
        site = self.getSite()
        root = site.resource.resource.resource

        self.failUnless(isinstance(
                root.getChild('principals'),
                CalDAVServiceMaker.principalResourceClass))

    def test_calendarResource(self):
        """
        Test the calendar resource
        """
        site = self.getSite()
        root = site.resource.resource.resource

        self.failUnless(isinstance(
                root.getChild('calendars'),
                CalDAVServiceMaker.calendarResourceClass))


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

    configOptions = {'HTTPPort': 8008}

    def test_sameDirectory(self):
        """
        Test that the principal hierarchy has a reference
        to the same DirectoryService as the calendar hierarchy
        """
        site = self.getSite()
        principals = site.resource.resource.resource.getChild('principals')
        calendars = site.resource.resource.resource.getChild('calendars')

        self.assertEquals(principals.directory,
                          calendars.directory)

    def test_aggregateDirectory(self):
        """
        Assert that the base directory service is actually
        an AggregateDirectoryService
        """
        site = self.getSite()
        principals = site.resource.resource.resource.getChild('principals')
        directory = principals.directory

        self.failUnless(isinstance(
                directory,
                AggregateDirectoryService))

    def test_sudoDirectoryService(self):
        """
        Test that a sudo directory service is available if the
        SudoersFile is set and exists
        """
        self.config['SudoersFile'] = self.mktemp()

        self.writeConfig()

        open(self.config['SudoersFile'], 'w').write(sudoersFile)

        site = self.getSite()
        principals = site.resource.resource.resource.getChild('principals')
        directory = principals.directory

        self.failUnless(self.config['SudoersFile'])

        sudoService = directory.serviceForRecordType(
            SudoDirectoryService.recordType_sudoers)

        self.assertEquals(sudoService.plistFile.path,
                          os.path.abspath(self.config['SudoersFile']))

        self.failUnless(SudoDirectoryService.recordType_sudoers in
                        directory.userRecordTypes)

    def test_sudoDirectoryServiceNoFile(self):
        """
        Test that there is no SudoDirectoryService if
        the SudoersFile does not exist.
        """
        self.config['SudoersFile'] = self.mktemp()

        self.writeConfig()
        site = self.getSite()
        principals = site.resource.resource.resource.getChild('principals')
        directory = principals.directory

        self.failUnless(self.config['SudoersFile'])

        self.assertRaises(
            UnknownRecordTypeError,
            directory.serviceForRecordType,
            SudoDirectoryService.recordType_sudoers)

    def test_sudoDirectoryServiceNotConfigured(self):
        """
        Test that there is no SudoDirectoryService if
        the SudoersFile is not configured
        """
        site = self.getSite()
        principals = site.resource.resource.resource.getChild('principals')
        directory = principals.directory

        self.failIf(self.config['SudoersFile'])

        self.assertRaises(
            UnknownRecordTypeError,
            directory.serviceForRecordType,
            SudoDirectoryService.recordType_sudoers)

    def test_configuredDirectoryService(self):
        """
        Test that the real directory service is the directory service
        set in the configuration file.
        """
        site = self.getSite()
        principals = site.resource.resource.resource.getChild('principals')
        directory = principals.directory

        realDirectory = directory.serviceForRecordType('users')

        configuredDirectory = namedAny(
            self.config['DirectoryService']['type'])

        self.failUnless(isinstance(
                realDirectory,
                configuredDirectory))
