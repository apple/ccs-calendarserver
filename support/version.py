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

import os
from os.path import dirname
import subprocess

def version():
    #
    # Compute the version number.
    #

    base_version = "5.2.1"

    branches = tuple(
        branch.format(version=base_version)
        for branch in (
            "tags/release/CalendarServer-{version}",
            "branches/release/CalendarServer-{version}-dev",
            "trunk",
        )
    )

    source_root = dirname(dirname(__file__))

    for branch in branches:
        svn_revision = subprocess.check_output(["svnversion", "-n", source_root, branch])

        if "S" in svn_revision:
            continue

        if branch == "trunk":
            base_version += "-trunk"
        elif branch.endswith("-dev"):
            base_version += "-dev"

        if svn_revision in ("exported", "Unversioned directory"):
            if os.environ.get("RC_XBS", None) == "YES":
                xbs_version = os.environ.get("RC_ProjectSourceVersion", "?")
                comment = "Apple Calendar Server {version}".format(version=xbs_version)
            else:
                comment = "unknown"
        else:
            comment = "r{revision}".format(revision=svn_revision)

        break
    else:
        base_version += "-unknown"
        comment = "r{revision}".format(revision=svn_revision)

    return (base_version, comment)

if __name__ == "__main__":
    base_version, comment = version()
    print("{version} ({comment})".format(version=base_version, comment=comment))
