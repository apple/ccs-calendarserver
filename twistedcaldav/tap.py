##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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
import sys

from zope.interface import implements

from twisted.python import log

from twisted.python.usage import Options, UsageError
from twisted.python.reflect import namedClass

from twisted.application import internet, service
from twisted.plugin import IPlugin

from twisted.cred.portal import Portal

from twisted.web2.dav import auth
from twisted.web2.dav import davxml
from twisted.web2.dav.resource import TwistedACLInheritable
from twisted.web2.auth.basic import BasicCredentialFactory
from twisted.web2.auth.digest import DigestCredentialFactory
from twisted.web2.channel import http

from twisted.web2.log import LogWrapperResource
from twisted.web2.server import Site

from twistedcaldav.cluster import makeService_multiprocess, makeService_pydir
from twistedcaldav.config import config, parseConfig, defaultConfig
from twistedcaldav.logging import RotatingFileAccessLoggingObserver
from twistedcaldav.root import RootResource
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory.aggregate import AggregateDirectoryService
from twistedcaldav.directory.sudo import SudoDirectoryService

from twistedcaldav.static import CalendarHomeProvisioningFile

try:
    from twistedcaldav.authkerb import NegotiateCredentialFactory
except ImportError:
    NegotiateCredentialFactory = None


class CalDAVService(service.MultiService):
    def __init__(self, logObserver):
        self.logObserver = logObserver
        service.MultiService.__init__(self)

    def privilegedStartService(self):
        service.MultiService.privilegedStartService(self)
        self.logObserver.start()

    def stopService(self):
        service.MultiService.stopService(self)
        self.logObserver.stop()


class CalDAVOptions(Options):
    optParameters = [
        ["config", "f", "/etc/caldavd/caldavd.plist",
         "Path to configuration file."],
        ]

    zsh_actions = {"config" : "_files -g '*.plist'"}

    def __init__(self, *args, **kwargs):
        super(CalDAVOptions, self).__init__(*args, **kwargs)

        self.overrides = {}

    def opt_option(self, option):
        """
        Set an option to override a value in the config file. True, False, int, 
        and float options are supported, as well as comma seperated lists. Only
        one option may be given for each --option flag, however multiple 
        --option flags may be specified.
        """

        if '=' in option:
            key, value = option.split('=')

            if key in defaultConfig:
                if isinstance(defaultConfig[key], bool):
                    value = value == "True"

                elif isinstance(defaultConfig[key], (int, float, long)):
                    value = type(defaultConfig[key])(value)
                
                elif isinstance(defaultConfig[key], (list, tuple)):
                    value = value.split(',')

                elif isinstance(defaultConfig[key], dict):
                    raise UsageError(
                        "We do not support dict options on the command line")

            self.overrides[key] = value
        else:
            self.opt_option('%s=True' % (option,))

    opt_o = opt_option

    def postOptions(self):
        if not os.path.exists(self['config']):
            print "Config file %s not found, using defaults" % (self['config'],)

        parseConfig(self['config'])

        config.update(self.overrides)

        self.parent['logfile'] = config.ErrorLogFile
        self.parent['pidfile'] = config.PIDFile


