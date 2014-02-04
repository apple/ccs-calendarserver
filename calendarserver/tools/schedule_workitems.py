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

from twisted.internet.defer import inlineCallbacks, succeed
from calendarserver.tools.cmdline import utilityMain, WorkerService
from calendarserver.push.notifier import PushNotificationWork
from txdav.caldav.datastore.scheduling.work import ScheduleOrganizerWork, \
    ScheduleReplyWork, ScheduleRefreshWork

useCurses = True

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



class WorkItemMonitorService(WorkerService, object):

    def __init__(self, store):
        super(WorkItemMonitorService, self).__init__(store)
        from twisted.internet import reactor
        self.reactor = reactor


    def doWork(self):
        self.screen = curses.initscr() if useCurses else None
        self.windows = []
        self.updateScreenGeometry()
        self.reactor.callLater(0, self.updateDisplay)
        return succeed(None)


    def postStartService(self):
        """
        Don't quit right away
        """
        pass


    def updateScreenGeometry(self):
        for win in self.windows:
            del win
        winY, winX = self.screen.getmaxyx() if useCurses else (100, 100)
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
            ("Organizer Requests", "100%", "25%", 1, 1, ScheduleOrganizerWork, "%s: %d", ("icalendarUid", "attendeeCount")),
            ("Attendee Replies", "100%", "25%", 1, 2, ScheduleReplyWork, "%s", ("icalendarUid",)),
            ("Attendee Refresh", "100%", "25%", 1, 3, ScheduleRefreshWork, "%s: %d", ("icalendarUid", "attendeeCount")),
#            ("Auto Reply", "100%", "25%", 1, 4, ScheduleAutoReplyWork, "%s", ("icalendarUid")),
            ("Push Notifications", "100%", "25%", 1, 4, PushNotificationWork, "%s: %d", ("pushID", "priority")),
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
            try:
                yield window.update()
            except Exception as e:
                print(str(e))
        if not useCurses:
            print("-------------")

        self.reactor.callLater(0.1, self.updateDisplay)



class WorkWindow(object):
    def __init__(self, nlines, ncols, begin_y, begin_x,
        store, title, workItemClass, fmt, attrs):
        self.window = curses.newwin(nlines, ncols, begin_y, begin_x) if useCurses else None
        self.ncols = ncols
        self.store = store
        self.title = title
        self.workItemClass = workItemClass
        self.fmt = fmt
        self.attrs = attrs
        self.iter = 0


    @inlineCallbacks
    def update(self):
        txn = self.store.newTransaction()
        records = (yield self.workItemClass.all(txn))
        self.iter += 1

        if useCurses:
            self.window.erase()
            self.window.border()
            self.window.addstr(0, 2, self.title + " %d (%d)" % (len(records), self.iter,))

        x = 1
        y = 1
        for record in records:
            txt = ""
            seconds = record.notBefore - datetime.datetime.utcnow()
            try:
                if useCurses:
                    self.window.addstr(y, x, "%d seconds" % int(seconds.total_seconds()))
                else:
                    txt = "%s:" % (self.title,)
            except curses.error:
                continue
            y += 1
            if self.attrs:
                try:
                    s = self.fmt % tuple([getattr(record, str(a)) for a in self.attrs])
                except Exception, e:
                    s = "Error: %s" % (str(e),)
                try:
                    if useCurses:
                        self.window.addnstr(y, x, s, self.ncols - 2)
                    else:
                        txt += " " + s
                except curses.error:
                    pass
                y += 1

            if not useCurses:
                print(txt)

        if useCurses:
            self.window.refresh()

        yield txn.commit()


if __name__ == "__main__":
    main()
