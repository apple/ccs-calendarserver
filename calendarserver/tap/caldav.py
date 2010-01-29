# -*- test-case-name: calendarserver.tap.test.test_caldav -*-
##
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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

__all__ = [
    "CalDAVService",
    "CalDAVOptions",
    "CalDAVServiceMaker",
]

import os
import socket
import stat
import sys
from time import sleep, time

from subprocess import Popen, PIPE
from pwd import getpwnam, getpwuid
from grp import getgrnam
from OpenSSL.SSL import Error as SSLError
import OpenSSL

from zope.interface import implements

from twisted.python.log import FileLogObserver
from twisted.python.usage import Options, UsageError
from twisted.python.reflect import namedClass
from twisted.plugin import IPlugin
from twisted.internet import reactor
from twisted.internet.reactor import callLater, spawnProcess
from twisted.internet.process import ProcessExitedAlready
from twisted.internet.protocol import Protocol, Factory
from twisted.application.internet import TCPServer, UNIXServer
from twisted.application.service import Service, MultiService, IServiceMaker
from twisted.scripts.mktap import getid
from twisted.runner import procmon
from twisted.cred.portal import Portal
from twisted.web2.dav import auth
from twisted.web2.auth.basic import BasicCredentialFactory
from twisted.web2.server import Site
from twisted.web2.static import File as FileResource

from twext.log import Logger, LoggingMixIn
from twext.log import logLevelForNamespace, setLogLevelForNamespace
from twext.internet.ssl import ChainingOpenSSLContextFactory
from twext.internet.tcp import MaxAcceptTCPServer, MaxAcceptSSLServer
from twext.web2.channel.http import LimitingHTTPFactory, SSLRedirectRequest

try:
    from twistedcaldav.version import version
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "support"))
    from version import version as getVersion
    version = "%s (%s)" % getVersion()

from twistedcaldav import memcachepool
from twistedcaldav.accesslog import AMPCommonAccessLoggingObserver
from twistedcaldav.accesslog import AMPLoggingFactory
from twistedcaldav.accesslog import DirectoryLogWrapperResource
from twistedcaldav.accesslog import RotatingFileAccessLoggingObserver
from twistedcaldav.config import ConfigurationError
from twistedcaldav.config import config
from twistedcaldav.directory import augment, calendaruserproxy
from twistedcaldav.directory.aggregate import AggregateDirectoryService
from twistedcaldav.directory.calendaruserproxyloader import XMLCalendarUserProxyLoader
from twistedcaldav.directory.digest import QopDigestCredentialFactory
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory.sudo import SudoDirectoryService
from twistedcaldav.directory.util import NotFilePath
from twistedcaldav.directory.wiki import WikiDirectoryService
from twistedcaldav.localization import processLocalizationFiles
from twistedcaldav.mail import IMIPReplyInboxResource
from twistedcaldav.notify import installNotificationClient
from twistedcaldav.resource import CalDAVResource, AuthenticationWrapper
from twistedcaldav.static import CalendarHomeProvisioningFile
from twistedcaldav.static import IScheduleInboxFile
from twistedcaldav.static import TimezoneServiceFile
from twistedcaldav.stdconfig import DEFAULT_CONFIG, DEFAULT_CONFIG_FILE
from twistedcaldav.timezones import TimezoneCache
from twistedcaldav.upgrade import upgradeData
from twistedcaldav.util import getNCPU

try:
    from twistedcaldav.authkerb import NegotiateCredentialFactory
    NegotiateCredentialFactory  # pacify pyflakes
except ImportError:
    NegotiateCredentialFactory = None

from calendarserver.provision.root import RootResource
from calendarserver.webadmin.resource import WebAdminResource
from calendarserver.webcal.resource import WebCalendarResource

log = Logger()


class CalDAVStatisticsProtocol (Protocol): 

    def connectionMade(self): 
        stats = self.factory.logger.observer.getGlobalHits() 
        self.transport.write("%s\r\n" % (stats,)) 
        self.transport.loseConnection() 

class CalDAVStatisticsServer (Factory): 

    protocol = CalDAVStatisticsProtocol 

    def __init__(self, logObserver): 
        self.logger = logObserver 

class CalDAVService (MultiService):
    def __init__(self, logObserver):
        self.logObserver = logObserver
        MultiService.__init__(self)

    def privilegedStartService(self):
        MultiService.privilegedStartService(self)
        self.logObserver.start()

    def stopService(self):
        MultiService.stopService(self)
        self.logObserver.stop()


