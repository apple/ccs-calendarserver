#!/usr/bin/env python
#
# MigrationExtra script to maintain the enabled/disabled state of the
# calendar server.
#
# This script examines the launchd preferences from the previous system
# (also taking into account the overrides.plist) and then invokes serveradmin
# to start/stop calendar server.
#
# The only argument this script currently cares about is --sourceRoot, which
# should point to the root of the previous system.
#
# Copyright (c) 2005-2010 Apple Inc.  All Rights Reserved.
#
# IMPORTANT NOTE:  This file is licensed only for use on Apple-labeled
# computers and is subject to the terms and conditions of the Apple
# Software License Agreement accompanying the package this file is a
# part of.  You may not port this file to another platform without
# Apple's written consent.

from __future__ import with_statement

import datetime
import grp
import optparse
import os
import pwd
import shutil
import subprocess
import sys

from plistlib import readPlist, writePlist

CALDAV_LAUNCHD_KEY = "org.calendarserver.calendarserver"
CARDDAV_LAUNCHD_KEY = "org.addressbookserver.addressbookserver"
LOG = "/Library/Logs/Migration/calendarmigrator.log"
SERVICE_NAME = "calendar"
LAUNCHD_OVERRIDES = "var/db/launchd.db/com.apple.launchd/overrides.plist"
LAUNCHD_PREFS_DIR = "System/Library/LaunchDaemons"
CALDAVD_CONFIG_DIR = "private/etc/caldavd"
CARDDAVD_CONFIG_DIR = "private/etc/carddavd"
CALDAVD_PLIST = "caldavd.plist"
CARDDAVD_PLIST = "carddavd.plist"
NEW_SERVER_ROOT = "/Library/Server/Calendar and Contacts"
RESOURCE_MIGRATION_TRIGGER = "trigger_resource_migration"
SERVER_ADMIN = "/usr/sbin/serveradmin"
LAUNCHCTL = "/bin/launchctl"


verbatimKeys = """
AccountingCategories
AccountingPrincipals
AdminPrincipals
Aliases
AnonymousDirectoryAddressBookAccess
AugmentService
BindAddresses
ConfigRoot
ControlPort
DatabaseRoot
DefaultLogLevel
DirectoryAddressBook
DirectoryService
EnableAddMember
EnableAnonymousReadNav
EnableCalDAV
EnableCardDAV
EnableDropBox
EnableExtendedAccessLog
EnableKeepAlive
EnableMonolithicCalendars
EnablePrincipalListings
EnablePrivateEvents
EnableProxyPrincipals
EnableSACLs
EnableSSL
EnableSearchAddressBook
EnableSyncReport
EnableTimezoneService
EnableWebAdmin
EnableWellKnown
ErrorLogEnabled
ErrorLogMaxRotatedFiles
ErrorLogRotateMB
FreeBusyURL
GlobalAddressBook
GlobalStatsLoggingFrequency
GlobalStatsLoggingPeriod
GlobalStatsSocket
GroupName
HTTPPort
HTTPRetryAfter
IdleConnectionTimeOut
Includes
ListenBacklog
Localization
LogLevels
LogRoot
MaxAccepts
MaxAttendeesPerInstance
MaxInstancesForRRULE
MaxMultigetWithDataHREFs
MaxQueryWithDataResults
MaxRequests
MaximumAttachmentSize
Memcached
MultiProcess
Notifications
Partitioning
Postgres
ProcessType
Profiling
ProxyDBService
ProxyLoadFromFile
ReadPrincipals
RejectClients
ResourceService
ResponseCompression
RotateAccessLog
RunRoot
SSLAuthorityChain
SSLCertAdmin
SSLCertificate
SSLCiphers
SSLMethod
SSLPrivateKey
Scheduling
ServerHostName
ServerRoot
Sharing
SudoersFile
Twisted
UIDReservationTimeOut
UseDatabase
UseMetaFD
UserName
UserQuota
WebCalendarRoot
umask
""".split()

