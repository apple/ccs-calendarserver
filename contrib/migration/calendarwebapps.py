#!/usr/bin/env python
#
# PromotionExtra script for calendar server.
#
# Copyright (c) 2011-2012 Apple Inc.  All Rights Reserved.
#
# IMPORTANT NOTE:  This file is licensed only for use on Apple-labeled
# computers and is subject to the terms and conditions of the Apple
# Software License Agreement accompanying the package this file is a
# part of.  You may not port this file to another platform without
# Apple's written consent.

import os
import shutil

SRC_CONFIG_DIR = "/Applications/Server.app/Contents/ServerRoot/private/etc/caldavd"
WEBAPPS_DIR = "/Library/Server/Web/Config/apache2/webapps"
WEBAPPS = ("com.apple.webapp.contacts.plist", "com.apple.webapp.contactsssl.plist")

def main():

    # Copy webapp plists
    for webapp in WEBAPPS:
        srcPlistPath = os.path.join(SRC_CONFIG_DIR, webapp)
        shutil.copy(srcPlistPath, WEBAPPS_DIR)

if __name__ == '__main__':
    main()
