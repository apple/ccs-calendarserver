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

import os

from subprocess import Popen, PIPE
from pwd import getpwnam
from grp import getgrnam
from OpenSSL import SSL

from zope.interface import implements

from twisted.internet.ssl import DefaultOpenSSLContextFactory
from twisted.internet.address import IPv4Address
from twisted.python.log import FileLogObserver
from twisted.python.usage import Options, UsageError
from twisted.python.reflect import namedClass
from twisted.application import internet, service
from twisted.plugin import IPlugin
from twisted.scripts.mktap import getid
from twisted.cred.portal import Portal
from twisted.web2.dav import auth
from twisted.web2.auth.basic import BasicCredentialFactory
from twisted.web2.server import Site

from twistedcaldav.log import Logger, logLevelForNamespace, setLogLevelForNamespace
from twistedcaldav.accesslog import DirectoryLogWrapperResource
from twistedcaldav.accesslog import RotatingFileAccessLoggingObserver
from twistedcaldav.accesslog import AMPCommonAccessLoggingObserver
from twistedcaldav.cluster import makeService_Combined, makeService_Master
from twistedcaldav.config import config, parseConfig, defaultConfig, defaultConfigFile, ConfigurationError
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
from twistedcaldav import pdmonster
from twistedcaldav import memcachepool
from twistedcaldav.notify import installNotificationClient

