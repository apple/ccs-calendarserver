##
# Copyright (c) 2005-2008 Apple Inc. All rights reserved.
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
import sys

from tempfile import mkstemp
from subprocess import Popen, PIPE
from pwd import getpwnam
from grp import getgrnam
from OpenSSL.SSL import Error as SSLError

from zope.interface import implements

from twisted.python.log import FileLogObserver
from twisted.python.usage import Options, UsageError
from twisted.python.reflect import namedClass
from twisted.plugin import IPlugin
from twisted.internet.reactor import callLater
from twisted.internet.process import ProcessExitedAlready
from twisted.internet.address import IPv4Address
from twisted.application.internet import TCPServer, SSLServer, UNIXServer
from twisted.application.service import Service, MultiService, IServiceMaker
from twisted.scripts.mktap import getid
from twisted.runner import procmon
from twisted.cred.portal import Portal
from twisted.web2.dav import auth
from twisted.web2.auth.basic import BasicCredentialFactory
from twisted.web2.server import Site

from twext.internet.ssl import ChainingOpenSSLContextFactory

from twistedcaldav.log import Logger, LoggingMixIn
from twistedcaldav.log import logLevelForNamespace, setLogLevelForNamespace
from twistedcaldav.accesslog import DirectoryLogWrapperResource
from twistedcaldav.accesslog import RotatingFileAccessLoggingObserver
from twistedcaldav.accesslog import AMPLoggingFactory
from twistedcaldav.accesslog import AMPCommonAccessLoggingObserver
from twistedcaldav.config import config, defaultConfig, defaultConfigFile
from twistedcaldav.config import ConfigurationError
from twistedcaldav.root import RootResource
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.directory.digest import QopDigestCredentialFactory
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory.aggregate import AggregateDirectoryService
from twistedcaldav.directory.sudo import SudoDirectoryService
from twistedcaldav.directory.wiki import WikiDirectoryService
from twistedcaldav.httpfactory import HTTP503LoggingFactory
from twistedcaldav.static import CalendarHomeProvisioningFile
from twistedcaldav.static import IScheduleInboxFile
from twistedcaldav.static import TimezoneServiceFile
from twistedcaldav.mail import IMIPInboxResource
from twistedcaldav.timezones import TimezoneCache
from twistedcaldav.upgrade import UpgradeTheServer
from twistedcaldav.pdmonster import PDClientAddressWrapper
from twistedcaldav import memcachepool
from twistedcaldav.notify import installNotificationClient
from twistedcaldav.util import getNCPU

try:
    from twistedcaldav.authkerb import NegotiateCredentialFactory
except ImportError:
    NegotiateCredentialFactory = None

log = Logger()


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
        "config", "f", defaultConfigFile, "Path to configuration file."
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
                defaultConfig,
                path.split("/"),
                value,
                self.overrides
            )
        else:
            self.opt_option("%s=True" % (option,))

    opt_o = opt_option

    def postOptions(self):
        if not os.path.exists(self["config"]):
            self.log_info("Config file %s not found, using defaults"
                          % (self["config"],))

        self.log_info("Reading configuration from file: %s"
                      % (self["config"],))
        config.loadConfig(self["config"])

        config.updateDefaults(self.overrides)

        uid, gid = None, None

        if self.parent["uid"] or self.parent["gid"]:
            uid, gid = getid(self.parent["uid"], self.parent["gid"])

        def gottaBeRoot():
            if os.getuid() != 0:
                import pwd
                username = pwd.getpwuid(os.getuid())[0]
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
                uid = getpwnam(username)[2]
            else:
                uid = -1

            if groupname:
                gid = getgrnam(groupname)[2]
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