class CalDAVServiceMaker(object):
    implements(IPlugin, service.IServiceMaker)

    tapname = "caldav"

    description = "The Darwin Calendar Server"

    options = CalDAVOptions

    #
    # default resource classes
    #

    rootResourceClass = RootResource
    principalResourceClass = DirectoryPrincipalProvisioningResource
    calendarResourceClass = CalendarHomeProvisioningFile

    def makeService_singleprocess(self, options):
        #
        # Setup the Directory
        #
        directories = []
        
        directoryClass = namedClass(config.DirectoryService['type'])
        baseDirectory = directoryClass(**config.DirectoryService['params'])

        directories.append(baseDirectory)

        sudoDirectory = None

        if config.SudoersFile and os.path.exists(config.SudoersFile):
            sudoDirectory = SudoDirectoryService(config.SudoersFile)
            sudoDirectory.realmName = baseDirectory.realmName

            CalDAVResource.sudoDirectory = sudoDirectory
            directories.append(sudoDirectory)

        directory = AggregateDirectoryService(directories)

        if sudoDirectory:
            directory.userRecordTypes.append(
                SudoDirectoryService.recordType_sudoers)

        #
        # Setup Resource hierarchy
        #

        log.msg("Setting up document root: %s" % (config.DocumentRoot,))

        principalCollection = self.principalResourceClass(
            os.path.join(config.DocumentRoot, 'principals'),
            '/principals/',
            directory
        )

        calendarCollection = self.calendarResourceClass(
            os.path.join(config.DocumentRoot, 'calendars'),
            directory,
            '/calendars/'
        )
        
        root = self.rootResourceClass(
            config.DocumentRoot, 
            principalCollections=(principalCollection,)
        )

        root.putChild('principals', principalCollection)
        root.putChild('calendars', calendarCollection)

        # Configure default ACLs on the root resource

        rootACEs = [
            davxml.ACE(
                davxml.Principal(davxml.All()),
                davxml.Grant(davxml.Privilege(davxml.Read())),
            ),
        ]

        for principal in config.AdminPrincipals:
            rootACEs.append(
                davxml.ACE(
                    davxml.Principal(davxml.HRef(principal)),
                    davxml.Grant(davxml.Privilege(davxml.All())),
                    davxml.Protected(),
                    TwistedACLInheritable(),
                )
            )

        root.setAccessControlList(davxml.ACL(*rootACEs))

        #
        # Configure the Site and Wrappers
        #

        credentialFactories = []

        portal = Portal(auth.DavRealm())

        portal.registerChecker(directory)

        realm = directory.realmName or ""

        for scheme, schemeConfig in config.Authentication.iteritems():
            scheme = scheme.lower()

            credFactory = None

            if schemeConfig['Enabled']:
                if scheme == 'kerberos':
                    if not NegotiateCredentialFactory:
                        log.msg("Kerberos support not available")
                        continue

                    credFactory = NegotiateCredentialFactory(
                        schemeConfig['ServicePrincipal'])

                elif scheme == 'digest':
                    credFactory = DigestCredentialFactory(
                        schemeConfig['Algorithm'], realm)

                elif scheme == 'basic':
                    credFactory = BasicCredentialFactory(realm)

            if credFactory:
                credentialFactories.append(credFactory)

        authWrapper = auth.AuthenticationWrapper(
            root,
            portal,
            credentialFactories,
            (auth.IPrincipal,))

        site = Site(LogWrapperResource(authWrapper))

        #
        # Configure the service
        # 

        channel = http.HTTPFactory(site)

        logObserver = RotatingFileAccessLoggingObserver(config.ServerLogFile)
        
        service = CalDAVService(logObserver)

        if not config.BindAddress:
            config.BindAddress = ['']

        for bindAddress in config.BindAddress:
            if not config.SSLOnly:
                httpService = internet.TCPServer(int(config.Port), channel,
                                                 interface=bindAddress)
                httpService.setServiceParent(service)

            if config.SSLEnable:
                from twisted.internet.ssl import DefaultOpenSSLContextFactory
                httpsService = internet.SSLServer(
                    int(config.SSLPort),
                    channel,
                    DefaultOpenSSLContextFactory(config.SSLPrivateKey,
                                                 config.SSLCertificate),
                    interface=bindAddress
                    )
                httpsService.setServiceParent(service)
            
        return service

    makeService_slave = makeService_singleprocess

    makeService_multiprocess = makeService_multiprocess

    makeService_master = makeService_pydir

    def makeService(self, options):
        serverType = config.ServerType
        
        serviceMethod = getattr(self, 'makeService_%s' % (serverType,), None)

        if not serviceMethod:
            raise UsageError(
                ("Unknown server type %s, please choose: singleprocess, "
                 "multiprocess, master, slave" % (serverType,)))

        else:
            return serviceMethod(options)
            

                                
