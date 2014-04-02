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

from itertools import chain
from os import listdir, environ as environment
from os.path import dirname, abspath, join as joinpath
import errno
import subprocess

from pip.req import parse_requirements
from setuptools import setup, find_packages as setuptools_find_packages


#
# Utilities
#
def find_packages():
    modules = []

    return modules + setuptools_find_packages()



def version():
    """
    Compute the version number.
    """

    base_version = "0.1"

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

    full_version = ""
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

description = "CalDAV/CardDAV protocol test suite"

long_description = file(joinpath(dirname(__file__), "README.txt")).read()

url = "http://trac.calendarserver.org/wiki/CalDAVTester"

classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 2.7",
    "Programming Language :: Python :: 2 :: Only",
    "Topic :: Software Development :: Testing",
]


#
# Dependencies
#

requirements_dir = joinpath(dirname(__file__), "requirements")


def read_requirements(reqs_filename):
    return [
        str(r.req) for r in
        parse_requirements(joinpath(requirements_dir, reqs_filename))
    ]


setup_requirements = []

install_requirements = read_requirements("py_base.txt")

extras_requirements = dict(
    (reqs_filename[4:-4], read_requirements(reqs_filename))
    for reqs_filename in listdir(requirements_dir)
    if reqs_filename.startswith("py_opt_") and reqs_filename.endswith(".txt")
)

# Requirements for development and testing
develop_requirements = read_requirements("py_develop.txt")

if environment.get("_DEVELOP", "false") == "true":
    install_requirements.extend(develop_requirements)
    install_requirements.extend(chain(*extras_requirements.values()))



#
# Set up Extension modules that need to be built
#

# from distutils.core import Extension

extensions = []



#
# Run setup
#

def doSetup():
    version_string = version()

    setup(
        name="CalDAVTester",
        version=version_string,
        description=description,
        long_description=long_description,
        url=url,
        classifiers=classifiers,
        author="Apple Inc.",
        author_email="calendarserver-dev@lists.macosforge.org",
        license="Apache License, Version 2.0",
        platforms=["all"],
        packages=find_packages(),
        package_data={},
        scripts=[],
        data_files=[],
        ext_modules=extensions,
        py_modules=[],
        setup_requires=setup_requirements,
        install_requires=install_requirements,
        extras_require=extras_requirements,
    )


#
# Main
#

if __name__ == "__main__":
    doSetup()