# These are going to require some processing
specialKeys = """
AccessLogFile
AccountingLogRoot
Authentication
BindHTTPPorts
BindSSLPorts
DataRoot
DocumentRoot
ErrorLogFile
MaxAddressBookMultigetHrefs
MaxAddressBookQueryResults
RedirectHTTPToHTTPS
SSLPort
""".split()

ignoredKkeys = """
ControlSocket
EnableAnonymousReadRoot
EnableFindSharedReport
EnableNotifications
PIDFile
PythonDirector
ResponseCacheTimeout
SSLPassPhraseDialog
ServerStatsFile
Verbose
""".split()


def main():

    optionParser = optparse.OptionParser()

    optionParser.add_option('--purge', choices=('0', '1'),
        metavar='[0|1]',
        help='remove old files after migration (IGNORED)')

    optionParser.add_option('--sourceRoot', type='string',
        metavar='DIR',
        help='path to the root of the system to migrate')

    optionParser.add_option('--sourceType', type='string',
        metavar='[System|TimeMachine]',
        help='migration source type (IGNORED)')

    optionParser.add_option('--sourceVersion', type='string',
        metavar='10.X.X',
        help='version number of previous system (IGNORED)')

    optionParser.add_option('--targetRoot', type='string',
        metavar='DIR',
        help='path to the root of the new system',
        default='/')

    optionParser.add_option('--language', choices=('en', 'fr', 'de', 'ja'),
        metavar='[en|fr|de|ja]',
        help='language identifier (IGNORED)')

    (options, args) = optionParser.parse_args()
    log("Options: %s" % (options,))

    if options.sourceRoot:

        if os.path.exists(options.sourceRoot):

            # If calendar service was running on previous system
            # turn it off while we process configuration.  There
            # is no need to turn off addressbook because it no longer
            # has its own launchd plist.
            enableCalDAV, enableCardDAV = examineRunState(options)
            if enableCalDAV:
                unloadService(options, CALDAV_LAUNCHD_KEY)

            newServerRootValue = migrateData(options)
            migrateConfiguration(options, newServerRootValue, enableCalDAV,
                enableCardDAV)

            setRunState(options, enableCalDAV, enableCardDAV)
            triggerResourceMigration(newServerRootValue)

    else:
        log("ERROR: --sourceRoot must be specified")
        sys.exit(1)


def examineRunState(options):
    """
    Try to determine whether the CalDAV and CardDAV services were running in
    previous system.

    @return: a tuple of booleans: whether CalDAV was enabled, and whether
    CardDAV was enabled
    """

    enableCalDAV = False
    enableCardDAV = False

    try:
        disabled = isServiceDisabled(options.sourceRoot, CALDAV_LAUNCHD_KEY)
        enableCalDAV = not disabled
        log("Calendar service '%s' was previously %s" %
            (CALDAV_LAUNCHD_KEY, "disabled" if disabled else "enabled"))
    except ServiceStateError, e:
        log("Couldn't determine previous state of calendar service '%s': %s" %
            (CALDAV_LAUNCHD_KEY, e))

    try:
        disabled = isServiceDisabled(options.sourceRoot, CARDDAV_LAUNCHD_KEY)
        enableCardDAV = not disabled
        log("Addressbook service '%s' was previously %s" %
            (CARDDAV_LAUNCHD_KEY, "disabled" if disabled else "enabled"))
    except ServiceStateError, e:
        log("Couldn't determine previous state of addressbook service '%s': %s" %
            (CARDDAV_LAUNCHD_KEY, e))

    return (enableCalDAV, enableCardDAV)


def setRunState(options, enableCalDAV, enableCardDAV):
    """
    Use serveradmin to launch the service if needed.
    """

    if enableCalDAV or enableCardDAV:
        log("Starting service via serveradmin")
        ret = subprocess.call([SERVER_ADMIN, "start", "calendar"])
        log("serveradmin exited with %d" % (ret,))


