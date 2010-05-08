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
from time import time

from subprocess import Popen, PIPE
from pwd import getpwnam, getpwuid
from grp import getgrnam
from OpenSSL.SSL import Error as SSLError
import OpenSSL

from zope.interface import implements

from twisted.python.log import FileLogObserver, ILogObserver
from twisted.python.logfile import LogFile
from twisted.python.usage import Options, UsageError
from twisted.python.reflect import namedClass
from twisted.plugin import IPlugin
from twisted.internet.defer import Deferred, gatherResults
from twisted.internet import error, reactor
from twisted.internet.reactor import callLater, addSystemEventTrigger
from twisted.internet.process import ProcessExitedAlready
from twisted.internet.protocol import Protocol, Factory
from twisted.application.internet import TCPServer, UNIXServer
from twisted.application.service import Service, MultiService, IServiceMaker
from twisted.scripts.mktap import getid
from twisted.runner import procmon
from twext.web2.server import Site

from twext.python.log import Logger, LoggingMixIn
from twext.python.log import logLevelForNamespace, setLogLevelForNamespace
from twext.internet.ssl import ChainingOpenSSLContextFactory
from twext.internet.tcp import MaxAcceptTCPServer, MaxAcceptSSLServer

from twext.web2.channel.http import LimitingHTTPFactory, SSLRedirectRequest

try:
    from twistedcaldav.version import version
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "support"))
    from version import version as getVersion
    version = "%s (%s)" % getVersion()

from twistedcaldav.config import ConfigurationError
from twistedcaldav.config import config
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory import calendaruserproxy
from twistedcaldav.directory.calendaruserproxyloader import XMLCalendarUserProxyLoader
from twistedcaldav.localization import processLocalizationFiles
from twistedcaldav.mail import IMIPReplyInboxResource
from twistedcaldav.static import CalendarHomeProvisioningFile
from twistedcaldav.static import IScheduleInboxFile
from twistedcaldav.static import TimezoneServiceFile
from twistedcaldav.stdconfig import DEFAULT_CONFIG, DEFAULT_CONFIG_FILE
from twistedcaldav.upgrade import upgradeData
from twistedcaldav.util import getNCPU

from twext.web2.metafd import ConnectionLimiter, ReportingHTTPService

try:
    from twistedcaldav.authkerb import NegotiateCredentialFactory
    NegotiateCredentialFactory  # pacify pyflakes
except ImportError:
    NegotiateCredentialFactory = None

from calendarserver.accesslog import AMPCommonAccessLoggingObserver
from calendarserver.accesslog import AMPLoggingFactory
from calendarserver.accesslog import RotatingFileAccessLoggingObserver
from calendarserver.provision.root import RootResource
from calendarserver.webadmin.resource import WebAdminResource
from calendarserver.webcal.resource import WebCalendarResource
from calendarserver.tap.util import getRootResource

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


class ErrorLoggingMultiService(MultiService):
    """ Registers a rotating file logger for error logging, iff
        config.ErrorLogEnabled is True. """

    def setServiceParent(self, app):
        MultiService.setServiceParent(self, app)

        if config.ErrorLogEnabled:
            errorLogFile = LogFile.fromFullPath(
                config.ErrorLogFile,
                rotateLength=config.ErrorLogRotateMB * 1024 * 1024,
                maxRotatedFiles=config.ErrorLogMaxRotatedFiles
            )
            errorLogObserver = FileLogObserver(errorLogFile).emit

            # Registering ILogObserver with the Application object
            # gets our observer picked up within AppLogger.start( )
            app.setComponent(ILogObserver, errorLogObserver)


