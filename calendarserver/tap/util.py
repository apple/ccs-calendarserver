# -*- test-case-name: calendarserver.tap.test.test_caldav -*-
##
# Copyright (c) 2005-2011 Apple Inc. All rights reserved.
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
    "FakeRequest",
]

import errno
import os
from time import sleep
from socket import fromfd, AF_UNIX, SOCK_STREAM

from twext.python.filepath import CachingFilePath as FilePath
from twext.python.log import Logger
from twext.web2.auth.basic import BasicCredentialFactory
from twext.web2.dav import auth
from twext.web2.http_headers import Headers
from twext.web2.resource import RedirectResource
from twext.web2.static import File as FileResource

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
from twistedcaldav.directory.sudo import SudoDirectoryService
from twistedcaldav.directory.wiki import WikiDirectoryService
from twistedcaldav.notify import NotifierFactory, getPubSubConfiguration
from twistedcaldav.directorybackedaddressbook import DirectoryBackedAddressBookResource
from twistedcaldav.resource import CalDAVResource, AuthenticationWrapper
from twistedcaldav.schedule import IScheduleInboxResource
from twistedcaldav.simpleresource import SimpleResource
from twistedcaldav.timezones import TimezoneCache
from twistedcaldav.timezoneservice import TimezoneServiceResource
from twistedcaldav.timezonestdservice import TimezoneStdServiceResource
from twistedcaldav.util import getMemorySize, getNCPU

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
        uid=uid, gid=gid
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



def transactionFactoryFromFD(dbampfd):
    """
    Create a transaction factory from an inherited file descriptor.
    """
    skt = fromfd(dbampfd, AF_UNIX, SOCK_STREAM)
    os.close(dbampfd)
    protocol = ConnectionPoolClient()
    transport = ConnectionWithPeer(skt, protocol)
    protocol.makeConnection(transport)
    transport.startReading()
    return protocol.newTransaction



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
        notifierFactory = NotifierFactory(
            config.Notifications.InternalNotificationHost,
            config.Notifications.InternalNotificationPort,
            pubSubConfig=getPubSubConfiguration(config)
        )
    else:
        notifierFactory = None
    quota = config.UserQuota
    if quota == 0:
        quota = None
    if txnFactory is not None:
        return CommonSQLDataStore(
            txnFactory, notifierFactory, FilePath(config.AttachmentsRoot),
            config.EnableCalDAV, config.EnableCardDAV,
            quota=quota
        )
    else:
        return CommonFileDataStore(
            FilePath(config.DocumentRoot),
            notifierFactory, config.EnableCalDAV, config.EnableCardDAV,
            quota=quota
        )



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
    principalResourceClass       = DirectoryPrincipalProvisioningResource

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
    # Add sudoers directory
    #
    sudoDirectory = None

    if config.SudoersFile and os.path.exists(config.SudoersFile):
        log.info("Configuring SudoDirectoryService with file: %s"
                      % (config.SudoersFile,))

        sudoDirectory = SudoDirectoryService(config.SudoersFile)
        sudoDirectory.realmName = baseDirectory.realmName

        CalDAVResource.sudoDirectory = sudoDirectory
        directories.insert(0, sudoDirectory)
    else:
        log.info( "Not using SudoDirectoryService; file doesn't exist: %s"
            % (config.SudoersFile,)
        )

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

    if sudoDirectory:
        directory.userRecordTypes.insert(0,
            SudoDirectoryService.recordType_sudoers)

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


def getRootResource(config, newStore, resources=None):
    """
    Set up directory service and resource hierarchy based on config.
    Return root resource.

    Additional resources can be added to the hierarchy by passing a list of
    tuples containing: path, resource class, __init__ args list, and optional
    authentication scheme ("basic" or "digest").

    If the store is specified, then it has already been constructed, so use it.
    Otherwise build one with L{storeFromConfig}.
    """

    if newStore is None:
        raise RuntimeError("Internal error, 'newStore' must be specified.")

    # FIXME: this is only here to workaround circular imports
    doBind()

    #
    # Default resource classes
    #
    rootResourceClass               = RootResource
    calendarResourceClass           = DirectoryCalendarHomeProvisioningResource
    iScheduleResourceClass          = IScheduleInboxResource
    timezoneServiceResourceClass    = TimezoneServiceResource
    timezoneStdServiceResourceClass = TimezoneStdServiceResource
    webCalendarResourceClass        = WebCalendarResource
    webAdminResourceClass           = WebAdminResource
    addressBookResourceClass        = DirectoryAddressBookHomeProvisioningResource
    directoryBackedAddressBookResourceClass = DirectoryBackedAddressBookResource

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
            credentialFactories.append(credFactory)


    #
    # Setup Resource hierarchy
    #
    log.info("Setting up document root at: %s"
                  % (config.DocumentRoot,))

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
                log.info("Deleted: %s" %    directoryPath)
            except (OSError, IOError), e:
                if e.errno != errno.ENOENT:
                    log.error("Could not delete: %s : %r" %  (directoryPath, e,))

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
                    RedirectResource(scheme=scheme, port=port, path=redirected_to)
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

    # iSchedule service is optional
    if config.Scheduling.iSchedule.Enabled:
        log.info("Setting up iSchedule inbox resource: %r"
                      % (iScheduleResourceClass,))

        ischedule = iScheduleResourceClass(
            root,
            newStore,
        )
        root.putChild("ischedule", ischedule)

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
    # Configure ancillary data
    #
    log.info("Setting up Timezone Cache")
    TimezoneCache.create()


    log.info("Configuring authentication wrapper")

    overrides = { }
    if resources:
        for path, cls, args, scheme in resources:

            # putChild doesn't want "/" starting the path
            root.putChild(path, cls(root, newStore, *args))

            # overrides requires "/" prepended
            path = "/" + path

            if scheme == "basic":
                overrides[path] = (BasicCredentialFactory(realm),)

            elif scheme == "digest":
                schemeConfig = config.Authentication.Digest
                overrides[path] = (QopDigestCredentialFactory(
                    schemeConfig["Algorithm"],
                    schemeConfig["Qop"],
                    realm,
                ),)
            log.info("Overriding %s with %s (%s)" % (path, cls, scheme))

    authWrapper = AuthenticationWrapper(
        root,
        portal,
        credentialFactories,
        (auth.IPrincipal,),
        overrides=overrides,
    )

    logWrapper = DirectoryLogWrapperResource(
        authWrapper,
        directory,
    )

    return logWrapper



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

    def __init__(self, rootResource, method, path):
        self.rootResource = rootResource
        self.method = method
        self.path = path
        self._resourcesByURL = {}
        self._urlsByResource = {}
        self.headers = Headers()

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
        if self._resourcesByURL.has_key(url):
            del self._resourcesByURL[url]
        if self._urlsByResource.has_key(resource):
            del self._urlsByResource[resource]

    def urlForResource(self, resource):
        url = self._urlsByResource.get(resource, None)
        if url is None:
            class NoURLForResourceError(RuntimeError):
                pass
            raise NoURLForResourceError(resource)
        return url

    def addResponseFilter(*args, **kwds):
        pass