def unloadService(options, service):
    """
    Use launchctl to unload a service
    """
    path = os.path.join(options.targetRoot, LAUNCHD_PREFS_DIR,
                        "%s.plist" % (service,))
    log("Unloading %s via launchctl" % (path,))
    ret = subprocess.call([LAUNCHCTL, "unload", "-w", path])
    log("launchctl exited with %d" % (ret,))


def triggerResourceMigration(newServerRootValue):
    """
    Leave a file in the server root to act as a signal that the server
    should migrate locations and resources from OD when it starts up.
    """
    triggerPath = os.path.join(newServerRootValue, RESOURCE_MIGRATION_TRIGGER)
    if not os.path.exists(newServerRootValue):
        log("New server root directory doesn't exist: %s" % (newServerRootValue,))
        return

    if not os.path.exists(triggerPath):
        # Create an empty trigger file
        log("Creating resource migration trigger file: %s" % (triggerPath,))
        open(triggerPath, "w").close()


def migrateConfiguration(options, newServerRootValue, enableCalDAV, enableCardDAV):
    """
    Copy files/directories/symlinks from previous system's /etc/caldavd
    and /etc/carddavd

    Skips anything ending in ".default".
    Regular files overwrite copies in new system.
    Directories and symlinks only copied over if they don't overwrite anything.
    """

    newConfigDir = os.path.join(options.targetRoot, CALDAVD_CONFIG_DIR)
    if not os.path.exists(newConfigDir):
        log("New configuration directory does not exist: %s" % (newConfigDir,))
        return


    for configDir in (CALDAVD_CONFIG_DIR, CARDDAVD_CONFIG_DIR):

        oldConfigDir = os.path.join(options.sourceRoot, configDir)
        if not os.path.exists(oldConfigDir):
            log("Old configuration directory does not exist: %s" % (oldConfigDir,))
            continue


        log("Copying configuration files from %s to %s" % (oldConfigDir, newConfigDir))

        for name in os.listdir(oldConfigDir):

            if not (name.endswith(".default") or name in (CALDAVD_PLIST, CARDDAVD_PLIST)):

                oldPath = os.path.join(oldConfigDir, name)
                newPath = os.path.join(newConfigDir, name)

                if os.path.islink(oldPath) and not os.path.exists(newPath):
                    # Recreate the symlink if it won't overwrite an existing file
                    link = os.readlink(oldPath)
                    log("Symlinking %s to %s" % (newPath, link))
                    os.symlink(link, newPath)

                elif os.path.isfile(oldPath):
                    # Copy the file over, overwriting copy in newConfigDir
                    log("Copying file %s to %s" % (oldPath, newConfigDir))
                    shutil.copy2(oldPath, newConfigDir)

                elif os.path.isdir(oldPath) and not os.path.exists(newPath):
                    # Copy the dir over, but only if new one doesn't exist
                    log("Copying directory %s to %s" % (oldPath, newPath))
                    shutil.copytree(oldPath, newPath, symlinks=True)


    # Migrate certain settings from the old plists to new:

    oldCalDAVPlistPath = os.path.join(options.sourceRoot, CALDAVD_CONFIG_DIR,
        CALDAVD_PLIST)
    if os.path.exists(oldCalDAVPlistPath):
        oldCalDAVDPlist = readPlist(oldCalDAVPlistPath)
    else:
        oldCalDAVDPlist = { }

    oldCardDAVDPlistPath = os.path.join(options.sourceRoot, CARDDAVD_CONFIG_DIR,
        CARDDAVD_PLIST)
    if os.path.exists(oldCardDAVDPlistPath):
        oldCardDAVDPlist = readPlist(oldCardDAVDPlistPath)
    else:
        oldCardDAVDPlist = { }

    newCalDAVDPlistPath = os.path.join(options.targetRoot, CALDAVD_CONFIG_DIR,
        CALDAVD_PLIST)
    if os.path.exists(newCalDAVDPlistPath):
        newCalDAVDPlist = readPlist(newCalDAVDPlistPath)
    else:
        newCalDAVDPlist = { }

    log("Processing %s and %s" % (oldCalDAVPlistPath, oldCardDAVDPlistPath))
    mergePlist(oldCalDAVDPlist, oldCardDAVDPlist, newCalDAVDPlist)

    newCalDAVDPlist["ServerRoot"] = newServerRootValue
    newCalDAVDPlist["DocumentRoot"] = "Documents"
    newCalDAVDPlist["DataRoot"] = "Data"

    newCalDAVDPlist["EnableCalDAV"] = enableCalDAV
    newCalDAVDPlist["EnableCardDAV"] = enableCardDAV

    log("Writing %s" % (newCalDAVDPlistPath,))
    writePlist(newCalDAVDPlist, newCalDAVDPlistPath)


