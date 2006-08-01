#!/usr/bin/env python

##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
#
# This file contains Original Code and/or Modifications of Original Code
# as defined in and that are subject to the Apple Public Source License
# Version 2.0 (the 'License'). You may not use this file except in
# compliance with the License. Please obtain a copy of the License at
# http://www.opensource.apple.com/apsl/ and read it before using this
# file.
# 
# The Original Code and all software distributed under the License are
# distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
# EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
# INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
# Please see the License for the specific language governing rights and
# limitations under the License.
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

import sys
import os

#
# Compute the version number.
#

svnversion = os.popen("svnversion -n %r trunk" % (os.path.dirname(__file__),))
svn_revision = svnversion.read()
svnversion.close()

if "S" in svn_revision:
    # FIXME: Get release version from svn URL.
    print "Working copy (%s) is not trunk.  Unable to determine version number." % (svn_revision,)
    sys.exit(1)
elif svn_revision == "exported":
    # Weird Apple thing: Get the B&I version number from the path
    segments = __file__.split(os.path.sep)[:-1]
    segments.reverse()
    for segment in segments:
        try:
            version = segment[segment.rindex("-")+1:]
            break
        except ValueError:
            continue
    else:
        version = "unknown"
else:
    version = "dev." + svn_revision

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
# Run setup
#

from distutils.core import setup

setup(
    name             = "twistedcaldav",
    version          = version,
    description      = description,
    long_description = long_description,
    url              = None,
    classifiers      = classifiers,
    author           = "Apple Computer, Inc.",
    author_email     = None,
    license          = None,
    platforms        = [ "all" ],
    packages         = [ "twistedcaldav", "twistedcaldav.method", "twistedcaldav.query" ],
    scripts          = [ "bin/caldavd" ],
    data_files       = [("caldavd", ["conf/repository.xml", "conf/caldavd.plist"]),],
)
