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

"""
A curses (or plain text) based dashboard for viewing various aspects of the
server as exposed by the L{DashboardProtocol} stats socket.
"""

from getopt import getopt, GetoptError

import curses
import json
import os
import sched
import sys
import time
import socket
import errno



def usage(e=None):
    name = os.path.basename(sys.argv[0])
    print("usage: %s [options]" % (name,))
    print("")
    print("  TODO: describe usage")
    print("")
    print("options:")
    print("  -h --help: print this help and exit")
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
            sys.argv[1:], "ht", [
                "help",
            ],
        )
    except GetoptError, e:
        usage(e)

    #
    # Get configuration
    #
    useCurses = True

    for opt, _ignore_arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        elif opt in ("-t"):
            useCurses = False

        else:
            raise NotImplementedError(opt)

    if useCurses:
        def _wrapped(stdscrn):
            curses.curs_set(0)
            curses.use_default_colors()
            d = Dashboard(stdscrn, True)
            d.run()
        curses.wrapper(_wrapped)
    else:
        d = Dashboard(None, False)
        d.run()



class Dashboard(object):
    """
    Main dashboard controller. Use Python's L{sched} feature to schedule
    updates.
    """

    screen = None
    registered_windows = {}

    def __init__(self, screen, usesCurses):
        self.screen = screen
        self.usesCurses = usesCurses
        self.paused = False
        self.seconds = 0.1
        self.sched = sched.scheduler(time.time, time.sleep)


    @classmethod
    def registerWindow(cls, wtype, keypress):
        """
        Register a window type along with a key press action. This allows the
        controller to select the appropriate window when its key is pressed,
        and also provides help information to the L{HelpWindow} for each
        available window type.
        """
        cls.registered_windows[keypress] = wtype


    def run(self):
        """
        Create the initial window and run the L{scheduler}.
        """
        self.windows = []
        self.displayWindow(None)
        self.sched.enter(0, 0, self.updateDisplay, ())
        self.sched.run()


    def displayWindow(self, wtype):
        """
        Display a new window type, clearing out the old one first.
        """
        if self.windows:
            for window in self.windows:
                window.clear()
            self.windows = []

        if wtype is not None:
            self.windows.append(wtype(self.usesCurses).makeWindow())
            self.windows[-1].update()
        else:
            top = 0
            for wtype in filter(
                lambda x: x.all, self.registered_windows.values()
            ):
                self.windows.append(wtype(self.usesCurses).makeWindow(top=top))
                self.windows[-1].update()
                top += self.windows[-1].nlines


    def updateDisplay(self):
        """
        Periodic update of the current window and check for a key press.
        """
        try:
            if not self.paused:
                for window in filter(
                    lambda x: x.requiresUpdate(), self.windows
                ):
                    window.update()
        except Exception as e:
            print(str(e))
        if not self.usesCurses:
            print("-------------")

        # Check keystrokes
        if self.usesCurses:
            try:
                c = self.windows[-1].window.getkey()
            except:
                c = -1
            if c == "q":
                sys.exit(0)
            elif c == " ":
                self.paused = not self.paused
            elif c == "t":
                self.seconds = 1.0 if self.seconds == 0.1 else 0.1
            elif c == "a":
                self.displayWindow(None)
            elif c in self.registered_windows:
                self.displayWindow(self.registered_windows[c])

        self.sched.enter(self.seconds, 0, self.updateDisplay, ())



class BaseWindow(object):
    """
    Common behavior for window types.
    """

    help = "Not Implemented"
    all = True

    def __init__(self, usesCurses):
        self.usesCurses = usesCurses


    def makeWindow(self, top=0, left=0):
        raise NotImplementedError()


    def _createWindow(
        self, title, nlines, ncols=BOX_WIDTH, begin_y=0, begin_x=0
    ):
        """
        Initialize a curses window based on the sizes required.
        """
        if self.usesCurses:
            self.window = curses.newwin(nlines, ncols, begin_y, begin_x)
            self.window.nodelay(1)
        else:
            self.window = None
        self.title = title
        self.nlines = nlines
        self.ncols = ncols
        self.iter = 0
        self.lastResult = {}


    def requiresUpdate(self):
        """
        Indicates whether a window type has dynamic data that should be
        refreshed on each update, or whether it is static data (e.g.,
        L{HelpWindow}) that only needs to be drawn once.
        """
        return True


    def clear(self):
        """
        Clear any drawing done by the current window type.
        """
        if self.usesCurses:
            self.window.erase()
            self.window.refresh()


    def update(self):
        """
        Periodic window update - redraw the window.
        """
        raise NotImplementedError()



