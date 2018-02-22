#!/usr/bin/env python

##
# Copyright (c) 2006-2017 Apple Inc. All rights reserved.
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
import sys

base_version = "9.3"
base_project = "ccs-calendarserver"


#
# Utilities
#
def find_packages():
    modules = [
        "twisted.plugins",
    ]

    def is_package(path):
        return (
            os.path.isdir(path) and
            os.path.isfile(os.path.join(path, "__init__.py"))
        )

    for pkg in filter(is_package, os.listdir(".")):
        modules.extend([pkg, ] + [
            "{}.{}".format(pkg, subpkg)
            for subpkg in setuptools_find_packages(pkg)
        ])
    return modules


def git_info(wc_path):
    """
    Look up info on a GIT working copy.
    """
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.STDOUT,
        )
    except OSError as e:
        if e.errno == errno.ENOENT:
            return None
        raise
    except subprocess.CalledProcessError:
        return None

    branch = branch.strip()

    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "--verify", "HEAD"],
            stderr=subprocess.STDOUT,
        )
    except OSError as e:
        if e.errno == errno.ENOENT:
            return None
        raise
    except subprocess.CalledProcessError:
        return None

    revision = revision.strip()

    try:
        tags = subprocess.check_output(
            ["git", "describe", "--exact-match", "HEAD"],
            stderr=subprocess.STDOUT,
        )
    except OSError as e:
        if e.errno == errno.ENOENT:
            return None
        raise
    except subprocess.CalledProcessError:
        tag = None
    else:
        tags = tags.strip().split()
        tag = tags[0]

    return dict(
        project=base_project,
        branch=branch,
        revision=revision,
        tag=tag,
    )


def version():
    """
    Compute the version number.
    """
    source_root = dirname(abspath(__file__))

    info = git_info(source_root)

    if info is None:
        # We don't have GIT info...
        return "{}a1+unknown".format(base_version)

    assert info["project"] == base_project, (
        "GIT project {!r} != {!r}"
        .format(info["project"], base_project)
    )

    if info["tag"]:
        project_version = info["tag"]
        try:
            project, version = project_version.split("-")
        except ValueError:
            project = project_version
            version = "Unknown"

        # Only process tags with our project name prefix
        if project == project_name:
            assert version == base_version, (
                "Tagged version {!r} != {!r}".format(version, base_version)
            )
            # This is a correctly tagged release of this project.
            return base_version

    if info["branch"].startswith("release/"):
        project_version = info["branch"][len("release/"):]
        project, version, dev = project_version.split("-")
        assert project == project_name, (
            "Branched project {!r} != {!r}".format(project, project_name)
        )
        assert version == base_version, (
            "Branched version {!r} != {!r}".format(version, base_version)
        )
        assert dev == "dev", (
            "Branch name doesn't end in -dev: {!r}".format(info["branch"])
        )
        # This is a release branch of this project.
        # Designate this as beta2, dev version based on git revision.
        return "{}b2.dev0+{}".format(base_version, info["revision"])

    if info["branch"] == "master":
        # This is master.
        # Designate this as beta1, dev version based on git revision.
        return "{}b1.dev0+{}".format(base_version, info["revision"])

    # This is some unknown branch or tag...
    return "{}a1.dev0+{}.{}".format(
        base_version,
        info["revision"],
        info["branch"].replace("/", ".").replace("-", ".").lower(),
    )


#
# Options
#

project_name = "CalendarServer"

description = "Calendar and Contacts Server"

long_description = file(joinpath(dirname(__file__), "README.rst")).read()

url = "https://github.com/apple/ccs-calendarserver"

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

    "dashcollect":
    ("calendarserver.tools.dashcollect", "main"),

    "dashview":
    ("calendarserver.tools.dashview", "main"),

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

    "migrate_wiki":
    ("calendarserver.tools.wiki", "main"),

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

    "trash":
    ("calendarserver.tools.trash", "main"),

    "upgrade":
    ("calendarserver.tools.upgrade", "main"),

    "verify_data":
    ("calendarserver.tools.calverify", "main"),

    "pod_migration":
    ("calendarserver.tools.pod_migration", "main"),
}

for tool, (module, function) in script_entry_points.iteritems():
    entry_points["console_scripts"].append(
        "calendarserver_{} = {}:{}".format(tool, module, function)
    )


#
# Dependencies
#

setup_requirements = []

install_requirements = [
    # Core frameworks
    "zope.interface",
    "Twisted==16.6.0",
    "twextpy",

    # Security frameworks
    "pycrypto",           # for Twisted
    "kerberos",

    # Data store
    "xattr",
    "twextpy[DAL]",
    "sqlparse",

    # Calendar
    "python-dateutil",
    "pytz",
    "pycalendar",

    # Process info
    "psutil",
    "setproctitle",
]

if sys.platform == "darwin" and os.getenv("USE_OPENSSL") is None:
    install_requirements.extend([
        "OSXFrameworks",
        "pySecureTransport",
    ])
else:
    install_requirements.extend([
        "pyOpenSSL>=0.15.1",    # also for Twisted
        "service_identity",   # for Twisted
    ])

extras_requirements = {
    "ldap": ["twextpy[ldap]"],
    "opendirectory": ["twextpy[opendirectory]"],
    "postgres": ["twextpy[postgres]", "pg8000"],
}

if "ORACLE_HOME" in os.environ:
    # We need a specific version here because we have to patch it
    extras_requirements["oracle"] = ["twextpy[oracle]", "cx_Oracle==5.2"]


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
        name=project_name,
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
                "*.txt",
                "zoneinfo/*.ics",
                "zoneinfo/*.txt",
                "zoneinfo/*.xml",
                "zoneinfo/*/*.ics",
                "zoneinfo/*/*/*.ics",
                "images/*/*.jpg",
            ],
            "calendarserver.webadmin": [
                "*.html",
                "*.xhtml"
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

            with open(scriptPath, "w") as newScript:
                newScript.write("\n".join(script))


#
# Main
#

if __name__ == "__main__":
    doSetup()
