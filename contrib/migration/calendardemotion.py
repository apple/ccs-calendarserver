#!/usr/bin/env python
#
# UninstallExtra script for calendar server.
#
# Copyright (c) 2011-2013 Apple Inc.  All Rights Reserved.
#
# IMPORTANT NOTE:  This file is licensed only for use on Apple-labeled
# computers and is subject to the terms and conditions of the Apple
# Software License Agreement accompanying the package this file is a
# part of.  You may not port this file to another platform without
# Apple's written consent.
from __future__ import print_function

import os
from plistlib import readPlist, writePlist

CALENDAR_SERVER_ROOT = "/Library/Server/Calendar and Contacts"
DEST_CONFIG_DIR = "%s/Config" % (CALENDAR_SERVER_ROOT,)
CALDAVD_PLIST = "caldavd.plist"

def main():

    plistPath = os.path.join(DEST_CONFIG_DIR, CALDAVD_PLIST)

    if os.path.exists(plistPath):
        try:
            # Turn off services
            plistData = readPlist(plistPath)
            plistData["EnableCalDAV"] = False
            plistData["EnableCardDAV"] = False
            writePlist(plistData, plistPath)

        except Exception, e:
            print("Unable to disable services in %s: %s" % (plistPath, e))


if __name__ == '__main__':
    main()
