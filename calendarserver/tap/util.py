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

"""
Utilities for assembling the service and resource hierarchy.
"""

__all__ = [
    "getRootResource",
    "getDBPool",
    "FakeRequest",
    "MemoryLimitService",
]

import errno
import os
from time import sleep
from socket import fromfd, AF_UNIX, SOCK_STREAM, socketpair
import psutil

from twext.python.filepath import CachingFilePath as FilePath
from twext.python.log import Logger
from twext.web2.auth.basic import BasicCredentialFactory
from twext.web2.dav import auth
from twext.web2.http_headers import Headers
from twext.web2.static import File as FileResource

from twisted.application.service import Service
from twisted.cred.portal import Portal
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor as _reactor
from twisted.internet.reactor import addSystemEventTrigger
from twisted.internet.tcp import Connection
from twisted.python.reflect import namedClass

from twistedcaldav.bind import doBind
from twistedcaldav.directory import calendaruserproxy
from twistedcaldav.directory.addressbook import DirectoryAddressBookHomeProvisioningResource
from twistedcaldav.directory.aggregate import AggregateDirectoryService
from twistedcaldav.directory.calendar import DirectoryCalendarHomeProvisioningResource
from twistedcaldav.directory.digest import QopDigestCredentialFactory
from twistedcaldav.directory.directory import GroupMembershipCache
from twistedcaldav.directory.internal import InternalDirectoryService
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory.wiki import WikiDirectoryService
from calendarserver.push.notifier import NotifierFactory 
from calendarserver.push.applepush import APNSubscriptionResource
from twistedcaldav.directorybackedaddressbook import DirectoryBackedAddressBookResource
from twistedcaldav.resource import AuthenticationWrapper
from twistedcaldav.scheduling.ischedule.dkim import DKIMUtils, DomainKeyResource
from twistedcaldav.scheduling.ischedule.resource import IScheduleInboxResource
from twistedcaldav.simpleresource import SimpleResource, SimpleRedirectResource
from twistedcaldav.timezones import TimezoneCache
from twistedcaldav.timezoneservice import TimezoneServiceResource
from twistedcaldav.timezonestdservice import TimezoneStdServiceResource
from twistedcaldav.util import getMemorySize, getNCPU
from twext.enterprise.ienterprise import POSTGRES_DIALECT
from twext.enterprise.ienterprise import ORACLE_DIALECT
from twext.enterprise.adbapi2 import ConnectionPool, ConnectionPoolConnection


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
from calendarserver.webadmin.resource import WebAdminResource
from calendarserver.webcal.resource import WebCalendarResource

from txdav.common.datastore.sql import CommonDataStore as CommonSQLDataStore
from txdav.common.datastore.file import CommonDataStore as CommonFileDataStore
from txdav.common.datastore.sql import current_sql_schema
from twext.python.filepath import CachingFilePath
from urllib import quote
from twisted.python.usage import UsageError


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
        logFile=config.Postgres.LogFile,
        socketDir=config.RunRoot,
        listenAddresses=config.Postgres.ListenAddresses,
        sharedBuffers=config.Postgres.SharedBuffers,
        maxConnections=config.Postgres.MaxConnections,
        options=config.Postgres.Options,
        uid=uid, gid=gid,
        spawnedDBUser=config.SpawnedDBUser,
        importFileName=config.DBImportFile
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



def storeFromConfig(config, txnFactory):
    """
    Produce an L{IDataStore} from the given configuration, transaction factory,
    and notifier factory.

    If the transaction factory is C{None}, we will create a filesystem
    store.  Otherwise, a SQL store, using that connection information.
    """
    #
    # Configure NotifierFactory
    #
    if config.Notifications.Enabled:
        # FIXME: NotifierFactory needs reference to the store in order
        # to get a txn in order to create a Work item
        notifierFactory = NotifierFactory(None, config.ServerHostName)
    else:
        notifierFactory = None
    quota = config.UserQuota
    if quota == 0:
        quota = None
    if txnFactory is not None:
        if config.EnableSSL:
            uri = "https://%s:%s" % (config.ServerHostName, config.SSLPort,)
        else:
            uri = "http://%s:%s" % (config.ServerHostName, config.HTTPPort,)
        attachments_uri = uri + "/calendars/__uids__/%(home)s/dropbox/%(dropbox_id)s/%(name)s"
        store = CommonSQLDataStore(
            txnFactory, notifierFactory,
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
            notifierFactory, config.EnableCalDAV, config.EnableCardDAV,
            quota=quota
        )
    if notifierFactory is not None:
        notifierFactory.store = store
    return store



