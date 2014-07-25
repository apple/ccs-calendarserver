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
    print("  -s: server host (and optional port) [localhost:8100]")
    print("")

    if e:
        sys.exit(64)
    else:
        sys.exit(0)


BOX_WIDTH = 52


def main():
    try:
        (optargs, _ignore_args) = getopt(
            sys.argv[1:], "hs:t", [
                "help",
            ],
        )
    except GetoptError, e:
        usage(e)

    #
    # Get configuration
    #
    useCurses = True
    server = ("localhost", 8100)

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        elif opt in ("-t"):
            useCurses = False

        elif opt in ("-s"):
            server = arg.split(":")
            if len(server) == 1:
                server.append(8100)
            else:
                server[1] = int(server[1])
            server = tuple(server)

        else:
            raise NotImplementedError(opt)

    if useCurses:
        def _wrapped(stdscrn):
            curses.curs_set(0)
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_RED, curses.COLOR_WHITE)
            d = Dashboard(server, stdscrn, True)
            d.run()
        curses.wrapper(_wrapped)
    else:
        d = Dashboard(None, False)
        d.run()



def safeDivision(value, total, factor=1):
    return value * factor / total if total else 0



def defaultIfNone(x, default):
    return x if x is not None else default



class Dashboard(object):
    """
    Main dashboard controller. Use Python's L{sched} feature to schedule
    updates.
    """

    screen = None
    registered_windows = {}
    registered_order = []

    def __init__(self, server, screen, usesCurses):
        self.screen = screen
        self.usesCurses = usesCurses
        self.paused = False
        self.seconds = 0.1 if usesCurses else 1.0
        self.sched = sched.scheduler(time.time, time.sleep)
        self.client = DashboardClient(server, True)
        self.client_error = False


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


    def resetWindows(self):
        """
        Reset the current set of windows.
        """
        if self.windows:
            for window in self.windows:
                window.deactivate()
            old_windows = self.windows
            self.windows = []
            top = 0
            for old in old_windows:
                self.windows.append(old.__class__(self.usesCurses, self.client).makeWindow(top=top))
                self.windows[-1].activate()
                top += self.windows[-1].nlines + 1


    def updateDisplay(self, initialUpdate=False):
        """
        Periodic update of the current window and check for a key press.
        """
        self.client.update()
        client_error = len(self.client.currentData) == 0
        if client_error ^ self.client_error:
            self.client_error = client_error
            self.resetWindows()
        elif filter(lambda x: x.requiresReset(), self.windows):
            self.resetWindows()

        try:
            if not self.paused or initialUpdate:
                for window in filter(
                    lambda x: x.requiresUpdate() or initialUpdate,
                    self.windows
                ):
                    window.update()
        except Exception:
            # print(str(e))
            pass
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
        self.currentData = {}
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
            t = time.time()
            while not data.endswith("\n"):
                try:
                    d = self.socket.recv(1024)
                except socket.error as se:
                    if se.args[0] != errno.EWOULDBLOCK:
                        raise
                    if time.time() - t > 5:
                        raise socket.error
                    continue
                if d:
                    data += d
                else:
                    break
            data = json.loads(data)
        except socket.error:
            data = {}
            self.socket = None
        except ValueError:
            data = {}
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
        data = self.readSock([item])
        return data[item] if data else None


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
        self.rowCount = 0
        self.needsReset = False


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


    def requiresReset(self):
        """
        Indicates that the window needs a full reset, because e.g., the
        number of items it didplays has changed.
        """
        return self.needsReset


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
        return self.client.currentData.get(self.clientItem)


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



