##
# Copyright (c) 2011-2012 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

from getopt import getopt, GetoptError
import os
import re
import subprocess
import sys

CONNECTNAME   = "_postgres"
USERNAME      = "caldav"
DATABASENAME  = "caldav"
PGSOCKETDIR   = "/Library/Server/PostgreSQL For Server Services/Socket"
SCHEMAFILE    = "/Applications/Server.app/Contents/ServerRoot/usr/share/caldavd/lib/python/txdav/common/datastore/sql_schema/current.sql"

# Executables:
CREATEDB      = "/Applications/Server.app/Contents/ServerRoot/usr/bin/createdb"
CREATEUSER    = "/Applications/Server.app/Contents/ServerRoot/usr/bin/createuser"
PSQL          = "/Applications/Server.app/Contents/ServerRoot/usr/bin/psql"

def usage(e=None):
    name = os.path.basename(sys.argv[0])
    print "usage: %s [options] username" % (name,)
    print ""
    print " Bootstrap calendar server postgres database and schema"
    print ""
    print "options:"
    print "  -h --help: print this help and exit"
    print "  -v --verbose: print additional information"
    print ""

    if e:
        sys.stderr.write("%s\n" % (e,))
        sys.exit(64)
    else:
        sys.exit(0)

def createUser(verbose=False):
    """
    Create the user which calendar server will use to access postgres.
    Return True if user is created, False if user already existed.
    Raise BootstrapError if there is an issue.
    """

    cmdArgs = [
        CREATEUSER,
        "-h", PGSOCKETDIR,
        "--username=%s" % (CONNECTNAME,),
        USERNAME,
        "--no-superuser",
        "--createdb",
        "--no-createrole"
    ]
    try:
        if verbose:
            print "\nAttempting to create user..."
            print "Executing: %s" % (" ".join(cmdArgs))
        out = subprocess.check_output(cmdArgs, stderr=subprocess.STDOUT)
        if verbose:
            print out
        return True
    except subprocess.CalledProcessError, e:
        if verbose:
            print e.output
        if "already exists" in e.output:
            return False
        raise BootstrapError(
            "%s failed:\n%s (exit code = %d)" %
            (CREATEUSER, e.output, e.returncode)
        )


def createDatabase(verbose=False):
    """
    Create the database which calendar server will use within postgres.
    Return True if database is created, False if database already existed.
    Raise BootstrapError if there is an issue.
    """

    cmdArgs = [
        CREATEDB,
        "-h", PGSOCKETDIR,
        "--username=%s" % (USERNAME,),
        DATABASENAME,
    ]
    try:
        if verbose:
            print "\nAttempting to create database..."
            print "Executing: %s" % (" ".join(cmdArgs))
        out = subprocess.check_output(cmdArgs, stderr=subprocess.STDOUT)
        if verbose:
            print out
        return True
    except subprocess.CalledProcessError, e:
        if verbose:
            print e.output
        if "already exists" in e.output:
            return False
        raise BootstrapError(
            "%s failed:\n%s (exit code = %d)" %
            (CREATEDB, e.output, e.returncode)
        )


def getSchemaVersion(verbose=False):
    """
    Return the version number for the schema installed in the database.
    Raise BootstrapError if there is an issue.
    """

    cmdArgs = [
        PSQL,
        "-h", PGSOCKETDIR,
        "-d", DATABASENAME,
        "-U", USERNAME,
        "-t",
        "-c", "select value from calendarserver where name='VERSION';",
    ]
    try:
        if verbose:
            print "\nAttempting to read schema version..."
            print "Executing: %s" % (" ".join(cmdArgs))
        out = subprocess.check_output(cmdArgs, stderr=subprocess.STDOUT)
        if verbose:
            print out
    except subprocess.CalledProcessError, e:
        if verbose:
            print e.output
        raise BootstrapError(
            "%s failed:\n%s (exit code = %d)" %
            (PSQL, e.output, e.returncode)
        )

    try:
        version = int(out)
    except ValueError, e:
        raise BootstrapError(
            "Failed to parse schema version: %s" % (e,)
        )
    return version

def installSchema(verbose=False):
    """
    Install the calendar server database schema.
    Return True if database is created, False if database already existed.
    Raise BootstrapError if there is an issue.
    """

    cmdArgs = [
        PSQL,
        "-h", PGSOCKETDIR,
        "-U", USERNAME,
        "-f", SCHEMAFILE,
    ]
    try:
        if verbose:
            print "Executing: %s" % (" ".join(cmdArgs))
        out = subprocess.check_output(cmdArgs, stderr=subprocess.STDOUT)
        if verbose:
            print out
        if "already exists" in out:
            return False
        return True
    except subprocess.CalledProcessError, e:
        if verbose:
            print e.output
        raise BootstrapError(
            "%s failed:\n%s (exit code = %d)" %
            (PSQL, e.output, e.returncode)
        )


class BootstrapError(Exception):
    pass

def error(s):
    sys.stderr.write("%s\n" % (s,))
    sys.exit(1)

def main():
    try:
        (optargs, args) = getopt(
            sys.argv[1:], "hv", [
                "help",
                "verbose",
            ],
        )
    except GetoptError, e:
        usage(e)

    verbose = False

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()
        elif opt in ("-v", "--verbose"):
            verbose = True
        else:
            raise NotImplementedError(opt)


    # Create the calendar server database user within postgres
    try:
        newlyCreated = createUser(verbose=verbose)
        if newlyCreated:
            print "Database user '%s' created" % (USERNAME,)
        else:
            print "Database User '%s' exists" % (USERNAME,)
    except BootstrapError, e:
        error("Failed to create database user '%s': %s" % (USERNAME, e))

    # Create the calendar server database within postgres
    try:
        newlyCreated = createDatabase(verbose=verbose)
        if newlyCreated:
            print "Database '%s' created" % (DATABASENAME,)
        else:
            print "Database '%s' exists" % (DATABASENAME,)
    except BootstrapError, e:
        error("Failed to create database '%s': %s" % (DATABASENAME, e))

    # Retrieve the version number of the installed schema
    try:
        version = getSchemaVersion(verbose=verbose)
    except BootstrapError, e:
        version = 0

    # Retrieve the version number from the schema file
    try:
        data = open(SCHEMAFILE).read()
    except IOError:
        print "Unable to open the schema file: %s" % (SCHEMAFILE,)
    else:
        found = re.search("insert into CALENDARSERVER values \('VERSION', '(\d+)'\);", data)
        if found is None:
            print "Schema is missing required schema VERSION insert statement: %s" % (SCHEMAFILE,)
        else:
            required_version = int(found.group(1))
            if version == required_version:
                print "Latest schema version (%d) is installed" % (version,)
        
            elif version == 0: # No schema installed
                installSchema(verbose=verbose)
                version = getSchemaVersion(verbose=verbose)
                print "Successfully installed schema version %d" % (version,)
        
            else: # upgrade needed
                error(
                    "Schema needs to be upgraded from %d to %d" %
                    (version, required_version)
                )

if __name__ == "__main__":
    main()
