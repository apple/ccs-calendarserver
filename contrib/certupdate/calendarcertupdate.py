#!/usr/bin/env python
#
# CertUpdate script for calendar / addresbook service.
#
# This script will be called with the path to the cert file in
# /etc/certificates and also the keychain persistent reference if
# we have one available. For the remove command, the handler
# returns 0 = don't care, 1 = please keep, 2 = an error occurred.
# For the replace command the handler returns
# 0 = don't care/ cert replaced, 2 = an error occurred.
#
# Copyright (c) 2011 Apple Inc.  All Rights Reserved.
#
# IMPORTANT NOTE:  This file is licensed only for use on Apple-labeled
# computers and is subject to the terms and conditions of the Apple
# Software License Agreement accompanying the package this file is a
# part of.  You may not port this file to another platform without
# Apple's written consent.

import datetime
import subprocess
import sys

from plistlib import readPlist, writePlist

LOG = "/var/log/caldavd/certupdate.log"
SERVICE_NAME = "calendar"
CALDAVD_PLIST = "/Library/Server/Calendar and Contacts/Config/caldavd.plist"
SERVER_ADMIN = "/usr/sbin/serveradmin"

def main():

    log(sys.argv)
    numArgs = len(sys.argv) - 1
    if numArgs == 3:
        if sys.argv[1] != "remove":
            die("Bad command line; 'remove' expected", 2)
        if isThisMyCert(CALDAVD_PLIST, sys.argv[2]):
            die("%s is in use by calendar" % (sys.argv[2],), 1)
        else:
            die("%s is not in use by calendar" % (sys.argv[2],), 0)

    elif numArgs == 5:
        if sys.argv[1] != "replace":
            die("Bad command line; 'replace' expected", 2)
        if isThisMyCert(CALDAVD_PLIST, sys.argv[2]):
            try:
                replaceCert(CALDAVD_PLIST, sys.argv[4])
                restartService(CALDAVD_PLIST)
                die("Replaced calendar cert with %s" % (sys.argv[4],), 0)
            except Exception, e:
                die("Error replacing calendar cert with %s: %s" % (sys.argv[4], e), 2)

        else:
            die("%s is not in use by calendar" % (sys.argv[2],), 0)

    else:
        # Wrong number of args
        die("Bad command line; incorrect number of arguments", 2)


def getMyCert(plistPath):
    """
    Return SSLCertificate from the plist at plistPath
    """
    plist = readPlist(plistPath)
    return plist.get("SSLCertificate", None)


def isThisMyCert(plistPath, otherCert):
    """
    Compare otherCert against SSLCertificate from the plist at plistPath
    """
    myCert = getMyCert(plistPath)
    return otherCert == myCert


def replaceCert(plistPath, otherCert):
    """
    Replace SSL settings in plist at plistPath based on otherCert path
    """
    log("Reading plist %s" % (plistPath,))
    plist = readPlist(plistPath)
    log("Read in plist %s" % (plistPath,))

    basePath = otherCert[:-len("cert.pem")]
    log("Base path is %s" % (basePath,))

    log("Setting SSLCertificate to %s" % (otherCert,))
    plist["SSLCertificate"] = otherCert

    otherChain = basePath + "chain.pem"
    log("Setting SSLAuthorityChain to %s" % (otherChain,))
    plist["SSLAuthorityChain"] = otherChain

    otherKey = basePath + "key.pem"
    log("Setting SSLPrivateKey to %s" % (otherKey,))
    plist["SSLPrivateKey"] = otherKey

    log("Writing plist %s" % (plistPath,))
    writePlist(plist, plistPath)


def restartService(plistPath):
    """
    Use serveradmin to restart the service.
    """

    plist = readPlist(plistPath)

    if not plist.get("EnableSSL", False):
        log("SSL is not enabled, so no need to restart")
        return

    if plist.get("EnableCardDAV", False):
        log("Stopping addressbook service via serveradmin")
        ret = subprocess.call([SERVER_ADMIN, "stop", "addressbook"])
        log("serveradmin exited with %d" % (ret,))
        log("Starting addressbook service via serveradmin")
        ret = subprocess.call([SERVER_ADMIN, "start", "addressbook"])
        log("serveradmin exited with %d" % (ret,))
    elif plist.get("EnableCalDAV", False):
        log("Stopping calendar service via serveradmin")
        ret = subprocess.call([SERVER_ADMIN, "stop", "calendar"])
        log("serveradmin exited with %d" % (ret,))
        log("Starting calendar service via serveradmin")
        ret = subprocess.call([SERVER_ADMIN, "start", "calendar"])
        log("serveradmin exited with %d" % (ret,))
    else:
        log("Neither calendar nor addressbook services were running")


def log(msg):
    try:
        timestamp = datetime.datetime.now().strftime("%b %d %H:%M:%S")
        msg = "calendarcertupdate: %s %s" % (timestamp, msg)
        with open(LOG, 'a') as output:
            output.write("%s\n" % (msg,)) # so it appears in our log
    except IOError:
        # Could not write to log
        pass


def die(msg, exitCode):
    """
    Log msg and exit with exitCode
    """
    log(msg)
    sys.exit(exitCode)


if __name__ == '__main__':
    main()