class BaseSocketWindow(BaseWindow):
    """
    Common behavior for a window that reads from the server's stats socket.
    """

    def __init__(self, usesCurses):
        super(BaseSocketWindow, self).__init__(usesCurses)
        self.socket = None
        self.sockname = ("localhost", 8100)
        self.useTCP = True


    def readSock(self, item):
        """
        Open a socket, send the specified request, and retrieve the response.
        Keep the socket open.
        """
        try:
            if self.socket is None:
                if self.useTCP:
                    self.socket = socket.socket(socket.AF_INET)
                else:
                    self.socket = socket.socket(
                        socket.AF_UNIX, socket.SOCK_STREAM
                    )
                self.socket.connect(self.sockname)
                self.socket.setblocking(0)
            self.socket.sendall(json.dumps([item]) + "\r\n")
            data = ""
            while not data.endswith("\n"):
                try:
                    d = self.socket.recv(1024)
                except socket.error as se:
                    if se.args[0] != errno.EWOULDBLOCK:
                        raise
                    continue
                if d:
                    data += d
                else:
                    break
            data = json.loads(data)[item]
        except socket.error as e:
            data = {
                "Failed": "Unable to read statistics from server: {} {}"
                .format(self.sockname, e)
            }
            self.socket = None
        return data



class HelpWindow(BaseWindow):
    """
    Display help for the dashboard.
    """

    help = "display dashboard help"
    all = False

    def __init__(self, usesCurses):
        super(HelpWindow, self).__init__(usesCurses)
        self.help = (
            "",
            "a - all windows",
            "  - (space) pause dashboard polling",
            "t - toggle update between 0.1 and 1.0 seconds",
            "",
            "q - exit the dashboard",
        )


    def makeWindow(self, top=0, left=0):
        self._createWindow(
            "Help",
            len(self.help) + len(Dashboard.registered_windows) + 2,
            begin_y=top, begin_x=left
        )
        return self


    def requiresUpdate(self):
        return False


    def update(self):

        if self.usesCurses:
            self.window.erase()
            self.window.border()
            self.window.addstr(0, 2, "Help for Dashboard")

        x = 1
        y = 1

        items = []
        for keypress, wtype in sorted(
            Dashboard.registered_windows.items(), key=lambda x: x[0]
        ):
            items.append("{} - {}".format(keypress, wtype.help))
        items.extend(self.help)
        for item in items:
            if self.usesCurses:
                self.window.addstr(y, x, item)
            else:
                print(item)
            y += 1

        if self.usesCurses:
            self.window.refresh()



class WorkWindow(BaseSocketWindow):
    """
    Display the status of the server's job queue.
    """

    help = "display server jobs"

    def makeWindow(self, top=0, left=0):
        nlines = self.readSock("jobcount")
        self._createWindow("Jobs", nlines + 5, begin_y=top, begin_x=left)
        return self


    def update(self):
        records = self.readSock("jobs")
        self.iter += 1

        if self.usesCurses:
            self.window.erase()
            self.window.border()
            self.window.addstr(
                0, 2,
                self.title + " {} ({})".format(len(records), self.iter)
            )

        x = 1
        y = 1
        s = " {:<40}{:>8} ".format("Work Type", "Count")
        if self.usesCurses:
            self.window.addstr(y, x, s, curses.A_REVERSE)
        else:
            print(s)
        y += 1
        for work_type, count in sorted(records.items(), key=lambda x: x[0]):
            changed = (
                work_type in self.lastResult and
                self.lastResult[work_type] != count
            )
            s = "{}{:<40}{:>8} ".format(
                ">" if count else " ", work_type, count
            )
            try:
                if self.usesCurses:
                    self.window.addstr(
                        y, x, s,
                        curses.A_REVERSE if changed else (
                            curses.A_BOLD if count else curses.A_NORMAL
                        )
                    )
                else:
                    print(s)
            except curses.error:
                pass
            y += 1

        s = " {:<40}{:>8} ".format("Total:", sum(records.values()))
        if self.usesCurses:
            self.window.hline(y, x, "-", BOX_WIDTH - 2)
            y += 1
            self.window.addstr(y, x, s)
        else:
            print(s)
        y += 1

        if self.usesCurses:
            self.window.refresh()

        self.lastResult = records



