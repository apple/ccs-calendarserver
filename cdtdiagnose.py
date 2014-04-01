#!/usr/bin/env python
#
##
# Copyright (c) 2013 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

import os
import datetime
import shutil
import sys
from subprocess import Popen, PIPE

server_root = "/Applications/Server.app/Contents/ServerRoot"
os.environ["PATH"] = "%s/usr/bin:%s" % (server_root, os.environ["PATH"])
library_root = "/Library/Server/Calendar and Contacts"

directory_node = "/LDAPv3/127.0.0.1"


def cmd(args, input=None, raiseOnFail=True):

    if input:
        p = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=True)
        result = p.communicate(input)
    else:
        p = Popen(args, stdout=PIPE, stderr=PIPE, shell=True)
        result = p.communicate()

    if raiseOnFail and p.returncode:
        raise RuntimeError(result[1])
    return result[0], p.returncode


if __name__ == "__main__":

    print "Running CDT diagnostics due to test failure."
    log = []

    def error(message, e):
        log.append("CDT diagnostic: %s" % (message,))
        log.append(str(e))
        print "\n".join(log)
        sys.exit(1)

    now = datetime.datetime.now()
    now = now.replace(microsecond=0)
    dirname = "cdtdiagnose-%s" % (now.strftime("%Y%m%d-%H%M%S"),)
    try:
        os.mkdir(dirname)
    except Exception as e:
        error("Could not create archive directory: '%s'" % (dirname,), e)

    # Copy CDT log file file
    server_path = "cdt.txt"
    archive_path = os.path.join(dirname, os.path.basename(server_path))
    try:
        shutil.copy(server_path, archive_path)
    except Exception as e:
        error("Could not copy cdt results file: '%s' to '%s'" % (server_path, archive_path,), e)

    # Copy serverinfo file
    server_path = "scripts/server/serverinfo-caldav.xml"
    archive_path = os.path.join(dirname, os.path.basename(server_path))
    try:
        shutil.copy(server_path, archive_path)
    except Exception as e:
        error("Could not copy server info file: '%s' to '%s'" % (server_path, archive_path,), e)

    # Get server logs
    server_path = "/var/log/caldavd"
    archive_path = os.path.join(dirname, "logs")
    try:
        shutil.copytree(server_path, archive_path)
    except Exception as e:
        error("Could not copy server logs: '%s' to '%s'" % (server_path, archive_path,), e)

    # Get server config files
    server_path = os.path.join(server_root, "etc", "caldavd")
    archive_path = os.path.join(dirname, "etc")
    try:
        shutil.copytree(server_path, archive_path)
    except Exception as e:
        error("Could not copy server conf: '%s' to '%s'" % (server_path, archive_path,), e)

    server_path = library_root
    archive_path = os.path.join(dirname, "Library")
    try:
        shutil.copytree(server_path, archive_path)
    except Exception as e:
        error("Could not copy library items: '%s' to '%s'" % (server_path, archive_path,), e)

    # Dump OD data
    try:
        results = ["*** Users"]
        results.extend(cmd("dscl %s -readall Users" % (directory_node,))[0].splitlines())
        results.append("\n\n*** Groups")
        results.extend(cmd("dscl %s -readall Groups" % (directory_node,))[0].splitlines())
        results.append("")

        with open(os.path.join(dirname, "dscl_dump.txt"), "w") as f:
            f.write("\n".join(results))
    except Exception as e:
        error("Could not dump OD data.", e)

    # Now archive the diagnostics data
    try:
        archive_name = shutil.make_archive(dirname, "gztar", dirname)
    except Exception as e:
        error("Could not make diagnostics archive.", e)

    print "Saved diagnostics to '%s'" % (archive_name,)
