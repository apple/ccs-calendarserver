#!/usr/bin/env python
##
# Copyright (c) 2009-2013 Apple Inc. All rights reserved.
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

"""
Tool to monitor network connection status and track queue sizes and
long-lived connections.
"""

import commands
import sys
import time

stateNames = (
    ("SYN_SENT",),
    ("SYN_RCVD",),
    ("ESTABLISHED",),
    ("CLOSE_WAIT",),
    ("LAST_ACK",),
    ("FIN_WAIT_1", "FIN_WAIT1"),
    ("FIN_WAIT_2", "FIN_WAIT2"),
    ("CLOSING",),
    ("TIME_WAIT",),
)

if __name__ == '__main__':
    
    pendingq = {}
    while True:
        timestamp = time.time()
        output = commands.getoutput("netstat -n")
    
        states = [(0, 0, 0)] * len(stateNames)

        newqs = {}
        for line in output.split("\n"):
            
            if not line.startswith("tcp4 ") and not line.startswith("tcp "):
                continue
            splits = line.split()
            if not splits[3].endswith("8443") and not splits[3].endswith("8008"):
                continue
            for ctr, items in enumerate(stateNames):
                
                for item in items:
                    if item in line:
                        
                        total, recvq, sendq = states[ctr]
                        total += 1
                        if splits[1] != "0":
                            recvq += 1
                        if splits[2] != "0":
                            sendq += 1
                        if item == "ESTABLISHED":
                            newqs[splits[4]] = (splits[1], splits[2],)
                        states[ctr] = (total, recvq, sendq,)
                        break
        
        oldqs = set(pendingq.keys())
        for key in oldqs.difference(newqs.keys()):
            del pendingq[key]
        oldqs = pendingq.keys()
        for key in newqs.keys():
            recv, sendq = newqs[key]
            if key in pendingq:
                pendingq[key] = (pendingq[key][0], recv, sendq,)
            else:
                pendingq[key] = (timestamp, recv, sendq,)

        print "------------------------"
        print ""
        print time.asctime()
        print "State        Total    RecvQ    SendQ"
        for ctr, items in enumerate(stateNames):
            print "%11s  %5d    %5d    %5d" % (items[0], states[ctr][0], states[ctr][1], states[ctr][2])
    
        print ""
        print "Source IP              Established (secs)    RecvQ    SendQ"
        for key, value in sorted(pendingq.iteritems(), key=lambda x:x[1]):
            startedat, recv, sendq = value
            deltatime = timestamp - startedat
            if deltatime > 0:
                print "%-20s   %3d                   %5s    %5s" % (key, deltatime, recv, sendq,)

        sys.stdout.flush()
        time.sleep(5)