class JobsWindow(BaseWindow):
    """
    Display the status of the server's job queue.
    """

    help = "display server jobs"
    clientItem = "jobs"
    FORMAT_WIDTH = 98

    def makeWindow(self, top=0, left=0):
        nlines = defaultIfNone(self.readItem("jobcount"), 0)
        self.rowCount = nlines
        self._createWindow("Jobs", self.rowCount + 6, ncols=self.FORMAT_WIDTH, begin_y=top, begin_x=left)
        return self


    def update(self):
        records = defaultIfNone(self.clientData(), {})
        if len(records) != self.rowCount:
            self.needsReset = True
            return
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
        s1 = " {:<40}{:>8}{:>10}{:>8}{:>8}{:>10}{:>10} ".format(
            "Work Type", "Queued", "Assigned", "Late", "Failed", "Completed", "Av-Time",
        )
        s2 = " {:<40}{:>8}{:>10}{:>8}{:>8}{:>10}{:>10} ".format(
            "", "", "", "", "", "", "(ms)",
        )
        if self.usesCurses:
            self.window.addstr(y, x, s1, curses.A_REVERSE)
            self.window.addstr(y + 1, x, s2, curses.A_REVERSE)
        else:
            print(s1)
            print(s2)
        y += 2
        total_queued = 0
        total_assigned = 0
        total_late = 0
        total_failed = 0
        total_completed = 0
        total_time = 0.0
        for work_type, details in sorted(records.items(), key=lambda x: x[0]):
            total_queued += details["queued"]
            total_assigned += details["assigned"]
            total_late += details["late"]
            total_failed += details["failed"]
            total_completed += details["completed"]
            total_time += details["time"]
            changed = (
                work_type in self.lastResult and
                self.lastResult[work_type]["queued"] != details["queued"]
            )
            s = "{}{:<40}{:>8}{:>10}{:>8}{:>8}{:>10}{:>10.1f} ".format(
                ">" if details["queued"] else " ",
                work_type,
                details["queued"],
                details["assigned"],
                details["late"],
                details["failed"],
                details["completed"],
                safeDivision(details["time"], details["completed"], 1000.0)
            )
            try:
                if self.usesCurses:
                    self.window.addstr(
                        y, x, s,
                        curses.A_REVERSE if changed else (
                            curses.A_BOLD if details["queued"] else curses.A_NORMAL
                        )
                    )
                else:
                    print(s)
            except curses.error:
                pass
            y += 1

        s = " {:<40}{:>8}{:>10}{:>8}{:>8}{:>10}{:>10.1f} ".format(
            "Total:",
            total_queued,
            total_assigned,
            total_late,
            total_failed,
            total_completed,
            safeDivision(total_time, total_completed, 1000.0)
        )
        if self.usesCurses:
            self.window.hline(y, x, "-", self.FORMAT_WIDTH - 2)
            y += 1
            self.window.addstr(y, x, s)
        else:
            print(s)
        y += 1

        if self.usesCurses:
            self.window.refresh()

        self.lastResult = records



class AssignmentsWindow(BaseWindow):
    """
    Displays the status of the server's master process worker slave slots.
    """

    help = "display server child job assignments"
    clientItem = "job_assignments"
    FORMAT_WIDTH = 40

    def makeWindow(self, top=0, left=0):
        slots = defaultIfNone(self.readItem(self.clientItem), {"workers": ()})["workers"]
        self.rowCount = len(slots)
        self._createWindow(
            "Job Assignments", self.rowCount + 5, self.FORMAT_WIDTH,
            begin_y=top, begin_x=left
        )
        return self


    def update(self):
        data = defaultIfNone(self.clientData(), {"workers": {}, "level": 0})
        records = data["workers"]
        if len(records) != self.rowCount:
            self.needsReset = True
            return
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
        s = " {:>4}{:>12}{:>8}{:>12} ".format(
            "Slot", "assigned", "load", "completed"
        )
        if self.usesCurses:
            self.window.addstr(y, x, s, curses.A_REVERSE)
        else:
            print(s)
        y += 1
        total_assigned = 0
        total_completed = 0
        for ctr, details in enumerate(records):
            assigned, load, completed = details
            total_assigned += assigned
            total_completed += completed
            changed = (
                ctr in self.lastResult and
                self.lastResult[ctr] != assigned
            )
            s = " {:>4}{:>12}{:>8}{:>12} ".format(
                ctr,
                assigned,
                load,
                completed,
            )
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

        s = " {:<6}{:>10}{:>8}{:>12}".format(
            "Total:",
            total_assigned,
            "{}%".format(data["level"]),
            total_completed,
        )
        if self.usesCurses:
            self.window.hline(y, x, "-", self.FORMAT_WIDTH - 2)
            y += 1
            self.window.addstr(y, x, s)
        else:
            print(s)
        y += 1

        if self.usesCurses:
            self.window.refresh()

        self.lastResult = records



