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
    "getRootResource",
]

import errno
import os
from time import sleep

from twisted.python.reflect import namedClass
from twisted.internet import reactor
from twisted.cred.portal import Portal
from twisted.web2.dav import auth
from twisted.web2.auth.basic import BasicCredentialFactory
from twisted.web2.static import File as FileResource
from twisted.python.filepath import FilePath

from twext.log import Logger

from twistedcaldav import memcachepool
from twistedcaldav.accesslog import DirectoryLogWrapperResource
from twistedcaldav.directory import augment, calendaruserproxy
from twistedcaldav.directory.aggregate import AggregateDirectoryService
from twistedcaldav.directory.calendaruserproxyloader import XMLCalendarUserProxyLoader
from twistedcaldav.directory.digest import QopDigestCredentialFactory
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory.sudo import SudoDirectoryService
from twistedcaldav.directory.util import NotFilePath
from twistedcaldav.directory.wiki import WikiDirectoryService
from twistedcaldav.notify import installNotificationClient
from twistedcaldav.resource import CalDAVResource, AuthenticationWrapper
from twistedcaldav.static import CalendarHomeProvisioningFile
from twistedcaldav.static import IScheduleInboxFile
from twistedcaldav.static import TimezoneServiceFile
from twistedcaldav.static import AddressBookHomeProvisioningFile, DirectoryBackedAddressBookFile
from twistedcaldav.timezones import TimezoneCache

try:
    from twistedcaldav.authkerb import NegotiateCredentialFactory
    NegotiateCredentialFactory  # pacify pyflakes
except ImportError:
    NegotiateCredentialFactory = None

from calendarserver.provision.root import RootResource
from calendarserver.webadmin.resource import WebAdminResource
from calendarserver.webcal.resource import WebCalendarResource

log = Logger()



def getRootResource(config, resources=None):
    """
    Set up directory service and resource hierarchy based on config.
    Return root resource.

    Additional resources can be added to the hierarchy by passing a list of
    tuples containing: path, resource class, __init__ args list, and optional
    authentication scheme ("basic" or "digest").
    """

    #
    # Default resource classes
    #
    rootResourceClass            = RootResource
    principalResourceClass       = DirectoryPrincipalProvisioningResource
    calendarResourceClass        = CalendarHomeProvisioningFile
    iScheduleResourceClass       = IScheduleInboxFile
    timezoneServiceResourceClass = TimezoneServiceFile
    webCalendarResourceClass     = WebCalendarResource
    webAdminResourceClass        = WebAdminResource
    addressBookResourceClass     = AddressBookHomeProvisioningFile
    directoryBackedAddressBookResourceClass = DirectoryBackedAddressBookFile

    #
    # Setup the Directory
    #
    directories = []

    directoryClass = namedClass(config.DirectoryService.type)

    log.info("Configuring directory service of type: %s"
        % (config.DirectoryService.type,))

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

        resourceDirectory = resourceClass(config.ResourceService.params)
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

    directory = AggregateDirectoryService(directories)

    if sudoDirectory:
        directory.userRecordTypes.insert(0,
            SudoDirectoryService.recordType_sudoers)

    #
    # Setup the Augment Service
    #
    augmentClass = namedClass(config.AugmentService.type)

    log.info("Configuring augment service of type: %s" % (augmentClass,))

    try:
        augment.AugmentService = augmentClass(**config.AugmentService.params)
    except IOError:
        log.error("Could not start augment service")
        raise

    #
    # Setup the PoxyDB Service
    #
    proxydbClass = namedClass(config.ProxyDBService.type)

    log.info("Configuring proxydb service of type: %s" % (proxydbClass,))

    try:
        calendaruserproxy.ProxyDBService = proxydbClass(**config.ProxyDBService.params)
    except IOError:
        log.error("Could not start proxydb service")
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
    log.info("Setting up principal collection: %r"
                  % (principalResourceClass,))

    principalCollection = principalResourceClass("/principals/", directory)

    log.info("Setting up calendar collection: %r" % (calendarResourceClass,))

    calendarCollection = calendarResourceClass(
        os.path.join(config.DocumentRoot, "calendars"),
        directory, "/calendars/",
    )

    log.info("Setting up root resource: %r" % (rootResourceClass,))

    root = rootResourceClass(
        config.DocumentRoot,
        principalCollections=(principalCollection,),
    )

    if config.EnableCardDAV:
        root.saclService = "addressbook" # XXX this needs to be dealt with
                                         # differently if caldav and carddav
                                         # are going to be in the same process
        log.info("Setting up address book collection: %r" % (addressBookResourceClass,))

        addressBookCollection = addressBookResourceClass(
            os.path.join(config.DocumentRoot, "addressbooks"),
            directory, "/addressbooks/"
        )

        directoryPath = os.path.join(config.DocumentRoot, "directory")
        doBacking = config.DirectoryAddressBook and config.EnableSearchAddressBook
        if doBacking:
            log.info("Setting up directory address book: %r" % (directoryBackedAddressBookResourceClass,))

            directoryBackedAddressBookCollection = directoryBackedAddressBookResourceClass(
                directoryPath,
                principalCollections=(principalCollection,)
            )
            # do this after process is owned by carddav user, not root.  XXX
            # this should be fixed to execute at a different stage of service
            # startup entirely.
            reactor.callLater(1.0, directoryBackedAddressBookCollection.provisionDirectory)
        else:
            # remove /directory from previous runs that may have created it
            try:
                FilePath(directoryPath).remove()
                log.info("Deleted: %s" %    directoryPath)
            except (OSError, IOError), e:
                if e.errno != errno.ENOENT:
                    log.error("Could not delete: %s : %r" %  (directoryPath, e,))

        root.putChild('addressbooks', addressBookCollection)
        if doBacking:
            root.putChild('directory', directoryBackedAddressBookCollection)

    root.putChild("principals", principalCollection)
    root.putChild("calendars", calendarCollection)

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
            NotFilePath(isfile=True),
            root,
        )
        root.putChild("timezones", timezoneService)

    # iSchedule service is optional
    if config.Scheduling.iSchedule.Enabled:
        log.info("Setting up iSchedule inbox resource: %r"
                      % (iScheduleResourceClass,))

        ischedule = iScheduleResourceClass(
            NotFilePath(isfile=True),
            root,
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
            root.putChild(path, cls(root, *args))

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

