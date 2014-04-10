#!/usr/bin/env python
#
# changeip script for calendar server
#
# Copyright (c) 2005-2014 Apple Inc.  All Rights Reserved.
#
# IMPORTANT NOTE:  This file is licensed only for use on Apple-labeled
# computers and is subject to the terms and conditions of the Apple
# Software License Agreement accompanying the package this file is a
# part of.  You may not port this file to another platform without
# Apple's written consent.
from __future__ import print_function
from __future__ import with_statement


import datetime
from getopt import getopt, GetoptError
import os
import plistlib
import subprocess
import sys


SERVER_APP_ROOT = "/Applications/Server.app/Contents/ServerRoot"
CALENDARSERVER_CONFIG = "%s/usr/sbin/calendarserver_config" % (SERVER_APP_ROOT,)


def serverRootLocation():
    """
    Return the ServerRoot value from the servermgr_calendar.plist.  If not
    present, return the default.
    """
    plist = "/Library/Preferences/com.apple.servermgr_calendar.plist"
    serverRoot = u"/Library/Server/Calendar and Contacts"
    if os.path.exists(plist):
        serverRoot = plistlib.readPlist(plist).get("ServerRoot", serverRoot)
    return serverRoot



def usage():
    name = os.path.basename(sys.argv[0])
    print("Usage: %s [-hv] old-ip new-ip [old-hostname new-hostname]" % (name,))
    print("  Options:")
    print("    -h           - print this message and exit")
    print("    -f <file>    - path to config file")
    print("  Arguments:")
    print("    old-ip       - current IPv4 address of the server")
    print("    new-ip       - new IPv4 address of the server")
    print("    old-hostname - current FQDN for the server")
    print("    new-hostname - new FQDN for the server")


def log(msg):
    serverRoot = serverRootLocation()
    logDir = os.path.join(serverRoot, "Logs")
    logFile = os.path.join(logDir, "changeip.log")

    try:
        timestamp = datetime.datetime.now().strftime("%b %d %H:%M:%S")
        msg = "changeip_calendar: %s %s" % (timestamp, msg)
        with open(logFile, 'a') as output:
            output.write("%s\n" % (msg,))
    except IOError:
        # Could not write to log
        pass


def main():

    name = os.path.basename(sys.argv[0])

    # Since the serveradmin command must be run as root, so must this script
    if os.getuid() != 0:
        print("%s must be run as root" % (name,))
        sys.exit(1)

    try:
        (optargs, args) = getopt(
            sys.argv[1:], "hf:", [
                "help",
                "config=",
            ]
        )
    except GetoptError:
        usage()
        sys.exit(1)

    configFile = None

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()
            sys.exit(1)

        elif opt in ("-f", "--config"):
            configFile = arg

    oldIP, newIP = args[0:2]
    try:
        oldHostname, newHostname = args[2:4]
    except ValueError:
        oldHostname = newHostname = None

    log("args: {}".format(args))

    config = readConfig(configFile=configFile)

    updateConfig(
        config,
        oldIP, newIP,
        oldHostname, newHostname
    )
    writeConfig(config)



def sendCommand(commandDict, configFile=None):

    args = [CALENDARSERVER_CONFIG]
    if configFile is not None:
        args.append("-f {}".format(configFile))

    child = subprocess.Popen(
        args=args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    commandString = plistlib.writePlistToString(commandDict)
    log("Sending to calendarserver_config: {}".format(commandString))

    output, error = child.communicate(input=commandString)
    log("Output from calendarserver_config: {}".format(output))
    if child.returncode:
        log(
            "Error from calendarserver_config: {}, {}".format(
                child.returncode, error
            )
        )
        return None
    else:
        return plistlib.readPlistFromString(output)["result"]


def readConfig(configFile=None):
    """
    Ask calendarserver_config for the current configuration
    """

    command = {
        "command": "readConfig"
    }
    return sendCommand(command)



def writeConfig(valuesDict, configFile=None):
    """
    Ask calendarserver_config to update the configuration
    """
    command = {
        "command": "writeConfig",
        "Values": valuesDict,
    }
    return sendCommand(command)


def updateConfig(
    config,
    oldIP, newIP,
    oldHostname, newHostname,
    configFile=None
):

    keys = (
        ("Scheduling", "iMIP", "Receiving", "Server"),
        ("Scheduling", "iMIP", "Sending", "Server"),
        ("Scheduling", "iMIP", "Sending", "Address"),
        ("ServerHostName",),
    )

    def _replace(value, oldIP, newIP, oldHostname, newHostname):
        newValue = value.replace(oldIP, newIP)
        if oldHostname and newHostname:
            newValue = newValue.replace(oldHostname, newHostname)
        if value != newValue:
            log("Changed %s -> %s" % (value, newValue))
        return newValue

    for keyPath in keys:
        parent = config
        path = keyPath[:-1]
        key = keyPath[-1]

        for step in path:
            if step not in parent:
                parent = None
                break
            parent = parent[step]

        if parent:
            if key in parent:
                value = parent[key]

                if isinstance(value, list):
                    newValue = []
                    for item in value:
                        item = _replace(
                            item, oldIP, newIP, oldHostname, newHostname
                        )
                        newValue.append(item)
                else:
                    newValue = _replace(
                        value, oldIP, newIP, oldHostname, newHostname
                    )

                parent[key] = newValue


if __name__ == '__main__':
    main()
