#!/usr/bin/env python

##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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

import os

for ctr in xrange(1, 20):
    path = "calendars/user/user%02d" % (ctr,)
    if not os.path.exists("%s/calendar.1000/" % (path,)):
        print "Expanding to %s" % (path,)
        cmd = "cd %s; tar zxf ../../../calendar.1000.tgz" % (path,)
        os.system(cmd)