log = Logger()

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
            log.info("Config file %s not found, using defaults"
                    % (self["config"],))

        log.info("Reading configuration from file: %s" % (self["config"],))
        parseConfig(self["config"])

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
            log.info("WARNING: changing umask from: 0%03o to 0%03o"
                     % (oldmask, config.umask,))

    def checkDirectory(self, dirpath, description, access=None, create=None):
        if not os.path.exists(dirpath):
            try:
                mode, username, groupname = create
            except TypeError:
                raise ConfigurationError("%s does not exist: %s"
                                         % (description, dirpath,))
            try:
                os.mkdir(dirpath)
            except (OSError, IOError), e:
                log.error("Could not create %s: %s" % (dirpath, e))
                raise ConfigurationError(
                    "%s does not exist and cannot be created: %s"
                    % (description, dirpath,)
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
                log.error("Unable to change mode/owner of %s: %s"
                          % (dirpath, e))

            log.info("Created directory: %s" % (dirpath,))

        if not os.path.isdir(dirpath):
            raise ConfigurationError("%s is not a directory: %s"
                                     % (description, dirpath,))

        if access and not os.access(dirpath, access):
            raise ConfigurationError(
                "Insufficient permissions for server on %s directory: %s"
                % (description, dirpath,)
            )

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

    if config.SSLPassPhraseDialog and os.path.isfile(config.SSLPassPhraseDialog):
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

class ChainingOpenSSLContextFactory(DefaultOpenSSLContextFactory):
    def __init__(
        self, privateKeyFileName, certificateFileName,
        sslmethod=SSL.SSLv23_METHOD, certificateChainFile=None,
        passwdCallback=None
    ):
        self.certificateChainFile = certificateChainFile
        self.passwdCallback = passwdCallback

        DefaultOpenSSLContextFactory.__init__(
            self,
            privateKeyFileName,
            certificateFileName,
            sslmethod=sslmethod
        )

    def cacheContext(self):
        # Unfortunate code duplication.
        ctx = SSL.Context(self.sslmethod)

        if self.passwdCallback is not None:
            ctx.set_passwd_cb(self.passwdCallback)

        ctx.use_certificate_file(self.certificateFileName)
        ctx.use_privatekey_file(self.privateKeyFileName)

        if self.certificateChainFile != "":
            ctx.use_certificate_chain_file(self.certificateChainFile)

        self._context = ctx


class CalDAVServiceMaker(object):
    implements(IPlugin, service.IServiceMaker)

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

        log.info("Configuring directory service of type: %s"
                 % (config.DirectoryService.type,))

        baseDirectory = directoryClass(**config.DirectoryService.params)

        directories.append(baseDirectory)

        sudoDirectory = None

        if config.SudoersFile and os.path.exists(config.SudoersFile):
            log.info("Configuring SudoDirectoryService with file: %s"
                     % (config.SudoersFile,))

            sudoDirectory = SudoDirectoryService(config.SudoersFile)
            sudoDirectory.realmName = baseDirectory.realmName

            CalDAVResource.sudoDirectory = sudoDirectory
            directories.insert(0, sudoDirectory)
        else:
            log.info("Not using SudoDirectoryService; file doesn't exist: %s"
                     % (config.SudoersFile,))

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
        log.info("Setting up document root at: %s"
                 % (config.DocumentRoot,))
        log.info("Setting up principal collection: %r"
                 % (self.principalResourceClass,))

        principalCollection = self.principalResourceClass(
            "/principals/",
            directory,
        )

        log.info("Setting up calendar collection: %r"
                 % (self.calendarResourceClass,))

        calendarCollection = self.calendarResourceClass(
            os.path.join(config.DocumentRoot, "calendars"),
            directory, "/calendars/",
        )

        log.info("Setting up root resource: %r" % (self.rootResourceClass,))

        root = self.rootResourceClass(
            config.DocumentRoot,
            principalCollections=(principalCollection,),
        )

        root.putChild("principals", principalCollection)
        root.putChild("calendars", calendarCollection)

        # Timezone service is optional
        if config.EnableTimezoneService:
            log.info("Setting up time zone service resource: %r"
                     % (self.timezoneServiceResourceClass,))

            timezoneService = self.timezoneServiceResourceClass(
                os.path.join(config.DocumentRoot, "timezones"),
                root,
            )
            root.putChild("timezones", timezoneService)

        # iSchedule service is optional
        if config.Scheduling.iSchedule.Enabled:
            log.info("Setting up iSchedule inbox resource: %r"
                     % (self.iScheduleResourceClass,))
    
            ischedule = self.iScheduleResourceClass(
                os.path.join(config.DocumentRoot, "ischedule"),
                root,
            )
            root.putChild("ischedule", ischedule)

        #
        # IMIP delivery resource
        #
        log.info("Setting up iMIP inbox resource: %r"
                 % (self.imipResourceClass,))

        imipInbox = self.imipResourceClass(root)
        root.putChild("inbox", imipInbox)

        #
        # Configure ancillary data
        #
        log.info("Setting up Timezone Cache")
        TimezoneCache.create()

        #
        # Configure the Site and Wrappers
        #
        credentialFactories = []

        portal = Portal(auth.DavRealm())

        portal.registerChecker(directory)

        realm = directory.realmName or ""

        log.info("Configuring authentication for realm: %s" % (realm,))

        for scheme, schemeConfig in config.Authentication.iteritems():
            scheme = scheme.lower()

            credFactory = None

            if schemeConfig["Enabled"]:
                log.info("Setting up scheme: %s" % (scheme,))

                if scheme == "kerberos":
                    if not NegotiateCredentialFactory:
                        log.info("Kerberos support not available")
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
                        log.info("Could not start Kerberos")
                        continue

                elif scheme == "digest":
                    credFactory = QopDigestCredentialFactory(
                        schemeConfig["Algorithm"],
                        schemeConfig["Qop"],
                        realm,
                        config.DataRoot,
                    )

                elif scheme == "basic":
                    credFactory = BasicCredentialFactory(realm)

                else:
                    log.error("Unknown scheme: %s" % (scheme,))

            if credFactory:
                credentialFactories.append(credFactory)

        log.info("Configuring authentication wrapper")

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
        log.info("Setting up service")

        if config.ProcessType == "Slave":
            if (
                config.MultiProcess.ProcessCount > 1 and
                config.MultiProcess.LoadBalancer.Enabled
            ):
                realRoot = pdmonster.PDClientAddressWrapper(
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

        log.info("Configuring log observer: %s" % (logObserver,))

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
                log.info("Adding server at %s:%s" % (bindAddress, port))

                httpService = internet.TCPServer(
                    int(port), channel,
                    interface=bindAddress,
                    backlog=config.ListenBacklog,
                )
                httpService.setServiceParent(service)

            for port in config.BindSSLPorts:
                log.info("Adding SSL server at %s:%s" % (bindAddress, port))

                try:
                    contextFactory = ChainingOpenSSLContextFactory(
                        config.SSLPrivateKey,
                        config.SSLCertificate,
                        certificateChainFile=config.SSLAuthorityChain,
                        passwdCallback=getSSLPassphrase,
                    )
                except SSL.Error, e:
                    log.error("Unable to set up SSL context factory: %s" % (e,))
                    log.error("Disabling SSL port: %s" % (port,))
                else:
                    httpsService = internet.SSLServer(
                        int(port), channel,
                        contextFactory, interface=bindAddress,
                        backlog=config.ListenBacklog,
                    )
                    httpsService.setServiceParent(service)

        # Change log level back to what it was before
        setLogLevelForNamespace(None, oldLogLevel)

        return service

    makeService_Combined = makeService_Combined
    makeService_Master   = makeService_Master
    makeService_Single   = makeService_Slave

    def makeService(self, options):

        # Now do any on disk upgrades we might need.
        UpgradeTheServer.doUpgrade()

        serverType = config.ProcessType

        serviceMethod = getattr(self, "makeService_%s" % (serverType,), None)

        if not serviceMethod:
            raise UsageError(
                "Unknown server type %s. "
                "Please choose: Master, Slave, Single or Combined"
                % (serverType,)
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
                log.info("SIGHUP recieved at %s" % (location(frame),))

                # Reload the config file
                config.reload()

                # If combined service send signal to all caldavd children
                if serverType == "Combined":
                    service.processMonitor.signalAll(signal.SIGHUP, "caldav")

                # FIXME: There is no memcachepool.getCachePool
                #   Also, better option is probably to add a hook to
                #   the config object instead of doing things here.
                #log.info("Suggesting new max clients for memcache.")
                #memcachepool.getCachePool().suggestMaxClients(
                #    config.Memcached.MaxClients
                #)

            signal.signal(signal.SIGHUP, sighup_handler)

            return service
