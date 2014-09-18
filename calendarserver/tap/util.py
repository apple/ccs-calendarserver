# -*- test-case-name: calendarserver.tap.test.test_caldav -*-
##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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

"""
Utilities for assembling the service and resource hierarchy.
"""

__all__ = [
    "FakeRequest",
    "getDBPool",
    "getRootResource",
    "getSSLPassphrase",
    "MemoryLimitService",
    "preFlightChecks",
]

import errno
import OpenSSL
import os
import psutil
from socket import fromfd, AF_UNIX, SOCK_STREAM, socketpair
from subprocess import Popen, PIPE
import sys


from twext.internet.ssl import ChainingOpenSSLContextFactory
from twext.python.filepath import CachingFilePath as FilePath
from twext.python.log import Logger
from txweb2.auth.basic import BasicCredentialFactory
from txweb2.dav import auth
from txweb2.dav.util import joinURL
from txweb2.http_headers import Headers
from txweb2.resource import Resource
from txweb2.static import File as FileResource

from twisted.application.service import Service
from twisted.cred.portal import Portal
from twisted.internet.defer import inlineCallbacks, returnValue, Deferred, succeed
from twisted.internet import reactor as _reactor
from twisted.internet.reactor import addSystemEventTrigger
from twisted.internet.tcp import Connection

from calendarserver.push.applepush import APNSubscriptionResource
from calendarserver.push.notifier import NotifierFactory
from twext.enterprise.adbapi2 import ConnectionPool, ConnectionPoolConnection
from twext.enterprise.ienterprise import ORACLE_DIALECT
from twext.enterprise.ienterprise import POSTGRES_DIALECT
from twistedcaldav.bind import doBind
from twistedcaldav.cache import CacheStoreNotifierFactory
from twistedcaldav.directory.addressbook import DirectoryAddressBookHomeProvisioningResource
from twistedcaldav.directory.calendar import DirectoryCalendarHomeProvisioningResource
from twistedcaldav.directory.digest import QopDigestCredentialFactory
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directorybackedaddressbook import DirectoryBackedAddressBookResource
from twistedcaldav.resource import AuthenticationWrapper
from twistedcaldav.simpleresource import SimpleResource, SimpleRedirectResource
from twistedcaldav.timezones import TimezoneCache
from twistedcaldav.timezoneservice import TimezoneServiceResource
from twistedcaldav.timezonestdservice import TimezoneStdServiceResource
from txdav.caldav.datastore.scheduling.ischedule.dkim import DKIMUtils, DomainKeyResource
from txdav.caldav.datastore.scheduling.ischedule.resource import IScheduleInboxResource


try:
    from twistedcaldav.authkerb import NegotiateCredentialFactory
    NegotiateCredentialFactory  # pacify pyflakes
except ImportError:
    NegotiateCredentialFactory = None

from twext.enterprise.adbapi2 import ConnectionPoolClient
from txdav.base.datastore.dbapiclient import DBAPIConnector, OracleConnector
from txdav.base.datastore.dbapiclient import postgresPreflight
from txdav.base.datastore.subpostgres import PostgresService

from calendarserver.accesslog import DirectoryLogWrapperResource
from calendarserver.provision.root import RootResource
from calendarserver.tools.util import checkDirectory
from calendarserver.webadmin.landing import WebAdminLandingResource
from calendarserver.webcal.resource import WebCalendarResource

from txdav.common.datastore.podding.resource import ConduitResource
from txdav.common.datastore.sql import CommonDataStore as CommonSQLDataStore
from txdav.common.datastore.file import CommonDataStore as CommonFileDataStore
from txdav.common.datastore.sql import current_sql_schema
from txdav.common.datastore.upgrade.sql.upgrade import NotAllowedToUpgrade
from twext.python.filepath import CachingFilePath
from urllib import quote
from twisted.python.usage import UsageError

from twext.who.checker import UsernamePasswordCredentialChecker
from twext.who.checker import HTTPDigestCredentialChecker
from twisted.cred.error import UnauthorizedLogin
from txweb2.dav.auth import IPrincipalCredentials

from twistedcaldav.config import ConfigurationError
from twistedcaldav.stdconfig import config


log = Logger()


def pgServiceFromConfig(config, subServiceFactory, uid=None, gid=None):
    """
    Construct a L{PostgresService} from a given configuration and subservice.

    @param config: the configuration to derive postgres configuration
        parameters from.

    @param subServiceFactory: A factory for the service to start once the
        L{PostgresService} has been initialized.

    @param uid: The user-ID to run the PostgreSQL server as.

    @param gid: The group-ID to run the PostgreSQL server as.

    @return: a service which can start postgres.

    @rtype: L{PostgresService}
    """
    dbRoot = CachingFilePath(config.DatabaseRoot)
    # Construct a PostgresService exactly as the parent would, so that we
    # can establish connection information.
    return PostgresService(
        dbRoot, subServiceFactory, current_sql_schema,
        databaseName=config.Postgres.DatabaseName,
        clusterName=config.Postgres.ClusterName,
        logFile=config.Postgres.LogFile,
        logDirectory=config.LogRoot if config.Postgres.LogRotation else "",
        socketDir=config.Postgres.SocketDirectory,
        listenAddresses=config.Postgres.ListenAddresses,
        sharedBuffers=config.Postgres.SharedBuffers,
        maxConnections=config.Postgres.MaxConnections,
        options=config.Postgres.Options,
        uid=uid, gid=gid,
        spawnedDBUser=config.SpawnedDBUser,
        importFileName=config.DBImportFile,
        pgCtl=config.Postgres.Ctl,
        initDB=config.Postgres.Init,
    )



