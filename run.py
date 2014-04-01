#!/usr/bin/env python
#
##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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
#
# Runs the CalDAVTester test suite ensuring that required packages are available.
#

import getopt
import os
import subprocess
import sys

cwd = os.getcwd()
top = cwd[:cwd.rfind("/")]
add_paths = []
svn = "/usr/bin/svn"
uri_base = "http://svn.calendarserver.org/repository/calendarserver"

packages = [
    ("pycalendar", "pycalendar/src", uri_base + "/PyCalendar/trunk", "HEAD"),
]

def usage():
    print """Usage: run.py [options]
Options:
    -h       Print this help and exit
    -s       Do setup only - do not run any tests
    -r       Run tests only - do not do setup
    -p       Print PYTHONPATH
"""



def setup():
    for package in packages:
        ppath = "%s/%s" % (top, package[0],)
        if not os.path.exists(ppath):
            print "%s package is not present." % (package[0],)
            os.system("%s checkout -r %s %s@%s %s" % (svn, package[3], package[2], package[3], ppath,))
        else:
            print "%s package is present." % (package[0],)
            fd = os.popen("%s info ../%s --xml" % (svn, package[0],))
            line = fd.read()
            wc_url = line[line.find("<url>") + 5:line.find("</url>")]
            if wc_url != package[2]:
                print "Current working copy (%s) is from the wrong URI: %s != %s, switching..." % (ppath, wc_url, package[2],)
                os.system("%s switch -r %s %s %s" % (svn, package[3], package[2], ppath,))
            else:
                rev = line[line.find("revision=\"") + 10:]
                rev = rev[:rev.find("\"")]
                if rev != package[3]:
                    print "Updating %s..." % (package[0],)
                    os.system("%s update -r %s %s" % (svn, package[3], ppath,))

        add_paths.append("%s/%s" % (top, package[1],))



def pythonpath():
    for package in packages:
        add_paths.append("%s/%s" % (top, package[1],))
    pypaths = sys.path
    pypaths.extend(add_paths)
    return ":".join(pypaths)



def runit():
    pythonpath = ":".join(add_paths)
    return subprocess.Popen(["./testcaldav.py", "--all"], env={"PYTHONPATH": pythonpath}).wait()



if __name__ == "__main__":

    try:
        do_setup = True
        do_run = True

        options, args = getopt.getopt(sys.argv[1:], "hprs")

        for option, value in options:
            if option == "-h":
                usage()
                sys.exit(0)
            elif option == "-p":
                print pythonpath()
                sys.exit(0)
            elif option == "-r":
                do_setup = False
            elif option == "-s":
                do_run = False
            else:
                print "Unrecognized option: %s" % (option,)
                usage()
                raise ValueError

        # Process arguments
        if len(args) != 0:
            print "No arguments allowed."
            usage()
            raise ValueError

        if (do_setup):
            setup()
        else:
            pythonpath()
        if (do_run):
            sys.exit(runit())
        else:
            sys.exit(0)
    except SystemExit, e:
        pass
    except Exception, e:
        sys.exit(str(e))
