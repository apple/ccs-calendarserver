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
import optparse
import os
import shutil
import sys

from plistlib import readPlist, writePlist

LAUNCHD_KEY = "org.calendarserver.calendarserver"
LOG = "/Library/Logs/Migration/calendarmigrator.log"
SERVICE_NAME = "calendar"
LAUNCHD_OVERRIDES = "var/db/launchd.db/com.apple.launchd/overrides.plist"
LAUNCHD_PREFS_DIR = "System/Library/LaunchDaemons"
CALDAVD_CONFIG_DIR = "private/etc/caldavd"

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

    if options.sourceRoot:

        if os.path.exists(options.sourceRoot):
            migrateConfiguration(options)
            migrateRunState(options)

    else:
        log("ERROR: --sourceRoot must be specified")
        sys.exit(1)


def migrateRunState(options):
    """
    Try to determine whether server was running in previous system, then
    modify the launchd settings in the new system.
    """

    try:
        disabled = isServiceDisabled(options.sourceRoot, LAUNCHD_KEY)
        log("Service '%s' was previously %s" %
            (LAUNCHD_KEY, "disabled" if disabled else "enabled"))
    except ServiceStateError, e:
        log("Couldn't determine previous state of service '%s': %s" %
            (LAUNCHD_KEY, e))
        return

    setServiceStateDisabled(options.targetRoot, LAUNCHD_KEY, disabled)


def migrateConfiguration(options):
    """
    Copy files/directories/symlinks from previous system's /etc/caldavd

    Skips anything ending in ".default".
    Regular files overwrite copies in new system.
    Directories and symlinks only copied over if they don't overwrite anything.
    """

    oldConfigDir = os.path.join(options.sourceRoot, CALDAVD_CONFIG_DIR)
    if not os.path.exists(oldConfigDir):
        log("Old configuration directory does not exist: %s" % (oldConfigDir,))
        return

    newConfigDir = os.path.join(options.targetRoot, CALDAVD_CONFIG_DIR)
    if not os.path.exists(newConfigDir):
        log("New configuration directory does not exist: %s" % (newConfigDir,))
        return

    log("Copying configuration files from %s to %s" % (oldConfigDir, newConfigDir))

    for name in os.listdir(oldConfigDir):

        if not name.endswith(".default"):

            oldPath = os.path.join(oldConfigDir, name)
            newPath = os.path.join(newConfigDir, name)

            if os.path.islink(oldPath) and not os.path.exists(newPath):
                # Recreate the symlink if it won't overwrite an existing file
                link = os.readlink(oldPath)
                log("Symlinking %s to %s" % (newPath, link))
                os.symlink(link, newPath)

            elif os.path.isfile(oldPath):

                if name == "caldavd.plist":
                    # Migrate certain settings from the old plist to new:
                    log("Parsing %s" % (oldPath,))
                    oldPlist = readPlist(oldPath)
                    if os.path.exists(newPath):
                        log("Parsing %s" % (newPath,))
                        newPlist = readPlist(newPath)
                        log("Removing %s" % (newPath,))
                        os.remove(newPath)
                    else:
                        newPlist = { }
                    log("Processing %s" % (oldPath,))
                    mergePlist(oldPlist, newPlist)
                    log("Writing %s" % (newPath,))
                    writePlist(newPlist, newPath)

                else:
                    # Copy the file over, overwriting copy in newConfigDir
                    log("Copying file %s to %s" % (oldPath, newConfigDir))
                    shutil.copy2(oldPath, newConfigDir)


            elif os.path.isdir(oldPath) and not os.path.exists(newPath):
                # Copy the dir over, but only if new one doesn't exist
                log("Copying directory %s to %s" % (oldPath, newPath))
                shutil.copytree(oldPath, newPath, symlinks=True)

def mergePlist(oldPlist, newPlist):

    # The following CalendarServer v1.x keys are ignored:
    # EnableNotifications, Verbose

    # These keys are copied verbatim:
    for key in (
        "AccessLogFile", "AdminPrincipals", "BindAddresses", "BindHTTPPorts",
        "BindSSLPorts", "ControlSocket", "DocumentRoot", "EnableDropBox",
        "EnableProxyPrincipals", "EnableSACLs", "ErrorLogFile", "GroupName",
        "HTTPPort", "MaximumAttachmentSize", "MultiProcess", "PIDFile",
        "ProcessType", "ResponseCompression", "RotateAccessLog",
        "SSLAuthorityChain", "SSLCertificate", "SSLPort", "SSLPrivateKey",
        "ServerHostName", "ServerStatsFile", "SudoersFile", "UserName",
        "UserQuota",
    ):
        if key in oldPlist:
            newPlist[key] = oldPlist[key]

    # "Wiki" is a new authentication in v2.x; copy all "Authentication" sub-keys    # over, and "Wiki" will be picked up from the new plist:
    if "Authentication" in oldPlist:
        for key in oldPlist["Authentication"]:
            newPlist["Authentication"][key] = oldPlist["Authentication"][key]

    # Strip out any unknown params from the DirectoryService:
    if "DirectoryService" in oldPlist:
        newPlist["DirectoryService"] = oldPlist["DirectoryService"]
        for key in newPlist["DirectoryService"]["params"].keys():
            if key not in (
                "node",
                "cacheTimeout", "xmlFile"
            ):
                del newPlist["DirectoryService"]["params"][key]

    # Place DataRoot as a sibling of DocumentRoot:
    parent = os.path.dirname(newPlist["DocumentRoot"].rstrip("/"))
    newPlist["DataRoot"] = os.path.join(parent, "Data")


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
            output.write("%s %s\n" % (timestamp, msg))
    except IOError:
        # Could not write to log
        pass


if __name__ == '__main__':
    main()
