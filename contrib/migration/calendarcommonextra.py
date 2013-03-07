#!/usr/bin/env python
#
# CommonExtra script for calendar server.
#
# Copyright (c) 2012-2013 Apple Inc.  All Rights Reserved.
#
# IMPORTANT NOTE:  This file is licensed only for use on Apple-labeled
# computers and is subject to the terms and conditions of the Apple
# Software License Agreement accompanying the package this file is a
# part of.  You may not port this file to another platform without
# Apple's written consent.
from __future__ import print_function

import datetime
import subprocess
from plistlib import readPlist, writePlist

LOG = "/Library/Logs/Migration/calendarmigrator.log"
SERVER_APP_ROOT = "/Applications/Server.app/Contents/ServerRoot"
CALENDAR_SERVER_ROOT = "/Library/Server/Calendar and Contacts"
CALDAVD_PLIST = "%s/Config/caldavd.plist" % (CALENDAR_SERVER_ROOT,)
SERVER_ADMIN = "%s/usr/sbin/serveradmin" % (SERVER_APP_ROOT,)
CERT_ADMIN = "/Applications/Server.app/Contents/ServerRoot/usr/sbin/certadmin"
PGDUMP = "%s/usr/bin/pg_dump" % (SERVER_APP_ROOT,)
DROPDB = "%s/usr/bin/dropdb" % (SERVER_APP_ROOT,)
POSTGRES_SERVICE_NAME = "postgres_server"
PGSOCKETDIR = "/Library/Server/PostgreSQL For Server Services/Socket"
USERNAME      = "caldav"
DATABASENAME  = "caldav"
DATADUMPFILENAME = "%s/DataDump.sql" % (CALENDAR_SERVER_ROOT,)

def log(msg):
    try:
        timestamp = datetime.datetime.now().strftime("%b %d %H:%M:%S")
        msg = "calendarcommonextra: %s %s" % (timestamp, msg)
        print(msg) # so it appears in Setup.log
        with open(LOG, 'a') as output:
            output.write("%s\n" % (msg,)) # so it appears in our log
    except IOError:
        # Could not write to log
        pass


def startPostgres():
    """
    Start postgres via serveradmin

    This will block until postgres is up and running
    """
    log("Starting %s via %s" % (POSTGRES_SERVICE_NAME, SERVER_ADMIN))
    ret = subprocess.call([SERVER_ADMIN, "start", POSTGRES_SERVICE_NAME])
    log("serveradmin exited with %d" % (ret,))

def stopPostgres():
    """
    Stop postgres via serveradmin
    """
    log("Stopping %s via %s" % (POSTGRES_SERVICE_NAME, SERVER_ADMIN))
    ret = subprocess.call([SERVER_ADMIN, "stop", POSTGRES_SERVICE_NAME])
    log("serveradmin exited with %d" % (ret,))


def dumpOldDatabase(dumpFile):
    """
    Use pg_dump to dump data to dumpFile
    """

    cmdArgs = [
        PGDUMP,
        "-h", PGSOCKETDIR,
        "--username=%s" % (USERNAME,),
        "--inserts",
        "--no-privileges",
        "--file=%s" % (dumpFile,),
        DATABASENAME
    ]
    try:
        log("Dumping data to %s" % (dumpFile,))
        log("Executing: %s" % (" ".join(cmdArgs)))
        out = subprocess.check_output(cmdArgs, stderr=subprocess.STDOUT)
        log(out)
        return True
    except subprocess.CalledProcessError, e:
        log(e.output)
        return False


def dropOldDatabase():
    """
    Use dropdb to delete the caldav database from the shared postgres server
    """

    cmdArgs = [
        DROPDB,
        "-h", PGSOCKETDIR,
        "--username=%s" % (USERNAME,),
        DATABASENAME
    ]
    try:
        log("\nDropping %s database" % (DATABASENAME,))
        log("Executing: %s" % (" ".join(cmdArgs)))
        out = subprocess.check_output(cmdArgs, stderr=subprocess.STDOUT)
        log(out)
        return True
    except subprocess.CalledProcessError, e:
        log(e.output)
        return False


def getDefaultCert():
    """
    Ask certadmin for default cert
    @returns: path to default certificate, or empty string if no default
    @rtype: C{str}
    """
    child = subprocess.Popen(
        args=[CERT_ADMIN, "--default-certificate-path"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    output, error = child.communicate()
    if child.returncode:
        log("Error looking up default certificate (%d): %s" % (child.returncode, error))
        return ""
    else:
        certPath = output.strip()
        log("Default certificate is: %s" % (certPath,))
        return certPath

def updateSettings(settings, otherCert):
    """
    Replace SSL settings based on otherCert path
    """
    basePath = otherCert[:-len("cert.pem")]
    log("Base path is %s" % (basePath,))

    log("Setting SSLCertificate to %s" % (otherCert,))
    settings["SSLCertificate"] = otherCert

    otherChain = basePath + "chain.pem"
    log("Setting SSLAuthorityChain to %s" % (otherChain,))
    settings["SSLAuthorityChain"] = otherChain

    otherKey = basePath + "key.pem"
    log("Setting SSLPrivateKey to %s" % (otherKey,))
    settings["SSLPrivateKey"] = otherKey

    settings["EnableSSL"] = True
    settings["RedirectHTTPToHTTPS"] = True
    settings.setdefault("Authentication", {}).setdefault("Basic", {})["Enabled"] = True

def setCert(plistPath, otherCert):
    """
    Replace SSL settings in plist at plistPath based on otherCert path
    """
    log("Reading plist %s" % (plistPath,))
    plist = readPlist(plistPath)
    log("Read in plist %s" % (plistPath,))

    updateSettings(plist, otherCert)

    log("Writing plist %s" % (plistPath,))
    writePlist(plist, plistPath)

def isSSLEnabled(plistPath):
    """
    Examine plist for EnableSSL
    """
    log("Reading plist %s" % (plistPath,))
    plist = readPlist(plistPath)
    return plist.get("EnableSSL", False)

def main():
    startPostgres()
    if dumpOldDatabase(DATADUMPFILENAME):
        dropOldDatabase()
    stopPostgres()

    if not isSSLEnabled(CALDAVD_PLIST):
        defaultCertPath = getDefaultCert()
        log("Default cert path: %s" % (defaultCertPath,))
        if defaultCertPath:
            setCert(CALDAVD_PLIST, defaultCertPath)


if __name__ == "__main__":
    main()
