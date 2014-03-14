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
            curses.init_pair(1, curses.COLOR_RED, curses.COLOR_WHITE)
            d = Dashboard(stdscrn, True)
            d.run()
        curses.wrapper(_wrapped)
    else:
        d = Dashboard(None, False)
        d.run()



def safeDivision(value, total, factor=1):
    return value * factor / total if total else 0



class Dashboard(object):
    """
    Main dashboard controller. Use Python's L{sched} feature to schedule
    updates.
    """

    screen = None
    registered_windows = {}
    registered_order = []

    def __init__(self, screen, usesCurses):
        self.screen = screen
        self.usesCurses = usesCurses
        self.paused = False
        self.seconds = 0.1 if usesCurses else 1.0
        self.sched = sched.scheduler(time.time, time.sleep)
        self.client = DashboardClient(("localhost", 8100), True)


    @classmethod
    def registerWindow(cls, wtype, keypress):
        """
        Register a window type along with a key press action. This allows the
        controller to select the appropriate window when its key is pressed,
        and also provides help information to the L{HelpWindow} for each
        available window type.
        """
        cls.registered_windows[keypress] = wtype
        cls.registered_order.append(keypress)


    def run(self):
        """
        Create the initial window and run the L{scheduler}.
        """
        self.windows = []
        self.displayWindow(None)
        self.sched.enter(self.seconds, 0, self.updateDisplay, ())
        self.sched.run()


    def displayWindow(self, wtype):
        """
        Display a new window type, clearing out the old one first.
        """
        if self.windows:
            for window in self.windows:
                window.deactivate()
            self.windows = []

        if wtype is not None:
            self.windows.append(wtype(self.usesCurses, self.client).makeWindow())
            self.windows[-1].activate()
        else:
            top = 0
            ordered_windows = [self.registered_windows[i] for i in self.registered_order]
            for wtype in filter(lambda x: x.all, ordered_windows):
                self.windows.append(wtype(self.usesCurses, self.client).makeWindow(top=top))
                self.windows[-1].activate()
                top += self.windows[-1].nlines + 1

        self.updateDisplay(True)


    def updateDisplay(self, initialUpdate=False):
        """
        Periodic update of the current window and check for a key press.
        """
        self.client.update()
        try:
            if not self.paused or initialUpdate:
                for window in filter(
                    lambda x: x.requiresUpdate() or initialUpdate,
                    self.windows
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

        if not initialUpdate:
            self.sched.enter(self.seconds, 0, self.updateDisplay, ())



class DashboardClient(object):
    """
    Client that connects to a server and fetches information.
    """

    def __init__(self, sockname, useTCP):
        self.socket = None
        self.sockname = sockname
        self.useTCP = useTCP
        self.currentData = None
        self.items = []


    def readSock(self, items):
        """
        Open a socket, send the specified request, and retrieve the response. Keep the socket open.
        """
        try:
            if self.socket is None:
                self.socket = socket.socket(socket.AF_INET if self.useTCP else socket.AF_UNIX, socket.SOCK_STREAM)
                self.socket.connect(self.sockname)
                self.socket.setblocking(0)
            self.socket.sendall(json.dumps(items) + "\r\n")
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
            data = json.loads(data)
        except socket.error as e:
            data = {"Failed": "Unable to read statistics from server: %s %s" % (self.sockname, e)}
            self.socket = None
        return data


    def update(self):
        """
        Update the current data from the server.
        """
        self.currentData = self.readSock(self.items)


    def getOneItem(self, item):
        """
        Update the current data from the server.
        """
        return self.readSock([item])[item]


    def addItem(self, item):
        """
        Add a server data item to monitor.
        """
        self.items.append(item)


    def removeItem(self, item):
        """
        No need to monitor this item.
        """
        self.items.remove(item)



class BaseWindow(object):
    """
    Common behavior for window types.
    """

    help = "Not Implemented"
    all = True
    clientItem = None

    def __init__(self, usesCurses, client):
        self.usesCurses = usesCurses
        self.client = client


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


    def activate(self):
        """
        About to start displaying.
        """
        if self.clientItem:
            self.client.addItem(self.clientItem)


    def deactivate(self):
        """
        Clear any drawing done by the current window type.
        """
        if self.clientItem:
            self.client.removeItem(self.clientItem)
        if self.usesCurses:
            self.window.erase()
            self.window.refresh()


    def update(self):
        """
        Periodic window update - redraw the window.
        """
        raise NotImplementedError()


    def clientData(self):
        return self.client.currentData[self.clientItem]


    def readItem(self, item):
        return self.client.getOneItem(item)



class HelpWindow(BaseWindow):
    """
    Display help for the dashboard.
    """

    help = "display dashboard help"
    all = False
    helpItems = (
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
            len(self.helpItems) + len(Dashboard.registered_windows) + 2,
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
        items.extend(self.helpItems)
        for item in items:
            if self.usesCurses:
                self.window.addstr(y, x, item)
            else:
                print(item)
            y += 1

        if self.usesCurses:
            self.window.refresh()



class WorkWindow(BaseWindow):
    """
    Display the status of the server's job queue.
    """

    help = "display server jobs"
    clientItem = "jobs"

    def makeWindow(self, top=0, left=0):
        nlines = self.readItem("jobcount")
        self._createWindow("Jobs", nlines + 5, begin_y=top, begin_x=left)
        return self


    def update(self):
        records = self.clientData()
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



class SlotsWindow(BaseWindow):
    """
    Displays the status of the server's master process worker slave slots.
    """

    help = "display server child slots"
    clientItem = "slots"
    FORMAT_WIDTH = 72

    def makeWindow(self, top=0, left=0):
        slots = self.readItem(self.clientItem)["slots"]
        self._createWindow(
            "Slots", len(slots) + 5, self.FORMAT_WIDTH,
            begin_y=top, begin_x=left
        )
        return self


    def update(self):
        data = self.clientData()
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
                curses.color_pair(1) + curses.A_BOLD if data["overloaded"] else curses.A_NORMAL
            )
        else:
            if data["overloaded"]:
                s += "    OVERLOADED"
            print(s)
        y += 1

        if self.usesCurses:
            self.window.refresh()

        self.lastResult = records



class SystemWindow(BaseWindow):
    """
    Displays the system information provided by the server.
    """

    help = "display system details"
    clientItem = "stats_system"

    def makeWindow(self, top=0, left=0):
        slots = self.readItem(self.clientItem)
        self._createWindow("System", len(slots) + 3, begin_y=top, begin_x=left)
        return self


    def update(self):
        records = self.clientData()
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



class StatsWindow(BaseWindow):
    """
    Displays the status of the server's master process worker slave slots.
    """

    help = "display server request stats"
    clientItem = "stats"
    FORMAT_WIDTH = 84

    def makeWindow(self, top=0, left=0):
        self._createWindow("Request Statistics", 8, self.FORMAT_WIDTH, begin_y=top, begin_x=left)
        return self


    def update(self):
        records = self.clientData()
        self.iter += 1

        if self.usesCurses:
            self.window.erase()
            self.window.border()
            self.window.addstr(0, 2, self.title + " {} ({})".format(len(records), self.iter,))

        x = 1
        y = 1
        s1 = " {:<8}{:>8}{:>10}{:>10}{:>10}{:>10}{:>8}{:>8}{:>8} ".format(
            "Period", "Reqs", "Av-Reqs", "Av-NoWr", "Av-Resp", "Max-Resp", "Slot", "CPU ", "500's"
        )
        s2 = " {:<8}{:>8}{:>10}{:>10}{:>10}{:>10}{:>8}{:>8}{:>8} ".format(
            "", "", "per sec", "(ms)", "(ms)", "(ms)", "Avg.", "Avg.", ""
        )
        if self.usesCurses:
            self.window.addstr(y, x, s1, curses.A_REVERSE)
            self.window.addstr(y + 1, x, s2, curses.A_REVERSE)
        else:
            print(s1)
            print(s2)
        y += 2
        for key, seconds in (("current", 60,), ("1m", 60,), ("5m", 5 * 60,), ("1h", 60 * 60,),):
            stat = records[key]
            s = " {:<8}{:>8}{:>10.1f}{:>10.1f}{:>10.1f}{:>10.1f}{:>8.2f}{:>7.1f}%{:>8} ".format(
                key,
                stat["requests"],
                safeDivision(float(stat["requests"]), seconds),
                safeDivision(stat["t"], stat["requests"]),
                safeDivision(stat["t"] - stat["t-resp-wr"], stat["requests"]),
                stat["T-MAX"],
                safeDivision(float(stat["slots"]), stat["requests"]),
                safeDivision(stat["cpu"], stat["requests"]),
                stat["500"],
            )
            try:
                if self.usesCurses:
                    self.window.addstr(y, x, s)
                else:
                    print(s)
            except curses.error:
                pass
            y += 1

        if self.usesCurses:
            self.window.refresh()

        self.lastResult = records


Dashboard.registerWindow(SystemWindow, "s")
Dashboard.registerWindow(StatsWindow, "r")
Dashboard.registerWindow(WorkWindow, "j")
Dashboard.registerWindow(SlotsWindow, "c")
Dashboard.registerWindow(HelpWindow, "h")


if __name__ == "__main__":
    main()
