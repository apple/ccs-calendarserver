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
# Copyright (c) 2005-2012 Apple Inc.  All Rights Reserved.
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

from plistlib import readPlist, readPlistFromString, writePlist

SERVER_APP_ROOT = "/Applications/Server.app/Contents/ServerRoot"
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
NEW_SERVER_DIR = "Calendar and Contacts"
NEW_SERVER_ROOT = "/Library/Server/" + NEW_SERVER_DIR
RESOURCE_MIGRATION_TRIGGER = "trigger_resource_migration"
SERVER_ADMIN = "%s/usr/sbin/serveradmin" % (SERVER_APP_ROOT,)
DITTO = "/usr/bin/ditto"


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
Servers
ServerPartitionID
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

ignoredKeys = """
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

            enableCalDAV, enableCardDAV = examineRunState(options)

            # Pull values out of previous plists
            (
                oldServerRootValue,
                oldCalDocumentRootValue,
                oldCalDataRootValue,
                oldABDocumentRootValue,
                uid,
                gid
            ) = examinePreviousSystem(
                options.sourceRoot,
                options.targetRoot
            )

            # Copy data as needed
            (
                newServerRoot,
                newServerRootValue,
                newDocumentRootValue,
                newDataRootValue
            ) = relocateData(
                options.sourceRoot,
                options.targetRoot,
                oldServerRootValue,
                oldCalDocumentRootValue,
                oldCalDataRootValue,
                oldABDocumentRootValue,
                uid,
                gid
            )

            # Combine old and new plists
            migrateConfiguration(
                options,
                newServerRootValue,
                newDocumentRootValue,
                newDataRootValue,
                enableCalDAV,
                enableCardDAV
            )

            triggerResourceMigration(newServerRoot)

            setRunState(options, enableCalDAV, enableCardDAV)

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

    enableCalDAV = None
    enableCardDAV = None

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

    if enableCalDAV:
        # Check previous plist in case previous system was Lion, since there
        # is now only one launchd key for both services
        oldCalDAVPlistPath = os.path.join(options.sourceRoot,
            CALDAVD_CONFIG_DIR, CALDAVD_PLIST)
        if os.path.exists(oldCalDAVPlistPath):
            log("Examining previous caldavd.plist for EnableCalDAV and EnableCardDAV: %s" % (oldCalDAVPlistPath,))
            oldCalDAVDPlist = readPlist(oldCalDAVPlistPath)
            if "EnableCalDAV" in oldCalDAVDPlist:
                enableCalDAV = oldCalDAVDPlist["EnableCalDAV"]
                log("Based on caldavd.plist, setting EnableCalDAV to %s" % (enableCalDAV,))
            if "EnableCardDAV" in oldCalDAVDPlist:
                enableCardDAV = oldCalDAVDPlist["EnableCardDAV"]
                log("Based on caldavd.plist, setting EnableCardDAV to %s" % (enableCardDAV,))

    # A value of None means we weren't able to determine, so default to off
    if enableCalDAV is None:
        enableCalDAV = False
    if enableCardDAV is None:
        enableCardDAV = False

    return (enableCalDAV, enableCardDAV)


def setRunState(options, enableCalDAV, enableCardDAV):
    """
    Use serveradmin to launch the service if needed.
    """

    if enableCalDAV or enableCardDAV:
        serviceName = "calendar" if enableCalDAV else "addressbook"
        log("Starting service via serveradmin start %s" % (serviceName,))
        ret = subprocess.call([SERVER_ADMIN, "start", serviceName])
        log("serveradmin exited with %d" % (ret,))


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


def migrateConfiguration(options, newServerRootValue,
    newDocumentRootValue, newDataRootValue, enableCalDAV, enableCardDAV):
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
    newCalDAVDPlist["DocumentRoot"] = newDocumentRootValue
    newCalDAVDPlist["DataRoot"] = newDataRootValue

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

    # Copy all "Authentication" sub-keys
    if "Authentication" in caldav:
        if "Authentication" not in combined:
            combined["Authentication"] = { }
        for key in caldav["Authentication"]:
            combined["Authentication"][key] = caldav["Authentication"][key]

        # Examine the Wiki URL -- if it's using :8089 then we leave the Wiki
        # section as is.  Otherwise, reset it so that it picks up the coded
        # default
        if "Wiki" in combined["Authentication"]:
            if "URL" in combined["Authentication"]["Wiki"]:
                url = combined["Authentication"]["Wiki"]["URL"]
                if ":8089" not in url:
                    combined["Authentication"]["Wiki"] = { "Enabled" : True }


    # Strip out any unknown params from the DirectoryService:
    if "DirectoryService" in caldav:
        combined["DirectoryService"] = caldav["DirectoryService"]
        for key in combined["DirectoryService"]["params"].keys():
            if key in ("requireComputerRecord",):
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
        timestamp = datetime.datetime.now().strftime("%b %d %H:%M:%S")
        msg = "calendarmigrator: %s %s" % (timestamp, msg)
        print msg # so it appears in Setup.log
        with open(LOG, 'a') as output:
            output.write("%s\n" % (msg,)) # so it appears in our log
    except IOError:
        # Could not write to log
        pass

def examinePreviousSystem(sourceRoot, targetRoot, diskAccessor=None):
    """
    Examines the old caldavd.plist and carddavd.plist to see where data
    lives in the previous system.
    """

    if diskAccessor is None:
        diskAccessor = DiskAccessor()

    oldServerRootValue = None
    oldCalDocumentRootValue = None
    oldCalDataRootValue = None
    oldABDocumentRootValue = None

    # Get uid and gid from new caldavd.plist
    newCalConfigDir = os.path.join(targetRoot, CALDAVD_CONFIG_DIR)
    newCalPlistPath = os.path.join(newCalConfigDir, CALDAVD_PLIST)
    if diskAccessor.exists(newCalPlistPath):
        contents = diskAccessor.readFile(newCalPlistPath)
        newCalPlist = readPlistFromString(contents)
        uid, gid = getServerIDs(newCalPlist)
        log("ServerIDs from %s: %d, %d" % (newCalPlistPath, uid, gid))
    else:
        uid = gid = -1
        log("Can't find new calendar plist at %s" % (newCalPlistPath,))

    # Try and read old caldavd.plist
    oldCalConfigDir = os.path.join(sourceRoot, CALDAVD_CONFIG_DIR)
    oldCalPlistPath = os.path.join(oldCalConfigDir, CALDAVD_PLIST)
    if diskAccessor.exists(oldCalPlistPath):
        contents = diskAccessor.readFile(oldCalPlistPath)
        oldCalPlist = readPlistFromString(contents)
        log("Found previous caldavd plist at %s" % (oldCalPlistPath,))

        oldServerRootValue = oldCalPlist.get("ServerRoot", None)
        oldCalDocumentRootValue = oldCalPlist.get("DocumentRoot", None)
        oldCalDataRootValue = oldCalPlist.get("DataRoot", None)

    else:
        log("Can't find previous calendar plist at %s" % (oldCalPlistPath,))
        oldCalPlist = None

    # Try and read old carddavd.plist
    oldABConfigDir = os.path.join(sourceRoot, CARDDAVD_CONFIG_DIR)
    oldABPlistPath = os.path.join(oldABConfigDir, CARDDAVD_PLIST)
    if diskAccessor.exists(oldABPlistPath):
        contents = diskAccessor.readFile(oldABPlistPath)
        oldABPlist = readPlistFromString(contents)
        log("Found previous carddavd plist at %s" % (oldABPlistPath,))

        oldABDocumentRootValue = oldABPlist.get("DocumentRoot", None)
    else:
        log("Can't find previous carddavd plist at %s" % (oldABPlistPath,))
        oldABPlist = None

    return (
        oldServerRootValue,
        oldCalDocumentRootValue,
        oldCalDataRootValue,
        oldABDocumentRootValue,
        uid,
        gid
    )


def relocateData(sourceRoot, targetRoot, oldServerRootValue,
    oldCalDocumentRootValue, oldCalDataRootValue, oldABDocumentRootValue,
    uid, gid, diskAccessor=None):
    """
    Copy data from sourceRoot to targetRoot, except when data is on another
    volume in which case we just refer to it there.
    """

    if diskAccessor is None:
        diskAccessor = DiskAccessor()

    log("RelocateData: sourceRoot=%s, targetRoot=%s, oldServerRootValue=%s, oldCalDocumentRootValue=%s, oldCalDataRootValue=%s, oldABDocumentRootValue=%s, uid=%d, gid=%d" % (sourceRoot, targetRoot, oldServerRootValue, oldCalDocumentRootValue, oldCalDataRootValue, oldABDocumentRootValue, uid, gid))

    if oldServerRootValue:
        newServerRootValue = oldServerRootValue
        # Source is Lion; see if ServerRoot refers to an external volume
        # or a directory in sourceRoot
        if diskAccessor.exists(oldServerRootValue):
            # refers to an external volume
            newServerRoot = newServerRootValue
        elif diskAccessor.exists(os.path.join(sourceRoot, oldServerRootValue)):
            # refers to a directory on sourceRoot
            newServerRoot = absolutePathWithRoot(targetRoot, newServerRootValue)
        else:
            # It doesn't exist, so use default
            newServerRootValue = NEW_SERVER_ROOT
            newServerRoot = absolutePathWithRoot(targetRoot, newServerRootValue)

        # If there was an old ServerRoot value, process DocumentRoot and
        # DataRoot because those could be relative to ServerRoot
        oldCalDocumentRootValueProcessed = os.path.join(oldServerRootValue,
            oldCalDocumentRootValue)
        oldCalDataRootValueProcessed = os.path.join(oldServerRootValue,
            oldCalDataRootValue)
    else:
        newServerRootValue = NEW_SERVER_ROOT
        newServerRoot = absolutePathWithRoot(targetRoot, newServerRootValue)
        oldCalDocumentRootValueProcessed = oldCalDocumentRootValue
        oldCalDataRootValueProcessed = oldCalDataRootValue

    # Set default values for these, possibly overridden below:
    newDocumentRootValue = "Documents"
    newDocumentRoot = absolutePathWithRoot(
        targetRoot,
        os.path.join(newServerRootValue, newDocumentRootValue)
    )
    newDataRootValue = "Data"
    newDataRoot = absolutePathWithRoot(
        targetRoot,
        os.path.join(newServerRootValue, newDataRootValue)
    )

    # Old Calendar DocumentRoot
    if oldCalDocumentRootValueProcessed:
        if diskAccessor.exists(oldCalDocumentRootValueProcessed):
            # Must be on an external volume if we see it existing at this point

            # If data is pre-lion (no ServerRoot value), and DocumentRoot
            # is external, let's consolidate everything so that the old
            # DocumentRoot becomes the new ServerRoot, and Documents and
            # Data become children
            if not oldServerRootValue: # pre-lion
                newServerRoot = newServerRootValue = os.path.join(os.path.dirname(oldCalDocumentRootValue.rstrip("/")), NEW_SERVER_DIR)
                if diskAccessor.exists(newServerRootValue):
                    diskAccessor.rename(newServerRootValue, newServerRootValue + ".bak")
                diskAccessor.mkdir(newServerRootValue)
                newDocumentRoot = newDocumentRootValue = os.path.join(newServerRootValue, "Documents")
                # Move old DocumentRoot under new ServerRoot
                diskAccessor.rename(oldCalDocumentRootValue, newDocumentRoot)
                newDataRoot = newDataRootValue = os.path.join(newServerRootValue, "Data")
                if diskAccessor.exists(absolutePathWithRoot(sourceRoot, oldCalDataRootValueProcessed)):
                    diskAccessor.ditto(
                        absolutePathWithRoot(sourceRoot, oldCalDataRootValueProcessed),
                        newDataRoot
                    )
                    diskAccessor.chown(newDataRoot, uid, gid, recursive=True)
                oldCalDataRootValueProcessed = None # to bypass processing below

            else: # Lion or later
                newDocumentRoot = newDocumentRootValue = oldCalDocumentRootValueProcessed
        elif diskAccessor.exists(absolutePathWithRoot(sourceRoot, oldCalDocumentRootValueProcessed)):
            diskAccessor.ditto(
                absolutePathWithRoot(sourceRoot, oldCalDocumentRootValueProcessed),
                newDocumentRoot
            )
            diskAccessor.chown(newDocumentRoot, uid, gid, recursive=True)

    # Old Calendar DataRoot
    if oldCalDataRootValueProcessed:
        if diskAccessor.exists(oldCalDataRootValueProcessed):
            # Must be on an external volume if we see it existing at this point
            # so don't copy it
            newDataRootValue = oldCalDataRootValueProcessed
        elif diskAccessor.exists(
            absolutePathWithRoot(sourceRoot, oldCalDataRootValueProcessed)
        ):
            diskAccessor.ditto(
                absolutePathWithRoot(sourceRoot, oldCalDataRootValueProcessed),
                newDataRoot
            )
            diskAccessor.chown(newDataRoot, uid, gid, recursive=True)

    # Old AddressBook DocumentRoot
    if oldABDocumentRootValue:
        newAddressBooks = os.path.join(newDocumentRoot, "addressbooks")
        if diskAccessor.exists(oldABDocumentRootValue):
            # Must be on an external volume if we see it existing at the point
            diskAccessor.ditto(
                os.path.join(oldABDocumentRootValue, "addressbooks"),
                newAddressBooks
            )
        elif diskAccessor.exists(
            absolutePathWithRoot(sourceRoot, oldABDocumentRootValue)
        ):
            diskAccessor.ditto(
                absolutePathWithRoot(
                    sourceRoot,
                    os.path.join(oldABDocumentRootValue, "addressbooks")
                ),
                os.path.join(newDocumentRoot, "addressbooks")
            )
        if diskAccessor.exists(newAddressBooks):
            diskAccessor.chown(newAddressBooks, uid, gid, recursive=True)


    newServerRootValue, newDocumentRootValue = relativize(newServerRootValue,
        newDocumentRootValue)
    newServerRootValue, newDataRootValue = relativize(newServerRootValue,
        newDataRootValue)

    return (
        newServerRoot,
        newServerRootValue,
        newDocumentRootValue,
        newDataRootValue
    )


def relativize(parent, child):
    """
    If child is really a child of parent, make child relative to parent.
    """
    if child.startswith(parent):
        parent = parent.rstrip("/")
        child = child[len(parent):].strip("/")
    return parent.rstrip("/"), child.rstrip("/")


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


class DiskAccessor(object):
    """
    A wrapper around various disk access methods so that unit tests can easily
    replace these with a stub that doesn't actually require disk access.
    """

    def exists(self, path):
        return os.path.exists(path)

    def readFile(self, path):
        input = file(path)
        contents = input.read()
        input.close()
        return contents

    def mkdir(self, path):
        return os.mkdir(path)

    def rename(self, before, after):
        try:
            return os.rename(before, after)
        except OSError:
            # Can't rename because it's cross-volume; must copy/delete
            shutil.copy2(before, after)
            return os.remove(before)

    def isfile(self, path):
        return os.path.isfile(path)

    def symlink(self, orig, link):
        return os.symlink(orig, link)

    def chown(self, path, uid, gid, recursive=False):
        os.chown(path, uid, gid)
        if recursive:
            for root, dirs, files in os.walk(path, followlinks=True):
                for name in dirs:
                    os.chown(os.path.join(root, name), uid, gid)
                for name in files:
                    os.chown(os.path.join(root, name), uid, gid)


    def walk(self, path, followlinks=True):
        return os.walk(path, followlinks=followlinks)

    def listdir(self, path):
        return list(os.listdir(path))

    def ditto(self, src, dest):
        log("Copying with ditto: %s to %s" % (src, dest))
        return subprocess.call([DITTO, src, dest])


if __name__ == '__main__':
    main()
