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

from calendarserver.tools.cmdline import utilityMain, WorkerService

from getopt import getopt, GetoptError

from twext.enterprise.jobqueue import JobItem

from twisted.internet.defer import inlineCallbacks, succeed

import curses
import os
import sys

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
    print("  -f --config <path>: specify caldavd.plist configuration path")
    print("  -t: text output, not curses")
    print("")

    if e:
        sys.exit(64)
    else:
        sys.exit(0)


BOX_WIDTH = 52

def main():

    try:
        (optargs, _ignore_args) = getopt(
            sys.argv[1:], "hef:t", [
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
    global useCurses
    configFileName = None
    debug = False

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        if opt in ("-e", "--error"):
            debug = True

        elif opt in ("-f", "--config"):
            configFileName = arg

        elif opt in ("-t"):
            useCurses = False

        else:
            raise NotImplementedError(opt)

    if useCurses:
        def _wrapped(stdscrn):
            JobItemMonitorService.screen = stdscrn
            curses.curs_set(0)
            curses.use_default_colors()
            utilityMain(configFileName, JobItemMonitorService, verbose=debug)
        curses.wrapper(_wrapped)
    else:
        utilityMain(configFileName, JobItemMonitorService, verbose=debug)



class JobItemMonitorService(WorkerService, object):

    screen = None

    def __init__(self, store):
        super(JobItemMonitorService, self).__init__(store)
        from twisted.internet import reactor
        self.reactor = reactor
        self.paused = False
        self.seconds = 0.1


    @inlineCallbacks
    def doWork(self):
        self.window = None
        yield self.displayJobs()
        self.reactor.callLater(0, self.updateDisplay)


    def postStartService(self):
        """
        Don't quit right away
        """
        pass


    @inlineCallbacks
    def displayHelp(self):
        if self.window is not None:
            self.window.clear()
        self.window = HelpWindow(10, BOX_WIDTH, 0, 0, self.store, "Help")
        yield self.window.update()


    @inlineCallbacks
    def displayJobs(self):
        if self.window is not None:
            self.window.clear()
        self.window = WorkWindow(JobItem.numberOfWorkTypes() + 5, BOX_WIDTH, 0, 0, self.store, "Jobs")
        yield self.window.update()


    @inlineCallbacks
    def updateDisplay(self):
        try:
            if not self.paused and self.window.requiresUpdate():
                yield self.window.update()
        except Exception as e:
            print(str(e))
        if not useCurses:
            print("-------------")

        # Check keystrokes
        if useCurses:
            try:
                c = self.window.window.getkey()
            except:
                c = -1
            if c == "q":
                self.reactor.stop()
            elif c == " ":
                self.paused = not self.paused
            elif c == "t":
                self.seconds = 1.0 if self.seconds == 0.1 else 1.0
            elif c == "h":
                yield self.displayHelp()
            elif c == "j":
                yield self.displayJobs()

        self.reactor.callLater(self.seconds, self.updateDisplay)



class BaseWindow(object):
    def __init__(self, nlines, ncols, begin_y, begin_x, store, title):
        self.window = curses.newwin(nlines, ncols, begin_y, begin_x) if useCurses else None
        if useCurses:
            self.window.nodelay(1)
        self.ncols = ncols
        self.store = store
        self.title = title
        self.iter = 0
        self.lastResult = {}


    def requiresUpdate(self):
        return True


    def clear(self):

        if useCurses:
            self.window.erase()
            self.window.refresh()


    def update(self):
        return succeed(True)



class HelpWindow(BaseWindow):

    def requiresUpdate(self):
        return False


    def update(self):

        if useCurses:
            self.window.erase()
            self.window.border()
            self.window.addstr(0, 2, "Help for Dashboard")

        x = 1
        y = 1

        for title in (
            "j - display server jobs",
            "h - display dashboard help",
            "",
            "  - (space) pause dashboard polling",
            "t - toggle update between 0.1 and 1.0 seconds",
            "",
            "q - exit the dashboard",
        ):
            if useCurses:
                self.window.addstr(y, x, title)
            else:
                print(title)
            y += 1

        if useCurses:
            self.window.refresh()

        return succeed(True)



class WorkWindow(BaseWindow):

    @inlineCallbacks
    def update(self):
        txn = self.store.newTransaction()
        records = (yield JobItem.histogram(txn))
        self.iter += 1

        if useCurses:
            self.window.erase()
            self.window.border()
            self.window.addstr(0, 2, self.title + " {} ({})".format(len(records), self.iter,))

        x = 1
        y = 1
        s = " {:<40}{:>8} ".format("Work Type", "Count")
        if useCurses:
            self.window.addstr(y, x, s, curses.A_REVERSE)
        else:
            print(s)
        y += 1
        for work_type, count in sorted(records.items(), key=lambda x: x[0]):
            changed = work_type in self.lastResult and self.lastResult[work_type] != count
            s = "{}{:<40}{:>8} ".format(">" if count else " ", work_type, count)
            try:
                if useCurses:
                    self.window.addstr(y, x, s, curses.A_REVERSE if changed else (curses.A_BOLD if count else curses.A_NORMAL))
                else:
                    print(s)
            except curses.error:
                pass
            y += 1

        s = " {:<40}{:>8} ".format("Total:", sum(records.values()))
        if useCurses:
            self.window.hline(y, x, "-", BOX_WIDTH - 2)
            y += 1
            self.window.addstr(y, x, s)
        else:
            print(s)
        y += 1

        if useCurses:
            self.window.refresh()

        self.lastResult = records
        yield txn.commit()


if __name__ == "__main__":
    main()