def directoryFromConfig(config):
    """
    Create an L{AggregateDirectoryService} from the given configuration.
    """
    #
    # Setup the Augment Service
    #
    if config.AugmentService.type:
        augmentClass = namedClass(config.AugmentService.type)
        log.info("Configuring augment service of type: %s" % (augmentClass,))
        try:
            augmentService = augmentClass(**config.AugmentService.params)
        except IOError:
            log.error("Could not start augment service")
            raise
    else:
        augmentService = None

    #
    # Setup the group membership cacher
    #
    if config.GroupCaching.Enabled:
        groupMembershipCache = GroupMembershipCache(
            config.GroupCaching.MemcachedPool,
            expireSeconds=config.GroupCaching.ExpireSeconds)
    else:
        groupMembershipCache = None

    #
    # Setup the Directory
    #
    directories = []

    directoryClass = namedClass(config.DirectoryService.type)
    principalResourceClass = DirectoryPrincipalProvisioningResource

    log.info("Configuring directory service of type: %s"
        % (config.DirectoryService.type,))

    config.DirectoryService.params.augmentService = augmentService
    config.DirectoryService.params.groupMembershipCache = groupMembershipCache
    baseDirectory = directoryClass(config.DirectoryService.params)

    # Wait for the directory to become available
    while not baseDirectory.isAvailable():
        sleep(5)

    directories.append(baseDirectory)

    #
    # Setup the Locations and Resources Service
    #
    if config.ResourceService.Enabled:
        resourceClass = namedClass(config.ResourceService.type)

        log.info("Configuring resource service of type: %s" % (resourceClass,))

        config.ResourceService.params.augmentService = augmentService
        config.ResourceService.params.groupMembershipCache = groupMembershipCache
        resourceDirectory = resourceClass(config.ResourceService.params)
        resourceDirectory.realmName = baseDirectory.realmName
        directories.append(resourceDirectory)

    #
    # Add wiki directory service
    #
    if config.Authentication.Wiki.Enabled:
        wikiDirectory = WikiDirectoryService()
        wikiDirectory.realmName = baseDirectory.realmName
        directories.append(wikiDirectory)

    #
    # Add internal directory service
    # Right now we only use this for CardDAV
    #
    if config.EnableCardDAV:
        internalDirectory = InternalDirectoryService(baseDirectory.realmName)
        directories.append(internalDirectory)

    directory = AggregateDirectoryService(directories, groupMembershipCache)

    #
    # Use system-wide realm on OSX
    #
    try:
        import ServerFoundation
        realmName = ServerFoundation.XSAuthenticator.defaultRealm().encode("utf-8")
        directory.setRealm(realmName)
    except ImportError:
        pass
    log.info("Setting up principal collection: %r"
                  % (principalResourceClass,))
    principalResourceClass("/principals/", directory)
    return directory