def pgConnectorFromConfig(config):
    """
    Create a postgres DB-API connector from the given configuration.
    """
    import pgdb
    return DBAPIConnector(pgdb, postgresPreflight, config.DSN).connect



def oracleConnectorFromConfig(config):
    """
    Create a postgres DB-API connector from the given configuration.
    """
    return OracleConnector(config.DSN).connect



class ConnectionWithPeer(Connection):

    connected = True

    def getPeer(self):
        return "<peer: %r %r>" % (self.socket.fileno(), id(self))


    def getHost(self):
        return "<host: %r %r>" % (self.socket.fileno(), id(self))



def transactionFactoryFromFD(dbampfd, dialect, paramstyle):
    """
    Create a transaction factory from an inherited file descriptor, such as one
    created by L{ConnectionDispenser}.
    """
    skt = fromfd(dbampfd, AF_UNIX, SOCK_STREAM)
    os.close(dbampfd)
    protocol = ConnectionPoolClient(dialect=dialect, paramstyle=paramstyle)
    transport = ConnectionWithPeer(skt, protocol)
    protocol.makeConnection(transport)
    transport.startReading()
    return protocol.newTransaction



class ConnectionDispenser(object):
    """
    A L{ConnectionDispenser} can dispense already-connected file descriptors,
    for use with subprocess spawning.
    """
    # Very long term FIXME: this mechanism should ideally be eliminated, by
    # making all subprocesses have a single stdio AMP connection that
    # multiplexes between multiple protocols.

    def __init__(self, connectionPool):
        self.pool = connectionPool


    def dispense(self):
        """
        Dispense a socket object, already connected to a server, for a client
        in a subprocess.
        """
        # FIXME: these sockets need to be re-dispensed when the process is
        # respawned, and they currently won't be.
        c, s = socketpair(AF_UNIX, SOCK_STREAM)
        protocol = ConnectionPoolConnection(self.pool)
        transport = ConnectionWithPeer(s, protocol)
        protocol.makeConnection(transport)
        transport.startReading()
        return c



def storeFromConfig(config, txnFactory, directoryService):
    """
    Produce an L{IDataStore} from the given configuration, transaction factory,
    and notifier factory.

    If the transaction factory is C{None}, we will create a filesystem
    store.  Otherwise, a SQL store, using that connection information.
    """
    #
    # Configure NotifierFactory
    #
    notifierFactories = {}
    if config.Notifications.Enabled:
        notifierFactories["push"] = NotifierFactory(config.ServerHostName, config.Notifications.CoalesceSeconds)

    if config.EnableResponseCache and config.Memcached.Pools.Default.ClientEnabled:
        notifierFactories["cache"] = CacheStoreNotifierFactory()

    quota = config.UserQuota
    if quota == 0:
        quota = None
    if txnFactory is not None:
        if config.EnableSSL:
            uri = "https://{config.ServerHostName}:{config.SSLPort}".format(config=config)
        else:
            uri = "https://{config.ServerHostName}:{config.HTTPPort}".format(config=config)
        attachments_uri = uri + "/calendars/__uids__/%(home)s/dropbox/%(dropbox_id)s/%(name)s"
        store = CommonSQLDataStore(
            txnFactory, notifierFactories,
            directoryService,
            FilePath(config.AttachmentsRoot), attachments_uri,
            config.EnableCalDAV, config.EnableCardDAV,
            config.EnableManagedAttachments,
            quota=quota,
            logLabels=config.LogDatabase.LabelsInSQL,
            logStats=config.LogDatabase.Statistics,
            logStatsLogFile=config.LogDatabase.StatisticsLogFile,
            logSQL=config.LogDatabase.SQLStatements,
            logTransactionWaits=config.LogDatabase.TransactionWaitSeconds,
            timeoutTransactions=config.TransactionTimeoutSeconds,
            cacheQueries=config.QueryCaching.Enabled,
            cachePool=config.QueryCaching.MemcachedPool,
            cacheExpireSeconds=config.QueryCaching.ExpireSeconds
        )
    else:
        store = CommonFileDataStore(
            FilePath(config.DocumentRoot),
            notifierFactories, directoryService,
            config.EnableCalDAV, config.EnableCardDAV,
            quota=quota
        )

    # FIXME: NotifierFactories need a reference to the store in order
    # to get a txn in order to possibly create a Work item
    for notifierFactory in notifierFactories.values():
        notifierFactory.store = store
    return store



