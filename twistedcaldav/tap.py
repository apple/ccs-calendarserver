##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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
import stat

from zope.interface import implements

from twisted.python import log

from twisted.python.usage import Options, UsageError
from twisted.python.reflect import namedClass

from twisted.application import internet, service
from twisted.plugin import IPlugin

from twisted.scripts.mktap import getid

from twisted.cred.portal import Portal

from twisted.web2.dav import auth
from twisted.web2.dav import davxml
from twisted.web2.dav.resource import TwistedACLInheritable
from twisted.web2.auth.basic import BasicCredentialFactory
from twisted.web2.channel import http

from twisted.web2.log import LogWrapperResource
from twisted.web2.server import Site

from twistedcaldav import logging

from twistedcaldav.cluster import makeService_Combined, makeService_Master
from twistedcaldav.config import config, parseConfig, defaultConfig, ConfigurationError
from twistedcaldav.logging import RotatingFileAccessLoggingObserver
from twistedcaldav.root import RootResource
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.directory.digest import QopDigestCredentialFactory
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
    optParameters = [[
        "config", "f", "/etc/caldavd/caldavd.plist", "Path to configuration file."
    ]]

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
                    raise UsageError("Dict options not supported on the command line")
                        
                elif value == 'None':
                    value = None

            self.overrides[key] = value
        else:
            self.opt_option('%s=True' % (option,))

    opt_o = opt_option

    def postOptions(self):
        if not os.path.exists(self['config']):
            log.msg("Config file %s not found, using defaults" % (
                    self['config'],))

        parseConfig(self['config'])

        config.updateDefaults(self.overrides)

        uid, gid = None, None

        if self.parent['uid'] or self.parent['gid']:
            uid, gid = getid(self.parent['uid'], 
                             self.parent['gid'])

        if uid:
            if uid != os.getuid() and os.getuid() != 0:
                import pwd
                username = pwd.getpwuid(os.getuid())[0]
                raise UsageError("Only root can drop privileges you are: %r"
                                 % (username,))

        if gid:
            if gid != os.getgid() and os.getgid() != 0:
                import grp
                groupname = grp.getgrgid(os.getgid())[0]
                raise UsageError("Only root can drop privileges, you are: %s"
                                 % (groupname,))

        # Ignore the logfile parameter if not daemonized and log to stdout.
        if self.parent['nodaemon']:
            self.parent['logfile'] = None
        else:
            self.parent['logfile'] = config.ErrorLogFile

        self.parent['pidfile'] = config.PIDFile

        # Verify that document root actually exists
        self.checkDirectory(
            config.DocumentRoot,
            "Document root",
            access=os.W_OK,
            #permissions=0750,
            #uname=config.UserName,
            #gname=config.GroupName
        )
            
        # Verify that ssl certs exist if needed
        if config.SSLPort:
            self.checkFile(
                config.SSLPrivateKey,
                "SSL Private key",
                access=os.R_OK,
                #permissions=0640
            )
            self.checkFile(
                config.SSLCertificate,
                "SSL Public key",
                access=os.R_OK,
                #permissions=0644
            )

        #
        # Nuke the file log observer's time format.
        #

        if not config.ErrorLogFile and config.ProcessType == 'Slave':
            log.FileLogObserver.timeFormat = ''

        # Check current umask and warn if changed
        oldmask = os.umask(config.umask)
        if oldmask != config.umask:
            log.msg("WARNING: changing umask from: 0%03o to 0%03o" % (
                    oldmask, config.umask,))
        
    def checkDirectory(self, dirpath, description, access=None, fail=False, permissions=None, uname=None, gname=None):
        if not os.path.exists(dirpath):
            raise ConfigurationError("%s does not exist: %s" % (description, dirpath,))
        elif not os.path.isdir(dirpath):
            raise ConfigurationError("%s is not a directory: %s" % (description, dirpath,))
        elif access and not os.access(dirpath, access):
            raise ConfigurationError("Insufficient permissions for server on %s directory: %s" % (description, dirpath,))
        self.securityCheck(dirpath, description, fail=fail, permissions=permissions, uname=uname, gname=gname)
    
    def checkFile(self, filepath, description, access=None, fail=False, permissions=None, uname=None, gname=None):
        if not os.path.exists(filepath):
            raise ConfigurationError("%s does not exist: %s" % (description, filepath,))
        elif not os.path.isfile(filepath):
            raise ConfigurationError("%s is not a file: %s" % (description, filepath,))
        elif access and not os.access(filepath, access):
            raise ConfigurationError("Insufficient permissions for server on %s directory: %s" % (description, filepath,))
        self.securityCheck(filepath, description, fail=fail, permissions=permissions, uname=uname, gname=gname)

    def securityCheck(self, path, description, fail=False, permissions=None, uname=None, gname=None):
        def raiseOrPrint(txt):
            if fail:
                raise ConfigurationError(txt)
            else:
                log.msg("WARNING: %s" % (txt,))

        pathstat = os.stat(path)
        if permissions:
            if stat.S_IMODE(pathstat[stat.ST_MODE]) != permissions:
                raiseOrPrint("The permisions on %s directory %s are 0%03o and do not match expected permissions: 0%03o"
                             % (description, path, stat.S_IMODE(pathstat[stat.ST_MODE]), permissions))
        if uname:
            import pwd
            try:
                pathuname = pwd.getpwuid(pathstat[stat.ST_UID])[0]
                if pathuname not in (uname, "_" + uname):
                    raiseOrPrint("The owner of %s directory %s is %s and does not match the expected owner: %s"
                                 % (description, path, pathuname, uname))
            except KeyError:
                raiseOrPrint("The owner of %s directory %s is unknown (%s) and does not match the expected owner: %s"
                             % (description, path, pathstat[stat.ST_UID], uname))
                    
        if gname:
            import grp
            try:
                pathgname = grp.getgrgid(pathstat[stat.ST_GID])[0]
                if pathgname != gname:
                    raiseOrPrint("The group of %s directory %s is %s and does not match the expected group: %s"
                                 % (description, path, pathgname, gname))
            except KeyError:
                raiseOrPrint("The group of %s directory %s is unknown (%s) and does not match the expected group: %s"
                             % (description, path, pathstat[stat.ST_GID], gname))
                    

