#!/ngs/app/ical/code/bin/python

##
# Copyright (c) 2012-2014 Apple Inc. All rights reserved.
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

# Sends SIGTERM to any calendar server child process whose VSIZE exceeds 2GB
# Only for use in a specific environment

import os
import signal

CUTOFFBYTES = 2 * 1024 * 1024 * 1024
PROCDIR = "/proc"
PYTHON = "/ngs/app/ical/code/bin/python"
CMDARG = "LogID"

serverProcessCount = 0
numKilled = 0

for pidString in sorted(os.listdir(PROCDIR)):

    try:
        pidNumber = int(pidString)
    except ValueError:
        # Not a process number
        continue

    pidDir = os.path.join(PROCDIR, pidString)
    statsFile = os.path.join(pidDir, "stat")
    statLine = open(statsFile).read()
    stats = statLine.split()
    vsize = int(stats[22])
    cmdFile = os.path.join(pidDir, "cmdline")
    if os.path.exists(cmdFile):
        cmdLine = open(cmdFile).read().split('\x00')
        if cmdLine[0].startswith(PYTHON):
            for arg in cmdLine[1:]:
                if arg.startswith(CMDARG):
                    break
            else:
                continue
            serverProcessCount += 1
            if vsize > CUTOFFBYTES:
                print("Killing process %d with VSIZE %d" % (pidNumber, vsize))
                os.kill(pidNumber, signal.SIGTERM)
                numKilled += 1

print("Examined %d server processes" % (serverProcessCount,))
print("Killed %d processes" % (numKilled,))