class CalDAVServiceMaker (LoggingMixIn):
    implements(IPlugin, IServiceMaker)

    tapname = "caldav"
    description = "The Darwin Calendar Server"
    options = CalDAVOptions

    #
    # Default resource classes
    #
    rootResourceClass            = RootResource
    principalResourceClass       = DirectoryPrincipalProvisioningResource
    calendarResourceClass        = CalendarHomeProvisioningFile
    iScheduleResourceClass       = IScheduleInboxFile
    imipResourceClass            = IMIPInboxResource
    timezoneServiceResourceClass = TimezoneServiceFile

    def makeService(self, options):

        # Now do any on disk upgrades we might need.
        UpgradeTheServer.doUpgrade()

        serviceMethod = getattr(self, "makeService_%s" % (config.ProcessType,), None)

        if not serviceMethod:
            raise UsageError(
                "Unknown server type %s. "
                "Please choose: Master, Slave, Single or Combined"
                % (config.ProcessType,)
            )
        else:
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
                config.reload()

                # If combined service send signal to all caldavd children
                if config.ProcessType == "Combined":
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

        baseDirectory = directoryClass(**config.DirectoryService.params)

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
        # Configure Memcached Client Pool
        #
        if config.Memcached.ClientEnabled:
            memcachepool.installPool(
                IPv4Address(
                    "TCP",
                    config.Memcached.BindAddress,
                    config.Memcached.Port,
                ),
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

        # Timezone service is optional
        if config.EnableTimezoneService:
            self.log_info("Setting up time zone service resource: %r"
                          % (self.timezoneServiceResourceClass,))

            timezoneService = self.timezoneServiceResourceClass(
                os.path.join(config.DocumentRoot, "timezones"),
                root,
            )
            root.putChild("timezones", timezoneService)

        # iSchedule service is optional
        if config.Scheduling.iSchedule.Enabled:
            self.log_info("Setting up iSchedule inbox resource: %r"
                          % (self.iScheduleResourceClass,))
    
            ischedule = self.iScheduleResourceClass(
                os.path.join(config.DocumentRoot, "ischedule"),
                root,
            )
            root.putChild("ischedule", ischedule)

        #
        # IMIP delivery resource
        #
        self.log_info("Setting up iMIP inbox resource: %r"
                      % (self.imipResourceClass,))

        imipInbox = self.imipResourceClass(root)
        root.putChild("inbox", imipInbox)

        #
        # Configure ancillary data
        #
        self.log_info("Setting up Timezone Cache")
        TimezoneCache.create()

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
                                type="http",
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

                else:
                    self.log_error("Unknown scheme: %s" % (scheme,))

            if credFactory:
                credentialFactories.append(credFactory)

        self.log_info("Configuring authentication wrapper")

        authWrapper = auth.AuthenticationWrapper(
            root,
            portal,
            credentialFactories,
            (auth.IPrincipal,),
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
            if (
                config.MultiProcess.ProcessCount > 1 and
                config.MultiProcess.LoadBalancer.Enabled
            ):
                realRoot = PDClientAddressWrapper(
                    logWrapper,
                    config.PythonDirector.ControlSocket,
                    directory,
                )
            else:
                realRoot = logWrapper

            logObserver = AMPCommonAccessLoggingObserver(
                config.ControlSocket,
            )

        elif config.ProcessType == "Single":
            realRoot = logWrapper

            logObserver = RotatingFileAccessLoggingObserver(
                config.AccessLogFile,
            )

        self.log_info("Configuring log observer: %s" % (logObserver,))

        service = CalDAVService(logObserver)

        site = Site(realRoot)

        channel = HTTP503LoggingFactory(
            site,
            maxRequests=config.MaxRequests,
            betweenRequestsTimeOut=config.IdleConnectionTimeOut,
        )

        def updateChannel(config, items):
            channel.maxRequests = config.MaxRequests

        config.addHook(updateChannel)

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

            for port in config.BindHTTPPorts:
                self.log_info("Adding server at %s:%s" % (bindAddress, port))

                httpService = TCPServer(
                    int(port), channel,
                    interface=bindAddress,
                    backlog=config.ListenBacklog,
                )
                httpService.setServiceParent(service)

            for port in config.BindSSLPorts:
                self.log_info("Adding SSL server at %s:%s"
                              % (bindAddress, port))

                try:
                    contextFactory = ChainingOpenSSLContextFactory(
                        config.SSLPrivateKey,
                        config.SSLCertificate,
                        certificateChainFile=config.SSLAuthorityChain,
                        passwdCallback=getSSLPassphrase,
                    )
                except SSLError, e:
                    self.log_error("Unable to set up SSL context factory: %s"
                                   % (e,))
                    self.log_error("Disabling SSL port: %s" % (port,))
                else:
                    httpsService = SSLServer(
                        int(port), channel,
                        contextFactory, interface=bindAddress,
                        backlog=config.ListenBacklog,
                    )
                    httpsService.setServiceParent(service)

        # Change log level back to what it was before
        setLogLevelForNamespace(None, oldLogLevel)

        return service

    makeService_Single   = makeService_Slave

    def makeService_Combined(self, options):
        s = MultiService()
        monitor = DelayedStartupProcessMonitor()
        monitor.setServiceParent(s)
        s.processMonitor = monitor

        parentEnv = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        }

        hosts = []
        sslHosts = []

        port = [config.HTTPPort,]
        sslPort = [config.SSLPort,]

        bindAddress = ["127.0.0.1"]

        #
        # Attempt to calculate the number of processes to use 1 per processor
        #
        if config.MultiProcess.ProcessCount == 0:
            try:
                cpuCount = getNCPU()
            except NotImplementedError, e:
                error = str(e)
            else:
                if cpuCount > 0:
                    error = None
                else:
                    error = (
                        "No processors detected, "
                        "which is difficult to believe."
                    )

            if error is None:
                self.log_info("%d processors found, configuring %d processes."
                              % (cpuCount, cpuCount))
            else:
                self.log_error("Could not autodetect number of CPUs: %s"
                               % (error,))
                self.log_error("Assuming one CPU, configuring one process.")
                cpuCount = 1

            config.MultiProcess.ProcessCount = cpuCount

        if config.MultiProcess.ProcessCount > 1:
            if config.BindHTTPPorts:
                port = [list(reversed(config.BindHTTPPorts))[0]]

            if config.BindSSLPorts:
                sslPort = [list(reversed(config.BindSSLPorts))[0]]

        elif config.MultiProcess.ProcessCount == 1:
            if config.BindHTTPPorts:
                port = config.BindHTTPPorts

            if config.BindSSLPorts:
                sslPort = config.BindSSLPorts

        if port[0] == 0:
            port = None

        if sslPort[0] == 0:
            sslPort = None

        # If the load balancer isn"t enabled, or if we only have one process
        # We listen directly on the interfaces.

        if (
            not config.MultiProcess.LoadBalancer.Enabled or
            config.MultiProcess.ProcessCount == 1
        ):
            bindAddress = config.BindAddresses

        for p in xrange(0, config.MultiProcess.ProcessCount):
            if config.MultiProcess.ProcessCount > 1:
                if port is not None:
                    port = [port[0] + 1]

                if sslPort is not None:
                    sslPort = [sslPort[0] + 1]

            process = TwistdSlaveProcess(
                config.Twisted.twistd,
                self.tapname,
                options["config"],
                bindAddress,
                port,
                sslPort
            )

            monitor.addProcess(
                process.getName(),
                process.getCommandLine(),
                env=parentEnv
            )

            if config.HTTPPort:
                hosts.append(process.getHostLine())

            if config.SSLPort:
                sslHosts.append(process.getHostLine(ssl=True))

        #
        # Set up pydirector config file.
        #
        if (config.MultiProcess.LoadBalancer.Enabled and
            config.MultiProcess.ProcessCount > 1):
            services = []

            if not config.BindAddresses:
                config.BindAddresses = [""]

            scheduler_map = {
                "LeastConnections": "leastconns",
                "RoundRobin": "roundrobin",
                "LeastConnectionsAndRoundRobin": "leastconnsrr",
            }

            for bindAddress in config.BindAddresses:
                httpListeners = []
                sslListeners = []

                httpPorts = config.BindHTTPPorts
                if not httpPorts:
                    if config.HTTPPort != 0:
                        httpPorts = (config.HTTPPort,)

                sslPorts = config.BindSSLPorts
                if not sslPorts:
                    if config.SSLPort != 0:
                        sslPorts = (config.SSLPort,)

                for ports, listeners in (
                    (httpPorts, httpListeners),
                    (sslPorts, sslListeners)
                ):
                    for port in ports:
                        listeners.append(
                            """<listen ip="%s:%s" />""" % (bindAddress, port)
                        )

                scheduler = config.MultiProcess.LoadBalancer.Scheduler

                pydirServiceTemplate = (
                    """<service name="%(name)s">"""
                    """%(listeningInterfaces)s"""
                    """<group name="main" scheduler="%(scheduler)s">"""
                    """%(hosts)s"""
                    """</group>"""
                    """<enable group="main" />"""
                    """</service>"""
                )

                if httpPorts:
                    services.append(
                        pydirServiceTemplate % {
                            "name": "http",
                            "listeningInterfaces": "\n".join(httpListeners),
                            "scheduler": scheduler_map[scheduler],
                            "hosts": "\n".join(hosts)
                        }
                    )

                if sslPorts:
                    services.append(
                        pydirServiceTemplate % {
                            "name": "https",
                            "listeningInterfaces": "\n".join(sslListeners),
                            "scheduler": scheduler_map[scheduler],
                            "hosts": "\n".join(sslHosts),
                        }
                    )

            pdconfig = """<pdconfig>%s<control socket="%s" /></pdconfig>""" % (
                "\n".join(services), config.PythonDirector.ControlSocket,
            )

            fd, fname = mkstemp(prefix="pydir")
            os.write(fd, pdconfig)
            os.close(fd)

            self.log_info("Adding pydirector service with configuration: %s"
                          % (fname,))

            monitor.addProcess(
                "pydir",
                [sys.executable, config.PythonDirector.pydir, fname],
                env=parentEnv,
            )

        if config.Memcached.ServerEnabled:
            self.log_info("Adding memcached service")

            memcachedArgv = [
                config.Memcached.memcached,
                "-p", str(config.Memcached.Port),
                "-l", config.Memcached.BindAddress,
            ]

            if config.Memcached.MaxMemory is not 0:
                memcachedArgv.extend(["-m", str(config.Memcached.MaxMemory)])

            if config.UserName:
                memcachedArgv.extend(["-u", config.UserName])

            memcachedArgv.extend(config.Memcached.Options)

            monitor.addProcess("memcached", memcachedArgv, env=parentEnv)

        if (
            config.Notifications.Enabled and
            config.Notifications.InternalNotificationHost == "localhost"
        ):
            self.log_info("Adding notification service")

            notificationsArgv = [
                sys.executable,
                config.Twisted.twistd,
                "-n", "caldav_notifier",
                "-f", options["config"],
            ]
            monitor.addProcess(
                "notifications",
                notificationsArgv,
                env=parentEnv,
            )

        if (
            config.Scheduling.iMIP.Enabled and
            config.Scheduling.iMIP.MailGatewayServer == "localhost"
        ):
            self.log_info("Adding mail gateway service")

            mailGatewayArgv = [
                sys.executable,
                config.Twisted.twistd,
                "-n", "caldav_mailgateway",
                "-f", options["config"],
            ]
            monitor.addProcess("mailgateway", mailGatewayArgv, env=parentEnv)


        logger = AMPLoggingFactory(
            RotatingFileAccessLoggingObserver(config.AccessLogFile)
        )

        loggingService = UNIXServer(config.ControlSocket, logger)

        loggingService.setServiceParent(s)

        return s

    def makeService_Master(self, options):
        service = procmon.ProcessMonitor()

        parentEnv = {"PYTHONPATH": os.environ.get("PYTHONPATH", "")}

        self.log_info("Adding pydirector service with configuration: %s"
                      % (config.PythonDirector.ConfigFile,))

        service.addProcess(
            "pydir",
            [
                sys.executable,
                config.PythonDirector.pydir,
                config.PythonDirector.ConfigFile
            ],
            env=parentEnv
        )

        return service


class TwistdSlaveProcess(object):
    prefix = "caldav"

    def __init__(self, twistd, tapname, configFile, interfaces, port, sslPort):
        self.twistd = twistd

        self.tapname = tapname

        self.configFile = configFile

        self.ports = port
        self.sslPorts = sslPort

        self.interfaces = interfaces

    def getName(self):
        if self.ports is not None:
            return "%s-%s" % (self.prefix, self.ports[0])
        elif self.sslPorts is not None:
            return "%s-%s" % (self.prefix, self.sslPorts[0])

        raise ConfigurationError(
            "Can't create TwistdSlaveProcess without a TCP Port"
        )

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
            "-o", "MultiProcess/ProcessCount=%d"
                  % (config.MultiProcess.ProcessCount,)
        ])

        if config.Memcached.ServerEnabled:
            args.extend(["-o", "Memcached/ClientEnabled=True"])

        if self.ports:
            args.extend([
                "-o", "BindHTTPPorts=%s" % (",".join(map(str, self.ports)),)
            ])

        if self.sslPorts:
            args.extend([
                "-o", "BindSSLPorts=%s" % (",".join(map(str, self.sslPorts)),)
            ])

        return args

    def getHostLine(self, ssl=False):
        name = self.getName()
        port = None

        if self.ports is not None:
            port = self.ports

        if ssl and self.sslPorts is not None:
            port = self.sslPorts

        if port is None:
            raise ConfigurationError("Can not add a host without a port")

        return """<host name="%s" ip="127.0.0.1:%s" />""" % (name, port[0])


class DelayedStartupProcessMonitor(procmon.ProcessMonitor):
    def startService(self):
        Service.startService(self)
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