class CalDAVOptions (Options, LoggingMixIn):
    optParameters = [[
        "config", "f", DEFAULT_CONFIG_FILE, "Path to configuration file."
    ]]

    zsh_actions = {"config" : "_files -g '*.plist'"}

    def __init__(self, *args, **kwargs):
        super(CalDAVOptions, self).__init__(*args, **kwargs)

        self.overrides = {}

    @staticmethod
    def coerceOption(configDict, key, value):
        """
        Coerce the given C{val} to type of C{configDict[key]}
        """
        if key in configDict:
            if isinstance(configDict[key], bool):
                value = value == "True"

            elif isinstance(configDict[key], (int, float, long)):
                value = type(configDict[key])(value)

            elif isinstance(configDict[key], (list, tuple)):
                value = value.split(",")

            elif isinstance(configDict[key], dict):
                raise UsageError(
                    "Dict options not supported on the command line"
                )

            elif value == "None":
                value = None

        return value

    @classmethod
    def setOverride(cls, configDict, path, value, overrideDict):
        """
        Set the value at path in configDict
        """
        key = path[0]

        if len(path) == 1:
            overrideDict[key] = cls.coerceOption(configDict, key, value)
            return

        if key in configDict:
            if not isinstance(configDict[key], dict):
                raise UsageError(
                    "Found intermediate path element that is not a dictionary"
                )

            if key not in overrideDict:
                overrideDict[key] = {}

            cls.setOverride(
                configDict[key], path[1:],
                value, overrideDict[key]
            )

    def opt_option(self, option):
        """
        Set an option to override a value in the config file. True, False, int,
        and float options are supported, as well as comma seperated lists. Only
        one option may be given for each --option flag, however multiple
        --option flags may be specified.
        """
        if "=" in option:
            path, value = option.split("=")
            self.setOverride(
                DEFAULT_CONFIG,
                path.split("/"),
                value,
                self.overrides
            )
        else:
            self.opt_option("%s=True" % (option,))

    opt_o = opt_option

    def postOptions(self):
        self.loadConfiguration()
        self.checkConfiguration()
            
    def loadConfiguration(self):
        if not os.path.exists(self["config"]):
            self.log_info("Config file %s not found, using defaults"
                          % (self["config"],))

        self.log_info("Reading configuration from file: %s"
                      % (self["config"],))

        try:
            config.load(self["config"])
        except ConfigurationError, e:
            log.err("Invalid configuration: %s" % (e,))
            sys.exit(1)

        config.updateDefaults(self.overrides)
        
    def checkConfiguration(self):
        uid, gid = None, None

        if self.parent["uid"] or self.parent["gid"]:
            uid, gid = getid(self.parent["uid"], self.parent["gid"])

        def gottaBeRoot():
            if os.getuid() != 0:
                username = getpwuid(os.getuid()).pw_name
                raise UsageError("Only root can drop privileges.  You are: %r"
                                 % (username,))

        if uid and uid != os.getuid():
            gottaBeRoot()

        if gid and gid != os.getgid():
            gottaBeRoot()

        #
        # Ignore the logfile parameter if not daemonized and log to stdout.
        #
        if self.parent["nodaemon"]:
            self.parent["logfile"] = None
        else:
            self.parent["logfile"] = config.ErrorLogFile

        self.parent["pidfile"] = config.PIDFile

        #
        # Verify that document root, data root actually exist
        #
        self.checkDirectory(
            config.DocumentRoot,
            "Document root",
            # Don't require write access because one might not allow editing on /
            access=os.R_OK,
            create=(0750, config.UserName, config.GroupName),
        )
        self.checkDirectory(
            config.DataRoot,
            "Data root",
            access=os.W_OK,
            create=(0750, config.UserName, config.GroupName),
        )

        #
        # Nuke the file log observer's time format.
        #

        if not config.ErrorLogFile and config.ProcessType == "Slave":
            FileLogObserver.timeFormat = ""

        # Check current umask and warn if changed
        oldmask = os.umask(config.umask)
        if oldmask != config.umask:
            self.log_info("WARNING: changing umask from: 0%03o to 0%03o"
                          % (oldmask, config.umask))

    def checkDirectory(self, dirpath, description, access=None, create=None):
        if not os.path.exists(dirpath):
            try:
                mode, username, groupname = create
            except TypeError:
                raise ConfigurationError("%s does not exist: %s"
                                         % (description, dirpath))
            try:
                os.mkdir(dirpath)
            except (OSError, IOError), e:
                self.log_error("Could not create %s: %s" % (dirpath, e))
                raise ConfigurationError(
                    "%s does not exist and cannot be created: %s"
                    % (description, dirpath)
                )

            if username:
                uid = getpwnam(username).pw_uid
            else:
                uid = -1

            if groupname:
                gid = getgrnam(groupname).gr_gid
            else:
                gid = -1

            try:
                os.chmod(dirpath, mode)
                os.chown(dirpath, uid, gid)
            except (OSError, IOError), e:
                self.log_error("Unable to change mode/owner of %s: %s"
                               % (dirpath, e))

            self.log_info("Created directory: %s" % (dirpath,))

        if not os.path.isdir(dirpath):
            raise ConfigurationError("%s is not a directory: %s"
                                     % (description, dirpath))

        if access and not os.access(dirpath, access):
            raise ConfigurationError(
                "Insufficient permissions for server on %s directory: %s"
                % (description, dirpath)
            )



class GroupOwnedUNIXServer(UNIXServer, object):
    """
    A L{GroupOwnedUNIXServer} is a L{UNIXServer} which changes the group
    ownership of its socket immediately after binding its port.

    @ivar gid: the group ID which should own the socket after it is bound.
    """
    def __init__(self, gid, *args, **kw):
        super(GroupOwnedUNIXServer, self).__init__(*args, **kw)
        self.gid = gid


    def privilegedStartService(self):
        """
        Bind the UNIX socket and then change its group.
        """
        super(GroupOwnedUNIXServer, self).privilegedStartService()
        fileName = self._port.port # Unfortunately, there's no public way to
                                   # access this. -glyph
        os.chown(fileName, os.getuid(), self.gid)



