#!/usr/bin/env python
#
# CommonExtra script for calendar server.
#
# Copyright (c) 2012 Apple Inc.  All Rights Reserved.
#
# IMPORTANT NOTE:  This file is licensed only for use on Apple-labeled
# computers and is subject to the terms and conditions of the Apple
# Software License Agreement accompanying the package this file is a
# part of.  You may not port this file to another platform without
# Apple's written consent.

import os
from plistlib import readPlist, writePlist

CALENDAR_SERVER_ROOT = "/Library/Server/Calendar and Contacts"
DEST_CONFIG_DIR = "%s/Config" % (CALENDAR_SERVER_ROOT,)
CALDAVD_PLIST = "caldavd.plist"


def updatePlist(plistData):
    """
    Remove the RunRoot, PIDFile keys so they use new defaults

    @param plistData: the plist data to update in place
    @type plistData: C{dict}
    """

    try:
        del plistData["RunRoot"]
    except:
        pass
    try:
        del plistData["PIDFile"]
    except:
        pass


def main():

    plistPath = os.path.join(DEST_CONFIG_DIR, CALDAVD_PLIST)

    if os.path.exists(plistPath):
        try:
            plistData = readPlist(plistPath)
            updatePlist(plistData)
            writePlist(plistData, plistPath)

        except Exception, e:
            print "Unable to update values in %s: %s" % (plistPath, e)


if __name__ == '__main__':
    main()