# MOVE2WHO -- should we move this class somewhere else?
class PrincipalCredentialChecker(object):
    credentialInterfaces = (IPrincipalCredentials,)

    @inlineCallbacks
    def requestAvatarId(self, credentials):
        credentials = IPrincipalCredentials(credentials)

        if credentials.authnPrincipal is None:
            raise UnauthorizedLogin(
                "No such user: {user}".format(
                    user=credentials.credentials.username
                )
            )

        # See if record is enabledForLogin
        if not credentials.authnPrincipal.record.isLoginEnabled():
            raise UnauthorizedLogin(
                "User not allowed to log in: {user}".format(
                    user=credentials.credentials.username
                )
            )

        # Handle Kerberos as a separate behavior
        try:
            from twistedcaldav.authkerb import NegotiateCredentials
        except ImportError:
            NegotiateCredentials = None

        if NegotiateCredentials and isinstance(credentials.credentials,
                                               NegotiateCredentials):
            # If we get here with Kerberos, then authentication has already succeeded
            returnValue(
                (
                    credentials.authnPrincipal,
                    credentials.authzPrincipal,
                )
            )
        else:
            if (yield credentials.authnPrincipal.record.verifyCredentials(credentials.credentials)):
                returnValue(
                    (
                        credentials.authnPrincipal,
                        credentials.authzPrincipal,
                    )
                )
            else:
                raise UnauthorizedLogin(
                    "Incorrect credentials for user: {user}".format(
                        user=credentials.credentials.username
                    )
                )