class CalDAVServiceMaker (LoggingMixIn):
    implements(IPlugin, IServiceMaker)

    tapname = "caldav"
    description = "Darwin Calendar Server"
    options = CalDAVOptions

    #
    # Default resource classes
    #
    rootResourceClass            = RootResource
    principalResourceClass       = DirectoryPrincipalProvisioningResource
    calendarResourceClass        = CalendarHomeProvisioningFile
    iScheduleResourceClass       = IScheduleInboxFile
    imipResourceClass            = IMIPReplyInboxResource
    timezoneServiceResourceClass = TimezoneServiceFile
    webCalendarResourceClass     = WebCalendarResource
    webAdminResourceClass        = WebAdminResource
    
    #
    # Default tap names
    #
    mailGatewayTapName = "caldav_mailgateway"
    notifierTapName = "caldav_notifier"


    def makeService(self, options):
        self.log_info("%s %s starting %s process..." % (self.description, version, config.ProcessType))

        serviceMethod = getattr(self, "makeService_%s" % (config.ProcessType,), None)

        if not serviceMethod:
            raise UsageError(
                "Unknown server type %s. "
                "Please choose: Slave, Single or Combined"
                % (config.ProcessType,)
            )
        else:

            if config.ProcessType in ('Combined', 'Single'):

                # Process localization string files
                processLocalizationFiles(config.Localization)

                # Now do any on disk upgrades we might need.
                # Memcache isn't running at this point, so temporarily change
                # the config so nobody tries to talk to it while upgrading
                memcacheSetting = config.Memcached.Pools.Default.ClientEnabled
                config.Memcached.Pools.Default.ClientEnabled = False
                upgradeData(config)
                config.Memcached.Pools.Default.ClientEnabled = memcacheSetting


            service = serviceMethod(options)

            #
            # Note: if there is a stopped process in the same session
            # as the calendar server and the calendar server is the
            # group leader then when twistd forks to drop privileges a
            # SIGHUP may be sent by the kernel, which can cause the
            # process to exit. This SIGHUP should be, at a minimum,
            # ignored.
            #

            def location(frame):
                if frame is None:
                    return "Unknown"
                else:
                    return "%s: %s" % (frame.f_code.co_name, frame.f_lineno)

            import signal
            def sighup_handler(num, frame):
                self.log_info("SIGHUP recieved at %s" % (location(frame),))

                # Reload the config file
                try:
                    config.reload()
                except ConfigurationError, e:
                    self.log_error("Invalid configuration: {0}".format(e))

                # If combined service send signal to all caldavd children
                if hasattr(service, "processMonitor"):
                    service.processMonitor.signalAll(signal.SIGHUP, "caldav")

                # FIXME: There is no memcachepool.getCachePool
                #   Also, better option is probably to add a hook to
                #   the config object instead of doing things here.
                #self.log_info("Suggesting new max clients for memcache.")
                #memcachepool.getCachePool().suggestMaxClients(
                #    config.Memcached.MaxClients
                #)

            signal.signal(signal.SIGHUP, sighup_handler)

            return service


    def makeService_Slave(self, options):
        #
        # Change default log level to "info" as its useful to have
        # that during startup
        #
        oldLogLevel = logLevelForNamespace(None)
        setLogLevelForNamespace(None, "info")

        #
        # Setup the Directory
        #
        directories = []

        directoryClass = namedClass(config.DirectoryService.type)

        self.log_info("Configuring directory service of type: %s"
                      % (config.DirectoryService.type,))

        baseDirectory = directoryClass(config.DirectoryService.params)

        # Wait for the directory to become available
        while not baseDirectory.isAvailable():
            sleep(5)

        directories.append(baseDirectory)

        sudoDirectory = None

        if config.SudoersFile and os.path.exists(config.SudoersFile):
            self.log_info("Configuring SudoDirectoryService with file: %s"
                          % (config.SudoersFile,))

            sudoDirectory = SudoDirectoryService(config.SudoersFile)
            sudoDirectory.realmName = baseDirectory.realmName

            CalDAVResource.sudoDirectory = sudoDirectory
            directories.insert(0, sudoDirectory)
        else:
            self.log_info(
                "Not using SudoDirectoryService; file doesn't exist: %s"
                % (config.SudoersFile,)
            )

        #
        # Add wiki directory service
        #
        if config.Authentication.Wiki.Enabled:
            wikiDirectory = WikiDirectoryService()
            wikiDirectory.realmName = baseDirectory.realmName
            directories.append(wikiDirectory)

        directory = AggregateDirectoryService(directories)

        if sudoDirectory:
            directory.userRecordTypes.insert(0,
                SudoDirectoryService.recordType_sudoers)

        #
        # Setup the Augment Service
        #
        augmentClass = namedClass(config.AugmentService.type)

        self.log_info("Configuring augment service of type: %s" % (augmentClass,))

        try:
            augment.AugmentService = augmentClass(**config.AugmentService.params)
        except IOError, e:
            self.log_error("Could not start augment service")
            raise

        #
        # Setup the PoxyDB Service
        #
        proxydbClass = namedClass(config.ProxyDBService.type)

        self.log_info("Configuring proxydb service of type: %s" % (proxydbClass,))

        try:
            calendaruserproxy.ProxyDBService = proxydbClass(**config.ProxyDBService.params)
        except IOError, e:
            self.log_error("Could not start proxydb service")
            raise

        #
        # Make sure proxies get initialized
        #
        if config.ProxyLoadFromFile:
            def _doProxyUpdate():
                loader = XMLCalendarUserProxyLoader(config.ProxyLoadFromFile)
                return loader.updateProxyDB()
            
            reactor.addSystemEventTrigger("after", "startup", _doProxyUpdate)

        #
        # Configure Memcached Client Pool
        #
        memcachepool.installPools(
            config.Memcached.Pools,
            config.Memcached.MaxClients,
        )

        #
        # Configure NotificationClient
        #
        if config.Notifications.Enabled:
            installNotificationClient(
                config.Notifications.InternalNotificationHost,
                config.Notifications.InternalNotificationPort,
            )

        #
        # Configure the Site and Wrappers
        #
        credentialFactories = []

        portal = Portal(auth.DavRealm())

        portal.registerChecker(directory)

        realm = directory.realmName or ""

        self.log_info("Configuring authentication for realm: %s" % (realm,))

        for scheme, schemeConfig in config.Authentication.iteritems():
            scheme = scheme.lower()

            credFactory = None

            if schemeConfig["Enabled"]:
                self.log_info("Setting up scheme: %s" % (scheme,))

                if scheme == "kerberos":
                    if not NegotiateCredentialFactory:
                        self.log_info("Kerberos support not available")
                        continue

                    try:
                        principal = schemeConfig["ServicePrincipal"]
                        if not principal:
                            credFactory = NegotiateCredentialFactory(
                                type="HTTP",
                                hostname=config.ServerHostName,
                            )
                        else:
                            credFactory = NegotiateCredentialFactory(
                                principal=principal,
                            )
                    except ValueError:
                        self.log_info("Could not start Kerberos")
                        continue

                elif scheme == "digest":
                    credFactory = QopDigestCredentialFactory(
                        schemeConfig["Algorithm"],
                        schemeConfig["Qop"],
                        realm,
                    )

                elif scheme == "basic":
                    credFactory = BasicCredentialFactory(realm)

                elif scheme == "wiki":
                    pass

                else:
                    self.log_error("Unknown scheme: %s" % (scheme,))

            if credFactory:
                credentialFactories.append(credFactory)


        # Set up a digest credential factory for use on the /inbox iMIP
        # injection resource
        schemeConfig = config.Authentication.Digest
        digestCredentialFactory = QopDigestCredentialFactory(
            schemeConfig["Algorithm"],
            schemeConfig["Qop"],
            realm,
        )

        #
        # Setup Resource hierarchy
        #
        self.log_info("Setting up document root at: %s"
                      % (config.DocumentRoot,))
        self.log_info("Setting up principal collection: %r"
                      % (self.principalResourceClass,))

        principalCollection = self.principalResourceClass(
            "/principals/",
            directory,
        )

        self.log_info("Setting up calendar collection: %r"
                      % (self.calendarResourceClass,))

        calendarCollection = self.calendarResourceClass(
            os.path.join(config.DocumentRoot, "calendars"),
            directory, "/calendars/",
        )

        self.log_info("Setting up root resource: %r"
                      % (self.rootResourceClass,))

        root = self.rootResourceClass(
            config.DocumentRoot,
            principalCollections=(principalCollection,),
        )

        root.putChild("principals", principalCollection)
        root.putChild("calendars", calendarCollection)

        for name, info in config.Aliases.iteritems():
            if os.path.sep in name or not info.get("path", None):
                self.log_error("Invalid alias: %s" % (name,))
                continue
            self.log_info("Adding alias %s -> %s" % (name, info["path"]))
            resource = FileResource(info["path"])
            root.putChild(name, resource)

        # Timezone service is optional
        if config.EnableTimezoneService:
            self.log_info("Setting up time zone service resource: %r"
                          % (self.timezoneServiceResourceClass,))

            timezoneService = self.timezoneServiceResourceClass(
                NotFilePath(isfile=True),
                root,
            )
            root.putChild("timezones", timezoneService)

        # iSchedule service is optional
        if config.Scheduling.iSchedule.Enabled:
            self.log_info("Setting up iSchedule inbox resource: %r"
                          % (self.iScheduleResourceClass,))

            ischedule = self.iScheduleResourceClass(
                NotFilePath(isfile=True),
                root,
            )
            root.putChild("ischedule", ischedule)

        #
        # IMIP delivery resource
        #
        if config.Scheduling.iMIP.Enabled:
            self.log_info("Setting up iMIP inbox resource: %r"
                          % (self.imipResourceClass,))

            # The authenticationWrapper below will be configured to always
            # allow digest auth on /inbox
            root.putChild("inbox", self.imipResourceClass(root))

        #
        # WebCal
        #
        if config.WebCalendarRoot:
            self.log_info("Setting up WebCalendar resource: %s"
                          % (config.WebCalendarRoot,))
            webCalendar = self.webCalendarResourceClass(
                config.WebCalendarRoot,
                principalCollections=(principalCollection,),
            )
            root.putChild("webcal", webCalendar)

        #
        # WebAdmin
        #
        if config.EnableWebAdmin:
            self.log_info("Setting up WebAdmin resource")
            webAdmin = self.webAdminResourceClass(
                config.WebCalendarRoot,
                root,
                directory,
                principalCollections=(principalCollection,),
            )
            root.putChild("admin", webAdmin)

        #
        # Configure ancillary data
        #
        self.log_info("Setting up Timezone Cache")
        TimezoneCache.create()



        self.log_info("Configuring authentication wrapper")

        authWrapper = AuthenticationWrapper(
            root,
            portal,
            credentialFactories,
            (auth.IPrincipal,),
            overrides = {
                "/inbox" : (digestCredentialFactory,),
            }
        )

        logWrapper = DirectoryLogWrapperResource(
            authWrapper,
            directory,
        )

        #
        # Configure the service
        #
        self.log_info("Setting up service")

        if config.ProcessType == "Slave":
            realRoot = logWrapper

            if config.ControlSocket:
                mode = "AF_UNIX"
                id = config.ControlSocket
                self.log_info("Logging via AF_UNIX: %s" % (id,))
            else:
                mode = "IF_INET"
                id = int(config.ControlPort)
                self.log_info("Logging via AF_INET: %d" % (id,))

            logObserver = AMPCommonAccessLoggingObserver(mode, id)

        elif config.ProcessType == "Single":
            # Make sure no old socket files are lying around.
            self.deleteStaleSocketFiles()

            realRoot = logWrapper

            logObserver = RotatingFileAccessLoggingObserver(
                config.AccessLogFile,
            )

        self.log_info("Configuring log observer: %s" % (logObserver,))

        service = CalDAVService(logObserver)

        site = Site(realRoot)

        httpFactory = LimitingHTTPFactory(
            site,
            maxRequests=config.MaxRequests,
            maxAccepts=config.MaxAccepts,
            betweenRequestsTimeOut=config.IdleConnectionTimeOut,
            vary=True,
        )
        if config.RedirectHTTPToHTTPS:
            redirectFactory = LimitingHTTPFactory(
                SSLRedirectRequest,
                maxRequests=config.MaxRequests,
                maxAccepts=config.MaxAccepts,
                betweenRequestsTimeOut=config.IdleConnectionTimeOut,
                vary=True,
            )

        def updateFactory(configDict):
            httpFactory.maxRequests = configDict.MaxRequests
            httpFactory.maxAccepts = configDict.MaxAccepts
            if config.RedirectHTTPToHTTPS:
                redirectFactory.maxRequests = configDict.MaxRequests
                redirectFactory.maxAccepts = configDict.MaxAccepts

        config.addPostUpdateHook(updateFactory)

        if config.InheritFDs or config.InheritSSLFDs:

            for fd in config.InheritSSLFDs:
                fd = int(fd)

                try:
                    contextFactory = ChainingOpenSSLContextFactory(
                        config.SSLPrivateKey,
                        config.SSLCertificate,
                        certificateChainFile=config.SSLAuthorityChain,
                        passwdCallback=getSSLPassphrase,
                        sslmethod=getattr(OpenSSL.SSL, config.SSLMethod),
                    )
                except SSLError, e:
                    log.error("Unable to set up SSL context factory: %s" % (e,))
                else:
                    MaxAcceptSSLServer(
                        fd, httpFactory,
                        contextFactory,
                        backlog=config.ListenBacklog,
                        inherit=True
                    ).setServiceParent(service)

            for fd in config.InheritFDs:
                fd = int(fd)

                if config.RedirectHTTPToHTTPS:
                    self.log_info("Redirecting to HTTPS port %s" % (config.SSLPort,))
                    useFactory = redirectFactory
                else:
                    useFactory = httpFactory

                MaxAcceptTCPServer(
                    fd, useFactory,
                    backlog=config.ListenBacklog,
                    inherit=True
                ).setServiceParent(service)


        else: # Not inheriting, therefore we open our own:

            if not config.BindAddresses:
                config.BindAddresses = [""]

            for bindAddress in config.BindAddresses:
                if config.BindHTTPPorts:
                    if config.HTTPPort == 0:
                        raise UsageError(
                            "HTTPPort required if BindHTTPPorts is not empty"
                        )
                elif config.HTTPPort != 0:
                        config.BindHTTPPorts = [config.HTTPPort]

                if config.BindSSLPorts:
                    if config.SSLPort == 0:
                        raise UsageError(
                            "SSLPort required if BindSSLPorts is not empty"
                        )
                elif config.SSLPort != 0:
                    config.BindSSLPorts = [config.SSLPort]

                for port in config.BindSSLPorts:
                    self.log_info("Adding SSL server at %s:%s"
                                  % (bindAddress, port))

                    try:
                        contextFactory = ChainingOpenSSLContextFactory(
                            config.SSLPrivateKey,
                            config.SSLCertificate,
                            certificateChainFile=config.SSLAuthorityChain,
                            passwdCallback=getSSLPassphrase,
                            sslmethod=getattr(OpenSSL.SSL, config.SSLMethod),
                        )
                    except SSLError, e:
                        self.log_error("Unable to set up SSL context factory: %s"
                                       % (e,))
                        self.log_error("Disabling SSL port: %s" % (port,))
                    else:
                        httpsService = MaxAcceptSSLServer(
                            int(port), httpFactory,
                            contextFactory, interface=bindAddress,
                            backlog=config.ListenBacklog,
                            inherit=False
                        )
                        httpsService.setServiceParent(service)

                for port in config.BindHTTPPorts:

                    if config.RedirectHTTPToHTTPS:
                        #
                        # Redirect non-SSL ports to the configured SSL port.
                        #
                        self.log_info("Redirecting HTTP port %s to HTTPS port %s"
                            % (port, config.SSLPort)
                        )
                        useFactory = redirectFactory
                    else:
                        self.log_info(
                            "Adding server at %s:%s"
                            % (bindAddress, port)
                        )
                        useFactory = httpFactory

                    MaxAcceptTCPServer(
                        int(port), useFactory,
                        interface=bindAddress,
                        backlog=config.ListenBacklog,
                        inherit=False
                    ).setServiceParent(service)


        # Change log level back to what it was before
        setLogLevelForNamespace(None, oldLogLevel)

        return service

    makeService_Single   = makeService_Slave

    def makeService_Combined(self, options):
        s = MultiService()

        # Make sure no old socket files are lying around.
        self.deleteStaleSocketFiles()

        # The logger service must come before the monitor service, otherwise
        # we won't know which logging port to pass to the slaves' command lines

        logger = AMPLoggingFactory(
            RotatingFileAccessLoggingObserver(config.AccessLogFile)
        )
        if config.GroupName:
            gid = getgrnam(config.GroupName).gr_gid
        else:
            gid = os.getgid()
        if config.ControlSocket:
            loggingService = GroupOwnedUNIXServer(
                gid, config.ControlSocket, logger, mode=0660
            )
        else:
            loggingService = ControlPortTCPServer(
                config.ControlPort, logger, interface="127.0.0.1"
            )
        loggingService.setName("logging")
        loggingService.setServiceParent(s)

        monitor = DelayedStartupProcessMonitor()
        monitor.setServiceParent(s)
        s.processMonitor = monitor

        parentEnv = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH", ""),
            "DYLD_LIBRARY_PATH": os.environ.get("DYLD_LIBRARY_PATH", ""),
        }
        if "KRB5_KTNAME" in os.environ:
            parentEnv["KRB5_KTNAME"] = os.environ["KRB5_KTNAME"]

        #
        # Attempt to calculate the number of processes to use 1 per processor
        #
        if config.MultiProcess.ProcessCount == 0:
            try:
                cpuCount = getNCPU()
            except NotImplementedError, e:
                self.log_error("Unable to detect number of CPUs: %s"
                               % (str(e),))
                cpuCount = 0
            else:
                if cpuCount < 1:
                    self.log_error(
                        "%d processors detected, which is hard to believe."
                        % (cpuCount,)
                    )

            processCount = config.MultiProcess.MinProcessCount
            if 2 * cpuCount > processCount:
                processCount = 2 * cpuCount

            self.log_info("%d processors found. Configuring %d processes."
                          % (cpuCount, processCount))

            config.MultiProcess.ProcessCount = processCount


        # Open the socket(s) to be inherited by the slaves

        if not config.BindAddresses:
            config.BindAddresses = [""]

        inheritFDs = []
        inheritSSLFDs = []

        s._inheritedSockets = [] # keep a reference to these so they don't close

        for bindAddress in config.BindAddresses:
            if config.BindHTTPPorts:
                if config.HTTPPort == 0:
                    raise UsageError(
                        "HTTPPort required if BindHTTPPorts is not empty"
                    )
            elif config.HTTPPort != 0:
                config.BindHTTPPorts = [config.HTTPPort]

            if config.BindSSLPorts:
                if config.SSLPort == 0:
                    raise UsageError(
                        "SSLPort required if BindSSLPorts is not empty"
                    )
            elif config.SSLPort != 0:
                config.BindSSLPorts = [config.SSLPort]

            def _openSocket(addr, port):
                log.info("Opening socket for inheritance at %s:%d" % (addr, port))
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setblocking(0)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((addr, port))
                sock.listen(config.ListenBacklog)
                s._inheritedSockets.append(sock)
                return sock

            for portNum in config.BindHTTPPorts:
                sock = _openSocket(bindAddress, int(portNum))
                inheritFDs.append(sock.fileno())

            for portNum in config.BindSSLPorts:
                sock = _openSocket(bindAddress, int(portNum))
                inheritSSLFDs.append(sock.fileno())


        for p in xrange(0, config.MultiProcess.ProcessCount):
            process = TwistdSlaveProcess(
                config.Twisted.twistd,
                self.tapname,
                options["config"],
                p,
                config.BindAddresses,
                inheritFDs=inheritFDs,
                inheritSSLFDs=inheritSSLFDs
            )

            monitor.addProcessObject(process, parentEnv)



        for name, pool in config.Memcached.Pools.items():
            if pool.ServerEnabled:
                self.log_info("Adding memcached service for pool: %s" % (name,))
        
                memcachedArgv = [
                    config.Memcached.memcached,
                    "-p", str(pool.Port),
                    "-l", pool.BindAddress,
                    "-U", "0",
                ]
        
                if config.Memcached.MaxMemory is not 0:
                    memcachedArgv.extend(["-m", str(config.Memcached.MaxMemory)])
        
                memcachedArgv.extend(config.Memcached.Options)
        
                monitor.addProcess('memcached-%s' % (name,), memcachedArgv, env=parentEnv)

        if (
            config.Notifications.Enabled and
            config.Notifications.InternalNotificationHost == "localhost"
        ):
            self.log_info("Adding notification service")

            notificationsArgv = [
                sys.executable,
                config.Twisted.twistd,
            ]
            if config.UserName:
                notificationsArgv.extend(("-u", config.UserName))
            if config.GroupName:
                notificationsArgv.extend(("-g", config.GroupName))
            notificationsArgv.extend((
                "--reactor=%s" % (config.Twisted.reactor,),
                "-n", self.notifierTapName,
                "-f", options["config"],
            ))
            monitor.addProcess("notifications", notificationsArgv,
                env=parentEnv)

        if (
            config.Scheduling.iMIP.Enabled and
            config.Scheduling.iMIP.MailGatewayServer == "localhost"
        ):
            self.log_info("Adding mail gateway service")

            mailGatewayArgv = [
                sys.executable,
                config.Twisted.twistd,
            ]
            if config.UserName:
                mailGatewayArgv.extend(("-u", config.UserName))
            if config.GroupName:
                mailGatewayArgv.extend(("-g", config.GroupName))
            mailGatewayArgv.extend((
                "--reactor=%s" % (config.Twisted.reactor,),
                "-n", self.mailGatewayTapName,
                "-f", options["config"],
            ))

            monitor.addProcess("mailgateway", mailGatewayArgv, env=parentEnv)

        self.log_info("Adding task service")
        taskArgv = [
            sys.executable,
            config.Twisted.twistd,
        ]
        if config.UserName:
            taskArgv.extend(("-u", config.UserName))
        if config.GroupName:
            taskArgv.extend(("-g", config.GroupName))
        taskArgv.extend((
            "--reactor=%s" % (config.Twisted.reactor,),
            "-n", "caldav_task",
            "-f", options["config"],
        ))

        monitor.addProcess("caldav_task", taskArgv, env=parentEnv)


        stats = CalDAVStatisticsServer(logger) 
        statsService = GroupOwnedUNIXServer(
            gid, config.GlobalStatsSocket, stats, mode=0660
        )
        statsService.setName("stats")
        statsService.setServiceParent(s)

        return s


    def deleteStaleSocketFiles(self):
        
        # Check all socket files we use.
        for checkSocket in [config.ControlSocket, config.GlobalStatsSocket] :
    
            # See if the file exists.
            if (os.path.exists(checkSocket)):
                # See if the file represents a socket.  If not, delete it.
                if (not stat.S_ISSOCK(os.stat(checkSocket).st_mode)):
                    self.log_warn("Deleting stale socket file (not a socket): %s" % checkSocket)
                    os.remove(checkSocket)
                else:
                    # It looks like a socket.  See if it's accepting connections.
                    tmpSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    numConnectFailures = 0
                    testPorts = [config.HTTPPort, config.SSLPort]
                    for testPort in testPorts :
                        try:
                            tmpSocket.connect(("127.0.0.1", testPort))
                            tmpSocket.shutdown(2)
                        except:
                            numConnectFailures = numConnectFailures+1
                    # If the file didn't connect on any expected ports,
                    # consider it stale and remove it.
                    if numConnectFailures == len(testPorts):
                        self.log_warn("Deleting stale socket file (not accepting connections): %s" % checkSocket)
                        os.remove(checkSocket)



