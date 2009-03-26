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
##

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "support"))

from version import version

def find_modules():
    modules = [
        "twisted.plugins",
    ]

    for root, dirs, files in os.walk("."):
        for exclude in (
            ".svn",
            "_trial_temp",
            "build",
        ):
            if exclude in dirs:
                dirs.remove(exclude)

        if "__init__.py" in files:
            modules.append(".".join(root.split(os.path.sep)[1:]))

    return modules

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

version_string = "%s (%s)" % version()
version_file = file(os.path.join("twistedcaldav", "version.py"), "w")
version_file.write('version = "%s"\n' % version_string)
version_file.close()

#
# Set up Extension modules that need to be built
#

from distutils.core import Extension

extensions = []

if sys.platform == "darwin":
    extensions.append(
        Extension(
            "calendarserver.platform.darwin._sacl",
            extra_link_args = ["-framework", "Security"],
            sources = ["calendarserver/platform/darwin/_sacl.c"]
        )
    )

#
# Run setup
#

from distutils.core import setup

dist = setup(
    name             = "twistedcaldav",
    version          = version_string,
    description      = description,
    long_description = long_description,
    url              = None,
    classifiers      = classifiers,
    author           = "Apple Inc.",
    author_email     = None,
    license          = None,
    platforms        = [ "all" ],
    packages         = find_modules(),
    package_data     = {
                         "twistedcaldav": [
                           "zoneinfo/*.ics",
                           "zoneinfo/*/*.ics",
                           "zoneinfo/*/*/*.ics",
                           "images/*/*.jpg",
                         ],
                       },
    scripts          = [ "bin/caldavd", "bin/caldav_export" ],
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
