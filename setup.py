#!/usr/bin/env python

##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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

from __future__ import print_function

from os.path import dirname, basename, abspath, join as joinpath, normpath
from setuptools import setup, find_packages as setuptools_find_packages
import errno
import os
import subprocess


#
# Utilities
#
def find_packages():
    modules = [
        "twisted.plugins",
    ]

    for pkg in filter(
        lambda p: os.path.isdir(p) and os.path.isfile(os.path.join(p, "__init__.py")),
        os.listdir(".")
    ):
        modules.extend([pkg, ] + [
            "{}.{}".format(pkg, subpkg)
            for subpkg in setuptools_find_packages(pkg)
        ])
    return modules



def version():
    """
    Compute the version number.
    """

    base_version = "6.1"

    branches = tuple(
        branch.format(
            project="twext",
            version=base_version,
        )
        for branch in (
            "tags/release/{project}-{version}",
            "branches/release/{project}-{version}-dev",
            "trunk",
        )
    )

    source_root = dirname(abspath(__file__))

    for branch in branches:
        cmd = ["svnversion", "-n", source_root, branch]

        try:
            svn_revision = subprocess.check_output(cmd)

        except OSError as e:
            if e.errno == errno.ENOENT:
                full_version = base_version + "-unknown"
                break
            raise

        if "S" in svn_revision:
            continue

        full_version = base_version

        if branch == "trunk":
            full_version += "b.trunk"
        elif branch.endswith("-dev"):
            full_version += "c.dev"

        if svn_revision in ("exported", "Unversioned directory"):
            full_version += "-unknown"
        else:
            full_version += "-r{revision}".format(revision=svn_revision)

        break
    else:
        full_version = base_version
        full_version += "a.unknown"
        full_version += "-r{revision}".format(revision=svn_revision)

    return full_version



#
# Options
#

name = "CalendarServer"

description = "Calendar and Contacts Server"

long_description = file(joinpath(dirname(__file__), "README.rst")).read()

url = "http://www.calendarserver.org/"

classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Framework :: Twisted",
    "Intended Audience :: Information Technology",
    "License :: OSI Approved :: Apache Software License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 2.7",
    "Programming Language :: Python :: 2 :: Only",
    "Topic :: Communications",
    "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
    "Topic :: Office/Business :: Groupware",
    "Topic :: Office/Business :: Scheduling",
]

author = "Apple Inc."

author_email = "calendarserver-dev@lists.macosforge.org"

license = "Apache License, Version 2.0"

platforms = ["all"]



#
# Entry points
#

entry_points = {
    "console_scripts": [],
}

script_entry_points = {
    "check_database_schema":
    ("calendarserver.tools.checkdatabaseschema", "main"),

    "command_gateway":
    ("calendarserver.tools.gateway", "main"),

    "config":
    ("calendarserver.tools.config", "main"),

    "dashboard":
    ("calendarserver.tools.dashboard", "main"),

    "dbinspect":
    ("calendarserver.tools.dbinspect", "main"),

    "diagnose":
    ("calendarserver.tools.diagnose", "main"),

    "dkimtool":
    ("calendarserver.tools.dkimtool", "main"),

    "export":
    ("calendarserver.tools.export", "main"),

    "icalendar_validate":
    ("calendarserver.tools.validcalendardata", "main"),

    "import":
    ("calendarserver.tools.importer", "main"),

    "manage_principals":
    ("calendarserver.tools.principals", "main"),

    "manage_push":
    ("calendarserver.tools.push", "main"),

    "manage_timezones":
    ("calendarserver.tools.managetimezones", "main"),

    "migrate_resources":
    ("calendarserver.tools.resources", "main"),

    "monitor_amp_notifications":
    ("calendarserver.tools.ampnotifications", "main"),

    "monitor_notifications":
    ("calendarserver.tools.notifications", "main"),

    "purge_attachments":
    ("calendarserver.tools.purge", "PurgeAttachmentsService.main"),

    "purge_events":
    ("calendarserver.tools.purge", "PurgeOldEventsService.main"),

    "purge_principals":
    ("calendarserver.tools.purge", "PurgePrincipalService.main"),

    "shell":
    ("calendarserver.tools.shell.terminal", "main"),

    "upgrade":
    ("calendarserver.tools.upgrade", "main"),

    "verify_data":
    ("calendarserver.tools.calverify", "main"),
}

