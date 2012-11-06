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


# NOTES:
# - Start the "postgres for server" instance
# - See if there is calendar/contacts data
# - pgdump to a file within DataRoot
# - Drop the database within "postgres for server" instance
# - Start our service (if needed)

import datetime
import subprocess

LOG = "/Library/Logs/Migration/calendarmigrator.log"
SERVER_APP_ROOT = "/Applications/Server.app/Contents/ServerRoot"
CALENDAR_SERVER_ROOT = "/Library/Server/Calendar and Contacts"
SERVER_ADMIN = "%s/usr/sbin/serveradmin" % (SERVER_APP_ROOT,)
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
        print msg # so it appears in Setup.log
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


def main():
    startPostgres()
    if dumpOldDatabase(DATADUMPFILENAME):
        dropOldDatabase()
    stopPostgres()


if __name__ == "__main__":
    main()
