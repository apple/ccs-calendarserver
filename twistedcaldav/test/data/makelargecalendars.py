#!/usr/bin/env python

##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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
# DRI: Cyrus Daboo, cdaboo@apple.com
##

import getopt
import os
import sys

if __name__ == "__main__":

    user_max = 99
    calendars = ("calendar.10", "calendar.100", "calendar.1000",)

    options, args = getopt.getopt(sys.argv[1:], "n:")

    for option, value in options:
        if option == "-n":
            user_max = int(value)
        else:
            print "Unrecognized option: %s" % (option,)
            raise ValueError
    
    for ctr in xrange(1, user_max + 1): 
        path = "calendars/users/user%02d" % (ctr,)
    
        try: os.makedirs(path)
        except OSError: pass
    
        try: os.makedirs(path)
        except OSError: pass
    
        for calendar in calendars:
            if not os.path.isdir(os.path.join(path, calendar)):
                print "Expanding %s to %s" % (calendar, path)
                cmd = "tar -C %r -zx -f %r" % (path, calendar + ".tgz")
                os.system(cmd)
