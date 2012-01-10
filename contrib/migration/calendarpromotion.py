#!/usr/bin/env python
#
# PromotionExtra script for calendar server.
#
# Copyright (c) 2011 Apple Inc.  All Rights Reserved.
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

SRC_CONFIG_DIR = "/Applications/Server.app/Contents/ServerRoot/private/etc/caldavd"
CALENDAR_SERVER_ROOT = "/Library/Server/Calendar and Contacts"
DEST_CONFIG_DIR = "%s/Config" % (CALENDAR_SERVER_ROOT,)
USER_NAME = "calendar"
GROUP_NAME = "calendar"
LOG_DIR = "/var/log/caldavd"

def main():

    try:
        # Create calendar ServerRoot
        os.mkdir(CALENDAR_SERVER_ROOT)

        # Copy configuration
        shutil.copytree(SRC_CONFIG_DIR, DEST_CONFIG_DIR)
    except OSError:
        # Already exists
        pass

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