class SlotsWindow(BaseSocketWindow):
    """
    Displays the status of the server's master process worker slave slots.
    """

    help = "display server child slots"
    FORMAT_WIDTH = 72

    def makeWindow(self, top=0, left=0):
        slots = self.readSock("slots")["slots"]
        self._createWindow(
            "Slots", len(slots) + 5, self.FORMAT_WIDTH,
            begin_y=top, begin_x=left
        )
        return self


    def update(self):
        data = self.readSock("slots")
        records = data["slots"]
        self.iter += 1

        if self.usesCurses:
            self.window.erase()
            self.window.border()
            self.window.addstr(
                0, 2,
                self.title + " {} ({})".format(len(records), self.iter)
            )

        x = 1
        y = 1
        s = " {:>4}{:>8}{:>8}{:>8}{:>8}{:>8}{:>8}{:>8}{:>8} ".format(
            "Slot", "unack", "ack", "uncls", "total",
            "start", "strting", "stopped", "abd"
        )
        if self.usesCurses:
            self.window.addstr(y, x, s, curses.A_REVERSE)
        else:
            print(s)
        y += 1
        for record in sorted(records, key=lambda x: x["slot"]):
            changed = (
                record["slot"] in self.lastResult and
                self.lastResult[record["slot"]] != record
            )
            s = " {:>4}{:>8}{:>8}{:>8}{:>8}{:>8}{:>8}{:>8}{:>8} ".format(
                record["slot"],
                record["unacknowledged"],
                record["acknowledged"],
                record["unclosed"],
                record["total"],
                record["started"],
                record["starting"],
                record["stopped"],
                record["abandoned"],
            )
            try:
                count = record["unacknowledged"] + record["acknowledged"]
                if self.usesCurses:
                    self.window.addstr(
                        y, x, s,
                        curses.A_REVERSE if changed else (
                            curses.A_BOLD if count else curses.A_NORMAL
                        )
                    )
                else:
                    print(s)
            except curses.error:
                pass
            y += 1

        s = " {:<12}{:>8}{:>16}".format(
            "Total:",
            sum([
                record["unacknowledged"] + record["acknowledged"]
                for record in records
            ]),
            sum([record["total"] for record in records]),
        )
        if self.usesCurses:
            self.window.hline(y, x, "-", self.FORMAT_WIDTH - 2)
            y += 1
            self.window.addstr(y, x, s)
            x += len(s) + 4
            s = "{:>10}".format("OVERLOADED" if data["overloaded"] else "")
            self.window.addstr(
                y, x, s,
                curses.A_REVERSE if data["overloaded"] else curses.A_NORMAL
            )
        else:
            if data["overloaded"]:
                s += "    OVERLOADED"
            print(s)
        y += 1

        if self.usesCurses:
            self.window.refresh()

        self.lastResult = records



class SystemWindow(BaseSocketWindow):
    """
    Displays the system information provided by the server.
    """

    help = "display system details"

    def makeWindow(self, top=0, left=0):
        slots = self.readSock("stats")["system"]
        self._createWindow("System", len(slots) + 3, begin_y=top, begin_x=left)
        return self


    def update(self):
        records = self.readSock("stats")["system"]
        self.iter += 1

        if self.usesCurses:
            self.window.erase()
            self.window.border()
            self.window.addstr(
                0, 2,
                self.title + " {} ({})".format(len(records), self.iter)
            )

        x = 1
        y = 1
        s = " {:<30}{:>18} ".format("Item", "Value")
        if self.usesCurses:
            self.window.addstr(y, x, s, curses.A_REVERSE)
        else:
            print(s)
        y += 1

        records["cpu use"] = "{:.2f}".format(records["cpu use"])
        records["memory percent"] = "{:.1f}".format(records["memory percent"])
        records["memory used"] = "{:.2f} GB".format(
            records["memory used"] / (1000.0 * 1000.0 * 1000.0)
        )
        records["uptime"] = int(time.time() - records["start time"])
        hours, mins = divmod(records["uptime"] / 60, 60)
        records["uptime"] = "{}:{:02d} hours".format(hours, mins)
        del records["start time"]

        for item, value in sorted(records.items(), key=lambda x: x[0]):
            changed = (
                item in self.lastResult and self.lastResult[item] != value
            )
            s = " {:<30}{:>18} ".format(item, value)
            try:
                if self.usesCurses:
                    self.window.addstr(
                        y, x, s,
                        curses.A_REVERSE if changed else curses.A_NORMAL
                    )
                else:
                    print(s)
            except curses.error:
                pass
            y += 1

        if self.usesCurses:
            self.window.refresh()

        self.lastResult = records


Dashboard.registerWindow(HelpWindow, "h")
Dashboard.registerWindow(WorkWindow, "j")
Dashboard.registerWindow(SlotsWindow, "c")
Dashboard.registerWindow(SystemWindow, "s")


if __name__ == "__main__":
    main()