class TwistdSlaveProcess(object):
    prefix = "caldav"

    def __init__(self, twistd, tapname, configFile, id, interfaces,
            inheritFDs=None, inheritSSLFDs=None):

        self.twistd = twistd

        self.tapname = tapname

        self.configFile = configFile

        self.id = id

        self.inheritFDs = inheritFDs
        self.inheritSSLFDs = inheritSSLFDs

        self.interfaces = interfaces

    def getName(self):
        return '%s-%s' % (self.prefix, self.id)

    def getCommandLine(self):
        args = [sys.executable, self.twistd]

        if config.UserName:
            args.extend(("-u", config.UserName))

        if config.GroupName:
            args.extend(("-g", config.GroupName))

        if config.Profiling.Enabled:
            args.append(
                "--profile=%s/%s.pstats"
                % (config.Profiling.BaseDirectory, self.getName())
            )
            args.extend(("--savestats", "--nothotshot"))

        args.extend([
            "--reactor=%s" % (config.Twisted.reactor,),
            "-n", self.tapname,
            "-f", self.configFile,
            "-o", "ProcessType=Slave",
            "-o", "BindAddresses=%s" % (",".join(self.interfaces),),
            "-o", "PIDFile=None",
            "-o", "ErrorLogFile=None",
            "-o", "LogID=%s" % (self.id,),
            "-o", "MultiProcess/ProcessCount=%d"
                  % (config.MultiProcess.ProcessCount,),
            "-o", "ControlPort=%d"
                  % (config.ControlPort,),
        ])

        if self.inheritFDs:
            args.extend([
                "-o", "InheritFDs=%s" % (",".join(map(str, self.inheritFDs)),)
            ])

        if self.inheritSSLFDs:
            args.extend([
                "-o", "InheritSSLFDs=%s" % (",".join(map(str, self.inheritSSLFDs)),)
            ])

        return args


