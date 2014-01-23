#!/usr/bin/python

##
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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
from __future__ import print_function

from getopt import getopt, GetoptError
import os
import subprocess
import sys
import tarfile

from twistedcaldav.config import config
from calendarserver.tools.util import loadConfig

SIPP = "/Applications/Server.app/Contents/ServerRoot"
if not os.path.exists(SIPP):
    SIPP = ""
USERNAME = "caldav"
DATABASENAME = "caldav"
DUMPFILENAME = "db_backup"

PSQL = "%s/usr/bin/psql" % (SIPP,)
PGDUMP = "%s/usr/bin/pg_dump" % (SIPP,)
PGSOCKETDIR = "/var/run/caldavd/PostgresSocket"

def usage(e=None):
    name = os.path.basename(sys.argv[0])
    print("usage: %s [options] command backup-file" % (name,))
    print("")
    print(" Backup or restore calendar and addressbook data")
    print("")
    print("options:")
    print("  -f --config <path>: Specify caldavd.plist configuration path")
    print("  -h --help: print this help and exit")
    print("  -v --verbose: print additional information")
    print("")
    print("commands:")
    print("  backup: create backup-file in compressed tar format (tgz)")
    print("  restore: restore from backup-file")
    print("")

    if e:
        sys.stderr.write("%s\n" % (e,))
        sys.exit(64)
    else:
        sys.exit(0)



def dumpData(dumpFile, verbose=False):
    """
    Use pg_dump to dump data to dumpFile
    """

    cmdArgs = [
        PGDUMP,
        "-h", PGSOCKETDIR,
        "--username=%s" % (USERNAME,),
        "--clean",
        "--no-privileges",
        "--file=%s" % (dumpFile,),
        DATABASENAME
    ]
    try:
        if verbose:
            print("\nDumping data to %s" % (dumpFile,))
            print("Executing: %s" % (" ".join(cmdArgs)))
        out = subprocess.check_output(cmdArgs, stderr=subprocess.STDOUT)
        if verbose:
            print(out)
    except subprocess.CalledProcessError, e:
        if verbose:
            print(e.output)
        raise BackupError(
            "%s failed:\n%s (exit code = %d)" %
            (PGDUMP, e.output, e.returncode)
        )



def loadData(dumpFile, verbose=False):
    """
    Use psql to load data from dumpFile
    """

    cmdArgs = [
        PSQL,
        "-h", PGSOCKETDIR,
        "--username=%s" % (USERNAME,),
        "--file=%s" % (dumpFile,)
    ]
    try:
        if verbose:
            print("\nLoading data from %s" % (dumpFile,))
            print("Executing: %s" % (" ".join(cmdArgs)))
        out = subprocess.check_output(cmdArgs, stderr=subprocess.STDOUT)
        if verbose:
            print(out)
    except subprocess.CalledProcessError, e:
        if verbose:
            print(e.output)
        raise BackupError(
            "%s failed:\n%s (exit code = %d)" %
            (PSQL, e.output, e.returncode)
        )



class BackupError(Exception):
    pass



def error(s):
    sys.stderr.write("%s\n" % (s,))
    sys.exit(1)



def main():
    try:
        (optargs, args) = getopt(
            sys.argv[1:], "f:hv", [
                "config=",
                "help",
                "verbose",
            ],
        )
    except GetoptError, e:
        usage(e)

    verbose = False
    configFileName = None

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()
        elif opt in ("-f", "--config"):
            configFileName = arg
        elif opt in ("-v", "--verbose"):
            verbose = True
        else:
            raise NotImplementedError(opt)

    if len(args) != 2:
        usage("Must specify a command and a backup-file name.")

    command = args[0]
    filename = args[1]

    loadConfig(configFileName)

    serverRoot = config.ServerRoot
    dataRoot = config.DataRoot
    dumpPath = os.path.join(serverRoot, DUMPFILENAME)

    if command == "backup":

        try:
            dumpData(dumpPath, verbose=verbose)

            if verbose:
                print("Creating %s" % (filename,))
            tar = tarfile.open(filename, "w:gz")

            if verbose:
                print("Adding %s" % (serverRoot,))
            tar.add(serverRoot)

            if not dataRoot.startswith(serverRoot):
                # DataRoot is not contained within ServerRoot (i.e, it's on
                # another volume)
                if verbose:
                    print("Adding %s" % (dataRoot,))
                tar.add(dataRoot)

            tar.close()

            if verbose:
                print("Done")
        except BackupError, e:
            error("Failed to dump database; error: %s" % (e,))

    elif command == "restore":

        try:
            tar = tarfile.open(filename, "r:gz")

            if verbose:
                print("Extracting from backup file: %s" % (filename,))
            tar.extractall(path="/")

            loadData(dumpPath, verbose=verbose)

            if verbose:
                print("Cleaning up database dump file: %s" % (dumpPath,))
            os.remove(dumpPath)

        except BackupError, e:
            error("Failed to dump database; error: %s" % (e,))
            raise

    else:
        error("Unknown command '%s'" % (command,))

if __name__ == "__main__":
    main()
