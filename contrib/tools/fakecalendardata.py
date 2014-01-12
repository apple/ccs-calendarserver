#!/usr/bin/env python
##
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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

import datetime
import getopt
import os
import random
import sys
import uuid

outputFile = None
fileCount = 0
lastWeek = None

calendar_template = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
PRODID:-//Apple Inc.//iCal 4.0.3//EN
BEGIN:VTIMEZONE
TZID:America/Los_Angeles
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
END:VTIMEZONE
%(VEVENTS)s\
END:VCALENDAR
"""

vevent_template = """\
BEGIN:VEVENT
UID:%(UID)s
DTSTART;TZID=America/Los_Angeles:%(START)s
DURATION:P1H
%(RRULE)s\
CREATED:20100729T193912Z
DTSTAMP:20100729T195557Z
%(ORGANIZER)s\
%(ATTENDEES)s\
SEQUENCE:0
SUMMARY:%(SUMMARY)s
TRANSP:OPAQUE
END:VEVENT
"""

attendee_template = """\
ATTENDEE;CN=User %(SEQUENCE)02d;CUTYPE=INDIVIDUAL;EMAIL=user%(SEQUENCE)02d@example.com;PARTSTAT=NE
 EDS-ACTION;ROLE=REQ-PARTICIPANT;RSVP=TRUE:urn:uuid:user%(SEQUENCE)02d
"""

organizer_template = """\
ORGANIZER;CN=User %(SEQUENCE)02d;EMAIL=user%(SEQUENCE)02d@example.com:urn:uuid:user%(SEQUENCE)02d
ATTENDEE;CN=User %(SEQUENCE)02d;EMAIL=user%(SEQUENCE)02d@example.com;PARTSTAT=ACCEPTE
 D:urn:uuid:user%(SEQUENCE)02d
"""

summary_template = "Event %d"
rrules_template = (
    "RRULE:FREQ=DAILY;COUNT=5\n",
    "RRULE:FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR\n",
    "RRULE:FREQ=YEARLY\n",
)

def makeVEVENT(recurring, atendees, date, hour, count):

    subs = {
        "UID": str(uuid.uuid4()),
        "START" : "",
        "RRULE" : "",
        "ORGANIZER" : "",
        "ATTENDEES" : "",
        "SUMMARY"   : summary_template % (count,)
    }

    if recurring:
        subs["RRULE"] = random.choice(rrules_template)

    if attendees:
        subs["ORGANIZER"] = organizer_template % {"SEQUENCE": 1}
        for ctr in range(2, random.randint(2, 10)):
            subs["ATTENDEES"] += attendee_template % {"SEQUENCE": ctr}

    subs["START"] = "%04d%02d%02dT%02d0000" % (date.year, date.month, date.day, hour)

    return vevent_template % subs



def argPath(path):
    fpath = os.path.expanduser(path)
    if not fpath.startswith("/"):
        fpath = os.path.join(pwd, fpath)
    return fpath



def usage(error_msg=None):
    if error_msg:
        print(error_msg)

    print("""Usage: fakecalendardata [options]
Options:
    -h          Print this help and exit
    -a          Percentage of events that should include attendees
    -c          Total number of events to generate
    -d          Directory to store separate .ics files into
    -r          Percentage of recurring events to create
    -p          Numbers of years in the past to start at
    -f          Number of years into the future to end at

Arguments: None

Description:
This utility will generate fake iCalendar data either into a single .ics
file or into multiple .ics files.
""")

    if error_msg:
        raise ValueError(error_msg)
    else:
        sys.exit(0)

if __name__ == "__main__":

    outputDir = None
    totalCount = 10
    percentRecurring = 20
    percentWithAttendees = 10
    yearsPast = 2
    yearsFuture = 1

    options, args = getopt.getopt(sys.argv[1:], "a:c:f:hd:p:r:", [])

    for option, value in options:
        if option == "-h":
            usage()
        elif option == "-a":
            percentWithAttendees = int(value)
        elif option == "-c":
            totalCount = int(value)
        elif option == "-d":
            outputDir = argPath(value)
        elif option == "-f":
            yearsFuture = int(value)
        elif option == "-p":
            yearsPast = int(value)
        elif option == "-r":
            percentRecurring = int(value)
        else:
            usage("Unrecognized option: %s" % (option,))

    if outputDir and not os.path.isdir(outputDir):
        usage("Must specify a valid output directory.")

    # Process arguments
    if len(args) != 0:
        usage("No arguments allowed")

    pwd = os.getcwd()

    totalRecurring = (totalCount * percentRecurring) / 100
    totalRecurringWithAttendees = (totalRecurring * percentWithAttendees) / 100
    totalRecurringWithoutAttendees = totalRecurring - totalRecurringWithAttendees

    totalNonRecurring = totalCount - totalRecurring
    totalNonRecurringWithAttendees = (totalNonRecurring * percentWithAttendees) / 100
    totalNonRecurringWithoutAttendees = totalNonRecurring - totalNonRecurringWithAttendees

    eventTypes = []
    eventTypes.extend([(True, True) for _ignore in range(totalRecurringWithAttendees)])
    eventTypes.extend([(True, False) for _ignore in range(totalRecurringWithoutAttendees)])
    eventTypes.extend([(False, True) for _ignore in range(totalNonRecurringWithAttendees)])
    eventTypes.extend([(False, False) for _ignore in range(totalNonRecurringWithoutAttendees)])
    random.shuffle(eventTypes)

    totalYears = yearsPast + yearsFuture
    totalDays = totalYears * 365

    startDate = datetime.date.today() - datetime.timedelta(days=yearsPast * 365)

    for i in range(len(eventTypes)):
        eventTypes[i] += (
            startDate + datetime.timedelta(days=random.randint(0, totalDays)),
            random.randint(8, 18),
        )

    vevents = []
    for count, (recurring, attendees, date, hour) in enumerate(eventTypes):
        #print(recurring, attendees, date, hour)
        vevents.append(makeVEVENT(recurring, attendees, date, hour, count + 1))

    print(calendar_template % {"VEVENTS" : "".join(vevents)})