def mergePlist(caldav, carddav, combined):

    # These keys are copied verbatim:
    for key in verbatimKeys:
        if key in carddav:
            combined[key] = carddav[key]
        if key in caldav:
            combined[key] = caldav[key]

    # "Wiki" is a new authentication in v2.x; copy all "Authentication" sub-keys    # over, and "Wiki" will be picked up from the new plist:
    if "Authentication" in caldav:
        for key in caldav["Authentication"]:
            combined["Authentication"][key] = caldav["Authentication"][key]

    # Strip out any unknown params from the DirectoryService:
    if "DirectoryService" in caldav:
        combined["DirectoryService"] = caldav["DirectoryService"]
        for key in combined["DirectoryService"]["params"].keys():
            if key not in ("node", "cacheTimeout", "xmlFile"):
                del combined["DirectoryService"]["params"][key]

    # Merge ports
    if not caldav.get("HTTPPort", 0):
        caldav["HTTPPort"] = 8008
    if not carddav.get("HTTPPort", 0):
        carddav["HTTPPort"] = 8800
    if not caldav.get("SSLPort", 0):
        caldav["SSLPort"] = 8443
    if not carddav.get("SSLPort", 0):
        carddav["SSLPort"] = 8843

    for portType in ["HTTPPort", "SSLPort"]:
        bindPorts = list(set(caldav.get("Bind%ss" % (portType,), [])).union(set(carddav.get("Bind%ss" % (portType,), []))))
        for prev in (carddav, caldav):
            port = prev.get(portType, 0)
            if port and port not in bindPorts:
                bindPorts.append(port)
        bindPorts.sort()
        combined["Bind%ss" % (portType,)] = bindPorts

    combined["HTTPPort"] = caldav["HTTPPort"]
    combined["SSLPort"] = caldav["SSLPort"]

    # Was SSL enabled?
    sslAuthorityChain = ""
    sslCertificate = ""
    sslPrivateKey = ""
    enableSSL = False
    for prev in (carddav, caldav):
        if (prev["SSLPort"] and prev.get("SSLCertificate", "")):
            sslAuthorityChain = prev.get("SSLAuthorityChain", "")
            sslCertificate = prev.get("SSLCertificate", "")
            sslPrivateKey = prev.get("SSLPrivateKey", "")
            enableSSL = True

    combined["SSLAuthorityChain"] = sslAuthorityChain
    combined["SSLCertificate"] = sslCertificate
    combined["SSLPrivateKey"] = sslPrivateKey
    combined["EnableSSL"] = enableSSL

    # If SSL is enabled, redirect HTTP to HTTPS.
    combined["RedirectHTTPToHTTPS"] = enableSSL


def isServiceDisabled(source, service):
    """
    Returns whether or not a service is disabled

    @param source: System root to examine
    @param service: launchd key representing service
    @return: True if service is disabled, False if enabled
    """

    overridesPath = os.path.join(source, LAUNCHD_OVERRIDES)
    if os.path.isfile(overridesPath):
        overrides = readPlist(overridesPath)
        try:
            return overrides[service]['Disabled']
        except KeyError:
            # Key is not in the overrides.plist, continue on
            pass

    prefsPath = os.path.join(source, LAUNCHD_PREFS_DIR, "%s.plist" % service)
    if os.path.isfile(prefsPath):
        prefs = readPlist(prefsPath)
        try:
            return prefs['Disabled']
        except KeyError:
            return False

    raise ServiceStateError("Neither %s nor %s exist" %
        (overridesPath, prefsPath))