def getRootResource(config, newStore, resources=None):
    """
    Set up directory service and resource hierarchy based on config.
    Return root resource.

    Additional resources can be added to the hierarchy by passing a list of
    tuples containing: path, resource class, __init__ args list, and optional
    authentication schemes list ("basic", "digest").

    If the store is specified, then it has already been constructed, so use it.
    Otherwise build one with L{storeFromConfig}.
    """

    if newStore is None:
        raise RuntimeError("Internal error, 'newStore' must be specified.")

    if resources is None:
        resources = []

    # FIXME: this is only here to workaround circular imports
    doBind()

    #
    # Default resource classes
    #
    rootResourceClass = RootResource
    calendarResourceClass = DirectoryCalendarHomeProvisioningResource
    iScheduleResourceClass = IScheduleInboxResource
    conduitResourceClass = ConduitResource
    timezoneServiceResourceClass = TimezoneServiceResource
    timezoneStdServiceResourceClass = TimezoneStdServiceResource
    webCalendarResourceClass = WebCalendarResource
    webAdminResourceClass = WebAdminLandingResource
    addressBookResourceClass = DirectoryAddressBookHomeProvisioningResource
    directoryBackedAddressBookResourceClass = DirectoryBackedAddressBookResource
    apnSubscriptionResourceClass = APNSubscriptionResource
    principalResourceClass = DirectoryPrincipalProvisioningResource

    directory = newStore.directoryService()
    principalCollection = principalResourceClass("/principals/", directory)

    #
    # Configure the Site and Wrappers
    #
    wireEncryptedCredentialFactories = []
    wireUnencryptedCredentialFactories = []

    portal = Portal(auth.DavRealm())

    portal.registerChecker(UsernamePasswordCredentialChecker(directory))
    portal.registerChecker(HTTPDigestCredentialChecker(directory))
    portal.registerChecker(PrincipalCredentialChecker())

    realm = directory.realmName.encode("utf-8") or ""

    log.info("Configuring authentication for realm: {realm}", realm=realm)

    for scheme, schemeConfig in config.Authentication.iteritems():
        scheme = scheme.lower()

        credFactory = None

        if schemeConfig["Enabled"]:
            log.info("Setting up scheme: {scheme}", scheme=scheme)

            if scheme == "kerberos":
                if not NegotiateCredentialFactory:
                    log.info("Kerberos support not available")
                    continue

                try:
                    principal = schemeConfig["ServicePrincipal"]
                    if not principal:
                        credFactory = NegotiateCredentialFactory(
                            serviceType="HTTP",
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
                )

            elif scheme == "basic":
                credFactory = BasicCredentialFactory(realm)

            elif scheme == "wiki":
                pass

            else:
                log.error("Unknown scheme: {scheme}", scheme=scheme)

        if credFactory:
            wireEncryptedCredentialFactories.append(credFactory)
            if schemeConfig.get("AllowedOverWireUnencrypted", False):
                wireUnencryptedCredentialFactories.append(credFactory)

    #
    # Setup Resource hierarchy
    #
    log.info("Setting up document root at: {root}", root=config.DocumentRoot)

    if config.EnableCalDAV:
        log.info("Setting up calendar collection: {cls}", cls=calendarResourceClass)
        calendarCollection = calendarResourceClass(
            directory,
            "/calendars/",
            newStore,
        )
        principalCollection.calendarCollection = calendarCollection

    if config.EnableCardDAV:
        log.info("Setting up address book collection: {cls}", cls=addressBookResourceClass)
        addressBookCollection = addressBookResourceClass(
            directory,
            "/addressbooks/",
            newStore,
        )
        principalCollection.addressBookCollection = addressBookCollection

        if config.DirectoryAddressBook.Enabled and config.EnableSearchAddressBook:
            log.info(
                "Setting up directory address book: {cls}",
                cls=directoryBackedAddressBookResourceClass)

            directoryBackedAddressBookCollection = directoryBackedAddressBookResourceClass(
                principalCollections=(principalCollection,),
                principalDirectory=directory,
                uri=joinURL("/", config.DirectoryAddressBook.name, "/")
            )
            if _reactor._started:
                directoryBackedAddressBookCollection.provisionDirectory()
            else:
                addSystemEventTrigger("after", "startup", directoryBackedAddressBookCollection.provisionDirectory)
        else:
            # remove /directory from previous runs that may have created it
            directoryPath = os.path.join(config.DocumentRoot, config.DirectoryAddressBook.name)
            try:
                FilePath(directoryPath).remove()
                log.info("Deleted: {path}", path=directoryPath)
            except (OSError, IOError), e:
                if e.errno != errno.ENOENT:
                    log.error("Could not delete: {path} : {error}", path=directoryPath, error=e)

    log.info("Setting up root resource: {cls}", cls=rootResourceClass)

    root = rootResourceClass(
        config.DocumentRoot,
        principalCollections=(principalCollection,),
    )

    root.putChild("principals", principalCollection)
    if config.EnableCalDAV:
        root.putChild("calendars", calendarCollection)
    if config.EnableCardDAV:
        root.putChild('addressbooks', addressBookCollection)
        if config.DirectoryAddressBook.Enabled and config.EnableSearchAddressBook:
            root.putChild(config.DirectoryAddressBook.name, directoryBackedAddressBookCollection)

    # /.well-known
    if config.EnableWellKnown:
        log.info("Setting up .well-known collection resource")

        wellKnownResource = SimpleResource(
            principalCollections=(principalCollection,),
            isdir=True,
            defaultACL=SimpleResource.allReadACL
        )
        root.putChild(".well-known", wellKnownResource)
        for enabled, wellknown_name, redirected_to in (
            (config.EnableCalDAV, "caldav", "/",),
            (config.EnableCardDAV, "carddav", "/",),
            (config.TimezoneService.Enabled, "timezone", "/stdtimezones",),
            (config.Scheduling.iSchedule.Enabled, "ischedule", "/ischedule"),
        ):
            if enabled:
                if config.EnableSSL:
                    scheme = "https"
                    port = config.SSLPort
                else:
                    scheme = "http"
                    port = config.HTTPPort
                wellKnownResource.putChild(
                    wellknown_name,
                    SimpleRedirectResource(
                        principalCollections=(principalCollection,),
                        isdir=False,
                        defaultACL=SimpleResource.allReadACL,
                        scheme=scheme, port=port, path=redirected_to)
                )

    for alias in config.Aliases:
        url = alias.get("url", None)
        path = alias.get("path", None)
        if not url or not path or url[0] != "/":
            log.error("Invalid alias: URL: {url}  Path: {path}", url=url, path=path)
            continue
        urlbits = url[1:].split("/")
        parent = root
        for urlpiece in urlbits[:-1]:
            child = parent.getChild(urlpiece)
            if child is None:
                child = Resource()
                parent.putChild(urlpiece, child)
            parent = child
        if parent.getChild(urlbits[-1]) is not None:
            log.error("Invalid alias: URL: {url}  Path: {path} already exists", url=url, path=path)
            continue
        resource = FileResource(path)
        parent.putChild(urlbits[-1], resource)
        log.info("Added alias {url} -> {path}", url=url, path=path)

    # Need timezone cache before setting up any timezone service
    log.info("Setting up Timezone Cache")
    TimezoneCache.create()

    # Timezone service is optional
    if config.EnableTimezoneService:
        log.info(
            "Setting up time zone service resource: {cls}",
            cls=timezoneServiceResourceClass)

        timezoneService = timezoneServiceResourceClass(
            root,
        )
        root.putChild("timezones", timezoneService)

    # Standard Timezone service is optional
    if config.TimezoneService.Enabled:
        log.info(
            "Setting up standard time zone service resource: {cls}",
            cls=timezoneStdServiceResourceClass)

        timezoneStdService = timezoneStdServiceResourceClass(
            root,
        )
        root.putChild("stdtimezones", timezoneStdService)

        # TODO: we only want the master to do this
        if _reactor._started:
            _reactor.callLater(0, timezoneStdService.onStartup)
        else:
            addSystemEventTrigger("after", "startup", timezoneStdService.onStartup)

    #
    # iSchedule/cross-pod service for podding
    #
    if config.Servers.Enabled:
        log.info("Setting up iSchedule podding inbox resource: {cls}", cls=iScheduleResourceClass)

        ischedule = iScheduleResourceClass(
            root,
            newStore,
            podding=True
        )
        root.putChild(config.Servers.InboxName, ischedule)

        log.info("Setting up podding conduit resource: {cls}", cls=conduitResourceClass)

        conduit = conduitResourceClass(
            root,
            newStore,
        )
        root.putChild(config.Servers.ConduitName, conduit)

    #
    # iSchedule service (not used for podding)
    #
    if config.Scheduling.iSchedule.Enabled:
        log.info("Setting up iSchedule inbox resource: {cls}", cls=iScheduleResourceClass)

        ischedule = iScheduleResourceClass(
            root,
            newStore,
        )
        root.putChild("ischedule", ischedule)

        # Do DomainKey resources
        DKIMUtils.validConfiguration(config)
        if config.Scheduling.iSchedule.DKIM.Enabled:
            log.info("Setting up domainkey resource: {res}", res=DomainKeyResource)
            domain = config.Scheduling.iSchedule.DKIM.Domain if config.Scheduling.iSchedule.DKIM.Domain else config.ServerHostName
            dk = DomainKeyResource(
                domain,
                config.Scheduling.iSchedule.DKIM.KeySelector,
                config.Scheduling.iSchedule.DKIM.PublicKeyFile,
            )
            wellKnownResource.putChild("domainkey", dk)

    #
    # WebCal
    #
    if config.WebCalendarRoot:
        log.info(
            "Setting up WebCalendar resource: {res}",
            res=config.WebCalendarRoot)
        webCalendar = webCalendarResourceClass(
            config.WebCalendarRoot,
            principalCollections=(principalCollection,),
        )
        root.putChild("webcal", webCalendar)

    #
    # WebAdmin
    #
    if config.EnableWebAdmin:
        log.info("Setting up WebAdmin resource")
        webAdmin = webAdminResourceClass(
            config.WebCalendarRoot,
            root,
            directory,
            newStore,
            principalCollections=(principalCollection,),
        )
        root.putChild("admin", webAdmin)

    #
    # Apple Push Notification Subscriptions
    #
    apnConfig = config.Notifications.Services.APNS
    if apnConfig.Enabled:
        log.info(
            "Setting up APNS resource at /{url}",
            url=apnConfig["SubscriptionURL"])
        apnResource = apnSubscriptionResourceClass(root, newStore)
        root.putChild(apnConfig["SubscriptionURL"], apnResource)

    #
    # Configure ancillary data
    #
    # MOVE2WHO
    log.info("Configuring authentication wrapper")

    overrides = {}
    if resources:
        for path, cls, args, schemes in resources:

            # putChild doesn't want "/" starting the path
            root.putChild(path, cls(root, newStore, *args))

            # overrides requires "/" prepended
            path = "/" + path

            overrides[path] = []
            for scheme in schemes:
                if scheme == "basic":
                    overrides[path].append(BasicCredentialFactory(realm))

                elif scheme == "digest":
                    schemeConfig = config.Authentication.Digest
                    overrides[path].append(QopDigestCredentialFactory(
                        schemeConfig["Algorithm"],
                        schemeConfig["Qop"],
                        realm,
                    ))
            log.info(
                "Overriding {path} with {cls} ({schemes})",
                path=path, cls=cls, schemes=schemes)

    authWrapper = AuthenticationWrapper(
        root,
        portal,
        wireEncryptedCredentialFactories,
        wireUnencryptedCredentialFactories,
        (auth.IPrincipal,),
        overrides=overrides
    )

    logWrapper = DirectoryLogWrapperResource(
        authWrapper,
        directory,
    )

    # FIXME:  Storing a reference to the root resource on the store
    # until scheduling no longer needs resource objects
    newStore.rootResource = root

    return logWrapper