class ControlPortTCPServer(TCPServer):
    """ This TCPServer retrieves the port number that was actually assigned
        when the service was started, and stores that into config.ControlPort
    """

    def startService(self):
        TCPServer.startService(self)
        # Record the port we were actually assigned
        config.ControlPort = self._port.getHost().port

class DelayedStartupProcessMonitor(procmon.ProcessMonitor):

    def __init__(self, *args, **kwargs):
        procmon.ProcessMonitor.__init__(self, *args, **kwargs)

        # processObjects stores TwistdSlaveProcesses which need to have their
        # command-lines determined just in time
        self.processObjects = []

    def addProcessObject(self, process, env):
        self.processObjects.append((process, env))

    def startService(self):
        Service.startService(self)

        # Now we're ready to build the command lines and actualy add the
        # processes to procmon.  This step must be done prior to setting
        # active to 1
        for processObject, env in self.processObjects:
            self.addProcess(
                processObject.getName(),
                processObject.getCommandLine(),
                env=env
            )

        self.active = 1
        delay = 0

        if config.MultiProcess.StaggeredStartup.Enabled:
            delay_interval = config.MultiProcess.StaggeredStartup.Interval
        else:
            delay_interval = 0

        for name in self.processes.keys():
            if name.startswith("caldav"):
                when = delay
                delay += delay_interval
            else:
                when = 0
            callLater(when, self.startProcess, name)

        self.consistency = callLater(
            self.consistencyDelay,
            self._checkConsistency
        )

    def signalAll(self, signal, startswithname=None):
        """
        Send a signal to all child processes.

        @param signal: the signal to send
        @type signal: C{int}
        @param startswithname: is set only signal those processes
            whose name starts with this string
        @type signal: C{str}
        """
        for name in self.processes.keys():
            if startswithname is None or name.startswith(startswithname):
                self.signalProcess(signal, name)

    def signalProcess(self, signal, name):
        """
        Send a signal to each monitored process

        @param signal: the signal to send
        @type signal: C{int}
        @param startswithname: is set only signal those processes
            whose name starts with this string
        @type signal: C{str}
        """
        if not self.protocols.has_key(name):
            return
        proc = self.protocols[name].transport
        try:
            proc.signalProcess(signal)
        except ProcessExitedAlready:
            pass

    def startProcess(self, name):
        if self.protocols.has_key(name):
            return
        p = self.protocols[name] = procmon.LoggingProtocol()
        p.service = self
        p.name = name
        args, uid, gid, env = self.processes[name]
        self.timeStarted[name] = time()

        childFDs = { 0 : "w", 1 : "r", 2 : "r" }

        # Examine args for -o InheritFDs= and -o InheritSSLFDs=
        # Add any file descriptors listed in those args to the childFDs
        # dictionary so those don't get closed across the spawn.
        for i in xrange(len(args)-1):
            if args[i] == "-o" and args[i+1].startswith("Inherit"):
                for fd in map(int, args[i+1].split("=")[1].split(",")):
                    childFDs[fd] = fd

        spawnProcess(p, args[0], args, uid=uid, gid=gid, env=env,
            childFDs=childFDs)