def setServiceStateDisabled(target, service, disabled):
    """
    Modifies launchd settings for a service

    @param target: System root
    @param service: launchd key representing service
    @param disabled: boolean
    """

    overridesPath = os.path.join(target, LAUNCHD_OVERRIDES)
    if os.path.isfile(overridesPath):
        overrides = readPlist(overridesPath)
        if not overrides.has_key(service):
            overrides[service] = { }
        overrides[service]['Disabled'] = disabled
        writePlist(overrides, overridesPath)


class ServiceStateError(Exception):
    """
    Could not determine service state
    """


def log(msg):
    try:
        with open(LOG, 'a') as output:
            timestamp = datetime.datetime.now().strftime("%b %d %H:%M:%S")
            msg = "calendarmigrator: %s %s" % (timestamp, msg)
            output.write("%s\n" % (msg,)) # so it appears in our log
            print msg # so it appears in Setup.log
    except IOError:
        # Could not write to log
        pass

def migrateData(options):
    """
    Examines the old caldavd.plist and carddavd.plist to see where data
    lives in the previous system.  If there is old data, calls relocateData( )
    """

    oldCalDocuments = None
    oldCalData = None
    oldABDocuments = None
    calendarDataInDefaultLocation = True
    addressbookDataInDefaultLocation = True
    uid = -1
    gid = -1
    newServerRoot = None # actual path
    newServerRootValue = NEW_SERVER_ROOT # value to put in plist

    oldCalConfigDir = os.path.join(options.sourceRoot, CALDAVD_CONFIG_DIR)
    oldCalPlistPath = os.path.join(oldCalConfigDir, CALDAVD_PLIST)
    if os.path.exists(oldCalPlistPath):
        oldCalPlist = readPlist(oldCalPlistPath)
        uid, gid = getServerIDs(oldCalPlist)
        log("ServerIDs: %d, %d" % (uid, gid))
    else:
        log("Can't find previous calendar plist at %s" % (oldCalPlistPath,))
        oldCalPlist = None
        newCalConfigDir = os.path.join(options.targetRoot, CALDAVD_CONFIG_DIR)
        newCalPlistPath = os.path.join(newCalConfigDir, CALDAVD_PLIST)
        if os.path.exists(newCalPlistPath):
            newCalPlist = readPlist(newCalPlistPath)
            uid, gid = getServerIDs(newCalPlist)
            log("ServerIDs: %d, %d" % (uid, gid))


    oldABConfigDir = os.path.join(options.sourceRoot, CARDDAVD_CONFIG_DIR)
    oldABPlistPath = os.path.join(oldABConfigDir, CARDDAVD_PLIST)
    if os.path.exists(oldABPlistPath):
        oldABPlist = readPlist(oldABPlistPath)
    else:
        log("Can't find previous addressbook plist at %s" % (oldABPlistPath,))
        oldABPlist = None

    if oldCalPlist is not None:
        # See if there is actually any calendar data

        oldDocumentRoot = oldCalPlist["DocumentRoot"]
        if oldDocumentRoot.rstrip("/") != "/Library/CalendarServer/Documents":
            log("Calendar data in non-standard location: %s" % (oldDocumentRoot,))
            calendarDataInDefaultLocation = False
        else:
            log("Calendar data in standard location: %s" % (oldDocumentRoot,))

        oldDataRoot = oldCalPlist["DataRoot"]

        oldCalendarsPath = os.path.join(oldDocumentRoot, "calendars")
        if os.path.exists(oldCalendarsPath):
            # There is calendar data
            oldCalDocuments = oldDocumentRoot
            oldCalData = oldDataRoot
            log("Calendar data to migrate from %s and %s" %
                (oldCalDocuments, oldCalData))

            if calendarDataInDefaultLocation:
                newServerRoot = absolutePathWithRoot(options.targetRoot,
                    NEW_SERVER_ROOT)
                newServerRootValue = NEW_SERVER_ROOT
            else:
                newServerRoot = absolutePathWithRoot(options.targetRoot,
                    oldDocumentRoot)
                newServerRootValue = oldDocumentRoot
        else:
            log("No calendar data to migrate")

    if oldABPlist is not None:
        # See if there is actually any addressbook data

        oldDocumentRoot = oldABPlist["DocumentRoot"]
        if oldDocumentRoot.rstrip("/") != "/Library/AddressBookServer/Documents":
            log("AddressBook data in non-standard location: %s" % (oldDocumentRoot,))
            addressbookDataInDefaultLocation = False
        else:
            log("AddressBook data in standard location: %s" % (oldDocumentRoot,))

        oldAddressbooksPath = os.path.join(oldDocumentRoot, "addressbooks")
        if os.path.exists(oldAddressbooksPath):
            # There is addressbook data
            oldABDocuments = oldDocumentRoot
            log("AddressBook data to migrate from %s" % (oldABDocuments,))

            if newServerRoot is None:
                # don't override server root computed from calendar
                if addressbookDataInDefaultLocation:
                    newServerRoot = absolutePathWithRoot(options.targetRoot,
                        NEW_SERVER_ROOT)
                    newServerRootValue = NEW_SERVER_ROOT
                else:
                    newServerRoot = absolutePathWithRoot(options.targetRoot,
                        oldDocumentRoot)
                    newServerRootValue = oldDocumentRoot
        else:
            log("No addressbook data to migrate")

    if (oldCalDocuments or oldABDocuments) and newServerRoot:
        relocateData(oldCalDocuments, oldCalData, oldABDocuments, uid, gid,
            calendarDataInDefaultLocation, addressbookDataInDefaultLocation,
            newServerRoot)

    return newServerRootValue