def getDBPool(config):
    """
    Inspect configuration to determine what database connection pool
    to set up.
    return: (L{ConnectionPool}, transactionFactory)
    """
    if config.DBType == 'oracle':
        dialect = ORACLE_DIALECT
        paramstyle = 'numeric'
    else:
        dialect = POSTGRES_DIALECT
        paramstyle = 'pyformat'
    pool = None
    if config.DBAMPFD:
        txnFactory = transactionFactoryFromFD(
            int(config.DBAMPFD), dialect, paramstyle
        )
    elif not config.UseDatabase:
        txnFactory = None
    elif not config.SharedConnectionPool:
        if config.DBType == '':
            # get a PostgresService to tell us what the local connection
            # info is, but *don't* start it (that would start one postgres
            # master per slave, resulting in all kinds of mayhem...)
            connectionFactory = pgServiceFromConfig(
                config, None).produceConnection
        elif config.DBType == 'postgres':
            connectionFactory = pgConnectorFromConfig(config)
        elif config.DBType == 'oracle':
            connectionFactory = oracleConnectorFromConfig(config)
        else:
            raise UsageError("unknown DB type: %r" % (config.DBType,))
        pool = ConnectionPool(connectionFactory, dialect=dialect,
                              paramstyle=paramstyle,
                              maxConnections=config.MaxDBConnectionsPerPool)
        txnFactory = pool.connection
    else:
        raise UsageError(
            "trying to use DB in slave, but no connection info from parent"
        )

    return (pool, txnFactory)



