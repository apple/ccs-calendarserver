#!/usr/bin/env python
#
# PromotionExtra script for calendar server.
#
# Copyright (c) 2011-2013 Apple Inc.  All Rights Reserved.
#
# IMPORTANT NOTE:  This file is licensed only for use on Apple-labeled
# computers and is subject to the terms and conditions of the Apple
# Software License Agreement accompanying the package this file is a
# part of.  You may not port this file to another platform without
# Apple's written consent.

import os
import shutil
from pwd import getpwnam
from grp import getgrnam
from plistlib import readPlist, writePlist

SRC_CONFIG_DIR = "/Applications/Server.app/Contents/ServerRoot/private/etc/caldavd"
CALENDAR_SERVER_ROOT = "/Library/Server/Calendar and Contacts"
DEST_CONFIG_DIR = "%s/Config" % (CALENDAR_SERVER_ROOT,)
CALDAVD_PLIST = "caldavd.plist"
USER_NAME = "calendar"
GROUP_NAME = "calendar"
LOG_DIR = "/var/log/caldavd"


def updatePlist(plistData):
    """
    Update the passed-in plist data with new values for disabling the XMPPNotifier,
    to set DBType to empty string indicating we'll be starting our own Postgres server,
    and to specify the new location for ConfigRoot ("Config" directory beneath ServerRoot).

    @param plistData: the plist data to update in place
    @type plistData: C{dict}
    """
    try:
        if plistData["Notifications"]["Services"]["XMPPNotifier"]["Enabled"]:
            plistData["Notifications"]["Services"]["XMPPNotifier"]["Enabled"] = False
    except KeyError:
        pass
    plistData["DBType"] = ""
    plistData["DSN"] = ""
    plistData["ConfigRoot"] = "Config"
    plistData["DBImportFile"] = "/Library/Server/Calendar and Contacts/DataDump.sql"
    # Remove RunRoot and PIDFile keys so they use the new defaults
    try:
        del plistData["RunRoot"]
    except:
        pass
    try:
        del plistData["PIDFile"]
    except:
        pass



def main():

    try:
        # Create calendar ServerRoot
        os.mkdir(CALENDAR_SERVER_ROOT)
    except OSError:
        # Already exists
        pass

    try:
        # Create calendar ConfigRoot
        os.mkdir(DEST_CONFIG_DIR)
    except OSError:
        # Already exists
        pass

    plistPath = os.path.join(DEST_CONFIG_DIR, CALDAVD_PLIST)

    if os.path.exists(plistPath):
        try:
            plistData = readPlist(plistPath)
            updatePlist(plistData)
            writePlist(plistData, plistPath)

        except Exception, e:
            print "Unable to disable update values in %s: %s" % (plistPath, e)

    else:
        # Copy configuration
        srcPlistPath = os.path.join(SRC_CONFIG_DIR, CALDAVD_PLIST)
        shutil.copy(srcPlistPath, DEST_CONFIG_DIR)

    # Create log directory
    try:
        os.mkdir(LOG_DIR, 0755)
    except OSError:
        # Already exists
        pass

    # Set ownership on log directory
    try:
        uid = getpwnam(USER_NAME).pw_uid
        gid = getgrnam(GROUP_NAME).gr_gid
        os.chown(LOG_DIR, uid, gid)
    except Exception, e:
        print "Unable to chown %s: %s" % (LOG_DIR, e)

if __name__ == '__main__':
    main()
