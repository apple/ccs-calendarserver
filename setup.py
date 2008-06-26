#!/usr/bin/env python

##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

import sys
import os

#
# Compute the version number.
#

base_version = "2.0"

branches = (
    "tags/release/CalendarServer-" + base_version,
    "branches/release/CalendarServer-" + base_version + "-dev",
    "trunk",
)

for branch in branches:
    cmd = "svnversion -n %r %s" % (os.path.dirname(__file__), branch)
    svnversion = os.popen(cmd)
    svn_revision = svnversion.read()
    svnversion.close()

    if "S" in svn_revision:
        continue

    if branch == "trunk":
        base_version = "trunk"
    elif branch.endswith("-dev"):
        base_version += "-dev"

    if svn_revision == "exported":
        if "RC_JASPER" in os.environ:
            # Weird Apple thing: Get the B&I version number from the path
            if __file__.startswith(os.path.sep):
                project_name = os.path.basename(os.path.dirname(__file__))
            else:
                wd = os.path.dirname(__file__)
                if wd:
                    os.chdir(wd)
                project_name = os.path.basename(os.getcwd())

            prefix = "CalendarServer-"

            if project_name.startswith(prefix):
                version = version = "%s (%s)" % (base_version, project_name[len(prefix):])
                break

        version = "%s (unknown)" % (base_version,)
    else:
        version = "%s (r%s)" % (base_version, svn_revision)

    break
else:
    version = "unknown (%s :: %s)" % (base_version, svn_revision)

#
# Options
#

description = "CalDAV protocol extensions to twisted.web2.dav",
long_description = """
Extends twisted.web2.dav to implement CalDAV-aware resources and methods.
"""

classifiers = None

#
# Write version file
#

version_file = file(os.path.join("twistedcaldav", "version.py"), "w")
version_file.write('version = "%s"\n' % (version,))
version_file.close()

#
# Set up Extension modules that need to be built
#

from distutils.core import Extension

extensions = []

if sys.platform == "darwin":
    extensions.append(
        Extension(
            "twistedcaldav._sacl",
            extra_compile_args = ["-arch", "ppc", "-arch", "i386"],
            extra_link_args = ["-framework", "Security", "-arch", "ppc", "-arch", "i386"],
            sources = ["twistedcaldav/_sacl.c"]
        )
    )

#
# Run setup
#

from distutils.core import setup

dist = setup(
    name             = "twistedcaldav",
    version          = version,
    description      = description,
    long_description = long_description,
    url              = None,
    classifiers      = classifiers,
    author           = "Apple Inc.",
    author_email     = None,
    license          = None,
    platforms        = [ "all" ],
    packages         = [
                         "twistedcaldav",
                         "twistedcaldav.directory", 
                         "twistedcaldav.method",
                         "twistedcaldav.query", 
                         "twistedcaldav.admin",
                         "twistedcaldav.py", 
                         "twisted",
                       ],
    package_data     = {
                         "twisted": ["plugins/caldav.py",
                                     "plugins/kqueuereactor.py"],
                         "twistedcaldav": ["zoneinfo/*.ics", "zoneinfo/*/*.ics", "zoneinfo/*/*/*.ics"],
                       },
    scripts          = [ "bin/caldavd", "bin/caladmin" ],
    data_files       = [ ("caldavd", ["conf/caldavd.plist"]) ],
    ext_modules      = extensions,
    py_modules       = ["kqreactor"],
)

if "install" in dist.commands:
    import os
    install_scripts = dist.command_obj["install"].install_scripts
    install_lib = dist.command_obj["install"].install_lib
    root = dist.command_obj["install"].root
    base = dist.command_obj["install"].install_base

    if root:
        install_lib = install_lib[len(root):]

    for script in dist.scripts:
        scriptPath = os.path.join(install_scripts, os.path.basename(script))

        print "rewriting %s" % (scriptPath,)

        script = []
    
        fileType = None

        for line in file(scriptPath, "r"):
            if not fileType:
                if line.startswith("#!"):
                    if "python" in line.lower():
                        fileType = "python"
                    elif "sh" in line.lower():
                        fileType = "sh"

            line = line.rstrip("\n")
            if fileType == "sh":
                if line == "#PYTHONPATH":
                    script.append('PYTHONPATH="%s:$PYTHONPATH"' % (install_lib,))
                elif line == "#PATH":
                    script.append('PATH="%s:$PATH"' % (os.path.join(base, "bin"),))
                else:
                    script.append(line)

            elif fileType == "python":
                if line == "#PYTHONPATH":
                    script.append('PYTHONPATH="%s"' % (install_lib,))
                elif line == "#PATH":
                    script.append('PATH="%s"' % (os.path.join(base, "bin"),))
                else:
                    script.append(line)

            else:
                script.append(line)

        newScript = open(scriptPath, "w")
        newScript.write("\n".join(script))
        newScript.close()