class FakeRequest(object):

    def __init__(self, rootResource, method, path, uri='/', transaction=None):
        self.rootResource = rootResource
        self.method = method
        self.path = path
        self.uri = uri
        self._resourcesByURL = {}
        self._urlsByResource = {}
        self.headers = Headers()
        if transaction is not None:
            self._newStoreTransaction = transaction


    @inlineCallbacks
    def _getChild(self, resource, segments):
        if not segments:
            returnValue(resource)

        child, remaining = (yield resource.locateChild(self, segments))
        returnValue((yield self._getChild(child, remaining)))


    @inlineCallbacks
    def locateResource(self, url):
        url = url.strip("/")
        segments = url.split("/")
        resource = (yield self._getChild(self.rootResource, segments))
        if resource:
            self._rememberResource(resource, url)
        returnValue(resource)


    @inlineCallbacks
    def locateChildResource(self, parent, childName):
        if parent is None or childName is None:
            returnValue(None)
        parentURL = self.urlForResource(parent)
        if not parentURL.endswith("/"):
            parentURL += "/"
        url = parentURL + quote(childName)
        segment = childName
        resource = (yield self._getChild(parent, [segment]))
        if resource:
            self._rememberResource(resource, url)
        returnValue(resource)


    def _rememberResource(self, resource, url):
        self._resourcesByURL[url] = resource
        self._urlsByResource[resource] = url
        return resource


    def _forgetResource(self, resource, url):
        if url in self._resourcesByURL:
            del self._resourcesByURL[url]
        if resource in self._urlsByResource:
            del self._urlsByResource[resource]


    def urlForResource(self, resource):
        url = self._urlsByResource.get(resource, None)
        if url is None:
            class NoURLForResourceError(RuntimeError):
                pass
            raise NoURLForResourceError(resource)
        return url


    def addResponseFilter(self, *args, **kwds):
        pass



def memoryForPID(pid, residentOnly=True):
    """
    Return the amount of memory in use for the given process.  If residentOnly is True,
        then RSS is returned; if False, then virtual memory is returned.
    @param pid: process id
    @type pid: C{int}
    @param residentOnly: Whether only resident memory should be included
    @type residentOnly: C{boolean}
    @return: Memory used by process in bytes
    @rtype: C{int}
    """
    memoryInfo = psutil.Process(pid).get_memory_info()
    return memoryInfo.rss if residentOnly else memoryInfo.vms



class MemoryLimitService(Service, object):
    """
    A service which when paired with a DelayedStartupProcessMonitor will periodically
    examine the memory usage of the monitored processes and stop any which exceed
    a configured limit.  Memcached processes are ignored.
    """

    def __init__(self, processMonitor, intervalSeconds, limitBytes, residentOnly, reactor=None):
        """
        @param processMonitor: the DelayedStartupProcessMonitor
        @param intervalSeconds: how often to check
        @type intervalSeconds: C{int}
        @param limitBytes: any monitored process over this limit is stopped
        @type limitBytes: C{int}
        @param residentOnly: whether only resident memory should be included
        @type residentOnly: C{boolean}
        @param reactor: for testing
        """
        self._processMonitor = processMonitor
        self._seconds = intervalSeconds
        self._bytes = limitBytes
        self._residentOnly = residentOnly
        self._delayedCall = None
        if reactor is None:
            from twisted.internet import reactor
        self._reactor = reactor

        # Unit tests can swap out _memoryForPID
        self._memoryForPID = memoryForPID


    def startService(self):
        """
        Start scheduling the memory checks
        """
        super(MemoryLimitService, self).startService()
        self._delayedCall = self._reactor.callLater(self._seconds, self.checkMemory)


    def stopService(self):
        """
        Stop checking memory
        """
        super(MemoryLimitService, self).stopService()
        if self._delayedCall is not None and self._delayedCall.active():
            self._delayedCall.cancel()
            self._delayedCall = None


    def checkMemory(self):
        """
        Stop any processes monitored by our paired processMonitor whose resident
        memory exceeds our configured limitBytes.  Reschedule intervalSeconds in
        the future.
        """
        try:
            for name in self._processMonitor.processes:
                if name.startswith("memcached"):
                    continue
                proto = self._processMonitor.protocols.get(name, None)
                if proto is not None:
                    proc = proto.transport
                    pid = proc.pid
                    try:
                        memory = self._memoryForPID(pid, self._residentOnly)
                    except Exception, e:
                        log.error(
                            "Unable to determine memory usage of PID: {pid} ({err})",
                            pid=pid, err=e)
                        continue
                    if memory > self._bytes:
                        log.warn(
                            "Killing large process: {name} PID:{pid} {memtype}:{mem}",
                            name=name, pid=pid,
                            memtype=("Resident" if self._residentOnly else "Virtual"),
                            mem=memory)
                        self._processMonitor.stopProcess(name)
        finally:
            self._delayedCall = self._reactor.callLater(self._seconds, self.checkMemory)



