#!/usr/bin/env python

##
# Copyright (c) 2006-2012 Apple Inc. All rights reserved.
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
from os.path import dirname, basename

def version():
    #
    # Compute the version number.
    #

    base_version = "4.2.1"

    branches = (
        "tags/release/CalendarServer-" + base_version,
        "branches/release/CalendarServer-" + base_version + "-dev",
        "trunk",
    )

    source_root = dirname(dirname(__file__))

    for branch in branches:
        cmd = "svnversion -n %r %s" % (source_root, branch)
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
            if "RC_XBS" in os.environ and os.environ["RC_XBS"] == "YES":
                project_name = basename(os.environ["SRCROOT"])

                prefix = "CalendarServer-"

                if project_name.startswith(prefix):
                    rc_version = project_name[len(prefix):]
                    if "." in rc_version:
                        comment = "Calendar Server v%s" % (rc_version,)
                    else:
                        comment = "Calendar Server [dev] r%s" % (rc_version,)
                    break

            comment = "unknown"
        else:
            comment = "r%s" % (svn_revision,)

        break
    else:
        base_version += "-unknown"
        comment = "r%s" % (svn_revision,)

    return (base_version, comment)

if __name__ == "__main__":
    base_version, comment = version()
    print "%s (%s)" % (base_version, comment)