def getSSLPassphrase(*ignored):

    if not config.SSLPrivateKey:
        return None

    if config.SSLCertAdmin and os.path.isfile(config.SSLCertAdmin):
        child = Popen(
            args=[
                "sudo", config.SSLCertAdmin,
                "--get-private-key-passphrase", config.SSLPrivateKey,
            ],
            stdout=PIPE, stderr=PIPE,
        )
        output, error = child.communicate()

        if child.returncode:
            log.error("Could not get passphrase for %s: %s"
                      % (config.SSLPrivateKey, error))
        else:
            return output.strip()

    if (
        config.SSLPassPhraseDialog and
        os.path.isfile(config.SSLPassPhraseDialog)
    ):
        sslPrivKey = open(config.SSLPrivateKey)
        try:
            keyType = None
            for line in sslPrivKey.readlines():
                if "-----BEGIN RSA PRIVATE KEY-----" in line:
                    keyType = "RSA"
                    break
                elif "-----BEGIN DSA PRIVATE KEY-----" in line:
                    keyType = "DSA"
                    break
        finally:
            sslPrivKey.close()

        if keyType is None:
            log.error("Could not get private key type for %s"
                      % (config.SSLPrivateKey,))
        else:
            child = Popen(
                args=[
                    config.SSLPassPhraseDialog,
                    "%s:%s" % (config.ServerHostName, config.SSLPort),
                    keyType,
                ],
                stdout=PIPE, stderr=PIPE,
            )
            output, error = child.communicate()

            if child.returncode:
                log.error("Could not get passphrase for %s: %s"
                          % (config.SSLPrivateKey, error))
            else:
                return output.strip()

    return None