def getRootResource(config, newStore, resources=None, directory=None):
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
    timezoneServiceResourceClass = TimezoneServiceResource
    timezoneStdServiceResourceClass = TimezoneStdServiceResource
    webCalendarResourceClass = WebCalendarResource
    webAdminResourceClass = WebAdminResource
    addressBookResourceClass = DirectoryAddressBookHomeProvisioningResource
    directoryBackedAddressBookResourceClass = DirectoryBackedAddressBookResource
    apnSubscriptionResourceClass = APNSubscriptionResource

    if directory is None:
        directory = directoryFromConfig(config)

    #
    # Setup the ProxyDB Service
    #
    proxydbClass = namedClass(config.ProxyDBService.type)

    log.info("Configuring proxydb service of type: %s" % (proxydbClass,))

    try:
        calendaruserproxy.ProxyDBService = proxydbClass(**config.ProxyDBService.params)
    except IOError:
        log.error("Could not start proxydb service")
        raise

    #
    # Configure the Site and Wrappers
    #
    wireEncryptedCredentialFactories = []
    wireUnencryptedCredentialFactories = []

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
                            type="HTTP",
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
                log.error("Unknown scheme: %s" % (scheme,))

        if credFactory:
            wireEncryptedCredentialFactories.append(credFactory)
            if schemeConfig.get("AllowedOverWireUnencrypted", False):
                wireUnencryptedCredentialFactories.append(credFactory)

    #
    # Setup Resource hierarchy
    #
    log.info("Setting up document root at: %s" % (config.DocumentRoot,))

    principalCollection = directory.principalCollection

    if config.EnableCalDAV:
        log.info("Setting up calendar collection: %r" % (calendarResourceClass,))
        calendarCollection = calendarResourceClass(
            directory,
            "/calendars/",
            newStore,
        )

    if config.EnableCardDAV:
        log.info("Setting up address book collection: %r" % (addressBookResourceClass,))
        addressBookCollection = addressBookResourceClass(
            directory,
            "/addressbooks/",
            newStore,
        )

        directoryPath = os.path.join(config.DocumentRoot, config.DirectoryAddressBook.name)
        if config.DirectoryAddressBook.Enabled and config.EnableSearchAddressBook:
            log.info("Setting up directory address book: %r" % (directoryBackedAddressBookResourceClass,))

            directoryBackedAddressBookCollection = directoryBackedAddressBookResourceClass(
                principalCollections=(principalCollection,)
            )
            if _reactor._started:
                directoryBackedAddressBookCollection.provisionDirectory()
            else:
                addSystemEventTrigger("after", "startup", directoryBackedAddressBookCollection.provisionDirectory)
        else:
            # remove /directory from previous runs that may have created it
            try:
                FilePath(directoryPath).remove()
                log.info("Deleted: %s" % directoryPath)
            except (OSError, IOError), e:
                if e.errno != errno.ENOENT:
                    log.error("Could not delete: %s : %r" % (directoryPath, e,))

    log.info("Setting up root resource: %r" % (rootResourceClass,))

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

    for name, info in config.Aliases.iteritems():
        if os.path.sep in name or not info.get("path", None):
            log.error("Invalid alias: %s" % (name,))
            continue
        log.info("Adding alias %s -> %s" % (name, info["path"]))
        resource = FileResource(info["path"])
        root.putChild(name, resource)

    # Timezone service is optional
    if config.EnableTimezoneService:
        log.info("Setting up time zone service resource: %r"
                      % (timezoneServiceResourceClass,))

        timezoneService = timezoneServiceResourceClass(
            root,
        )
        root.putChild("timezones", timezoneService)

    # Standard Timezone service is optional
    if config.TimezoneService.Enabled:
        log.info("Setting up standard time zone service resource: %r"
                      % (timezoneStdServiceResourceClass,))

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
    # iSchedule service
    #
    if config.Scheduling.iSchedule.Enabled:
        log.info("Setting up iSchedule inbox resource: %r"
                      % (iScheduleResourceClass,))

        ischedule = iScheduleResourceClass(
            root,
            newStore,
        )
        root.putChild("ischedule", ischedule)

        # Do DomainKey resources
        DKIMUtils.validConfiguration(config)
        if config.Scheduling.iSchedule.DKIM.Enabled:
            log.info("Setting up domainkey resource: %r" % (DomainKeyResource,))
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
        log.info("Setting up WebCalendar resource: %s"
                      % (config.WebCalendarRoot,))
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
            principalCollections=(principalCollection,),
        )
        root.putChild("admin", webAdmin)

    #
    # Apple Push Notification Subscriptions
    #
    apnConfig = config.Notifications.Services.APNS
    if apnConfig.Enabled:
        log.info("Setting up APNS resource at /%s" %
            (apnConfig["SubscriptionURL"],))
        apnResource = apnSubscriptionResourceClass(root, newStore)
        root.putChild(apnConfig["SubscriptionURL"], apnResource)

    #
    # Configure ancillary data
    #
    log.info("Setting up Timezone Cache")
    TimezoneCache.create()

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
            log.info("Overriding %s with %s (%s)" % (path, cls, schemes))

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



def computeProcessCount(minimum, perCPU, perGB, cpuCount=None, memSize=None):
    """
    Determine how many process to spawn based on installed RAM and CPUs,
    returning at least "mininum"
    """

    if cpuCount is None:
        try:
            cpuCount = getNCPU()
        except NotImplementedError, e:
            log.error("Unable to detect number of CPUs: %s" % (str(e),))
            return minimum

    if memSize is None:
        try:
            memSize = getMemorySize()
        except NotImplementedError, e:
            log.error("Unable to detect amount of installed RAM: %s" % (str(e),))
            return minimum

    countByCore = perCPU * cpuCount
    countByMemory = perGB * (memSize / (1024 * 1024 * 1024))

    # Pick the smaller of the two:
    count = min(countByCore, countByMemory)

    # ...but at least "minimum"
    return max(count, minimum)



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
                        log.error("Unable to determine memory usage of PID: %d (%s)" % (pid, e))
                        continue
                    if memory > self._bytes:
                        log.warn("Killing large process: %s PID:%d %s:%d" %
                            (name, pid, "Resident" if self._residentOnly else "Virtual", memory))
                        self._processMonitor.stopProcess(name)
        finally:
            self._delayedCall = self._reactor.callLater(self._seconds, self.checkMemory)