class HTTPSlotsWindow(BaseWindow):
    """
    Displays the status of the server's master process worker slave slots.
    """

    help = "display server child slots"
    clientItem = "slots"
    FORMAT_WIDTH = 72

    def makeWindow(self, top=0, left=0):
        slots = defaultIfNone(self.readItem(self.clientItem), {"slots": ()})["slots"]
        self.rowCount = len(slots)
        self._createWindow(
            "HTTP Slots", self.rowCount + 5, self.FORMAT_WIDTH,
            begin_y=top, begin_x=left
        )
        return self


    def update(self):
        data = defaultIfNone(self.clientData(), {"slots": {}, "overloaded": False})
        records = data["slots"]
        if len(records) != self.rowCount:
            self.needsReset = True
            return
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
            sum(
                [
                    record["unacknowledged"] + record["acknowledged"]
                    for record in records
                ]
            ),
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
        slots = defaultIfNone(self.readItem(self.clientItem), (1, 2, 3, 4,))
        self.rowCount = len(slots)
        self._createWindow("System", self.rowCount + 3, begin_y=top, begin_x=left)
        return self


    def update(self):
        records = defaultIfNone(self.clientData(), {
            "cpu use": 0.0,
            "memory percent": 0.0,
            "memory used": 0,
            "start time": time.time(),
        })
        if len(records) != self.rowCount:
            self.needsReset = True
            return
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



class RequestStatsWindow(BaseWindow):
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
        records = defaultIfNone(self.clientData(), {})
        self.iter += 1

        if self.usesCurses:
            self.window.erase()
            self.window.border()
            self.window.addstr(0, 2, self.title + " {} ({})".format(len(records), self.iter,))

        x = 1
        y = 1
        s1 = " {:<8}{:>8}{:>10}{:>10}{:>10}{:>10}{:>8}{:>8}{:>8} ".format(
            "Period", "Reqs", "Av-Reqs", "Av-Resp", "Av-NoWr", "Max-Resp", "Slot", "CPU ", "500's"
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
            stat = records.get(key, {
                "requests": 0,
                "t": 0.0,
                "t-resp-wr": 0.0,
                "T-MAX": 0.0,
                "slots": 0,
                "cpu": 0.0,
                "500": 0,
            })
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



class DirectoryStatsWindow(BaseWindow):
    """
    Displays the status of the server's directory service calls
    """

    help = "display directory service stats"
    clientItem = "directory"
    FORMAT_WIDTH = 89


    def makeWindow(self, top=0, left=0):
        nlines = len(defaultIfNone(self.readItem("directory"), {}))
        self.rowCount = nlines
        self._createWindow(
            "Directory Service", self.rowCount + 6, ncols=self.FORMAT_WIDTH,
            begin_y=top, begin_x=left
        )
        return self


    def update(self):
        records = defaultIfNone(self.clientData(), {})
        if len(records) != self.rowCount:
            self.needsReset = True
            return

        self.iter += 1

        if self.usesCurses:
            self.window.erase()
            self.window.border()
            self.window.addstr(0, 2, self.title + " {} ({})".format(len(records), self.iter,))

        x = 1
        y = 1
        s1 = " {:<40}{:>15}{:>15}{:>15} ".format(
            "Method", "Calls", "Total", "Average"
        )
        s2 = " {:<40}{:>15}{:>15}{:>15} ".format(
            "", "", "(sec)", "(ms)"
        )
        if self.usesCurses:
            self.window.addstr(y, x, s1, curses.A_REVERSE)
            self.window.addstr(y + 1, x, s2, curses.A_REVERSE)
        else:
            print(s1)
            print(s2)
        y += 2

        overallCount = 0
        overallTimeSpent = 0.0

        for methodName, (count, timeSpent) in sorted(records.items(), key=lambda x: x[0]):
            overallCount += count
            overallTimeSpent += timeSpent

            s = " {:<40}{:>15d}{:>15.1f}{:>15.3f} ".format(
                methodName,
                count,
                timeSpent,
                (1000.0 * timeSpent) / count,
            )
            try:
                if self.usesCurses:
                    self.window.addstr(y, x, s)
                else:
                    print(s)
            except curses.error:
                pass
            y += 1

        s = " {:<40}{:>15d}{:>15.1f}{:>15.5f} ".format(
            "Total:",
            overallCount,
            overallTimeSpent,
            safeDivision(overallTimeSpent, overallCount, 1000.0)
        )
        if self.usesCurses:
            self.window.hline(y, x, "-", self.FORMAT_WIDTH - 2)
            y += 1
            self.window.addstr(y, x, s)
        else:
            print(s)
        y += 1

        if self.usesCurses:
            self.window.refresh()



Dashboard.registerWindow(SystemWindow, "s")
Dashboard.registerWindow(RequestStatsWindow, "r")
Dashboard.registerWindow(JobsWindow, "j")
Dashboard.registerWindow(AssignmentsWindow, "w")
Dashboard.registerWindow(HTTPSlotsWindow, "c")
Dashboard.registerWindow(DirectoryStatsWindow, "d")
Dashboard.registerWindow(HelpWindow, "h")


if __name__ == "__main__":
    main()