def checkDirectories(config):
    """
    Make sure that various key directories exist (and create if needed)
    """

    #
    # Verify that server root actually exists
    #
    checkDirectory(
        config.ServerRoot,
        "Server root",
        # Require write access because one might not allow editing on /
        access=os.W_OK,
        wait=True  # Wait in a loop until ServerRoot exists
    )

    #
    # Verify that other root paths are OK
    #
    if config.DataRoot.startswith(config.ServerRoot + os.sep):
        checkDirectory(
            config.DataRoot,
            "Data root",
            access=os.W_OK,
            create=(0750, config.UserName, config.GroupName),
        )
    if config.DocumentRoot.startswith(config.DataRoot + os.sep):
        checkDirectory(
            config.DocumentRoot,
            "Document root",
            # Don't require write access because one might not allow editing on /
            access=os.R_OK,
            create=(0750, config.UserName, config.GroupName),
        )
    if config.ConfigRoot.startswith(config.ServerRoot + os.sep):
        checkDirectory(
            config.ConfigRoot,
            "Config root",
            access=os.W_OK,
            create=(0750, config.UserName, config.GroupName),
        )
    # Always create  these:
    checkDirectory(
        config.LogRoot,
        "Log root",
        access=os.W_OK,
        create=(0750, config.UserName, config.GroupName),
    )
    checkDirectory(
        config.RunRoot,
        "Run root",
        access=os.W_OK,
        create=(0770, config.UserName, config.GroupName),
    )



class Stepper(object):
    """
    Manages the sequential, deferred execution of "steps" which are objects
    implementing these methods:

        - stepWithResult(result)
            @param result: the result returned from the previous step
            @returns: Deferred

        - stepWithFailure(failure)
            @param failure: a Failure encapsulating the exception from the
                previous step
            @returns: Failure to continue down the errback chain, or a
                Deferred returning a non-Failure to switch back to the
                callback chain

    "Step" objects are added in order by calling addStep(), and when start()
    is called, the Stepper will call the stepWithResult() of the first step.
    If stepWithResult() doesn't raise an Exception, the Stepper will call the
    next step's stepWithResult().  If a stepWithResult() raises an Exception,
    the Stepper will call the next step's stepWithFailure() -- if it's
    implemented -- passing it a Failure object.  If the stepWithFailure()
    decides it can handle the Failure and proceed, it can return a non-Failure
    which is an indicator to the Stepper to call the next step's
    stepWithResult().

    TODO: Create an IStep interface (?)
    """

    def __init__(self):
        self.steps = []
        self.failure = None
        self.result = None
        self.running = False


    def addStep(self, step):
        """
        Adds a step object to the ordered list of steps

        @param step: the object to add
        @type step: an object implementing stepWithResult()

        @return: the Stepper object itself so addStep() calls can be chained
        """
        if self.running:
            raise RuntimeError("Can't add step after start")
        self.steps.append(step)
        return self


    def defaultStepWithResult(self, result):
        return succeed(result)


    def defaultStepWithFailure(self, failure):
        if failure.type not in (
            NotAllowedToUpgrade, ConfigurationError,
            OpenSSL.SSL.Error
        ):
            log.failure("Step failure", failure=failure)
        return failure

    # def protectStep(self, callback):
    #     def _protected(result):
    #         try:
    #             return callback(result)
    #         except Exception, e:
    #             # TODO: how to turn Exception into Failure
    #             return Failure()
    #     return _protected


    def start(self, result=None):
        """
        Begin executing the added steps in sequence.  If a step object
        does not implement a stepWithResult/stepWithFailure method, a
        default implementation will be used.

        @param result: an optional value to pass to the first step
        @return: the Deferred that will fire when steps are done
        """
        self.running = True
        self.deferred = Deferred()

        for step in self.steps:

            # See if we need to use a default implementation of the step methods:
            if hasattr(step, "stepWithResult"):
                callBack = step.stepWithResult
                # callBack = self.protectStep(step.stepWithResult)
            else:
                callBack = self.defaultStepWithResult
            if hasattr(step, "stepWithFailure"):
                errBack = step.stepWithFailure
            else:
                errBack = self.defaultStepWithFailure

            # Add callbacks to the Deferred
            self.deferred.addCallbacks(callBack, errBack)

        # Get things going
        self.deferred.callback(result)

        return self.deferred



def requestShutdown(programPath, reason):
    """
    Log the shutdown reason and call the shutdown-requesting program.

    In the case the service is spawned by launchd (or equivalent), if our
    service decides it needs to shut itself down, because of a misconfiguration,
    for example, we can't just exit.  We may need to go through the system
    machinery to unload our job, manage reverse proxies, update admin UI, etc.
    Therefore you can configure the ServiceDisablingProgram plist key to point
    to a program to run which will stop our service.

    @param programPath: the full path to a program to call (with no args)
    @type programPath: C{str}
    @param reason: a shutdown reason to log
    @type reason: C{str}
    """
    log.error("Shutting down Calendar and Contacts server")
    log.error(reason)
    Popen(
        args=[config.ServiceDisablingProgram],
        stdout=PIPE,
        stderr=PIPE,
    ).communicate()



