# -*- test-case-name: calendarserver.tap.test.test_caldav -*-
##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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
from __future__ import print_function

__all__ = [
    "CalDAVService",
    "CalDAVOptions",
    "CalDAVServiceMaker",
]

import os
import signal
import socket
import stat
import sys
from time import time
from subprocess import Popen, PIPE
from pwd import getpwuid, getpwnam
from grp import getgrnam
import OpenSSL
from OpenSSL.SSL import Error as SSLError
from os import getuid, getgid

from zope.interface import implements

from twisted.plugin import IPlugin

from twisted.python.log import FileLogObserver, ILogObserver
from twisted.python.logfile import LogFile
from twisted.python.usage import Options, UsageError

from twisted.internet.defer import gatherResults, Deferred, inlineCallbacks, succeed

from twisted.internet.process import ProcessExitedAlready
from twisted.internet.protocol import Protocol, Factory
from twisted.internet.protocol import ProcessProtocol

from twisted.application.internet import TCPServer, UNIXServer
from twisted.application.service import MultiService, IServiceMaker
from twisted.application.service import Service

from twistedcaldav.config import config, ConfigurationError
from twistedcaldav.stdconfig import DEFAULT_CONFIG, DEFAULT_CONFIG_FILE
from twext.web2.server import Site
from twext.python.log import Logger, LoggingMixIn
from twext.python.log import logLevelForNamespace, setLogLevelForNamespace
from twext.python.filepath import CachingFilePath
from twext.internet.ssl import ChainingOpenSSLContextFactory
from twext.internet.tcp import MaxAcceptTCPServer, MaxAcceptSSLServer
from twext.web2.channel.http import LimitingHTTPFactory, SSLRedirectRequest
from twext.web2.metafd import ConnectionLimiter, ReportingHTTPService

from txdav.common.datastore.sql_tables import schema
from txdav.common.datastore.upgrade.sql.upgrade import (
    UpgradeDatabaseSchemaStep, UpgradeDatabaseAddressBookDataStep,
    UpgradeDatabaseCalendarDataStep, UpgradeDatabaseOtherStep,
)
from txdav.common.datastore.upgrade.migrate import UpgradeToDatabaseStep

from twistedcaldav.directory import calendaruserproxy
from twistedcaldav.directory.directory import GroupMembershipCacheUpdater
from twistedcaldav.localization import processLocalizationFiles
from twistedcaldav import memcachepool
from twistedcaldav.upgrade import UpgradeFileSystemFormatStep, PostDBImportStep

from calendarserver.tap.util import pgServiceFromConfig, getDBPool, MemoryLimitService
from calendarserver.tap.util import directoryFromConfig, checkDirectories
from calendarserver.tap.util import Stepper

from twext.enterprise.ienterprise import POSTGRES_DIALECT
from twext.enterprise.ienterprise import ORACLE_DIALECT
from twext.enterprise.adbapi2 import ConnectionPool

try:
    from twistedcaldav.authkerb import NegotiateCredentialFactory
    NegotiateCredentialFactory  # pacify pyflakes
except ImportError:
    NegotiateCredentialFactory = None

from calendarserver.tap.util import ConnectionDispenser

from calendarserver.controlsocket import ControlSocket
from twisted.internet.endpoints import UNIXClientEndpoint, TCP4ClientEndpoint

from calendarserver.controlsocket import ControlSocketConnectingService
from twisted.protocols.amp import AMP
from twext.enterprise.queue import WorkerFactory as QueueWorkerFactory
from twext.enterprise.queue import PeerConnectionPool
from calendarserver.accesslog import AMPCommonAccessLoggingObserver
from calendarserver.accesslog import AMPLoggingFactory
from calendarserver.accesslog import RotatingFileAccessLoggingObserver
from calendarserver.tap.util import getRootResource
from calendarserver.tap.util import storeFromConfig
from calendarserver.tap.util import pgConnectorFromConfig
from calendarserver.tap.util import oracleConnectorFromConfig
from calendarserver.push.notifier import PushDistributor
from calendarserver.push.amppush import AMPPushMaster, AMPPushForwarder
from calendarserver.push.applepush import ApplePushNotifierService
from twistedcaldav.scheduling.imip.inbound import MailRetriever

try:
    from calendarserver.version import version
    version
except ImportError:
    from twisted.python.modules import getModule
    sys.path.insert(
        0, getModule(__name__).pathEntry.filePath.child("support").path)
    from version import version as getVersion
    version = "%s (%s*)" % getVersion()

from twext.web2.server import VERSION as TWISTED_VERSION
TWISTED_VERSION = "CalendarServer/%s %s" % (
    version.replace(" ", ""), TWISTED_VERSION,
)

log = Logger()

from twisted.python.util import uidFromString, gidFromString


# Control socket message-routing constants.
_LOG_ROUTE = "log"
_QUEUE_ROUTE = "queue"

_CONTROL_SERVICE_NAME = "control"


def getid(uid, gid):
    if uid is not None:
        uid = uidFromString(uid)
    if gid is not None:
        gid = gidFromString(gid)
    return (uid, gid)



def conflictBetweenIPv4AndIPv6():
    """
    Is there a conflict between binding an IPv6 and an IPv4 port?  Return True
    if there is, False if there isn't.

    This is a temporary workaround until maybe Twisted starts setting
    C{IPPROTO_IPV6 / IPV6_V6ONLY} on IPv6 sockets.

    @return: C{True} if listening on IPv4 conflicts with listening on IPv6.
    """
    s4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        s4.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s6.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s4.bind(("", 0))
        s4.listen(1)
        usedport = s4.getsockname()[1]
        try:
            s6.bind(("::", usedport))
        except socket.error:
            return True
        else:
            return False
    finally:
        s4.close()
        s6.close()



def _computeEnvVars(parent):
    """
    Compute environment variables to be propagated to child processes.
    """
    result = {}
    requiredVars = [
        "PATH",
        "PYTHONPATH",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
    ]

    optionalVars = [
        "PYTHONHASHSEED",
        "KRB5_KTNAME",
        "ORACLE_HOME",
        "VERSIONER_PYTHON_PREFER_32_BIT",
    ]

    for varname in requiredVars:
        result[varname] = parent.get(varname, "")
    for varname in optionalVars:
        if varname in parent:
            result[varname] = parent[varname]
    return result

PARENT_ENVIRONMENT = _computeEnvVars(os.environ)



class CalDAVStatisticsProtocol (Protocol):

    def connectionMade(self):
        stats = self.factory.logger.observer.getStats()
        self.transport.write("%s\r\n" % (stats,))
        self.transport.loseConnection()



class CalDAVStatisticsServer (Factory):

    protocol = CalDAVStatisticsProtocol

    def __init__(self, logObserver):
        self.logger = logObserver



