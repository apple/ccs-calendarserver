#!/usr/bin/env python
#
# changeip script for calendar server
#
# Copyright (c) 2005-2013 Apple Inc.  All Rights Reserved.
#
# IMPORTANT NOTE:  This file is licensed only for use on Apple-labeled
# computers and is subject to the terms and conditions of the Apple
# Software License Agreement accompanying the package this file is a
# part of.  You may not port this file to another platform without
# Apple's written consent.
from __future__ import print_function
from __future__ import with_statement

import os
import sys
from getopt import getopt, GetoptError

from plistlib import readPlist, writePlist


def usage():
    name = os.path.basename(sys.argv[0])
    print("Usage: %s [-hv] old-ip new-ip [old-hostname new-hostname]" % (name,))
    print("  Options:")
    print("    -h           - print this message and exit")
    print("    -v           - print additional information when running")
    print("  Arguments:")
    print("    old-ip       - current IPv4 address of the server")
    print("    new-ip       - new IPv4 address of the server")
    print("    old-hostname - current FQDN for the server")
    print("    new-hostname - new FQDN for the server")


def main():

    name = os.path.basename(sys.argv[0])

    # Since the serveradmin command must be run as root, so must this script
    if os.getuid() != 0:
        print("%s must be run as root" % (name,))
        sys.exit(1)

    try:
        (optargs, args) = getopt(
            sys.argv[1:], "hvf:", [
                "help",
                "verbose",
                "config=",
            ]
        )
    except GetoptError:
        usage()
        sys.exit(1)

    verbose = False
    configFile = "/Library/Server/Calendar and Contacts/Config/caldavd.plist"

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()
            sys.exit(1)

        elif opt in ("-v", "--verbose"):
            verbose = True

        elif opt in ("-f", "--config"):
            configFile = arg

    oldIP, newIP = args[0:2]
    try:
        oldHostname, newHostname = args[2:4]
    except ValueError:
        oldHostname = newHostname = None

    if verbose:
        print("Calendar Server: updating %s" % (configFile,))

    try:
        plist = readPlist(configFile)
    except IOError:
        print("Error: could not open %s" % (configFile,))
        sys.exit(1)
    except Exception, e:
        print("Error: could not parse %s" % (configFile,))
        raise e

    writePlist(plist, "%s.changeip.bak" % (configFile,))

    updatePlist(plist, oldIP, newIP, oldHostname, newHostname, verbose=verbose)
    writePlist(plist, configFile)

    if verbose:
        print("Calendar Server: done")

def updatePlist(plist, oldIP, newIP, oldHostname, newHostname, verbose=False):

    keys = (
        ("Authentication", "Wiki", "Hostname"),
        ("BindAddresses",),
        ("Scheduling", "iMIP", "Receiving", "Server"),
        ("Scheduling", "iMIP", "Sending", "Server"),
        ("Scheduling", "iMIP", "Sending", "Address"),
        ("ServerHostName",),
    )

    def _replace(value, oldIP, newIP, oldHostname, newHostname):
        newValue = value.replace(oldIP, newIP)
        if oldHostname and newHostname:
            newValue = newValue.replace(oldHostname, newHostname)
        if verbose and value != newValue:
            print("Changed %s -> %s" % (value, newValue))
        return newValue

    for keyPath in keys:
        parent = plist
        path = keyPath[:-1]
        key = keyPath[-1]

        for step in path:
            if not parent.has_key(step):
                parent = None
                break
            parent = parent[step]

        if parent:
            if parent.has_key(key):
                value = parent[key]

                if isinstance(value, list):
                    newValue = []
                    for item in value:
                        item = _replace(item, oldIP, newIP, oldHostname,
                            newHostname)
                        newValue.append(item)
                else:
                    newValue = _replace(value, oldIP, newIP, oldHostname,
                        newHostname)

                parent[key] = newValue






if __name__ == '__main__':
    main()