for n, (m, f) in script_entry_points.iteritems():
    entry_points["console_scripts"].append(
        "calendarserver_{} = {}:{}".format(n, m, f)
    )



#
# Dependencies
#

setup_requirements = []

install_requirements = [
    # Core frameworks
    "zope.interface",
    "Twisted>=13.2.0",
    "twextpy",

    # Security frameworks
    "pyOpenSSL>=0.13.1",
    "service_identity",
    "pycrypto",
    "pyasn1",
    "kerberos",

    # Data store
    "xattr",
    "twextpy[DAL]",
    "sqlparse>=0.1.11",

    # Calendar
    "python-dateutil",
    "pytz",
    "pycalendar",

    # Process info
    "psutil",
    "setproctitle",
]

extras_requirements = {
    "LDAP": ["twextpy[LDAP]", "python-ldap"],
    "OpenDirectory": ["twextpy[OpenDirectory]", "pyobjc-framework-OpenDirectory"],
    "Oracle": ["twextpy[Oracle]", "cx_Oracle"],
    "Postgres": ["twextpy[Postgres]", "PyGreSQL"],
}



#
# Set up Extension modules that need to be built
#

extensions = []


#
# Run setup
#

def doSetup():
    # Write version file
    version_string = version()
    version_filename = joinpath(
        dirname(__file__), "calendarserver", "version.py"
    )
    version_file = file(version_filename, "w")

    try:
        version_file.write(
            'version = "{0}"\n\n'.format(version_string)
        )
    finally:
        version_file.close()

    dist = setup(
        name=name,
        version=version_string,
        description=description,
        long_description=long_description,
        url=url,
        classifiers=classifiers,
        author=author,
        author_email=author_email,
        license=license,
        platforms=platforms,
        packages=find_packages(),
        package_data={
            "twistedcaldav": [
                "*.html",
                "zoneinfo/*.ics",
                "zoneinfo/*/*.ics",
                "zoneinfo/*/*/*.ics",
                "images/*/*.jpg",
            ],
            "calendarserver.webadmin": [
                "*.html"
            ],
            "twistedcaldav.directory": [
                "*.html"
            ],
            "txdav.common.datastore": [
                "sql_schema/*.sql",
                "sql_schema/*/*.sql",
                "sql_schema/*/*/*.sql",
            ],
        },
        entry_points=entry_points,
        scripts=[
            "bin/caldavd",
        ],
        data_files=[
            ("caldavd", ["conf/caldavd.plist"]),
        ],
        ext_modules=extensions,
        py_modules=[],
        setup_requires=setup_requirements,
        install_requires=install_requirements,
        extras_require=extras_requirements,
    )

    if "install" in dist.commands:
        install_obj = dist.command_obj["install"]
        if install_obj.root is None:
            return
        install_scripts = normpath(install_obj.install_scripts)
        install_lib = normpath(install_obj.install_lib)
        root = normpath(install_obj.root)
        base = normpath(install_obj.install_base)

        if root:
            install_lib = install_lib[len(root):]

        for script in dist.scripts:
            scriptPath = joinpath(install_scripts, basename(script))

            print("Rewriting {0}".format(scriptPath))

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
                        script.append(
                            'PYTHONPATH="{add}:$PYTHONPATH"'
                            .format(add=install_lib)
                        )
                    elif line == "#PATH":
                        script.append(
                            'PATH="{add}:$PATH"'
                            .format(add=joinpath(base, "usr", "bin"))
                        )
                    else:
                        script.append(line)

                elif fileType == "python":
                    if line == "#PYTHONPATH":
                        script.append(
                            'PYTHONPATH="{path}"'
                            .format(path=install_lib)
                        )
                    elif line == "#PATH":
                        script.append(
                            'PATH="{path}"'
                            .format(path=joinpath(base, "usr", "bin"))
                        )
                    else:
                        script.append(line)

                else:
                    script.append(line)

            newScript = open(scriptPath, "w")
            newScript.write("\n".join(script))
            newScript.close()


#
# Main
#

if __name__ == "__main__":
    doSetup()
