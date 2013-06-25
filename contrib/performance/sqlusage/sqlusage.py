##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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

from StringIO import StringIO
from caldavclientlibrary.client.clientsession import CalDAVSession
from caldavclientlibrary.protocol.url import URL
from caldavclientlibrary.protocol.webdav.definitions import davxml
from calendarserver.tools import tables
from contrib.performance.sqlusage.requests.invite import InviteTest
from contrib.performance.sqlusage.requests.multiget import MultigetTest
from contrib.performance.sqlusage.requests.propfind import PropfindTest
from contrib.performance.sqlusage.requests.put import PutTest
from contrib.performance.sqlusage.requests.query import QueryTest
from contrib.performance.sqlusage.requests.sync import SyncTest
from pycalendar.datetime import PyCalendarDateTime
from twext.web2.dav.util import joinURL
import getopt
import itertools
import sys

"""
This tool is designed to analyze how SQL is being used for various HTTP requests.
It will execute a series of HTTP requests against a test server configuration and
count the total number of SQL statements per request, the total number of rows
returned per request and the total SQL execution time per request. Each series
will be repeated against a varying calendar size so the variation in SQL use
with calendar size can be plotted.
"""

EVENT_COUNTS = (0, 1, 5, 10, 50, 100, 500, 1000, 5000)

ICAL = """BEGIN:VCALENDAR
CALSCALE:GREGORIAN
PRODID:-//Example Inc.//Example Calendar//EN
VERSION:2.0
BEGIN:VTIMEZONE
LAST-MODIFIED:20040110T032845Z
TZID:US/Eastern
BEGIN:DAYLIGHT
DTSTART:20000404T020000
RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=4
TZNAME:EDT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
END:DAYLIGHT
BEGIN:STANDARD
DTSTART:20001026T020000
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10
TZNAME:EST
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
DTSTAMP:20051222T205953Z
CREATED:20060101T150000Z
DTSTART;TZID=US/Eastern:%d0101T100000
DURATION:PT1H
SUMMARY:event 1
UID:%d-ics
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

class SQLUsageSession(CalDAVSession):

    def __init__(self, server, port=None, ssl=False, user="", pswd="", principal=None, root=None, logging=False):

        super(SQLUsageSession, self).__init__(server, port, ssl, user, pswd, principal, root, logging)
        self.homeHref = "/calendars/users/%s/" % (self.user,)
        self.calendarHref = "/calendars/users/%s/calendar/" % (self.user,)
        self.inboxHref = "/calendars/users/%s/inbox/" % (self.user,)



class SQLUsage(object):

    def __init__(self, server, port, users, pswds, logFilePath):
        self.server = server
        self.port = port
        self.users = users
        self.pswds = pswds
        self.logFilePath = logFilePath
        self.requestLabels = []
        self.results = {}
        self.currentCount = 0


    def runLoop(self, counts):

        # Make the sessions
        sessions = [
            SQLUsageSession(self.server, self.port, user=user, pswd=pswd, root="/")
            for user, pswd in itertools.izip(self.users, self.pswds)
        ]

        # Set of requests to execute
        requests = [
            MultigetTest("multiget-1", sessions, self.logFilePath, 1),
            MultigetTest("multiget-50", sessions, self.logFilePath, 50),
            PropfindTest("propfind-cal", sessions, self.logFilePath, 1),
            SyncTest("sync-full", sessions, self.logFilePath, True, 0),
            SyncTest("sync-1", sessions, self.logFilePath, False, 1),
            QueryTest("query-1", sessions, self.logFilePath, 1),
            QueryTest("query-10", sessions, self.logFilePath, 10),
            PutTest("put", sessions, self.logFilePath),
            InviteTest("invite", sessions, self.logFilePath),
        ]
        self.requestLabels = [request.label for request in requests]

        # Warm-up server by doing calendar home and calendar propfinds
        props = (davxml.resourcetype,)
        for session in sessions:
            session.getPropertiesOnHierarchy(URL(path=session.homeHref), props)
            session.getPropertiesOnHierarchy(URL(path=session.calendarHref), props)

        # Now loop over sets of events
        for count in counts:
            print("Testing count = %d" % (count,))
            self.ensureEvents(sessions[0], sessions[0].calendarHref, count)
            result = {}
            for request in requests:
                print("  Test = %s" % (request.label,))
                result[request.label] = request.execute(count)
            self.results[count] = result


    def report(self):

        self._printReport("SQL Statement Count", "count", "%d")
        self._printReport("SQL Rows Returned", "rows", "%d")
        self._printReport("SQL Time", "timing", "%.1f")


    def _printReport(self, title, attr, colFormat):
        table = tables.Table()

        print(title)
        headers = ["Events"] + self.requestLabels
        table.addHeader(headers)
        formats = [tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY)] + \
            [tables.Table.ColumnFormat(colFormat, tables.Table.ColumnFormat.RIGHT_JUSTIFY)] * len(self.requestLabels)
        table.setDefaultColumnFormats(formats)
        for k in sorted(self.results.keys()):
            row = [k] + [getattr(self.results[k][item], attr) for item in self.requestLabels]
            table.addRow(row)
        os = StringIO()
        table.printTable(os=os)
        print(os.getvalue())
        print("")


    def ensureEvents(self, session, calendarhref, n):
        """
        Make sure the required number of events are present in the calendar.

        @param n: number of events
        @type n: C{int}
        """
        now = PyCalendarDateTime.getNowUTC()
        for i in range(n - self.currentCount):
            index = self.currentCount + i + 1
            href = joinURL(calendarhref, "%d.ics" % (index,))
            session.writeData(URL(path=href), ICAL % (now.getYear() + 1, index,), "text/calendar")

        self.currentCount = n



def usage(error_msg=None):
    if error_msg:
        print(error_msg)

    print("""Usage: sqlusage.py [options] [FILE]
Options:
    -h             Print this help and exit
    --server       Server hostname
    --port         Server port
    --user         User name
    --pswd         Password
    --counts       Comma-separated list of event counts to test

Arguments:
    FILE           File name for sqlstats.log to analyze.

Description:
This utility will analyze the output of s pg_stat_statement table.
""")

    if error_msg:
        raise ValueError(error_msg)
    else:
        sys.exit(0)

if __name__ == '__main__':

    server = "localhost"
    port = 8008
    users = ("user01", "user02",)
    pswds = ("user01", "user02",)
    file = "sqlstats.logs"
    counts = EVENT_COUNTS

    options, args = getopt.getopt(sys.argv[1:], "h", ["server=", "port=", "user=", "pswd=", "counts=", ])

    for option, value in options:
        if option == "-h":
            usage()
        elif option == "--server":
            server = value
        elif option == "--port":
            port = int(value)
        elif option == "--user":
            users = value.split(",")
        elif option == "--pswd":
            pswds = value.split(",")
        elif option == "--counts":
            counts = [int(i) for i in value.split(",")]
        else:
            usage("Unrecognized option: %s" % (option,))

    # Process arguments
    if len(args) == 1:
        file = args[0]
    elif len(args) != 0:
        usage("Must zero or one file arguments")

    sql = SQLUsage(server, port, users, pswds, file)
    sql.runLoop(counts)
    sql.report()