def relocateData(oldCalDocuments, oldCalData, oldABDocuments, uid, gid,
    calendarDataInDefaultLocation, addressbookDataInDefaultLocation,
    newServerRoot):
    """
    Relocates existing calendar data to the new default location iff the data
    was previously in the old default location; otherwise the old calendar
    DocumentRoot becomes the new ServerRoot directory, the contents of the
    old DocumentRoot are moved into ServerRoot/Documents and the contents of
    old DataRoot are copied/moved into ServerRoot/Data.  If there is addressbook
    data, a symlink is created as ServerRoot/Documents/addressbooks pointing
    to the old addressbook directory so that the import-to-PostgreSQL will
    find it.
    """

    log("RelocateData: cal documents=%s, cal data=%s, ab documents=%s, new server root=%s"
        % (oldCalDocuments, oldCalData, oldABDocuments, newServerRoot))

    if oldCalDocuments and os.path.exists(oldCalDocuments):

        if calendarDataInDefaultLocation:
            # We're in the default location, relocate to new location
            newCalDocuments = os.path.join(newServerRoot, "Documents")
            if not os.path.exists(newCalDocuments):
                os.mkdir(newCalDocuments)
            newCalData = os.path.join(newServerRoot, "Data")
            if not os.path.exists(newCalData):
                os.mkdir(newCalData)
            if os.path.exists(oldCalDocuments):
                # Move evertying from oldCalDocuments
                for item in list(os.listdir(oldCalDocuments)):
                    source = os.path.join(oldCalDocuments, item)
                    dest = os.path.join(newCalDocuments, item)
                    log("Relocating %s to %s" % (source, dest))
                    os.rename(source, dest)
            else:
                log("Warning: %s does not exist; nothing to migrate" % (oldCalDocuments,))
        else:
            # The admin has moved calendar data to a non-standard location so
            # we're going to leave it there, but move things down a level so
            # that the old DocumentRoot becomes new ServerRoot

            # Create "Documents" directory with same ownership as oldCalDocuments
            newCalDocuments = os.path.join(newServerRoot, "Documents")
            log("New documents directory: %s" % (newCalDocuments,))
            newCalData = os.path.join(newServerRoot, "Data")
            log("New data directory: %s" % (newCalData,))
            os.mkdir(newCalDocuments)
            os.mkdir(newCalData)
            for item in list(os.listdir(newServerRoot)):
                if item not in ("Documents", "Data"):
                    source = os.path.join(newServerRoot, item)
                    dest = os.path.join(newCalDocuments, item)
                    log("Relocating %s to %s" % (source, dest))
                    os.rename(source, dest)

        # Relocate calendar DataRoot, copying all files
        if os.path.exists(oldCalData):
            if not os.path.exists(newCalData):
                os.mkdir(newCalData)
            for item in list(os.listdir(oldCalData)):
                source = os.path.join(oldCalData, item)
                if not os.path.isfile(source):
                    continue
                dest = os.path.join(newCalData, item)
                log("Relocating %s to %s" % (source, dest))
                try:
                    os.rename(source, dest)
                except OSError:
                    # Can't rename because it's cross-volume; must copy/delete
                    shutil.copy2(source, dest)
                    os.remove(source)

        # Symlink to AB document root so server will find it an import to
        # PostgreSQL
        if oldABDocuments and os.path.exists(oldABDocuments):
            oldAddressBooks = os.path.join(oldABDocuments, "addressbooks")
            newAddressBooks = os.path.join(newCalDocuments, "addressbooks")
            log("Symlinking AddressBook data: %s to %s" % (newAddressBooks, oldAddressBooks))
            os.symlink(oldAddressBooks, newAddressBooks)


    elif oldABDocuments and os.path.exists(oldABDocuments):
        # No calendar data, only addressbook data

        if addressbookDataInDefaultLocation:
            # We're in the default location, relocate to new location
            newABDocuments = os.path.join(newServerRoot, "Documents")
            if os.path.exists(newABDocuments):
                # Move evertying from oldABDocuments
                for item in list(os.listdir(oldABDocuments)):
                    source = os.path.join(oldABDocuments, item)
                    dest = os.path.join(newABDocuments, item)
                    log("Relocating %s to %s" % (source, dest))
                    os.rename(source, dest)
            else:
                log("Error: %s does not exist" % (newABDocuments,))
        else:
            # The admin has moved addressbook data to a non-standard location so
            # we're going to leave it there, but move things down a level so
            # that the old DocumentRoot becomes new ServerRoot

            # Create "Documents" directory with same ownership as oldABDocuments
            newABDocuments = os.path.join(newServerRoot, "Documents")
            newABData = os.path.join(newServerRoot, "Data")
            log("New documents directory: %s" % (newABDocuments,))
            os.mkdir(newABDocuments)
            os.mkdir(newABData)
            for item in list(os.listdir(newServerRoot)):
                if item not in ("Documents", "Data"):
                    source = os.path.join(newServerRoot, item)
                    dest = os.path.join(newABDocuments, item)
                    log("Relocating %s to %s" % (source, dest))
                    os.rename(source, dest)

    if newServerRoot and os.path.exists(newServerRoot):
        """
        Change onwnership of entire ServerRoot
        """
        os.chown(newServerRoot, uid, gid)
        for root, dirs, files in os.walk(newServerRoot, followlinks=True):
            for name in dirs:
                os.chown(os.path.join(root, name), uid, gid)
            for name in files:
                os.chown(os.path.join(root, name), uid, gid)



def getServerIDs(plist):
    """
    Given a caldavd.plist, return the userid and groupid for the UserName and
    GroupName specified.
    """
    uid = -1
    if plist["UserName"]:
        uid = pwd.getpwnam(plist["UserName"]).pw_uid
    gid = -1
    if plist["GroupName"]:
        gid = grp.getgrnam(plist["GroupName"]).gr_gid
    return uid, gid

def absolutePathWithRoot(root, path):
    """
    Combine root and path as long as path does not start with /Volumes/
    """
    if path.startswith("/Volumes/"):
        return path
    else:
        path = path.strip("/")
        return os.path.join(root, path)

if __name__ == '__main__':
    main()