class CalDAVService (ErrorLoggingMultiService):
    def __init__(self, logObserver):
        self.logObserver = logObserver # accesslog observer
        MultiService.__init__(self)

    def privilegedStartService(self):
        MultiService.privilegedStartService(self)
        self.logObserver.start()

    def stopService(self):
        d = MultiService.stopService(self)
        self.logObserver.stop()
        return d


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

        self.parent["pidfile"] = config.PIDFile


        #
        # Verify that server root actually exists
        #
        self.checkDirectory(
            config.ServerRoot,
            "Server root",
            # Require write access because one might not allow editing on /
            access=os.W_OK,
            create=(0750, config.UserName, config.GroupName),
        )
        
        #
        # Verify that other root paths are OK
        #
        if config.DocumentRoot.startswith(config.ServerRoot + os.sep):
            self.checkDirectory(
                config.DocumentRoot,
                "Document root",
                # Don't require write access because one might not allow editing on /
                access=os.R_OK,
                create=(0750, config.UserName, config.GroupName),
            )
        if config.DataRoot.startswith(config.ServerRoot + os.sep):
            self.checkDirectory(
                config.DataRoot,
                "Data root",
                access=os.W_OK,
                create=(0750, config.UserName, config.GroupName),
            )

        if config.ConfigRoot.startswith(config.ServerRoot + os.sep):
            self.checkDirectory(
                config.ConfigRoot,
                "Config root",
                access=os.W_OK,
                create=(0750, config.UserName, config.GroupName),
            )

        if config.LogRoot.startswith(config.ServerRoot + os.sep):
            self.checkDirectory(
                config.LogRoot,
                "Log root",
                access=os.W_OK,
                create=(0750, config.UserName, config.GroupName),
            )

        if config.RunRoot.startswith(config.ServerRoot + os.sep):
            self.checkDirectory(
                config.RunRoot,
                "Run root",
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

                # Memcached is not needed for the "master" process
                if config.ProcessType in ('Combined',):
                    config.Memcached.Pools.Default.ClientEnabled = False

                # Note: if the master process ever needs access to memcached
                # we'll either have to start memcached prior to the
                # updateProxyDB call below, or disable memcached
                # client config only while updateProxyDB is running.

                # Process localization string files
                processLocalizationFiles(config.Localization)

                # Now do any on disk upgrades we might need.
                upgradeData(config)

                # Make sure proxies get initialized
                if config.ProxyLoadFromFile:
                    def _doProxyUpdate():
                        proxydbClass = namedClass(config.ProxyDBService.type)
                        calendaruserproxy.ProxyDBService = proxydbClass(**config.ProxyDBService.params)
                        loader = XMLCalendarUserProxyLoader(config.ProxyLoadFromFile)
                        return loader.updateProxyDB()
                    addSystemEventTrigger("after", "startup", _doProxyUpdate)



            try:
                service = serviceMethod(options)
            except ConfigurationError, e:
                sys.stderr.write("Configuration error: %s\n" % (e,))
                sys.exit(1)

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


    def createContextFactory(self):
        """
        Create an SSL context factory for use with any SSL socket talking to
        this server.
        """
        return ChainingOpenSSLContextFactory(
            config.SSLPrivateKey,
            config.SSLCertificate,
            certificateChainFile=config.SSLAuthorityChain,
            passwdCallback=getSSLPassphrase,
            sslmethod=getattr(OpenSSL.SSL, config.SSLMethod),
            ciphers=config.SSLCiphers.strip()
        )


    def makeService_Slave(self, options):
        #
        # Change default log level to "info" as its useful to have
        # that during startup
        #
        oldLogLevel = logLevelForNamespace(None)
        setLogLevelForNamespace(None, "info")

        additional = []
        if config.Scheduling.iMIP.Enabled:
            additional.append(("inbox", IMIPReplyInboxResource, [], "basic"))
        rootResource = getRootResource(config, additional)

        #
        # Configure the service
        #
        self.log_info("Setting up service")

        if config.ProcessType == "Slave":
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

            logObserver = RotatingFileAccessLoggingObserver(
                config.AccessLogFile,
            )

        self.log_info("Configuring access log observer: %s" % (logObserver,))

        service = CalDAVService(logObserver)

        site = Site(rootResource)

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

        config.addPostUpdateHooks((updateFactory,))

        if config.InheritFDs or config.InheritSSLFDs:
            # Inherit sockets to call accept() on them individually.

            for fd in config.InheritSSLFDs:
                fd = int(fd)

                try:
                    contextFactory = self.createContextFactory()
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

        elif config.MetaFD:
            # Inherit a single socket to receive accept()ed connections via
            # recvmsg() and SCM_RIGHTS.

            fd = int(config.MetaFD)

            try:
                contextFactory = self.createContextFactory()
            except SSLError, e:
                self.log_error("Unable to set up SSL context factory: %s" % (e,))
                # None is okay as a context factory for ReportingHTTPService as
                # long as we will never receive a file descriptor with the
                # 'SSL' tag on it, since that's the only time it's used.
                contextFactory = None

            ReportingHTTPService(
                site, fd, contextFactory
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
                        contextFactory = self.createContextFactory()
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
        s = ErrorLoggingMultiService()

        # Make sure no old socket files are lying around.
        self.deleteStaleSocketFiles()

        # The logger service must come before the monitor service, otherwise
        # we won't know which logging port to pass to the slaves' command lines

        logger = AMPLoggingFactory(
            RotatingFileAccessLoggingObserver(config.AccessLogFile)
        )
        if config.GroupName:
            try:
                gid = getgrnam(config.GroupName).gr_gid
            except KeyError, e:
                raise ConfigurationError("Invalid group name: %s" % (config.GroupName,))
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

        if config.UseMetaFD:
            cl = ConnectionLimiter(config.MaxAccepts,
                                   (config.MaxRequests *
                                    config.MultiProcess.ProcessCount))
            cl.setServiceParent(s)
        else:
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

            if config.UseMetaFD:
                for ports, description in [(config.BindSSLPorts, "SSL"),
                                           (config.BindHTTPPorts, "TCP")]:
                    for port in ports:
                        cl.addPortService(description, port, bindAddress, config.ListenBacklog)
            else:
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
            if config.UseMetaFD:
                extraArgs = dict(metaSocket=cl.dispatcher.addSocket())
            else:
                extraArgs = dict(inheritFDs=inheritFDs,
                                 inheritSSLFDs=inheritSSLFDs)
            process = TwistdSlaveProcess(
                sys.argv[0],
                self.tapname,
                options["config"],
                p,
                config.BindAddresses,
                **extraArgs
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
                if config.UserName:
                    memcachedArgv.extend(["-u", config.UserName])
        
                memcachedArgv.extend(config.Memcached.Options)
        
                monitor.addProcess('memcached-%s' % (name,), memcachedArgv, env=parentEnv)

        if (
            config.Notifications.Enabled and
            config.Notifications.InternalNotificationHost == "localhost"
        ):
            self.log_info("Adding notification service")

            notificationsArgv = [
                sys.executable,
                sys.argv[0],
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
                sys.argv[0],
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
            sys.argv[0],
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
            gid, config.GlobalStatsSocket, stats, mode=0440
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
    """
    A L{TwistdSlaveProcess} is information about how to start a slave process
    running a C{twistd} plugin, to be used by
    L{DelayedStartupProcessMonitor.addProcessObject}.

    @ivar inheritFDs: File descriptors to be inherited for calling accept() on
        in the subprocess.
    @type inheritFDs: C{list} of C{int}, or C{None}

    @ivar inheritSSLFDs: File descriptors to be inherited for calling accept()
        on in the subprocess, and speaking TLS on the resulting sockets.
    @type inheritSSLFDs: C{list} of C{int}, or C{None}

    @ivar metaSocket: an AF_UNIX/SOCK_DGRAM socket (initialized from the
        dispatcher passed to C{__init__}) that is to be inherited by the
        subprocess and used to accept incoming connections.

    @type metaSocket: L{socket.socket}
    """
    prefix = "caldav"

    def __init__(self, twistd, tapname, configFile, id, interfaces,
                 inheritFDs=None, inheritSSLFDs=None, metaSocket=None):

        self.twistd = twistd

        self.tapname = tapname

        self.configFile = configFile

        self.id = id
        def emptyIfNone(x):
            if x is None:
                return []
            else:
                return x
        self.inheritFDs = emptyIfNone(inheritFDs)
        self.inheritSSLFDs = emptyIfNone(inheritSSLFDs)
        self.metaSocket = metaSocket
        self.interfaces = interfaces

    def getName(self):
        return '%s-%s' % (self.prefix, self.id)


    def getFileDescriptors(self):
        """
        @return: a mapping of file descriptor numbers for the new (child)
            process to file descriptor numbers in the current (master) process.
        """
        fds = {}
        maybeMetaFD = []
        if self.metaSocket is not None:
            maybeMetaFD.append(self.metaSocket.fileno())
        for fd in self.inheritSSLFDs + self.inheritFDs + maybeMetaFD:
            fds[fd] = fd
        return fds


    def getCommandLine(self):
        """
        @return: a list of command-line arguments, including the executable to
            be used to start this subprocess.

        @rtype: C{list} of C{str}
        """
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
            "-o", "ErrorLogEnabled=False",
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

        if self.metaSocket is not None:
            args.extend([
                    "-o", "MetaFD=%s" % (self.metaSocket.fileno(),)
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
    """
    A L{DelayedStartupProcessMonitor} is a L{procmon.ProcessMonitor} that
    defers building its command lines until the service is actually ready to
    start.  It also specializes process-starting to allow for process objects
    to determine their arguments as they are started up rather than entirely
    ahead of time.

    @ivar processObjects: a C{list} of L{TwistdSlaveProcess} to add using
        C{self.addProcess} when this service starts up.

    @ivar _extraFDs: a mapping from process names to extra file-descriptor
        maps.  (By default, all processes will have the standard stdio mapping,
        so all file descriptors here should be >2.)  This is updated during
        L{DelayedStartupProcessMonitor.startService}, by inspecting the result
        of L{TwistdSlaveProcess.getFileDescriptors}.

    @ivar reactor: an L{IReactorProcess} for spawning processes, defaulting to
        the global reactor.
    """

    def __init__(self, *args, **kwargs):
        procmon.ProcessMonitor.__init__(self, *args, **kwargs)
        self.processObjects = []
        self._extraFDs = {}
        from twisted.internet import reactor
        self.reactor = reactor
        self.stopping = False


    def addProcessObject(self, process, env):
        """
        Add a process object to be run when this service is started.

        @param env: a dictionary of environment variables.

        @param process: a L{TwistdSlaveProcesses} object to be started upon
            service startup.
        """
        self.processObjects.append((process, env))


    def startService(self):
        Service.startService(self)

        # Now we're ready to build the command lines and actualy add the
        # processes to procmon.  This step must be done prior to setting
        # active to 1
        for processObject, env in self.processObjects:
            name = processObject.getName()
            self.addProcess(
                name,
                processObject.getCommandLine(),
                env=env
            )
            self._extraFDs[name] = processObject.getFileDescriptors()

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

    def stopService(self):
        """
        Return a deferred that fires when all child processes have ended
        """

        Service.stopService(self)

        self.stopping = True
        self.active = 0
        self.consistency.cancel()

        self.deferreds = { }
        for name in self.processes.keys():
            self.deferreds[name] = Deferred()
            self.stopProcess(name)

        return gatherResults(self.deferreds.values())

    def processEnded(self, name):
        """
        When a child process has ended it calls me so I can fire the
        appropriate deferred which was created in stopService
        """

        if self.stopping:
            deferred = self.deferreds.get(name, None)
            if deferred is not None:
                deferred.callback(None)


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
        p = self.protocols[name] = DelayedStartupLoggingProtocol()
        p.service = self
        p.name = name
        args, uid, gid, env = self.processes[name]
        self.timeStarted[name] = time()

        childFDs = { 0 : "w", 1 : "r", 2 : "r" }

        childFDs.update(self._extraFDs.get(name, {}))

        self.reactor.spawnProcess(
            p, args[0], args, uid=uid, gid=gid, env=env,
            childFDs=childFDs
        )

    def _forceStopProcess(self, proc, name):
        """
        After self.killTime seconds has passed, this method sends a KILL
        to the process.  Clean up the now-called murder deferred.
        """
        try:
            # This deferred has fired so remove it to keep from trying to
            # cancel it later
            del self.murder[name]
        except KeyError:
            pass
        try:
            proc.signalProcess('KILL')
        except error.ProcessExitedAlready:
            pass


    def stopProcess(self, name):
        """
        Stop the process gently at first (TERM), but schedule a KILL for
        self.killTime seconds later.
        """

        if not self.protocols.has_key(name):
            return
        proc = self.protocols[name].transport
        del self.protocols[name]
        try:
            proc.signalProcess('TERM')
        except error.ProcessExitedAlready:
            pass
        else:
            self.murder[name] = reactor.callLater(self.killTime, self._forceStopProcess, proc, name)




class DelayedStartupLineLogger(object):
    """
    A line logger that can handle very long lines.
    """

    MAX_LENGTH = 1024
    tag = None
    exceeded = False            # Am I in the middle of parsing a long line?
    _buffer = ''

    def makeConnection(self, transport):
        """
        Ignore this IProtocol method, since I don't need a transport.
        """


    def dataReceived(self, data):
        lines = (self._buffer + data).split("\n")
        while len(lines) > 1:
            line = lines.pop(0)
            if len(line) > self.MAX_LENGTH:
                self.lineLengthExceeded(line)
            elif self.exceeded:
                self.lineLengthExceeded(line)
                self.exceeded = False
            else:
                self.lineReceived(line)
        lastLine = lines.pop(0)
        if len(lastLine) > self.MAX_LENGTH:
            self.lineLengthExceeded(lastLine)
            self.exceeded = True
            self._buffer = ''
        else:
            self._buffer = lastLine


    def lineReceived(self, line):
        from twisted.python.log import msg
        msg('[%s] %s' % (self.tag, line))


    def lineLengthExceeded(self, line):
        """
        A very long line is being received.  Log it immediately and forget
        about buffering it.
        """
        for i in range(len(line)/self.MAX_LENGTH):
            self.lineReceived(line[i*self.MAX_LENGTH:(i+1)*self.MAX_LENGTH]
                              + " (truncated, continued)")



class DelayedStartupLoggingProtocol(procmon.LoggingProtocol, object):
    """
    Logging protocol that handles lines which are too long.
    """

    def connectionMade(self):
        """
        Replace the superclass's output monitoring logic with one that can
        handle lineLengthExceeded.
        """
        super(DelayedStartupLoggingProtocol, self).connectionMade()
        self.output = DelayedStartupLineLogger()
        self.output.tag = self.name

    def processEnded(self, reason):
        """
        Let the service know that this child process has ended
        """
        procmon.LoggingProtocol.processEnded(self, reason)
        self.service.processEnded(self.name)


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