class CalDAVServiceMaker(object):
    implements(IPlugin, service.IServiceMaker)

    tapname = "caldav"

    description = "The Darwin Calendar Server"

    options = CalDAVOptions

    #
    # default resource classes
    #

    rootResourceClass      = RootResource
    principalResourceClass = DirectoryPrincipalProvisioningResource
    calendarResourceClass  = CalendarHomeProvisioningFile

    def makeService_Slave(self, options):
        #
        # Setup the Directory
        #
        directories = []
        
        directoryClass = namedClass(config.DirectoryService['type'])
        
        log.msg("Configuring directory service of type: %s"
                % (config.DirectoryService['type'],))
        
        baseDirectory = directoryClass(**config.DirectoryService['params'])

        directories.append(baseDirectory)

        sudoDirectory = None

        if config.SudoersFile and os.path.exists(config.SudoersFile):
            log.msg("Configuring SudoDirectoryService with file: %s"
                    % (config.SudoersFile,))
                
            sudoDirectory = SudoDirectoryService(config.SudoersFile)
            sudoDirectory.realmName = baseDirectory.realmName

            CalDAVResource.sudoDirectory = sudoDirectory
            directories.append(sudoDirectory)
        else:
            log.msg("Not using SudoDirectoryService; file doesn't exist: %s"
                    % (config.SudoersFile,))

        directory = AggregateDirectoryService(directories)

        if sudoDirectory:
            directory.userRecordTypes.append(
                SudoDirectoryService.recordType_sudoers)

        #
        # Setup Resource hierarchy
        #

        log.msg("Setting up document root at: %s" % (config.DocumentRoot,))
        
        log.msg("Setting up principal collection: %r" % (self.principalResourceClass,))

        principalCollection = self.principalResourceClass(
            os.path.join(config.DocumentRoot, 'principals'),
            '/principals/',
            directory
        )

        log.msg("Setting up calendar collection: %r" % (self.calendarResourceClass,))

        calendarCollection = self.calendarResourceClass(
            os.path.join(config.DocumentRoot, 'calendars'),
            directory,
            '/calendars/'
        )
        
        log.msg("Setting up root resource: %r" % (self.rootResourceClass,))
        
        root = self.rootResourceClass(
            config.DocumentRoot, 
            principalCollections=(principalCollection,)
        )

        root.putChild('principals', principalCollection)
        root.putChild('calendars', calendarCollection)

        # Configure default ACLs on the root resource

        log.msg("Setting up default ACEs on root resource")

        rootACEs = [
            davxml.ACE(
                davxml.Principal(davxml.All()),
                davxml.Grant(davxml.Privilege(davxml.Read())),
            ),
        ]
        
        log.msg("Setting up AdminPrincipals")

        for principal in config.AdminPrincipals:
            log.msg("Added %s as admin principal" % (principal,))
            
            rootACEs.append(
                davxml.ACE(
                    davxml.Principal(davxml.HRef(principal)),
                    davxml.Grant(davxml.Privilege(davxml.All())),
                    davxml.Protected(),
                    TwistedACLInheritable(),
                )
            )

        log.msg("Setting root ACL")

        root.setAccessControlList(davxml.ACL(*rootACEs))

        #
        # Configure the Site and Wrappers
        #

        credentialFactories = []

        portal = Portal(auth.DavRealm())

        portal.registerChecker(directory)

        realm = directory.realmName or ""

        log.msg("Configuring authentication for realm: %s" % (realm,))

        for scheme, schemeConfig in config.Authentication.iteritems():
            scheme = scheme.lower()

            credFactory = None
            
            if schemeConfig['Enabled']:
                log.msg("Setting up scheme: %s" % (scheme,))
                
                if scheme == 'kerberos':
                    if not NegotiateCredentialFactory:
                        log.msg("Kerberos support not available")
                        continue

                    service = schemeConfig['ServicePrincipal']

                    if '@' in service:
                        rest, kerbRealm = service.split('@', 1)
                    else:
                        kerbRealm = config.ServerHostName
                        
                    credFactory = NegotiateCredentialFactory(
                        service,
                        kerbRealm
                    )

                elif scheme == 'digest':
                    credFactory = QopDigestCredentialFactory(
                        schemeConfig['Algorithm'],
                        schemeConfig['Qop'],
                        realm
                    )

                elif scheme == 'basic':
                    credFactory = BasicCredentialFactory(realm)

                else:
                    log.err("Unknown scheme: %s" % (scheme,))

            if credFactory:
                credentialFactories.append(credFactory)

        log.msg("Configuring authentication wrapper")

        authWrapper = auth.AuthenticationWrapper(
            root,
            portal,
            credentialFactories,
            (auth.IPrincipal,)
        )

        site = Site(LogWrapperResource(authWrapper))

        #
        # Configure the service
        # 

        log.msg("Setting up service")

        channel = http.HTTPFactory(site)

        log.msg("Configuring log observer: %s" % (
            config.ControlSocket,))

        logObserver = logging.AMPCommonAccessLoggingObserver(
            config.ControlSocket)

        service = CalDAVService(logObserver)

        if not config.BindAddresses:
            config.BindAddresses = [""]

        for bindAddress in config.BindAddresses:
            if config.BindHTTPPorts:
                if config.HTTPPort == -1:
                    raise UsageError("HTTPPort required if BindHTTPPorts is not empty")
            elif config.HTTPPort != -1:
                    config.BindHTTPPorts = [config.HTTPPort]

            if config.BindSSLPorts:
                if config.SSLPort == -1:
                    raise UsageError("SSLPort required if BindSSLPorts is not empty")
            elif config.SSLPort != -1:
                config.BindSSLPorts = [config.SSLPort]

            if config.BindSSLPorts:
                from twisted.internet.ssl import DefaultOpenSSLContextFactory

            for port in config.BindHTTPPorts:
                log.msg("Adding server at %s:%s" % (bindAddress, port))
                
                httpService = internet.TCPServer(int(port), channel, interface=bindAddress)
                httpService.setServiceParent(service)

            for port in config.BindSSLPorts:
                log.msg("Adding SSL server at %s:%s" % (bindAddress, port))
            
                httpsService = internet.SSLServer(
                    int(port), channel,
                    DefaultOpenSSLContextFactory(config.SSLPrivateKey, config.SSLCertificate),
                    interface=bindAddress
                )
                httpsService.setServiceParent(service)

        return service

    makeService_Combined = makeService_Combined
    makeService_Master   = makeService_Master

    def makeService(self, options):
        serverType = config.ProcessType

        serviceMethod = getattr(self, "makeService_%s" % (serverType,), None)

        if not serviceMethod:
            raise UsageError("Unknown server type %s.  Please choose: Master, Slave or Combined"
                             % (serverType,))
        else:
            service = serviceMethod(options)           
            
            # Temporary hack to work around SIGHUP problem
            # If there is a stopped process in the same session as the calendar server
            # and the calendar server is the group leader then when twistd forks to drop
            # privelages a SIGHUP may be sent by the kernel. This SIGHUP should be ignored.
            # Note that this handler is not unset, so any further SIGHUPs are also ignored.
            import signal
            def sighup_handler(num, frame):
                if frame is None:
                    location = "Unknown"
                else:
                    location = str(frame.f_code.co_name) + ": " + str(frame.f_lineno)
                log.msg("SIGHUP recieved at " + location)
            signal.signal(signal.SIGHUP, sighup_handler)

            return service