class ErrorLoggingMultiService(MultiService, object):
    """ Registers a rotating file logger for error logging, if
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

    # The ConnectionService is a MultiService which bundles all the connection
    # services together for the purposes of being able to stop them and wait
    # for all of their connections to close before shutting down.
    connectionServiceName = "ConnectionService"

    def __init__(self, logObserver):
        self.logObserver = logObserver  # accesslog observer
        MultiService.__init__(self)


    def privilegedStartService(self):
        MultiService.privilegedStartService(self)
        self.logObserver.start()


    @inlineCallbacks
    def stopService(self):
        """
        Wait for outstanding requests to finish
        @return: a Deferred which fires when all outstanding requests are complete
        """
        connectionService = self.getServiceNamed(self.connectionServiceName)
        # Note: removeService() also calls stopService()
        yield self.removeService(connectionService)
        # At this point, all outstanding requests have been responded to
        yield super(CalDAVService, self).stopService()
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
        and float options are supported, as well as comma separated lists. Only
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
        try:
            self.loadConfiguration()
            self.checkConfiguration()
        except ConfigurationError, e:
            print("Invalid configuration: %s" % (e,))
            sys.exit(1)


    def loadConfiguration(self):
        if not os.path.exists(self["config"]):
            raise ConfigurationError("Config file %s not found. Exiting."
                                     % (self["config"],))

        print("Reading configuration from file: %s" % (self["config"],))

        config.load(self["config"])
        config.updateDefaults(self.overrides)


    def checkDirectories(self, config):
        checkDirectories(config)


    def checkConfiguration(self):

        # Having CalDAV *and* CardDAV both disabled is an illegal configuration
        # for a running server (but is fine for command-line utilities)
        if not config.EnableCalDAV and not config.EnableCardDAV:
            print("Neither EnableCalDAV nor EnableCardDAV are set to True.")
            sys.exit(1)

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

        self.checkDirectories(config)


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
        self.parent['umask'] = config.umask



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

        # Unfortunately, there's no public way to access this. -glyph
        fileName = self._port.port
        os.chown(fileName, os.getuid(), self.gid)



class SlaveSpawnerService(Service):
    """
    Service to add all Python subprocesses that need to do work to a
    L{DelayedStartupProcessMonitor}:

        - regular slave processes (CalDAV workers)
    """

    def __init__(self, maker, monitor, dispenser, dispatcher, configPath,
                 inheritFDs=None, inheritSSLFDs=None):
        self.maker = maker
        self.monitor = monitor
        self.dispenser = dispenser
        self.dispatcher = dispatcher
        self.configPath = configPath
        self.inheritFDs = inheritFDs
        self.inheritSSLFDs = inheritSSLFDs


    def startService(self):
        for slaveNumber in xrange(0, config.MultiProcess.ProcessCount):
            if config.UseMetaFD:
                extraArgs = dict(metaSocket=self.dispatcher.addSocket())
            else:
                extraArgs = dict(inheritFDs=self.inheritFDs,
                                 inheritSSLFDs=self.inheritSSLFDs)
            if self.dispenser is not None:
                extraArgs.update(ampSQLDispenser=self.dispenser)
            process = TwistdSlaveProcess(
                sys.argv[0], self.maker.tapname, self.configPath, slaveNumber,
                config.BindAddresses, **extraArgs
            )
            self.monitor.addProcessObject(process, PARENT_ENVIRONMENT)



class ReExecService(MultiService, LoggingMixIn):
    """
    A MultiService which catches SIGHUP and re-exec's the process.
    """

    def __init__(self, pidfilePath, reactor=None):
        """
        @param pidFilePath: Absolute path to the pidfile which will need to be
            removed
        @type pidFilePath: C{str}
        """
        self.pidfilePath = pidfilePath
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor
        MultiService.__init__(self)


    def reExec(self):
        """
        Removes pidfile, registers an exec to happen after shutdown, then
        stops the reactor.
        """
        self.log_info("SIGHUP received - restarting")
        try:
            self.log_info("Removing pidfile: %s" % (self.pidfilePath,))
            os.remove(self.pidfilePath)
        except OSError:
            pass
        self.reactor.addSystemEventTrigger("after", "shutdown", os.execv,
            sys.executable, [sys.executable] + sys.argv)
        self.reactor.stop()


    def sighupHandler(self, num, frame):
        self.reactor.callFromThread(self.reExec)


    def startService(self):
        self.previousHandler = signal.signal(signal.SIGHUP, self.sighupHandler)
        MultiService.startService(self)


    def stopService(self):
        signal.signal(signal.SIGHUP, self.previousHandler)
        MultiService.stopService(self)


class PreProcessingService(Service):
    """
    A Service responsible for running any work that needs to be finished prior
    to the main service starting.  Once that work is done, it instantiates the
    main service and adds it to the Service hierarchy (specifically to its
    parent).  If the final work step does not return a Failure, that is an 
    indication the store is ready and it is passed to the main service.
    Otherwise, None is passed to the main service in place of a store.  This
    is mostly useful in the case of command line utilities that need to do
    something different if the store is not available (e.g. utilities that
    aren't allowed to upgrade the database).
    """

    def __init__(self, serviceCreator, connectionPool, store, logObserver,
        reactor=None):
        """
        @param serviceCreator: callable which will be passed the connection
            pool, store, and log observer, and should return a Service
        @param connectionPool: connection pool to pass to serviceCreator
        @param store: the store object being processed
        @param logObserver: log observer to pass to serviceCreator
        """
        self.serviceCreator = serviceCreator
        self.connectionPool = connectionPool
        self.store = store
        self.logObserver = logObserver
        self.stepper = Stepper()

        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor

    def stepWithResult(self, result):
        """
        The final "step"; if we get here we know our store is ready, so
        we create the main service and pass in the store.
        """
        service = self.serviceCreator(self.connectionPool, self.store,
            self.logObserver)
        if self.parent is not None:
            self.reactor.callLater(0, service.setServiceParent, self.parent)
        return succeed(None)

    def stepWithFailure(self, failure):
        """
        The final "step", but if we get here we know our store is not ready,
        so we create the main service and pass in a None for the store.
        """
        try:
            service = self.serviceCreator(self.connectionPool, None,
                self.logObserver)
            if self.parent is not None:
                self.reactor.callLater(0, service.setServiceParent, self.parent)
        except StoreNotAvailable:
            self.reactor.stop()

        return succeed(None)

    def addStep(self, step):
        """
        Hand the step to our Stepper

        @param step: an object implementing stepWithResult( )
        """
        self.stepper.addStep(step)
        return self

    def startService(self):
        """
        Add ourself as the final step, and then tell the coordinator to start
        working on each step one at a time.
        """
        self.addStep(self)
        self.stepper.start()


class PostUpgradeStopRequested(Exception):
    """
    Raised when we've been asked to stop just after upgrade has completed.
    """

class StoreNotAvailable(Exception):
    """
    Raised when we want to give up because the store is not available
    """

class QuitAfterUpgradeStep(object):

    def __init__(self, triggerFile, reactor=None):
        self.triggerFile = triggerFile
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor

    def removeTriggerFile(self):
        try:
            os.remove(self.triggerFile)
        except OSError:
            pass

    def stepWithResult(self, result):
        if os.path.exists(self.triggerFile):
            self.removeTriggerFile()
            self.reactor.stop()
            raise PostUpgradeStopRequested()
        else:
            return succeed(result)

    def stepWithFailure(self, failure):
        if os.path.exists(self.triggerFile):
            self.removeTriggerFile()
            self.reactor.stop()
            raise PostUpgradeStopRequested()
        else:
            return failure


class CalDAVServiceMaker (LoggingMixIn):
    implements(IPlugin, IServiceMaker)

    tapname = "caldav"
    description = "Calendar and Contacts Server"
    options = CalDAVOptions


    def makeService(self, options):
        """
        Create the top-level service.
        """
        self.log_info("%s %s starting %s process..." % (self.description, version, config.ProcessType))

        try:
            from setproctitle import setproctitle, getproctitle
        except ImportError:
            pass
        else:
            origTitle = getproctitle()
            if config.LogID:
                logID = " #%s" % (config.LogID,)
            else:
                logID = ""
            if config.ProcessType is not "Utility":
                origTitle = ""
            setproctitle("CalendarServer %s [%s%s] %s" % (version, config.ProcessType, logID, origTitle))

        serviceMethod = getattr(self, "makeService_%s" % (config.ProcessType,), None)

        if not serviceMethod:
            raise UsageError(
                "Unknown server type %s. "
                "Please choose: Slave, Single or Combined"
                % (config.ProcessType,)
            )
        else:
            #
            # Configure Memcached Client Pool
            #
            memcachepool.installPools(
                config.Memcached.Pools,
                config.Memcached.MaxClients,
            )

            if config.ProcessType in ("Combined", "Single"):
                # Process localization string files
                processLocalizationFiles(config.Localization)

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
        """
        Create a "slave" service, a subprocess of a service created with
        L{makeService_Combined}, which does the work of actually handling
        CalDAV and CardDAV requests.
        """
        pool, txnFactory = getDBPool(config)
        store = storeFromConfig(config, txnFactory)
        logObserver = AMPCommonAccessLoggingObserver()
        result = self.requestProcessingService(options, store, logObserver)
        directory = result.rootResource.getDirectory()
        if pool is not None:
            pool.setServiceParent(result)

        if config.ControlSocket:
            id = config.ControlSocket
            self.log_info("Control via AF_UNIX: %s" % (id,))
            endpointFactory = lambda reactor: UNIXClientEndpoint(
                reactor, id)
        else:
            id = int(config.ControlPort)
            self.log_info("Control via AF_INET: %d" % (id,))
            endpointFactory = lambda reactor: TCP4ClientEndpoint(
                reactor, "127.0.0.1", id)
        controlSocketClient = ControlSocket()
        class LogClient(AMP):
            def startReceivingBoxes(self, sender):
                super(LogClient, self).startReceivingBoxes(sender)
                logObserver.addClient(self)
        f = Factory()
        f.protocol = LogClient
        controlSocketClient.addFactory(_LOG_ROUTE, f)
        from txdav.common.datastore.sql import CommonDataStore as SQLStore
        if isinstance(store, SQLStore):
            def queueMasterAvailable(connectionFromMaster):
                store.queuer = store.queuer.transferProposalCallbacks(connectionFromMaster)
            queueFactory = QueueWorkerFactory(store.newTransaction, schema,
                                              queueMasterAvailable)
            controlSocketClient.addFactory(_QUEUE_ROUTE, queueFactory)
        controlClient = ControlSocketConnectingService(
            endpointFactory, controlSocketClient
        )
        controlClient.setServiceParent(result)

        # Optionally set up push notifications
        pushDistributor = None
        if config.Notifications.Enabled:
            observers = []
            if config.Notifications.Services.APNS.Enabled:
                pushSubService = ApplePushNotifierService.makeService(
                    config.Notifications.Services.APNS, store)
                observers.append(pushSubService)
                pushSubService.setServiceParent(result)
            if config.Notifications.Services.AMP.Enabled:
                pushSubService = AMPPushForwarder(controlSocketClient)
                observers.append(pushSubService)
            if observers:
                pushDistributor = PushDistributor(observers)

        # Optionally set up mail retrieval
        if config.Scheduling.iMIP.Enabled:
            mailRetriever = MailRetriever(store, directory,
                config.Scheduling.iMIP.Receiving)
            mailRetriever.setServiceParent(result)
        else:
            mailRetriever = None

        # Optionally set up group cacher
        if config.GroupCaching.Enabled:
            groupCacher = GroupMembershipCacheUpdater(
                calendaruserproxy.ProxyDBService,
                directory,
                config.GroupCaching.UpdateSeconds,
                config.GroupCaching.ExpireSeconds,
                namespace=config.GroupCaching.MemcachedPool,
                useExternalProxies=config.GroupCaching.UseExternalProxies
                )
        else:
            groupCacher = None

        def decorateTransaction(txn):
            txn._pushDistributor = pushDistributor
            txn._rootResource = result.rootResource
            txn._mailRetriever = mailRetriever
            txn._groupCacher = groupCacher

        store.callWithNewTransactions(decorateTransaction)

        # Optionally enable Manhole access
        if config.Manhole.Enabled:
            try:
                from twisted.conch.manhole_tap import makeService as manholeMakeService
                portString = "tcp:%d:interface=127.0.0.1" % (config.Manhole.StartingPortNumber + int(config.LogID) + 1,)
                manholeService = manholeMakeService({
                    "sshPort" : None,
                    "telnetPort" : portString,
                    "namespace" : {
                        "config" : config,
                        "service" : result,
                        "store" : store,
                        "directory" : directory,
                        },
                    "passwd" : config.Manhole.PasswordFilePath,
                })
                manholeService.setServiceParent(result)
                # Using print(because logging isn't ready at this point)
                print("Manhole access enabled: %s" % (portString,))
            except ImportError:
                print("Manhole access could not enabled because manhole_tap could not be imported")

        return result


    def requestProcessingService(self, options, store, logObserver):
        """
        Make a service that will actually process HTTP requests.

        This may be a 'Slave' service, which runs as a worker subprocess of the
        'Combined' configuration, or a 'Single' service, which is a stand-alone
        process that answers CalDAV/CardDAV requests by itself.
        """
        #
        # Change default log level to "info" as its useful to have
        # that during startup
        #
        oldLogLevel = logLevelForNamespace(None)
        setLogLevelForNamespace(None, "info")

        # Note: 'additional' was used for IMIP reply resource, and perhaps
        # we can remove this
        additional = []

        #
        # Configure the service
        #
        self.log_info("Setting up service")

        self.log_info("Configuring access log observer: %s" % (logObserver,))
        service = CalDAVService(logObserver)

        rootResource = getRootResource(config, store, additional)
        service.rootResource = rootResource

        underlyingSite = Site(rootResource)

        # Need to cache SSL port info here so we can access it in a Request to
        # deal with the possibility of being behind an SSL decoder
        underlyingSite.EnableSSL = config.EnableSSL
        underlyingSite.SSLPort = config.SSLPort
        underlyingSite.BindSSLPorts = config.BindSSLPorts

        requestFactory = underlyingSite

        if config.RedirectHTTPToHTTPS:
            self.log_info("Redirecting to HTTPS port %s" % (config.SSLPort,))
            def requestFactory(*args, **kw):
                return SSLRedirectRequest(site=underlyingSite, *args, **kw)

        # Add the Strict-Transport-Security header to all secured requests
        # if enabled.
        if config.StrictTransportSecuritySeconds:
            previousRequestFactory = requestFactory
            def requestFactory(*args, **kw):
                request = previousRequestFactory(*args, **kw)
                def responseFilter(ignored, response):
                    ignored, secure = request.chanRequest.getHostInfo()
                    if secure:
                        response.headers.addRawHeader("Strict-Transport-Security",
                            "max-age={max_age:d}"
                            .format(max_age=config.StrictTransportSecuritySeconds))
                    return response
                request.addResponseFilter(responseFilter)
                return request

        httpFactory = LimitingHTTPFactory(
            requestFactory,
            maxRequests=config.MaxRequests,
            maxAccepts=config.MaxAccepts,
            betweenRequestsTimeOut=config.IdleConnectionTimeOut,
            vary=True,
        )

        def updateFactory(configDict, reloading=False):
            httpFactory.maxRequests = configDict.MaxRequests
            httpFactory.maxAccepts = configDict.MaxAccepts

        config.addPostUpdateHooks((updateFactory,))

        # Bundle the various connection services within a single MultiService
        # that can be stopped before the others for graceful shutdown.
        connectionService = MultiService()
        connectionService.setName(CalDAVService.connectionServiceName)
        connectionService.setServiceParent(service)

        # For calendarserver.tap.test.test_caldav.BaseServiceMakerTests.getSite():
        connectionService.underlyingSite = underlyingSite

        if config.InheritFDs or config.InheritSSLFDs:
            # Inherit sockets to call accept() on them individually.

            if config.EnableSSL:
                for fdAsStr in config.InheritSSLFDs:
                    try:
                        contextFactory = self.createContextFactory()
                    except SSLError, e:
                        log.error("Unable to set up SSL context factory: %s" % (e,))
                    else:
                        MaxAcceptSSLServer(
                            int(fdAsStr), httpFactory,
                            contextFactory,
                            backlog=config.ListenBacklog,
                            inherit=True
                        ).setServiceParent(connectionService)
            for fdAsStr in config.InheritFDs:
                MaxAcceptTCPServer(
                    int(fdAsStr), httpFactory,
                    backlog=config.ListenBacklog,
                    inherit=True
                ).setServiceParent(connectionService)

        elif config.MetaFD:
            # Inherit a single socket to receive accept()ed connections via
            # recvmsg() and SCM_RIGHTS.

            try:
                contextFactory = self.createContextFactory()
            except SSLError, e:
                self.log_error("Unable to set up SSL context factory: %s" % (e,))
                # None is okay as a context factory for ReportingHTTPService as
                # long as we will never receive a file descriptor with the
                # 'SSL' tag on it, since that's the only time it's used.
                contextFactory = None

            ReportingHTTPService(
                requestFactory, int(config.MetaFD), contextFactory
            ).setServiceParent(connectionService)

        else:  # Not inheriting, therefore we open our own:
            for bindAddress in self._allBindAddresses():
                self._validatePortConfig()
                if config.EnableSSL:
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
                            httpsService.setServiceParent(connectionService)

                for port in config.BindHTTPPorts:
                    MaxAcceptTCPServer(
                        int(port), httpFactory,
                        interface=bindAddress,
                        backlog=config.ListenBacklog,
                        inherit=False
                    ).setServiceParent(connectionService)

        # Change log level back to what it was before
        setLogLevelForNamespace(None, oldLogLevel)
        return service


    def _validatePortConfig(self):
        """
        If BindHTTPPorts is specified, HTTPPort must also be specified to
        indicate which is the preferred port (the one to be used in URL
        generation, etc).  If only HTTPPort is specified, BindHTTPPorts should
        be set to a list containing only that port number.  Similarly for
        BindSSLPorts/SSLPort.

        @raise UsageError: if configuration is not valid.
        """
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


    def _allBindAddresses(self):
        """
        An empty array for the config value of BindAddresses should be
        equivalent to an array containing two BindAddresses; one with a single
        empty string, and one with "::", meaning "bind everything on both IPv4
        and IPv6".
        """
        if not config.BindAddresses:
            if getattr(socket, "has_ipv6", False):
                if conflictBetweenIPv4AndIPv6():
                    # If there's a conflict between v4 and v6, then almost by
                    # definition, v4 is mapped into the v6 space, so we will
                    # listen "only" on v6.
                    config.BindAddresses = ["::"]
                else:
                    config.BindAddresses = ["", "::"]
            else:
                config.BindAddresses = [""]
        return config.BindAddresses


    def makeService_Single(self, options):
        """
        Create a service to be used in a single-process, stand-alone
        configuration.  Memcached will be spawned automatically.
        """
        def slaveSvcCreator(pool, store, logObserver):

            if store is None:
                raise StoreNotAvailable()

            result = self.requestProcessingService(options, store, logObserver)


            # Optionally set up push notifications
            pushDistributor = None
            if config.Notifications.Enabled:
                observers = []
                if config.Notifications.Services.APNS.Enabled:
                    pushSubService = ApplePushNotifierService.makeService(
                        config.Notifications.Services.APNS, store)
                    observers.append(pushSubService)
                    pushSubService.setServiceParent(result)
                if config.Notifications.Services.AMP.Enabled:
                    pushSubService = AMPPushMaster(None, result,
                        config.Notifications.Services.AMP.Port,
                        config.Notifications.Services.AMP.EnableStaggering,
                        config.Notifications.Services.AMP.StaggerSeconds
                        )
                    observers.append(pushSubService)
                if observers:
                    pushDistributor = PushDistributor(observers)

            directory = result.rootResource.getDirectory()

            # Optionally set up mail retrieval
            if config.Scheduling.iMIP.Enabled:
                mailRetriever = MailRetriever(store, directory,
                    config.Scheduling.iMIP.Receiving)
                mailRetriever.setServiceParent(result)
            else:
                mailRetriever = None

            # Optionally set up group cacher
            if config.GroupCaching.Enabled:
                groupCacher = GroupMembershipCacheUpdater(
                    calendaruserproxy.ProxyDBService,
                    directory,
                    config.GroupCaching.UpdateSeconds,
                    config.GroupCaching.ExpireSeconds,
                    namespace=config.GroupCaching.MemcachedPool,
                    useExternalProxies=config.GroupCaching.UseExternalProxies
                    )
            else:
                groupCacher = None

            def decorateTransaction(txn):
                txn._pushDistributor = pushDistributor
                txn._rootResource = result.rootResource
                txn._mailRetriever = mailRetriever
                txn._groupCacher = groupCacher

            store.callWithNewTransactions(decorateTransaction)

            return result

        uid, gid = getSystemIDs(config.UserName, config.GroupName)

        # Make sure no old socket files are lying around.
        self.deleteStaleSocketFiles()
        logObserver = RotatingFileAccessLoggingObserver(
            config.AccessLogFile,
        )

        # Optionally launch memcached.  Note, this is not going through a
        # ProcessMonitor because there is code elsewhere that needs to
        # access memcached before startService() gets called, so we're just
        # directly using Popen to spawn memcached.
        for name, pool in config.Memcached.Pools.items():
            if pool.ServerEnabled:
                self.log_info(
                    "Adding memcached service for pool: %s" % (name,)
                )
                memcachedArgv = [
                    config.Memcached.memcached,
                    "-p", str(pool.Port),
                    "-l", pool.BindAddress,
                    "-U", "0",
                ]
                if config.Memcached.MaxMemory is not 0:
                    memcachedArgv.extend(
                        ["-m", str(config.Memcached.MaxMemory)]
                    )
                if config.UserName:
                    memcachedArgv.extend(["-u", config.UserName])
                memcachedArgv.extend(config.Memcached.Options)
                Popen(memcachedArgv)

        return self.storageService(slaveSvcCreator, logObserver, uid=uid, gid=gid)


    def makeService_Utility(self, options):
        """
        Create a service to be used in a command-line utility

        Specify the actual utility service class in config.UtilityServiceClass.
        When created, that service will have access to the storage facilities.
        """

        def toolServiceCreator(pool, store, ignored):
            return config.UtilityServiceClass(store)

        uid, gid = getSystemIDs(config.UserName, config.GroupName)
        return self.storageService(toolServiceCreator, None, uid=uid, gid=gid)


    def storageService(self, createMainService, logObserver, uid=None, gid=None):
        """
        If necessary, create a service to be started used for storage; for
        example, starting a database backend.  This service will then start the
        main service.

        This has the effect of delaying any child process spawning or
        stand alone port-binding until the backing for the selected data store
        implementation is ready to process requests.

        @param createMainService: This is the service that will be doing the main
            work of the current process.  If the configured storage mode does
            not require any particular setup, then this may return the
            C{mainService} argument.

        @type createMainService: C{callable} that takes C{(connectionPool, store)}
            and returns L{IService}

        @param uid: the user ID to run the backend as, if this process is
            running as root (also the uid to chown Attachments to).
        @type uid: C{int}

        @param gid: the user ID to run the backend as, if this process is
            running as root (also the gid to chown Attachments to).
        @type gid: C{int}

        @return: the appropriate a service to start.

        @rtype: L{IService}
        """
        def createSubServiceFactory(dialect=POSTGRES_DIALECT,
                                    paramstyle='pyformat'):
            def subServiceFactory(connectionFactory):
                ms = MultiService()
                cp = ConnectionPool(connectionFactory, dialect=dialect,
                                    paramstyle=paramstyle,
                                    maxConnections=config.MaxDBConnectionsPerPool)
                cp.setServiceParent(ms)
                store = storeFromConfig(config, cp.connection)

                pps = PreProcessingService(createMainService, cp, store,
                    logObserver)

                # The following "steps" will run sequentially when the service
                # hierarchy is started.  If any of the steps raise an exception
                # the subsequent steps' stepWithFailure methods will be called
                # instead, until one of them returns a non-Failure.

                # Still need this for Snow Leopard support
                pps.addStep(
                    UpgradeFileSystemFormatStep(config)
                )

                pps.addStep(
                    UpgradeDatabaseSchemaStep(
                        store, uid=overrideUID, gid=overrideGID,
                        failIfUpgradeNeeded=config.FailIfUpgradeNeeded
                    )
                )
                pps.addStep(
                    UpgradeDatabaseAddressBookDataStep(
                        store, uid=overrideUID, gid=overrideGID
                    )
                )
                pps.addStep(
                    UpgradeDatabaseCalendarDataStep(
                        store, uid=overrideUID, gid=overrideGID
                    )
                )

                pps.addStep(
                    UpgradeToDatabaseStep(
                        UpgradeToDatabaseStep.fileStoreFromPath(
                            CachingFilePath(config.DocumentRoot)
                        ),
                        store, uid=overrideUID, gid=overrideGID,
                        merge=config.MergeUpgrades
                    )
                )

                pps.addStep(
                    UpgradeDatabaseOtherStep(
                        store, uid=overrideUID, gid=overrideGID
                    )
                )

                # Conditionally stop after upgrade at this point
                pps.addStep(
                    QuitAfterUpgradeStep(config.StopAfterUpgradeTriggerFile)
                )

                pps.addStep(
                    PostDBImportStep(store, config,
                        getattr(self, "doPostImport", True)
                    )
                )
                pps.setServiceParent(ms)
                return ms

            return subServiceFactory

        # FIXME: this is replicating the logic of getDBPool(), except for the
        # part where the pgServiceFromConfig service is actually started here,
        # and discarded in that function.  This should be refactored to simply
        # use getDBPool.

        if config.UseDatabase:

            if os.getuid() == 0:  # Only override if root
                overrideUID = uid
                overrideGID = gid
            else:
                overrideUID = None
                overrideGID = None

            if config.DBType == '':
                # Spawn our own database as an inferior process, then connect
                # to it.
                pgserv = pgServiceFromConfig(
                    config,
                    createSubServiceFactory(),
                    uid=overrideUID, gid=overrideGID
                )
                return pgserv
            elif config.DBType == 'postgres':
                # Connect to a postgres database that is already running.
                return createSubServiceFactory()(pgConnectorFromConfig(config))
            elif config.DBType == 'oracle':
                # Connect to an Oracle database that is already running.
                return createSubServiceFactory(dialect=ORACLE_DIALECT,
                                               paramstyle='numeric')(
                    oracleConnectorFromConfig(config)
                )
            else:
                raise UsageError("Unknown database type %r" (config.DBType,))
        else:
            store = storeFromConfig(config, None)
            return createMainService(None, store, logObserver)


    def makeService_Combined(self, options):
        """
        Create a master service to coordinate a multi-process configuration,
        spawning subprocesses that use L{makeService_Slave} to perform work.
        """
        s = ErrorLoggingMultiService()

        # Add a service to re-exec the master when it receives SIGHUP
        ReExecService(config.PIDFile).setServiceParent(s)

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
            except KeyError:
                raise ConfigurationError("Invalid group name: %s" %
                                         (config.GroupName,))
        else:
            gid = os.getgid()

        if config.UserName:
            try:
                uid = getpwnam(config.UserName).pw_uid
            except KeyError:
                raise ConfigurationError("Invalid user name: %s" %
                                         (config.UserName,))
        else:
            uid = os.getuid()

        controlSocket = ControlSocket()
        controlSocket.addFactory(_LOG_ROUTE, logger)

        # Optionally set up AMPPushMaster
        if config.Notifications.Enabled and config.Notifications.Services.AMP.Enabled:
            ampSettings = config.Notifications.Services.AMP
            AMPPushMaster(
                controlSocket,
                s,
                ampSettings["Port"],
                ampSettings["EnableStaggering"],
                ampSettings["StaggerSeconds"]
            )
        if config.ControlSocket:
            controlSocketService = GroupOwnedUNIXServer(
                gid, config.ControlSocket, controlSocket, mode=0660
            )
        else:
            controlSocketService = ControlPortTCPServer(
                config.ControlPort, controlSocket, interface="127.0.0.1"
            )
        controlSocketService.setName(_CONTROL_SERVICE_NAME)
        controlSocketService.setServiceParent(s)

        monitor = DelayedStartupProcessMonitor()
        s.processMonitor = monitor
        monitor.setServiceParent(s)

        if config.MemoryLimiter.Enabled:
            memoryLimiter = MemoryLimitService(monitor, config.MemoryLimiter.Seconds,
                config.MemoryLimiter.Bytes, config.MemoryLimiter.ResidentOnly)
            memoryLimiter.setServiceParent(s)

        for name, pool in config.Memcached.Pools.items():
            if pool.ServerEnabled:
                self.log_info(
                    "Adding memcached service for pool: %s" % (name,)
                )
                memcachedArgv = [
                    config.Memcached.memcached,
                    "-p", str(pool.Port),
                    "-l", pool.BindAddress,
                    "-U", "0",
                ]
                if config.Memcached.MaxMemory is not 0:
                    memcachedArgv.extend(
                        ["-m", str(config.Memcached.MaxMemory)]
                    )
                if config.UserName:
                    memcachedArgv.extend(["-u", config.UserName])
                memcachedArgv.extend(config.Memcached.Options)
                monitor.addProcess('memcached-%s' % (name,), memcachedArgv,
                                   env=PARENT_ENVIRONMENT)


        # Open the socket(s) to be inherited by the slaves
        inheritFDs = []
        inheritSSLFDs = []

        if config.UseMetaFD:
            cl = ConnectionLimiter(config.MaxAccepts,
                                   (config.MaxRequests *
                                    config.MultiProcess.ProcessCount))
            dispatcher = cl.dispatcher
        else:
            s._inheritedSockets = []  # keep a reference to these so they don't close
            dispatcher = None

        for bindAddress in self._allBindAddresses():
            self._validatePortConfig()
            if config.UseMetaFD:
                portsList = [(config.BindHTTPPorts, "TCP")]
                if config.EnableSSL:
                    portsList.append((config.BindSSLPorts, "SSL"))
                for ports, description in portsList:
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

                if config.EnableSSL:
                    for portNum in config.BindSSLPorts:
                        sock = _openSocket(bindAddress, int(portNum))
                        inheritSSLFDs.append(sock.fileno())

        # Start listening on the stats socket, for administrators to inspect
        # the current stats on the server.
        if config.Stats.EnableUnixStatsSocket:
            stats = CalDAVStatisticsServer(logger)
            statsService = GroupOwnedUNIXServer(
                gid, config.Stats.UnixStatsSocket, stats, mode=0660
            )
            statsService.setName("unix-stats")
            statsService.setServiceParent(s)
        if config.Stats.EnableTCPStatsSocket:
            stats = CalDAVStatisticsServer(logger)
            statsService = TCPServer(
                config.Stats.TCPStatsPort, stats, interface=""
            )
            statsService.setName("tcp-stats")
            statsService.setServiceParent(s)

        # Optionally enable Manhole access
        if config.Manhole.Enabled:
            try:
                from twisted.conch.manhole_tap import makeService as manholeMakeService
                portString = "tcp:%d:interface=127.0.0.1" % (config.Manhole.StartingPortNumber,)
                manholeService = manholeMakeService({
                    "sshPort" : None,
                    "telnetPort" : portString,
                    "namespace" : {
                        "config" : config,
                        "service" : s,
                        },
                    "passwd" : config.Manhole.PasswordFilePath,
                })
                manholeService.setServiceParent(s)
                # Using print(because logging isn't ready at this point)
                print("Manhole access enabled: %s" % (portString,))
            except ImportError:
                print("Manhole access could not enabled because manhole_tap could not be imported")


        # Finally, let's get the real show on the road.  Create a service that
        # will spawn all of our worker processes when started, and wrap that
        # service in zero to two necessary layers before it's started: first,
        # the service which spawns a subsidiary database (if that's necessary,
        # and we don't have an external, already-running database to connect
        # to), and second, the service which does an upgrade from the
        # filesystem to the database (if that's necessary, and there is
        # filesystem data in need of upgrading).
        def spawnerSvcCreator(pool, store, ignored):
            if store is None:
                raise StoreNotAvailable()

            from twisted.internet import reactor
            pool = PeerConnectionPool(reactor, store.newTransaction,
                                      7654, schema)
            store.queuer = store.queuer.transferProposalCallbacks(pool)
            controlSocket.addFactory(_QUEUE_ROUTE,
                                     pool.workerListenerFactory())
            # TODO: now that we have the shared control socket, we should get
            # rid of the connection dispenser and make a shared / async
            # connection pool implementation that can dispense transactions
            # synchronously as the interface requires.
            if pool is not None and config.SharedConnectionPool:
                self.log_warn("Using Shared Connection Pool")
                dispenser = ConnectionDispenser(pool)
            else:
                dispenser = None
            multi = MultiService()
            pool.setServiceParent(multi)
            spawner = SlaveSpawnerService(
                self, monitor, dispenser, dispatcher, options["config"],
                inheritFDs=inheritFDs, inheritSSLFDs=inheritSSLFDs
            )
            spawner.setServiceParent(multi)
            if config.UseMetaFD:
                cl.setServiceParent(multi)

            directory = directoryFromConfig(config)
            rootResource = getRootResource(config, store, [])

            # Optionally set up mail retrieval
            if config.Scheduling.iMIP.Enabled:
                mailRetriever = MailRetriever(store, directory,
                    config.Scheduling.iMIP.Receiving)
                mailRetriever.setServiceParent(multi)
            else:
                mailRetriever = None

            # Optionally set up group cacher
            if config.GroupCaching.Enabled:
                groupCacher = GroupMembershipCacheUpdater(
                    calendaruserproxy.ProxyDBService,
                    directory,
                    config.GroupCaching.UpdateSeconds,
                    config.GroupCaching.ExpireSeconds,
                    namespace=config.GroupCaching.MemcachedPool,
                    useExternalProxies=config.GroupCaching.UseExternalProxies
                    )
            else:
                groupCacher = None

            def decorateTransaction(txn):
                txn._pushDistributor = None
                txn._rootResource = rootResource
                txn._mailRetriever = mailRetriever
                txn._groupCacher = groupCacher

            store.callWithNewTransactions(decorateTransaction)

            return multi

        ssvc = self.storageService(spawnerSvcCreator, None, uid, gid)
        ssvc.setServiceParent(s)
        return s


    def deleteStaleSocketFiles(self):

        # Check all socket files we use.
        for checkSocket in [config.ControlSocket, config.Stats.UnixStatsSocket] :

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
                            numConnectFailures = numConnectFailures + 1
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

    @ivar twistd: The path to the twistd executable to launch.
    @type twistd: C{str}

    @ivar tapname: The name of the twistd plugin to launch.
    @type tapname: C{str}

    @ivar id: The instance identifier for this slave process.
    @type id: C{int}

    @ivar interfaces: A sequence of interface addresses which the process will
        be configured to bind to.
    @type interfaces: sequence of C{str}

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

    @ivar ampSQLDispenser: a factory for AF_UNIX/SOCK_STREAM sockets that are
        to be inherited by subprocesses and used for sending AMP SQL commands
        back to its parent.
    """
    prefix = "caldav"

    def __init__(self, twistd, tapname, configFile, id, interfaces,
                 inheritFDs=None, inheritSSLFDs=None, metaSocket=None,
                 ampSQLDispenser=None):

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
        self.ampSQLDispenser = ampSQLDispenser
        self.ampDBSocket = None


    def getName(self):
        return '%s-%s' % (self.prefix, self.id)


    def getFileDescriptors(self):
        """
        @return: a mapping of file descriptor numbers for the new (child)
            process to file descriptor numbers in the current (master) process.
        """
        fds = {}
        extraFDs = []
        if self.metaSocket is not None:
            extraFDs.append(self.metaSocket.fileno())
        if self.ampSQLDispenser is not None:
            self.ampDBSocket = self.ampSQLDispenser.dispense()
            extraFDs.append(self.ampDBSocket.fileno())
        for fd in self.inheritSSLFDs + self.inheritFDs + extraFDs:
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
            args.extend(("--savestats", "--profiler", "cprofile-cpu"))

        args.extend([
            "--reactor=%s" % (config.Twisted.reactor,),
            "-n", self.tapname,
            "-f", self.configFile,
            "-o", "ProcessType=Slave",
            "-o", "BindAddresses=%s" % (",".join(self.interfaces),),
            "-o", "PIDFile=%s-instance-%s.pid" % (self.tapname, self.id,),
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
        if self.ampDBSocket is not None:
            args.extend([
                    "-o", "DBAMPFD=%s" % (self.ampDBSocket.fileno(),)
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



class DelayedStartupProcessMonitor(Service, object):
    """
    A L{DelayedStartupProcessMonitor} is a L{procmon.ProcessMonitor} that
    defers building its command lines until the service is actually ready to
    start.  It also specializes process-starting to allow for process objects
    to determine their arguments as they are started up rather than entirely
    ahead of time.

    Also, unlike L{procmon.ProcessMonitor}, its C{stopService} returns a
    L{Deferred} which fires only when all processes have shut down, to allow
    for a clean service shutdown.

    @ivar reactor: an L{IReactorProcess} for spawning processes, defaulting to
        the global reactor.

    @ivar delayInterval: the amount of time to wait between starting subsequent
        processes.

    @ivar stopping: a flag used to determine whether it is time to fire the
        Deferreds that track service shutdown.
    """

    threshold = 1
    killTime = 5
    minRestartDelay = 1
    maxRestartDelay = 3600

    def __init__(self, reactor=None):
        super(DelayedStartupProcessMonitor, self).__init__()
        if reactor is None:
            from twisted.internet import reactor
        self._reactor = reactor
        self.processes = {}
        self.protocols = {}
        self.delay = {}
        self.timeStarted = {}
        self.murder = {}
        self.restart = {}
        self.stopping = False
        if config.MultiProcess.StaggeredStartup.Enabled:
            self.delayInterval = config.MultiProcess.StaggeredStartup.Interval
        else:
            self.delayInterval = 0


    def addProcess(self, name, args, uid=None, gid=None, env={}):
        """
        Add a new monitored process and start it immediately if the
        L{DelayedStartupProcessMonitor} service is running.

        Note that args are passed to the system call, not to the shell. If
        running the shell is desired, the common idiom is to use
        C{ProcessMonitor.addProcess("name", ['/bin/sh', '-c', shell_script])}

        @param name: A name for this process.  This value must be
            unique across all processes added to this monitor.
        @type name: C{str}
        @param args: The argv sequence for the process to launch.
        @param uid: The user ID to use to run the process.  If C{None},
            the current UID is used.
        @type uid: C{int}
        @param gid: The group ID to use to run the process.  If C{None},
            the current GID is used.
        @type uid: C{int}
        @param env: The environment to give to the launched process. See
            L{IReactorProcess.spawnProcess}'s C{env} parameter.
        @type env: C{dict}
        @raises: C{KeyError} if a process with the given name already
            exists
        """
        class SimpleProcessObject(object):
            def getName(self):
                return name
            def getCommandLine(self):
                return args
            def getFileDescriptors(self):
                return []
        self.addProcessObject(SimpleProcessObject(), env, uid, gid)


    def addProcessObject(self, process, env, uid=None, gid=None):
        """
        Add a process object to be run when this service is started.

        @param env: a dictionary of environment variables.

        @param process: a L{TwistdSlaveProcesses} object to be started upon
            service startup.
        """
        name = process.getName()
        self.processes[name] = (process, env, uid, gid)
        self.delay[name] = self.minRestartDelay
        if self.running:
            self.startProcess(name)


    def startService(self):
        # Now we're ready to build the command lines and actually add the
        # processes to procmon.
        super(DelayedStartupProcessMonitor, self).startService()
        for name in self.processes:
            self.startProcess(name)


    def stopService(self):
        """
        Return a deferred that fires when all child processes have ended.
        """
        self.stopping = True
        self.deferreds = {}
        for name in self.processes:
            self.deferreds[name] = Deferred()
        super(DelayedStartupProcessMonitor, self).stopService()

        # Cancel any outstanding restarts
        for name, delayedCall in self.restart.items():
            if delayedCall.active():
                delayedCall.cancel()

        for name in self.processes:
            self.stopProcess(name)
        return gatherResults(self.deferreds.values())


    def removeProcess(self, name):
        """
        Stop the named process and remove it from the list of monitored
        processes.

        @type name: C{str}
        @param name: A string that uniquely identifies the process.
        """
        self.stopProcess(name)
        del self.processes[name]


    def stopProcess(self, name):
        """
        @param name: The name of the process to be stopped
        """
        if name not in self.processes:
            raise KeyError('Unrecognized process name: %s' % (name,))

        proto = self.protocols.get(name, None)
        if proto is not None:
            proc = proto.transport
            try:
                proc.signalProcess('TERM')
            except ProcessExitedAlready:
                pass
            else:
                self.murder[name] = self._reactor.callLater(
                                            self.killTime,
                                            self._forceStopProcess, proc)


    def processEnded(self, name):
        """
        When a child process has ended it calls me so I can fire the
        appropriate deferred which was created in stopService
        """
        # Cancel the scheduled _forceStopProcess function if the process
        # dies naturally
        if name in self.murder:
            if self.murder[name].active():
                self.murder[name].cancel()
            del self.murder[name]

        del self.protocols[name]

        if self._reactor.seconds() - self.timeStarted[name] < self.threshold:
            # The process died too fast - back off
            nextDelay = self.delay[name]
            self.delay[name] = min(self.delay[name] * 2, self.maxRestartDelay)

        else:
            # Process had been running for a significant amount of time
            # restart immediately
            nextDelay = 0
            self.delay[name] = self.minRestartDelay

        # Schedule a process restart if the service is running
        if self.running and name in self.processes:
            self.restart[name] = self._reactor.callLater(nextDelay,
                                                         self.startProcess,
                                                         name)
        if self.stopping:
            deferred = self.deferreds.pop(name, None)
            if deferred is not None:
                deferred.callback(None)


    def _forceStopProcess(self, proc):
        """
        @param proc: An L{IProcessTransport} provider
        """
        try:
            proc.signalProcess('KILL')
        except ProcessExitedAlready:
            pass


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
        Send a signal to a single monitored process, by name, if that process
        is running; otherwise, do nothing.

        @param signal: the signal to send
        @type signal: C{int}
        @param name: the name of the process to signal.
        @type signal: C{str}
        """
        if not name in self.protocols:
            return
        proc = self.protocols[name].transport
        try:
            proc.signalProcess(signal)
        except ProcessExitedAlready:
            pass


    def reallyStartProcess(self, name):
        """
        Actually start a process.  (Re-implemented here rather than just using
        the inherited implementation of startService because ProcessMonitor
        doesn't allow customization of subprocess environment).
        """
        if name in self.protocols:
            return
        p = self.protocols[name] = DelayedStartupLoggingProtocol()
        p.service = self
        p.name = name
        procObj, env, uid, gid = self.processes[name]
        self.timeStarted[name] = time()

        childFDs = {0 : "w", 1 : "r", 2 : "r"}

        childFDs.update(procObj.getFileDescriptors())

        args = procObj.getCommandLine()

        self._reactor.spawnProcess(
            p, args[0], args, uid=uid, gid=gid, env=env,
            childFDs=childFDs
        )

    _pendingStarts = 0

    def startProcess(self, name):
        """
        Start process named 'name'.  If another process has started recently,
        wait until some time has passed before actually starting this process.

        @param name: the name of the process to start.
        """
        interval = (self.delayInterval * self._pendingStarts)
        self._pendingStarts += 1
        def delayedStart():
            self._pendingStarts -= 1
            self.reallyStartProcess(name)
        self._reactor.callLater(interval, delayedStart)


    def restartAll(self):
        """
        Restart all processes. This is useful for third party management
        services to allow a user to restart servers because of an outside change
        in circumstances -- for example, a new version of a library is
        installed.
        """
        for name in self.processes:
            self.stopProcess(name)


    def __repr__(self):
        l = []
        for name, (procObj, uid, gid, _ignore_env) in self.processes.items():
            uidgid = ''
            if uid is not None:
                uidgid = str(uid)
            if gid is not None:
                uidgid += ':' + str(gid)

            if uidgid:
                uidgid = '(' + uidgid + ')'
            l.append('%r%s: %r' % (name, uidgid, procObj))
        return ('<' + self.__class__.__name__ + ' '
                + ' '.join(l)
                + '>')



class DelayedStartupLineLogger(object):
    """
    A line logger that can handle very long lines.
    """

    MAX_LENGTH = 1024
    CONTINUED_TEXT = " (truncated, continued)"
    tag = None
    exceeded = False  # Am I in the middle of parsing a long line?
    _buffer = ''

    def makeConnection(self, transport):
        """
        Ignore this IProtocol method, since I don't need a transport.
        """
        pass


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
        segments = self._breakLineIntoSegments(line)
        for segment in segments:
            self.lineReceived(segment)


    def _breakLineIntoSegments(self, line):
        """
        Break a line into segments no longer than self.MAX_LENGTH.  Each
        segment (except for the final one) has self.CONTINUED_TEXT appended.
        Returns the array of segments.
        @param line: The line to break up
        @type line: C{str}
        @return: array of C{str}
        """
        length = len(line)
        numSegments = length / self.MAX_LENGTH + (1 if length % self.MAX_LENGTH else 0)
        segments = []
        for i in range(numSegments):
            msg = line[i * self.MAX_LENGTH:(i + 1) * self.MAX_LENGTH]
            if i < numSegments - 1:  # not the last segment
                msg += self.CONTINUED_TEXT
            segments.append(msg)
        return segments



class DelayedStartupLoggingProtocol(ProcessProtocol):
    """
    Logging protocol that handles lines which are too long.
    """

    service = None
    name = None
    empty = 1

    def connectionMade(self):
        """
        Replace the superclass's output monitoring logic with one that can
        handle lineLengthExceeded.
        """
        self.output = DelayedStartupLineLogger()
        self.output.makeConnection(self.transport)
        self.output.tag = self.name


    def outReceived(self, data):
        self.output.dataReceived(data)
        self.empty = data[-1] == '\n'

    errReceived = outReceived


    def processEnded(self, reason):
        """
        Let the service know that this child process has ended
        """
        if not self.empty:
            self.output.dataReceived('\n')
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
            log.info("Obtained passphrase for %s" % (config.SSLPrivateKey))
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



def getSystemIDs(userName, groupName):
    """
    Return the system ID numbers corresponding to either:
    A) the userName and groupName if non-empty, or
    B) the real user ID and group ID of the process
    @param userName: The name of the user to look up the ID of.  An empty
        value indicates the real user ID of the process should be returned
        instead.
    @type userName: C{str}
    @param groupName: The name of the group to look up the ID of.  An empty
        value indicates the real group ID of the process should be returned
        instead.
    @type groupName: C{str}
    """
    if userName:
        try:
            uid = getpwnam(userName).pw_uid
        except KeyError:
            raise ConfigurationError("Invalid user name: %s" % (userName,))
    else:
        uid = getuid()

    if groupName:
        try:
            gid = getgrnam(groupName).gr_gid
        except KeyError:
            raise ConfigurationError("Invalid group name: %s" % (groupName,))
    else:
        gid = getgid()

    return uid, gid
