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

from getopt import getopt, GetoptError
import os
import sys
import curses
import datetime

from twisted.internet.defer import inlineCallbacks
from calendarserver.tools.cmdline import utilityMain
from twisted.application.service import Service
from calendarserver.push.notifier import PushNotificationWork
from twistedcaldav.directory.directory import GroupCacherPollingWork
from txdav.caldav.datastore.scheduling.imip.inbound import IMIPPollingWork, IMIPReplyWork

def usage(e=None):

    name = os.path.basename(sys.argv[0])
    print("usage: %s [options]" % (name,))
    print("")
    print("  TODO: describe usage")
    print("")
    print("options:")
    print("  -h --help: print this help and exit")
    print("  -e --error: send stderr to stdout")
    print("  -f --config <path>: Specify caldavd.plist configuration path")
    print("")

    if e:
        sys.exit(64)
    else:
        sys.exit(0)



def main():

    try:
        (optargs, _ignore_args) = getopt(
            sys.argv[1:], "hef:", [
                "help",
                "error",
                "config=",
            ],
        )
    except GetoptError, e:
        usage(e)

    #
    # Get configuration
    #
    configFileName = None
    debug = False

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        if opt in ("-e", "--error"):
            debug = True

        elif opt in ("-f", "--config"):
            configFileName = arg

        else:
            raise NotImplementedError(opt)

    utilityMain(configFileName, WorkItemMonitorService, verbose=debug)



class WorkItemMonitorService(Service):

    def __init__(self, store):
        self.store = store
        from twisted.internet import reactor
        self.reactor = reactor


    def startService(self):
        self.screen = curses.initscr()
        self.windows = []
        self.updateScreenGeometry()
        self.reactor.callLater(0, self.updateDisplay)


    def updateScreenGeometry(self):
        for win in self.windows:
            del win
        winY, winX = self.screen.getmaxyx()
        seencolumns = [1]
        seenrows = [1]
        heightSoFar = 0
        begin_x = 0
        begin_y = 0
        # Specify height and width of each window as one of:
        #    absolute value (int), e.g.: 42
        #    percentage of window height / width (string), e.g.: "42%"
        # Specify row and column for each window as though it is a cell in an invisible html table
        # Itemize windows in ascending order by row, col
        for title, height, width, row, col, workItemClass, fmt, attrs in (
            ("Group Membership Indexing", "10%", "50%", 1, 1, GroupCacherPollingWork, "", ()),
            ("IMIP Reply Polling", "10%", "50%", 1, 2, IMIPPollingWork, "", ()),
            ("IMIP Reply Processing", "20%", "100%", 2, 1, IMIPReplyWork, "%s %s", ("organizer", "attendee")),
            ("Push Notifications", "69%", "100%", 3, 1, PushNotificationWork, "%s", ("pushID",)),
        ):
            if (isinstance(height, basestring)):
                height = max(int(winY * (float(height.strip("%")) / 100.0)), 3)
            if (isinstance(width, basestring)):
                width = max(int(winX * (float(width.strip("%")) / 100.0)), 10)
            if col not in seencolumns:
                heightSoFar = max(height, heightSoFar)
                seencolumns.append(col)
            if row not in seenrows:
                begin_y = heightSoFar
                heightSoFar += height
                begin_x = 0
                seenrows.append(row)
                seencolumns = [col]
            window = WorkWindow(height, width, begin_y, begin_x,
                self.store, title, workItemClass, fmt, attrs)
            self.windows.append(window)
            begin_x += width


    @inlineCallbacks
    def updateDisplay(self):
        for window in self.windows:
            yield window.update()

        self.reactor.callLater(1, self.updateDisplay)



class WorkWindow(object):
    def __init__(self, nlines, ncols, begin_y, begin_x,
        store, title, workItemClass, fmt, attrs):
        self.window = curses.newwin(nlines, ncols, begin_y, begin_x)
        self.ncols = ncols
        self.store = store
        self.title = title
        self.workItemClass = workItemClass
        self.fmt = fmt
        self.attrs = attrs


    @inlineCallbacks
    def update(self):
        self.window.erase()
        self.window.border()
        self.window.addstr(0, 2, self.title)
        txn = self.store.newTransaction()
        records = (yield self.workItemClass.all(txn))

        x = 1
        y = 1
        for record in records:
            seconds = record.notBefore - datetime.datetime.utcnow()
            try:
                self.window.addstr(y, x, "%d seconds" % int(seconds.total_seconds()))
            except curses.error:
                continue
            y += 1
            if self.attrs:
                try:
                    s = self.fmt % tuple([getattr(record, str(a)) for a in self.attrs])
                except Exception, e:
                    s = "Error: %s" % (str(e),)
                try:
                    self.window.addnstr(y, x, s, self.ncols - 2)
                except curses.error:
                    pass
                y += 1
        self.window.refresh()

if __name__ == "__main__":
    main()