def preFlightChecks(config):
    """
    Perform checks prior to spawning any processes.  Returns True if the checks
    are ok, False if they don't and we have a ServiceDisablingProgram configured.
    Otherwise exits.
    """

    success, reason = verifyConfig(config)

    if success:
        success, reason = verifyTLSCertificate(config)

    if success:
        success, reason = verifyAPNSCertificate(config)

    if not success:
        if config.ServiceDisablingProgram:
            # If pre-flight checks fail, we don't want launchd to
            # repeatedly launch us, we want our job to get unloaded.
            # If the config.ServiceDisablingProgram is assigned and exists
            # we schedule it to run after startService finishes.
            # Its job is to carry out the platform-specific tasks of disabling
            # the service.
            if os.path.exists(config.ServiceDisablingProgram):
                addSystemEventTrigger(
                    "after", "startup",
                    requestShutdown, config.ServiceDisablingProgram, reason
                )
            return False

        else:
            sys.exit(1)

    return True



def verifyConfig(config):
    """
    At least one of EnableCalDAV or EnableCardDAV must be True
    """

    if config.EnableCalDAV or config.EnableCardDAV:
        return True, "A protocol is enabled"

    return False, "Neither CalDAV nor CardDAV are enabled"



def verifyTLSCertificate(config):
    """
    If a TLS certificate is configured, make sure it exists, is non empty,
    and that it's valid.
    """

    if config.SSLCertificate:
        if not os.path.exists(config.SSLCertificate):
            message = (
                "The configured TLS certificate ({cert}) is missing".format(
                    cert=config.SSLCertificate
                )
            )
            return False, message
    else:
        return True, "TLS disabled"

    length = os.stat(config.SSLCertificate).st_size
    if length == 0:
            message = (
                "The configured TLS certificate ({cert}) is empty".format(
                    cert=config.SSLCertificate
                )
            )
            return False, message

    try:
        ChainingOpenSSLContextFactory(
            config.SSLPrivateKey,
            config.SSLCertificate,
            certificateChainFile=config.SSLAuthorityChain,
            passwdCallback=getSSLPassphrase,
            sslmethod=getattr(OpenSSL.SSL, config.SSLMethod),
            ciphers=config.SSLCiphers.strip()
        )
    except Exception as e:
        message = (
            "The configured TLS certificate ({cert}) cannot be used: {reason}".format(
                cert=config.SSLCertificate,
                reason=str(e)
            )
        )
        return False, message

    return True, "TLS enabled"



def verifyAPNSCertificate(config):
    """
    If APNS certificates are configured, make sure they're valid.
    """

    if config.Notifications.Services.APNS.Enabled:

        for protocol in ("CalDAV", "CardDAV"):
            protoConfig = config.Notifications.Services.APNS[protocol]

            if not os.path.exists(protoConfig.CertificatePath):
                message = (
                    "The {proto} APNS certificate ({cert}) is missing".format(
                        proto=protocol,
                        cert=protoConfig.CertificatePath
                    )
                )
                return False, message

            try:
                if protoConfig.Passphrase:
                    passwdCallback = lambda *ignored: protoConfig.Passphrase
                else:
                    passwdCallback = None

                ChainingOpenSSLContextFactory(
                    protoConfig.PrivateKeyPath,
                    protoConfig.CertificatePath,
                    certificateChainFile=protoConfig.AuthorityChainPath,
                    passwdCallback=passwdCallback,
                    sslmethod=getattr(OpenSSL.SSL, "TLSv1_METHOD"),
                )
            except Exception as e:
                message = (
                    "The {proto} APNS certificate ({cert}) cannot be used: {reason}".format(
                        proto=protocol,
                        cert=protoConfig.CertificatePath,
                        reason=str(e)
                    )
                )
                return False, message

        return True, "APNS enabled"

    else:
        return True, "APNS disabled"



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
            log.error(
                "Could not get passphrase for {key}: {error}",
                key=config.SSLPrivateKey, error=error
            )
        else:
            log.info(
                "Obtained passphrase for {key}", key=config.SSLPrivateKey
            )
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
            log.error(
                "Could not get private key type for {key}",
                key=config.SSLPrivateKey
            )
        else:
            child = Popen(
                args=[
                    config.SSLPassPhraseDialog,
                    "{}:{}".format(config.ServerHostName, config.SSLPort),
                    keyType,
                ],
                stdout=PIPE, stderr=PIPE,
            )
            output, error = child.communicate()

            if child.returncode:
                log.error(
                    "Could not get passphrase for {key}: {error}",
                    key=config.SSLPrivateKey, error=error
                )
            else:
                return output.strip()

    return None
