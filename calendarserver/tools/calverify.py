#!/usr/bin/env python
# -*- test-case-name: calendarserver.tools.test.test_calverify -*-
##
# Copyright (c) 2011-2012 Apple Inc. All rights reserved.
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
This tool scans the calendar store to analyze organizer/attendee event
states to verify that the organizer's view of attendee state matches up
with the attendees' views. It can optionally apply a fix to bring the two
views back into line.

In theory the implicit scheduling model should eliminate the possibility
of mismatches, however, because we store separate resources for organizer
and attendee events, there is a possibility of mismatch. This is greatly
lessened via the new transaction model of database changes, but it is
possible there are edge cases or actual implicit processing errors we have
missed. This tool will allow us to track mismatches to help determine these
errors and get them fixed.

Even in the long term if we move to a "single instance" store where the
organizer event resource is the only one we store (with attendee views
derived from that), in a situation where we have server-to-server scheduling
it is possible for mismatches to creep in. In that case having a way to analyze
multiple DBs for inconsistency would be good too. 

"""

from calendarserver.tools import tables
from calendarserver.tools.cmdline import utilityMain
from calendarserver.tools.util import getDirectory
from pycalendar import definitions
from pycalendar.calendar import PyCalendar
from pycalendar.datetime import PyCalendarDateTime
from pycalendar.exceptions import PyCalendarError
from pycalendar.period import PyCalendarPeriod
from pycalendar.timezone import PyCalendarTimezone
from twext.enterprise.dal.syntax import Select, Parameter, Count
from twisted.application.service import Service
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.python import log
from twisted.python.text import wordWrap
from twisted.python.usage import Options
from twistedcaldav import caldavxml
from twistedcaldav.dateops import pyCalendarTodatetime
from twistedcaldav.ical import Component, ignoredComponents,\
    InvalidICalendarDataError, Property
from twistedcaldav.scheduling.itip import iTipGenerator
from twistedcaldav.stdconfig import DEFAULT_CONFIG_FILE
from twistedcaldav.util import normalizationLookup
from txdav.base.propertystore.base import PropertyName
from txdav.common.datastore.sql_tables import schema, _BIND_MODE_OWN
from txdav.common.icommondatastore import InternalDataStoreError
import base64
import collections
import os
import sys
import time
import traceback
import uuid

VERSION = "4"

def usage(e=None):
    if e:
        print e
        print ""
    try:
        CalVerifyOptions().opt_help()
    except SystemExit:
        pass
    if e:
        sys.exit(64)
    else:
        sys.exit(0)


description = ''.join(
    wordWrap(
        """
        Usage: calendarserver_verify_data [options] [input specifiers]
        """,
        int(os.environ.get('COLUMNS', '80'))
    )
)
description += "\nVersion: %s" % (VERSION,)


def safePercent(x, y, multiplier=100.0):
    return ((multiplier * x) / y) if y else 0


class CalVerifyOptions(Options):
    """
    Command-line options for 'calendarserver_verify_data'
    """

    synopsis = description

    optFlags = [
        ['ical', 'i', "Calendar data check."],
        ['badcua', 'b', "Calendar data check for bad CALENDARSERVER-OLD-CUA only."],
        ['nobase64', 'n', "Do not apply CALENDARSERVER-OLD-CUA base64 transform when fixing."],
        ['mismatch', 's', "Detect organizer/attendee mismatches."],
        ['missing', 'm', "Show 'orphaned' homes."],
        ['fix', 'x', "Fix problems."],
        ['verbose', 'v', "Verbose logging."],
        ['details', 'V', "Detailed logging."],
        ['tzid', 't', "Timezone to adjust displayed times to."],
    ]

    optParameters = [
        ['config', 'f', DEFAULT_CONFIG_FILE, "Specify caldavd.plist configuration path."],
        ['data', 'd', "./calverify-data", "Path where ancillary data is stored."],
        ['uuid', 'u', "", "Only check this user."],
        ['uid', 'U', "", "Only this event UID."],
    ]


    def __init__(self):
        super(CalVerifyOptions, self).__init__()
        self.outputName = '-'


    def opt_output(self, filename):
        """
        Specify output file path (default: '-', meaning stdout).
        """
        self.outputName = filename

    opt_o = opt_output


    def openOutput(self):
        """
        Open the appropriate output file based on the '--output' option.
        """
        if self.outputName == '-':
            return sys.stdout
        else:
            return open(self.outputName, 'wb')



class CalVerifyService(Service, object):
    """
    Service which runs, exports the appropriate records, then stops the reactor.
    """

    metadata = {
        "accessMode": "PUBLIC",
        "isScheduleObject": True,
        "scheduleTag": "abc",
        "scheduleEtags": (),
        "hasPrivateComment": False,
    }

    metadata_inbox = {
        "accessMode": "PUBLIC",
        "isScheduleObject": False,
        "scheduleTag": "",
        "scheduleEtags": (),
        "hasPrivateComment": False,
    }

    def __init__(self, store, options, output, reactor, config):
        super(CalVerifyService, self).__init__()
        self.store   = store
        self.options = options
        self.output  = output
        self.reactor = reactor
        self.config = config
        self._directory = None
        
        self.cuaCache = {}
        self.validForCalendaringUUIDs = {}
        
        self.results = {}
        self.summary = []
        self.fixAttendeesForOrganizerMissing = 0
        self.fixAttendeesForOrganizerMismatch = 0
        self.fixOrganizersForAttendeeMissing = 0
        self.fixOrganizersForAttendeeMismatch = 0
        self.fixFailed = 0
        self.fixedAutoAccepts = [] 
        self.total = 0
        self.totalErrors = None
        self.totalExceptions = None


    def startService(self):
        """
        Start the service.
        """
        super(CalVerifyService, self).startService()
        self.doCalVerify()


    @inlineCallbacks
    def doCalVerify(self):
        """
        Do the export, stopping the reactor when done.
        """
        self.output.write("\n---- CalVerify version: %s ----\n" % (VERSION,))

        try:
            if self.options["missing"]:
                yield self.doOrphans()
                
            if self.options["mismatch"] or self.options["ical"] or self.options["badcua"]:
                yield self.doScan(self.options["ical"] or self.options["badcua"], self.options["mismatch"], self.options["fix"])

            self.printSummary()

            self.output.close()
        except:
            log.err()

        self.reactor.stop()


    @inlineCallbacks
    def doOrphans(self):
        """
        Report on home collections for which there are no directory records, or record is for user on
        a different pod, or a user not enabled for calendaring. 
        """
        self.output.write("\n---- Finding calendar homes with missing or disabled directory records ----\n")
        self.txn = self.store.newTransaction()

        if self.options["verbose"]:
            t = time.time()
        uids = yield self.getAllHomeUIDs()
        if self.options["verbose"]:
            self.output.write("getAllHomeUIDs time: %.1fs\n" % (time.time() - t,))
        missing = []
        wrong_server = []
        disabled = []
        uids_len = len(uids)
        uids_div = 1 if uids_len < 100 else uids_len / 100
        self.addToSummary("Total Homes", uids_len)

        for ctr, uid in enumerate(uids):
            if self.options["verbose"] and divmod(ctr, uids_div)[1] == 0:
                self.output.write(("\r%d of %d (%d%%)" % (
                    ctr+1,
                    uids_len,
                    ((ctr+1) * 100 / uids_len),
                )).ljust(80))
                self.output.flush()

            record = self.directoryService().recordWithGUID(uid)
            if record is None:
                contents = yield self.countHomeContents(uid)
                missing.append((uid, contents,))
            elif not record.thisServer():
                contents = yield self.countHomeContents(uid)
                wrong_server.append((uid, contents,))
            elif not record.enabledForCalendaring:
                contents = yield self.countHomeContents(uid)
                disabled.append((uid, contents,))
            
            # To avoid holding locks on all the rows scanned, commit every 100 resources
            if divmod(ctr, 100)[1] == 0:
                yield self.txn.commit()
                self.txn = self.store.newTransaction()

        yield self.txn.commit()
        self.txn = None
        if self.options["verbose"]:
            self.output.write("\r".ljust(80) + "\n")

        # Print table of results
        table = tables.Table()
        table.addHeader(("Owner UID", "Calendar Objects"))
        for uid, count in sorted(missing, key=lambda x:x[0]):
            table.addRow((
                uid,
                count,
            ))
        
        self.output.write("\n")
        self.output.write("Homes without a matching directory record (total=%d):\n" % (len(missing),))
        table.printTable(os=self.output)
        self.addToSummary("Homes without a matching directory record", len(missing), uids_len)
        
        # Print table of results
        table = tables.Table()
        table.addHeader(("Owner UID", "Calendar Objects"))
        for uid, count in sorted(wrong_server, key=lambda x:x[0]):
            record = self.directoryService().recordWithGUID(uid)
            table.addRow((
                "%s/%s (%s)" % (record.recordType if record else "-", record.shortNames[0] if record else "-", uid,),
                count,
            ))
        
        self.output.write("\n")
        self.output.write("Homes not hosted on this server (total=%d):\n" % (len(wrong_server),))
        table.printTable(os=self.output)
        self.addToSummary("Homes not hosted on this server", len(wrong_server), uids_len)
        
        # Print table of results
        table = tables.Table()
        table.addHeader(("Owner UID", "Calendar Objects"))
        for uid, count in sorted(disabled, key=lambda x:x[0]):
            record = self.directoryService().recordWithGUID(uid)
            table.addRow((
                "%s/%s (%s)" % (record.recordType if record else "-", record.shortNames[0] if record else "-", uid,),
                count,
            ))
        
        self.output.write("\n")
        self.output.write("Homes without an enabled directory record (total=%d):\n" % (len(disabled),))
        table.printTable(os=self.output)
        self.addToSummary("Homes without an enabled directory record", len(disabled), uids_len)
        

    @inlineCallbacks
    def getAllHomeUIDs(self):
        ch = schema.CALENDAR_HOME
        rows = (yield Select(
            [ch.OWNER_UID,],
            From=ch,
        ).on(self.txn))
        returnValue(tuple([uid[0] for uid in rows]))


    @inlineCallbacks
    def countHomeContents(self, uid):
        ch = schema.CALENDAR_HOME
        cb = schema.CALENDAR_BIND
        co = schema.CALENDAR_OBJECT
        kwds = { "UID" : uid }
        rows = (yield Select(
            [Count(co.RESOURCE_ID),],
            From=ch.join(
                cb, type="inner", on=(ch.RESOURCE_ID == cb.CALENDAR_HOME_RESOURCE_ID).And(
                    cb.BIND_MODE == _BIND_MODE_OWN)).join(
                co, type="inner", on=(cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID)),
            Where=(ch.OWNER_UID == Parameter("UID"))
        ).on(self.txn, **kwds))
        returnValue(int(rows[0][0]) if rows else 0)


    @inlineCallbacks
    def doScan(self, ical, mismatch, fix, start=None):
        
        self.output.write("\n---- Scanning calendar data ----\n")

        self.now = PyCalendarDateTime.getNowUTC()
        self.start = start if start is not None else PyCalendarDateTime.getToday()
        self.start.setDateOnly(False)
        self.end = self.start.duplicate()
        self.end.offsetYear(1)
        self.fix = fix
        
        self.tzid = PyCalendarTimezone(tzid=self.options["tzid"] if self.options["tzid"] else "America/Los_Angeles")

        self.txn = self.store.newTransaction()

        if self.options["verbose"]:
            t = time.time()
        descriptor = None
        if ical:
            if self.options["uuid"]:
                rows = yield self.getAllResourceInfoWithUUID(self.options["uuid"], inbox=True)
                descriptor = "getAllResourceInfoWithUUID"
            elif self.options["uid"]:
                rows = yield self.getAllResourceInfoWithUID(self.options["uid"], inbox=True)
                descriptor = "getAllResourceInfoWithUID"
            else:
                rows = yield self.getAllResourceInfo(inbox=True)
                descriptor = "getAllResourceInfo"
        else:
            if self.options["uid"]:
                rows = yield self.getAllResourceInfoWithUID(self.options["uid"])
                descriptor = "getAllResourceInfoWithUID"
            else:
                rows = yield self.getAllResourceInfoTimeRange(self.start)
                descriptor = "getAllResourceInfoTimeRange"

        yield self.txn.commit()
        self.txn = None

        if self.options["verbose"]:
            self.output.write("%s time: %.1fs\n" % (descriptor, time.time() - t,))
        
        self.total = len(rows)
        self.output.write("Number of events to process: %s\n" % (len(rows,)))
        self.results["Number of events to process"] = len(rows)
        self.addToSummary("Number of events to process", self.total)
        
        # Split into organizer events and attendee events
        self.organized = []
        self.organized_byuid = {}
        self.attended = []
        self.attended_byuid = collections.defaultdict(list)
        self.matched_attendee_to_organizer = collections.defaultdict(set)
        skipped, inboxes = self.buildResourceInfo(rows)
                
        self.output.write("Number of organizer events to process: %s\n" % (len(self.organized),))
        self.output.write("Number of attendee events to process: %s\n" % (len(self.attended,)))
        self.results["Number of organizer events to process"] = len(self.organized)
        self.results["Number of attendee events to process"] = len(self.attended)
        self.results["Number of skipped events"] = skipped
        self.results["Number of inbox events"] = inboxes
        self.addToSummary("Number of organizer events to process", len(self.organized), self.total)
        self.addToSummary("Number of attendee events to process", len(self.attended), self.total)
        self.addToSummary("Number of skipped events", skipped, self.total)
        if ical:
            self.addToSummary("Number of inbox events", inboxes, self.total)
        self.addSummaryBreak()

        if ical:
            yield self.calendarDataCheck(rows)
        elif mismatch:
            self.totalErrors = 0
            yield self.verifyAllAttendeesForOrganizer()
            yield self.verifyAllOrganizersForAttendee()
            
            # Need to add fix summary information
            if fix:
                self.addSummaryBreak()
                self.results["Fixed missing attendee events"] = self.fixAttendeesForOrganizerMissing
                self.results["Fixed mismatched attendee events"] = self.fixAttendeesForOrganizerMismatch
                self.results["Fixed missing organizer events"] = self.fixOrganizersForAttendeeMissing
                self.results["Fixed mismatched organizer events"] = self.fixOrganizersForAttendeeMismatch
                self.results["Fix failures"] = self.fixFailed
                self.results["Fixed Auto-Accepts"] = self.fixedAutoAccepts
                self.addToSummary("Fixed missing attendee events", self.fixAttendeesForOrganizerMissing)
                self.addToSummary("Fixed mismatched attendee events", self.fixAttendeesForOrganizerMismatch)
                self.addToSummary("Fixed missing organizer events", self.fixOrganizersForAttendeeMissing)
                self.addToSummary("Fixed mismatched organizer events", self.fixOrganizersForAttendeeMismatch)
                self.addToSummary("Fix failures", self.fixFailed)
                
                self.printAutoAccepts()
        
        yield succeed(None)


    @inlineCallbacks
    def getAllResourceInfo(self, inbox=False):
        co = schema.CALENDAR_OBJECT
        cb = schema.CALENDAR_BIND
        ch = schema.CALENDAR_HOME
        
        if inbox:
            cojoin = (cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                    cb.BIND_MODE == _BIND_MODE_OWN)
        else:
            cojoin = (cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                    cb.BIND_MODE == _BIND_MODE_OWN).And(
                    cb.CALENDAR_RESOURCE_NAME != "inbox")

        kwds = {}
        rows = (yield Select(
            [ch.OWNER_UID, co.RESOURCE_ID, co.ICALENDAR_UID, cb.CALENDAR_RESOURCE_NAME, co.MD5, co.ORGANIZER, co.CREATED, co.MODIFIED],
            From=ch.join(
                cb, type="inner", on=(ch.RESOURCE_ID == cb.CALENDAR_HOME_RESOURCE_ID)).join(
                co, type="inner", on=cojoin),
            GroupBy=(ch.OWNER_UID, co.RESOURCE_ID, co.ICALENDAR_UID, cb.CALENDAR_RESOURCE_NAME, co.MD5, co.ORGANIZER, co.CREATED, co.MODIFIED,),
        ).on(self.txn, **kwds))
        returnValue(tuple(rows))


    @inlineCallbacks
    def getAllResourceInfoWithUUID(self, uuid, inbox=False):
        co = schema.CALENDAR_OBJECT
        cb = schema.CALENDAR_BIND
        ch = schema.CALENDAR_HOME

        if inbox:
            cojoin = (cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                    cb.BIND_MODE == _BIND_MODE_OWN)
        else:
            cojoin = (cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                    cb.BIND_MODE == _BIND_MODE_OWN).And(
                    cb.CALENDAR_RESOURCE_NAME != "inbox")

        kwds = {"uuid": uuid}
        if len(uuid) != 36:
            where = (ch.OWNER_UID.StartsWith(Parameter("uuid")))
        else:
            where = (ch.OWNER_UID == Parameter("uuid"))
        rows = (yield Select(
            [ch.OWNER_UID, co.RESOURCE_ID, co.ICALENDAR_UID, cb.CALENDAR_RESOURCE_NAME, co.MD5, co.ORGANIZER, co.CREATED, co.MODIFIED],
            From=ch.join(
                cb, type="inner", on=(ch.RESOURCE_ID == cb.CALENDAR_HOME_RESOURCE_ID)).join(
                co, type="inner", on=cojoin),
            Where=where,
            GroupBy=(ch.OWNER_UID, co.RESOURCE_ID, co.ICALENDAR_UID, cb.CALENDAR_RESOURCE_NAME, co.MD5, co.ORGANIZER, co.CREATED, co.MODIFIED,),
        ).on(self.txn, **kwds))
        returnValue(tuple(rows))


    @inlineCallbacks
    def getAllResourceInfoTimeRange(self, start):
        co = schema.CALENDAR_OBJECT
        cb = schema.CALENDAR_BIND
        ch = schema.CALENDAR_HOME
        tr = schema.TIME_RANGE
        kwds = {
            "Start" : pyCalendarTodatetime(start),
            "Max"   : pyCalendarTodatetime(PyCalendarDateTime(1900, 1, 1, 0, 0, 0))
        }
        rows = (yield Select(
            [ch.OWNER_UID, co.RESOURCE_ID, co.ICALENDAR_UID, cb.CALENDAR_RESOURCE_NAME, co.MD5, co.ORGANIZER, co.CREATED, co.MODIFIED],
            From=ch.join(
                cb, type="inner", on=(ch.RESOURCE_ID == cb.CALENDAR_HOME_RESOURCE_ID)).join(
                co, type="inner", on=(cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                    cb.BIND_MODE == _BIND_MODE_OWN).And(
                    cb.CALENDAR_RESOURCE_NAME != "inbox").And(
                    co.ORGANIZER != "")).join(
                tr, type="left", on=(co.RESOURCE_ID == tr.CALENDAR_OBJECT_RESOURCE_ID)),
            Where=(tr.START_DATE >= Parameter("Start")).Or(co.RECURRANCE_MAX == Parameter("Max")),
            GroupBy=(ch.OWNER_UID, co.RESOURCE_ID, co.ICALENDAR_UID, cb.CALENDAR_RESOURCE_NAME, co.MD5, co.ORGANIZER, co.CREATED, co.MODIFIED,),
        ).on(self.txn, **kwds))
        returnValue(tuple(rows))


    @inlineCallbacks
    def getAllResourceInfoWithUID(self, uid, inbox=False):
        co = schema.CALENDAR_OBJECT
        cb = schema.CALENDAR_BIND
        ch = schema.CALENDAR_HOME

        if inbox:
            cojoin = (cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                    cb.BIND_MODE == _BIND_MODE_OWN)
        else:
            cojoin = (cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                    cb.BIND_MODE == _BIND_MODE_OWN).And(
                    cb.CALENDAR_RESOURCE_NAME != "inbox")

        kwds = {
            "UID" : uid,
        }
        rows = (yield Select(
            [ch.OWNER_UID, co.RESOURCE_ID, co.ICALENDAR_UID, cb.CALENDAR_RESOURCE_NAME, co.MD5, co.ORGANIZER, co.CREATED, co.MODIFIED],
            From=ch.join(
                cb, type="inner", on=(ch.RESOURCE_ID == cb.CALENDAR_HOME_RESOURCE_ID)).join(
                co, type="inner", on=cojoin),
            Where=(co.ICALENDAR_UID == Parameter("UID")),
            GroupBy=(ch.OWNER_UID, co.RESOURCE_ID, co.ICALENDAR_UID, cb.CALENDAR_RESOURCE_NAME, co.MD5, co.ORGANIZER, co.CREATED, co.MODIFIED,),
        ).on(self.txn, **kwds))
        returnValue(tuple(rows))


    @inlineCallbacks
    def getAllResourceInfoForResourceID(self, resid):
        co = schema.CALENDAR_OBJECT
        cb = schema.CALENDAR_BIND
        ch = schema.CALENDAR_HOME
        kwds = {"resid": resid}
        rows = (yield Select(
            [ch.RESOURCE_ID, cb.CALENDAR_RESOURCE_ID,],
            From=ch.join(
                cb, type="inner", on=(ch.RESOURCE_ID == cb.CALENDAR_HOME_RESOURCE_ID)).join(
                co, type="inner", on=(cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                    cb.BIND_MODE == _BIND_MODE_OWN)),
            Where=(co.RESOURCE_ID == Parameter("resid")),
        ).on(self.txn, **kwds))
        returnValue(rows[0])


    def buildResourceInfo(self, rows, onlyOrganizer=False, onlyAttendee=False):
        skipped = 0
        inboxes = 0
        for owner, resid, uid, calname, md5, organizer, created, modified in rows:
            
            # Skip owners not enabled for calendaring
            if not self.testForCalendaringUUID(owner):
                skipped += 1
                continue

            # Skip inboxes
            if calname == "inbox":
                inboxes += 1
                continue

            # If targeting a specific organizer, skip events belonging to others
            if self.options["uuid"]:
                if not organizer.startswith("urn:uuid:") or self.options["uuid"] != organizer[9:]:
                    continue
                
            # Cache organizer/attendee states
            if organizer.startswith("urn:uuid:") and owner == organizer[9:]:
                if not onlyAttendee:
                    self.organized.append((owner, resid, uid, md5, organizer, created, modified,))
                    self.organized_byuid[uid] = (owner, resid, uid, md5, organizer, created, modified,)
            else:
                if not onlyOrganizer:
                    self.attended.append((owner, resid, uid, md5, organizer, created, modified,))
                    self.attended_byuid[uid].append((owner, resid, uid, md5, organizer, created, modified,))
        
        return skipped, inboxes

    def testForCalendaringUUID(self, uuid):
        """
        Determine if the specified directory UUID is valid for calendaring. Keep a cache of
        valid and invalid so we can do this quickly.

        @param uuid: the directory UUID to test
        @type uuid: C{str}
        
        @return: C{True} if valid, C{False} if not
        """

        if uuid not in self.validForCalendaringUUIDs:
            record = self.directoryService().recordWithGUID(uuid)
            self.validForCalendaringUUIDs[uuid] = record is not None and record.enabledForCalendaring and record.thisServer()
        return self.validForCalendaringUUIDs[uuid]


    @inlineCallbacks
    def calendarDataCheck(self, rows):
        """
        Check each calendar resource for valid iCalendar data.
        """

        self.output.write("\n---- Verifying each calendar object resource ----\n")
        self.txn = self.store.newTransaction()

        if self.options["verbose"]:
            t = time.time()

        results_bad = []
        count = 0
        total = len(rows)
        badlen = 0
        rjust = 10
        for owner, resid, uid, calname, _ignore_md5, _ignore_organizer, _ignore_created, _ignore_modified in rows:
            result, message = yield self.validCalendarData(resid, calname == "inbox")
            if not result:
                results_bad.append((owner, uid, resid, message))
                badlen += 1
            count += 1
            if self.options["verbose"]:
                if count == 1:
                    self.output.write("Bad".rjust(rjust) + "Current".rjust(rjust) + "Total".rjust(rjust) + "Complete".rjust(rjust) + "\n")
                if divmod(count, 100)[1] == 0:
                    self.output.write((
                        "\r" + 
                        ("%s" % badlen).rjust(rjust) +
                        ("%s" % count).rjust(rjust) +
                        ("%s" % total).rjust(rjust) +
                        ("%d%%" % safePercent(count, total)).rjust(rjust)
                    ).ljust(80))
                    self.output.flush()
            
            # To avoid holding locks on all the rows scanned, commit every 100 resources
            if divmod(count, 100)[1] == 0:
                yield self.txn.commit()
                self.txn = self.store.newTransaction()

        yield self.txn.commit()
        self.txn = None
        if self.options["verbose"]:
                    self.output.write((
                        "\r" + 
                        ("%s" % badlen).rjust(rjust) +
                        ("%s" % count).rjust(rjust) +
                        ("%s" % total).rjust(rjust) +
                        ("%d%%" % safePercent(count, total)).rjust(rjust)
                    ).ljust(80) + "\n")
        
        # Print table of results
        table = tables.Table()
        table.addHeader(("Owner", "Event UID", "RID", "Problem",))
        for item in results_bad:
            owner, uid, resid, message = item
            owner_record = self.directoryService().recordWithGUID(owner)
            table.addRow((
                "%s/%s (%s)" % (owner_record.recordType if owner_record else "-", owner_record.shortNames[0] if owner_record else "-", owner,),
                uid,
                resid,
                message,
            ))
        
        self.output.write("\n")
        self.output.write("Bad iCalendar data (total=%d):\n" % (len(results_bad),))
        table.printTable(os=self.output)
        
        self.results["Bad iCalendar data"] = results_bad
        self.addToSummary("Bad iCalendar data", len(results_bad), total)
         
        if self.options["verbose"]:
            diff_time = time.time() - t
            self.output.write("Time: %.2f s  Average: %.1f ms/resource\n" % (
                diff_time,
                (1000.0 * diff_time) / total,
            ))

    errorPrefix = "Calendar data had unfixable problems:\n  "

    @inlineCallbacks
    def validCalendarData(self, resid, isinbox):
        """
        Check the calendar resource for valid iCalendar data.
        """

        caldata = yield self.getCalendar(resid, self.fix)
        if caldata is None:
            if self.parseError:
                returnValue((False, self.parseError))
            else:
                returnValue((True, "Nothing to scan"))

        component = Component(None, pycalendar=caldata)
        if self.config.MaxInstancesForRRULE:
            component.truncateRecurrence(self.config.MaxInstancesForRRULE)
        result = True
        message = ""
        try:
            if self.options["ical"]:
                component.validCalendarData(doFix=False, validateRecurrences=True)
                component.validCalendarForCalDAV(methodAllowed=isinbox)
                component.validOrganizerForScheduling(doFix=False)
            self.noPrincipalPathCUAddresses(component, doFix=False)
        except ValueError, e:
            result = False
            message = str(e)
            if message.startswith(self.errorPrefix):
                message = message[len(self.errorPrefix):]
            lines = message.splitlines()
            message = lines[0] + (" ++" if len(lines) > 1 else "")
            if self.fix:
                fixresult, fixmessage = yield self.fixCalendarData(resid, isinbox)
                if fixresult:
                    message = "Fixed: " + message
                else:
                    message = fixmessage + message

        returnValue((result, message,))


    def noPrincipalPathCUAddresses(self, component, doFix):
        
        def lookupFunction(cuaddr, principalFunction, config):
    
            # Return cached results, if any.
            if self.cuaCache.has_key(cuaddr):
                return self.cuaCache[cuaddr]
    
            result = normalizationLookup(cuaddr, principalFunction, config)
            _ignore_name, guid, _ignore_cuaddrs = result
            if guid is None:
                if cuaddr.find("__uids__") != -1:
                    guid = cuaddr[cuaddr.find("__uids__/")+9:][:36]
                    result = "", guid, set()
                    
    
            # Cache the result
            self.cuaCache[cuaddr] = result
            return result

        for subcomponent in component.subcomponents():
            if subcomponent.name() in ignoredComponents:
                continue
            organizer = subcomponent.getProperty("ORGANIZER")
            if organizer:
                cuaddr = organizer.value()
                
                # http(s) principals need to be converted to urn:uuid
                if cuaddr.startswith("http"):
                    if doFix:
                        component.normalizeCalendarUserAddresses(lookupFunction, self.directoryService().principalForCalendarUserAddress)
                    else:
                        raise InvalidICalendarDataError("iCalendar ORGANIZER starts with 'http(s)'")
                else:
                    if ("@" in cuaddr) and (":" not in cuaddr) and ("/" not in cuaddr):
                        if doFix:
                            # Add back in mailto: then re-normalize to urn:uuid if possible
                            organizer.setValue("mailto:%s" % (cuaddr,))
                            component.normalizeCalendarUserAddresses(lookupFunction, self.directoryService().principalForCalendarUserAddress)
                            
                            # Remove any SCHEDULE-AGENT=NONE
                            if organizer.parameterValue("SCHEDULE-AGENT", "SERVER") == "NONE":
                                organizer.removeParameter("SCHEDULE-AGENT")
                        else:
                            raise InvalidICalendarDataError("iCalendar ORGANIZER missing mailto:")

                # CALENDARSERVER-OLD-CUA needs to be base64 encoded
                if organizer.hasParameter("CALENDARSERVER-OLD-CUA"):
                    oldcua = organizer.parameterValue("CALENDARSERVER-OLD-CUA")
                    if not oldcua.startswith("base64-") and not self.options["nobase64"]:
                        if doFix:
                            organizer.setParameter("CALENDARSERVER-OLD-CUA", "base64-%s" % (base64.b64encode(oldcua)))
                        else:
                            raise InvalidICalendarDataError("iCalendar ORGANIZER CALENDARSERVER-OLD-CUA not base64")

            for attendee in subcomponent.properties("ATTENDEE"):
                cuaddr = attendee.value()

                # http(s) principals need to be converted to urn:uuid
                if cuaddr.startswith("http"):
                    if doFix:
                        component.normalizeCalendarUserAddresses(lookupFunction, self.directoryService().principalForCalendarUserAddress)
                    else:
                        raise InvalidICalendarDataError("iCalendar ATTENDEE starts with 'http(s)'")
                else:
                    if ("@" in cuaddr) and (":" not in cuaddr) and ("/" not in cuaddr):
                        if doFix:
                            # Add back in mailto: then re-normalize to urn:uuid if possible
                            attendee.setValue("mailto:%s" % (cuaddr,))
                            component.normalizeCalendarUserAddresses(lookupFunction, self.directoryService().principalForCalendarUserAddress)
                        else:
                            raise InvalidICalendarDataError("iCalendar ATTENDEE missing mailto:")

                # CALENDARSERVER-OLD-CUA needs to be base64 encoded
                if attendee.hasParameter("CALENDARSERVER-OLD-CUA"):
                    oldcua = attendee.parameterValue("CALENDARSERVER-OLD-CUA")
                    if not oldcua.startswith("base64-") and not self.options["nobase64"]:
                        if doFix:
                            attendee.setParameter("CALENDARSERVER-OLD-CUA", "base64-%s" % (base64.b64encode(oldcua)))
                        else:
                            raise InvalidICalendarDataError("iCalendar ATTENDEE CALENDARSERVER-OLD-CUA not base64")


    @inlineCallbacks
    def fixCalendarData(self, resid, isinbox):
        """
        Fix problems in calendar data using store APIs.
        """

        homeID, calendarID = yield self.getAllResourceInfoForResourceID(resid)
        home = yield self.txn.calendarHomeWithResourceID(homeID)
        calendar = yield home.childWithID(calendarID)
        calendarObj = yield calendar.objectResourceWithID(resid)
        
        try:
            component = yield calendarObj.component()
        except InternalDataStoreError:
            returnValue((False, "Failed parse: "))

        result = True
        message = ""
        try:
            if self.options["ical"]:
                component.validCalendarData(doFix=True, validateRecurrences=True)
                component.validCalendarForCalDAV(methodAllowed=isinbox)
                component.validOrganizerForScheduling(doFix=True)
            self.noPrincipalPathCUAddresses(component, doFix=True)
        except ValueError:
            result = False
            message = "Failed fix: "
        
        if result:
            # Write out fix, commit and get a new transaction
            try:
                # Use _migrating to ignore possible overridden instance errors - we are either correcting or ignoring those
                self.txn._migrating = True
                component = yield calendarObj.setComponent(component)
            except Exception, e:
                print e, component
                print traceback.print_exc()
                result = False
                message = "Exception fix: "
            yield self.txn.commit()
            self.txn = self.store.newTransaction()

        returnValue((result, message,))


    @inlineCallbacks
    def fixBadOldCua(self, resid, caltxt):
        """
        Fix bad CALENDARSERVER-OLD-CUA lines and write fixed data to store. Assumes iCalendar data lines unfolded.
        """

        # Get store objects
        homeID, calendarID = yield self.getAllResourceInfoForResourceID(resid)
        home = yield self.txn.calendarHomeWithResourceID(homeID)
        calendar = yield home.childWithID(calendarID)
        calendarObj = yield calendar.objectResourceWithID(resid)
        
        # Do raw data fix one line at a time
        caltxt = self.fixBadOldCuaLines(caltxt)
        
        # Re-parse
        try:
            component = Component.fromString(caltxt)
        except InvalidICalendarDataError:
            returnValue(None)

        # Write out fix, commit and get a new transaction
        # Use _migrating to ignore possible overridden instance errors - we are either correcting or ignoring those
        self.txn._migrating = True
        component = yield calendarObj.setComponent(component)
        yield self.txn.commit()
        self.txn = self.store.newTransaction()

        returnValue(caltxt)


    def fixBadOldCuaLines(self, caltxt):
        """
        Fix bad CALENDARSERVER-OLD-CUA lines. Assumes iCalendar data lines unfolded.
        """

        # Do raw data fix one line at a time
        lines = caltxt.splitlines()
        for ctr, line in enumerate(lines):
            startpos = line.find(";CALENDARSERVER-OLD-CUA=\"//")
            if startpos != -1:
                endpos = line.find("urn:uuid:")
                if endpos != -1:
                    endpos += len("urn:uuid:XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX\"")
                    badparam = line[startpos+len(";CALENDARSERVER-OLD-CUA=\""):endpos]
                    endbadparam = badparam.find(";")
                    if endbadparam != -1:
                        badparam = badparam[:endbadparam].replace("\\", "")
                        if badparam.find("8443") != -1:
                            badparam = "https:" + badparam
                        else:
                            badparam = "http:" + badparam
                        if self.options["nobase64"]:
                            badparam = "\"" + badparam + "\""
                        else:
                            badparam = "base64-%s" % (base64.b64encode(badparam),)
                        badparam = ";CALENDARSERVER-OLD-CUA=" + badparam
                        lines[ctr] = line[:startpos] + badparam + line[endpos:]
        caltxt = "\r\n".join(lines) + "\r\n"
        return caltxt

    @inlineCallbacks
    def verifyAllAttendeesForOrganizer(self):
        """
        Make sure that for each organizer, each referenced attendee has a consistent view of the organizer's event.
        We will look for events that an organizer has and are missing for the attendee, and events that an organizer's
        view of attendee status does not match the attendee's view of their own status.
        """
        
        self.output.write("\n---- Verifying Organizer events against Attendee copies ----\n")
        self.txn = self.store.newTransaction()

        results_missing = []
        results_mismatch = []
        attendeeResIDs = {}
        organized_len = len(self.organized)
        organizer_div = 1 if organized_len < 100 else organized_len / 100

        # Test organized events
        t = time.time()
        for ctr, organizerEvent in enumerate(self.organized):
            
            if self.options["verbose"] and divmod(ctr, organizer_div)[1] == 0:
                self.output.write(("\r%d of %d (%d%%) Missing: %d  Mismatched: %s" % (
                    ctr+1,
                    organized_len,
                    ((ctr+1) * 100 / organized_len),
                    len(results_missing),
                    len(results_mismatch),
                )).ljust(80))
                self.output.flush()

            # To avoid holding locks on all the rows scanned, commit every 10 seconds
            if time.time() - t > 10:
                yield self.txn.commit()
                self.txn = self.store.newTransaction()
                t = time.time()

            # Get the organizer's view of attendee states            
            organizer, resid, uid, _ignore_md5, _ignore_organizer, org_created, org_modified = organizerEvent
            calendar = yield self.getCalendar(resid)
            if calendar is None:
                continue
            if self.options["verbose"] and self.masterComponent(calendar) is None:
                self.output.write("Missing master for organizer: %s, resid: %s, uid: %s\n" % (organizer, resid, uid,))
            organizerViewOfAttendees = self.buildAttendeeStates(calendar, self.start, self.end)
            try:
                del organizerViewOfAttendees[organizer]
            except KeyError:
                # Odd - the organizer is not an attendee - this usually does not happen
                pass
            if len(organizerViewOfAttendees) == 0:
                continue
            
            # Get attendee states for matching UID
            eachAttendeesOwnStatus = {}
            attendeeCreatedModified = {}
            for attendeeEvent in self.attended_byuid.get(uid, ()):
                owner, attresid, attuid, _ignore_md5, _ignore_organizer, att_created, att_modified = attendeeEvent
                attendeeCreatedModified[owner] = (att_created, att_modified,)
                calendar = yield self.getCalendar(attresid)
                if calendar is None:
                    continue
                eachAttendeesOwnStatus[owner] = self.buildAttendeeStates(calendar, self.start, self.end, attendee_only=owner)
                attendeeResIDs[(owner, attuid)] = attresid
            
            # Look at each attendee in the organizer's meeting
            for organizerAttendee, organizerViewOfStatus in organizerViewOfAttendees.iteritems():
                broken = False

                self.matched_attendee_to_organizer[uid].add(organizerAttendee)
                
                # Skip attendees not enabled for calendaring
                if not self.testForCalendaringUUID(organizerAttendee):
                    continue

                # Double check the missing attendee situation in case we missed it during the original query
                if organizerAttendee not in eachAttendeesOwnStatus:
                    # Try to reload the attendee data
                    calendar, attresid, att_created, att_modified = yield self.getCalendarForOwnerByUID(organizerAttendee, uid)
                    if calendar is not None:
                        eachAttendeesOwnStatus[organizerAttendee] = self.buildAttendeeStates(calendar, self.start, self.end, attendee_only=organizerAttendee)
                        attendeeResIDs[(organizerAttendee, uid)] = attresid
                        attendeeCreatedModified[organizerAttendee] = (att_created, att_modified,)
                        #print "Reloaded missing attendee data"
                     
                # If an entry for the attendee exists, then check whether attendee status matches
                if organizerAttendee in eachAttendeesOwnStatus:
                    attendeeOwnStatus = eachAttendeesOwnStatus[organizerAttendee].get(organizerAttendee, set())
                    att_created, att_modified = attendeeCreatedModified[organizerAttendee]

                    if organizerViewOfStatus != attendeeOwnStatus:
                        # Check that the difference is only cancelled or declined on the organizers side
                        for _organizerInstance, partstat in organizerViewOfStatus.difference(attendeeOwnStatus):
                            if partstat not in ("DECLINED", "CANCELLED"):
                                results_mismatch.append((uid, resid, organizer, org_created, org_modified, organizerAttendee, att_created, att_modified))
                                self.results.setdefault("Mismatch Attendee", set()).add((uid, organizer, organizerAttendee,))
                                broken = True
                                if self.options["details"]:
                                    self.output.write("Mismatch: on Organizer's side:\n")
                                    self.output.write("          UID: %s\n" % (uid,))
                                    self.output.write("          Organizer: %s\n" % (organizer,))
                                    self.output.write("          Attendee: %s\n" % (organizerAttendee,))
                                    self.output.write("          Instance: %s\n" % (_organizerInstance,))
                                break
                        # Check that the difference is only cancelled on the attendees side
                        for _attendeeInstance, partstat in attendeeOwnStatus.difference(organizerViewOfStatus):
                            if partstat not in ("CANCELLED",):
                                if not broken:
                                    results_mismatch.append((uid, resid, organizer, org_created, org_modified, organizerAttendee, att_created, att_modified))
                                    self.results.setdefault("Mismatch Attendee", set()).add((uid, organizer, organizerAttendee,))
                                broken = True
                                if self.options["details"]:
                                    self.output.write("Mismatch: on Attendee's side:\n")
                                    self.output.write("          Organizer: %s\n" % (organizer,))
                                    self.output.write("          Attendee: %s\n" % (organizerAttendee,))
                                    self.output.write("          Instance: %s\n" % (_attendeeInstance,))
                                break

                # Check that the status for this attendee is always declined which means a missing copy of the event is OK
                else:
                    for _ignore_instance_id, partstat in organizerViewOfStatus:
                        if partstat not in ("DECLINED", "CANCELLED"):
                            results_missing.append((uid, resid, organizer, organizerAttendee, org_created, org_modified))
                            self.results.setdefault("Missing Attendee", set()).add((uid, organizer, organizerAttendee,))
                            broken = True
                            break
                
                # If there was a problem we can fix it
                if broken and self.fix:
                    yield self.fixByReinvitingAttendee(resid, attendeeResIDs.get((organizerAttendee, uid)), organizerAttendee)

        yield self.txn.commit()
        self.txn = None
        if self.options["verbose"]:
            self.output.write("\r".ljust(80) + "\n")

        # Print table of results
        table = tables.Table()
        table.addHeader(("Organizer", "Attendee", "Event UID", "Organizer RID", "Created", "Modified",))
        results_missing.sort()
        for item in results_missing:
            uid, resid, organizer, attendee, created, modified = item
            organizer_record = self.directoryService().recordWithGUID(organizer)
            attendee_record = self.directoryService().recordWithGUID(attendee)
            table.addRow((
                "%s/%s (%s)" % (organizer_record.recordType if organizer_record else "-", organizer_record.shortNames[0] if organizer_record else "-", organizer,),
                "%s/%s (%s)" % (attendee_record.recordType if attendee_record else "-", attendee_record.shortNames[0] if attendee_record else "-", attendee,),
                uid,
                resid,
                created,
                "" if modified == created else modified,
            ))
        
        self.output.write("\n")
        self.output.write("Events missing from Attendee's calendars (total=%d):\n" % (len(results_missing),))
        table.printTable(os=self.output)
        self.addToSummary("Events missing from Attendee's calendars", len(results_missing), self.total)
        self.totalErrors += len(results_missing)

        # Print table of results
        table = tables.Table()
        table.addHeader(("Organizer", "Attendee", "Event UID", "Organizer RID", "Created", "Modified", "Attendee RID", "Created", "Modified",))
        results_mismatch.sort()
        for item in results_mismatch:
            uid, org_resid, organizer, org_created, org_modified, attendee, att_created, att_modified = item
            organizer_record = self.directoryService().recordWithGUID(organizer)
            attendee_record = self.directoryService().recordWithGUID(attendee)
            table.addRow((
                "%s/%s (%s)" % (organizer_record.recordType if organizer_record else "-", organizer_record.shortNames[0] if organizer_record else "-", organizer,),
                "%s/%s (%s)" % (attendee_record.recordType if attendee_record else "-", attendee_record.shortNames[0] if attendee_record else "-", attendee,),
                uid,
                org_resid,
                org_created,
                "" if org_modified == org_created else org_modified,
                attendeeResIDs[(attendee, uid)],
                att_created,
                "" if att_modified == att_created else att_modified,
            ))
        
        self.output.write("\n")
        self.output.write("Events mismatched between Organizer's and Attendee's calendars (total=%d):\n" % (len(results_mismatch),))
        table.printTable(os=self.output)
        self.addToSummary("Events mismatched between Organizer's and Attendee's calendars", len(results_mismatch), self.total)
        self.totalErrors += len(results_mismatch)


    @inlineCallbacks
    def verifyAllOrganizersForAttendee(self):
        """
        Make sure that for each attendee, there is a matching event for the organizer.
        """

        self.output.write("\n---- Verifying Attendee events against Organizer copies ----\n")
        self.txn = self.store.newTransaction()

        # Now try to match up each attendee event
        missing = []
        mismatched = []
        attended_len = len(self.attended)
        attended_div = 1 if attended_len < 100 else attended_len / 100

        t = time.time()
        for ctr, attendeeEvent in enumerate(tuple(self.attended)): # self.attended might mutate during the loop
            
            if self.options["verbose"] and divmod(ctr, attended_div)[1] == 0:
                self.output.write(("\r%d of %d (%d%%) Missing: %d  Mismatched: %s" % (
                    ctr+1,
                    attended_len,
                    ((ctr+1) * 100 / attended_len),
                    len(missing),
                    len(mismatched),
                )).ljust(80))
                self.output.flush()

            # To avoid holding locks on all the rows scanned, commit every 10 seconds
            if time.time() - t > 10:
                yield self.txn.commit()
                self.txn = self.store.newTransaction()
                t = time.time()

            attendee, resid, uid, _ignore_md5, organizer, att_created, att_modified = attendeeEvent
            calendar = yield self.getCalendar(resid)
            if calendar is None:
                continue
            eachAttendeesOwnStatus = self.buildAttendeeStates(calendar, self.start, self.end, attendee_only=attendee)
            if attendee not in eachAttendeesOwnStatus:
                continue

            # Only care about data for hosted organizers                
            if not organizer.startswith("urn:uuid:"):
                continue
            organizer = organizer[9:]

            # Skip organizers not enabled for calendaring
            if not self.testForCalendaringUUID(organizer):
                continue

            # Double check the missing attendee situation in case we missed it during the original query
            if uid not in self.organized_byuid:
                # Try to reload the organizer info data
                rows = yield self.getAllResourceInfoWithUID(uid)
                self.buildResourceInfo(rows, onlyOrganizer=True)
                
                #if uid in self.organized_byuid:
                #    print "Reloaded missing organizer data: %s" % (uid,)
                 
            if uid not in self.organized_byuid:

                # Check whether attendee has all instances cancelled
                if self.allCancelled(eachAttendeesOwnStatus):
                    continue
                
                missing.append((uid, attendee, organizer, resid, att_created, att_modified,))
                self.results.setdefault("Missing Organizer", set()).add((uid, attendee, organizer,))
                
                # If there is a miss we fix by removing the attendee data
                if self.fix:
                    # This is where we attempt a fix
                    fix_result = (yield self.fixByRemovingEvent(resid))
                    if fix_result:
                        self.fixOrganizersForAttendeeMissing += 1
                    else:
                        self.fixFailed += 1 

            elif attendee not in self.matched_attendee_to_organizer[uid]:
                # Check whether attendee has all instances cancelled
                if self.allCancelled(eachAttendeesOwnStatus):
                    continue

                mismatched.append((uid, attendee, organizer, resid, att_created, att_modified,))
                self.results.setdefault("Mismatch Organizer", set()).add((uid, attendee, organizer,))
                
                # If there is a mismatch we fix by re-inviting the attendee
                if self.fix:
                    yield self.fixByReinvitingAttendee(self.organized_byuid[uid][1], resid, attendee)

        yield self.txn.commit()
        self.txn = None
        if self.options["verbose"]:
            self.output.write("\r".ljust(80) + "\n")

        # Print table of results
        table = tables.Table()
        table.addHeader(("Organizer", "Attendee", "UID", "Attendee RID", "Created", "Modified",))
        missing.sort()
        unique_set = set()
        for item in missing:
            uid, attendee, organizer, resid, created, modified = item
            unique_set.add(uid)
            if organizer:
                organizerRecord = self.directoryService().recordWithGUID(organizer)
                organizer = "%s/%s (%s)" % (organizerRecord.recordType if organizerRecord else "-", organizerRecord.shortNames[0] if organizerRecord else "-", organizer,)
            attendeeRecord = self.directoryService().recordWithGUID(attendee)
            table.addRow((
                organizer,
                "%s/%s (%s)" % (attendeeRecord.recordType if attendeeRecord else "-", attendeeRecord.shortNames[0] if attendeeRecord else "-", attendee,),
                uid,
                resid,
                created,
                "" if modified == created else modified,
            ))
        
        self.output.write("\n")
        self.output.write("Attendee events missing in Organizer's calendar (total=%d, unique=%d):\n" % (len(missing), len(unique_set),))
        table.printTable(os=self.output)
        self.addToSummary("Attendee events missing in Organizer's calendar", len(missing), self.total)
        self.totalErrors += len(missing)

        # Print table of results
        table = tables.Table()
        table.addHeader(("Organizer", "Attendee", "UID", "Organizer RID", "Created", "Modified", "Attendee RID", "Created", "Modified",))
        mismatched.sort()
        for item in mismatched:
            uid, attendee, organizer, resid, att_created, att_modified = item
            if organizer:
                organizerRecord = self.directoryService().recordWithGUID(organizer)
                organizer = "%s/%s (%s)" % (organizerRecord.recordType if organizerRecord else "-", organizerRecord.shortNames[0] if organizerRecord else "-", organizer,)
            attendeeRecord = self.directoryService().recordWithGUID(attendee)
            table.addRow((
                organizer,
                "%s/%s (%s)" % (attendeeRecord.recordType if attendeeRecord else "-", attendeeRecord.shortNames[0] if attendeeRecord else "-", attendee,),
                uid,
                self.organized_byuid[uid][1],
                self.organized_byuid[uid][5],
                self.organized_byuid[uid][6],
                resid,
                att_created,
                "" if att_modified == att_created else att_modified,
            ))
        
        self.output.write("\n")
        self.output.write("Attendee events mismatched in Organizer's calendar (total=%d):\n" % (len(mismatched),))
        table.printTable(os=self.output)
        self.addToSummary("Attendee events mismatched in Organizer's calendar", len(mismatched), self.total)
        self.totalErrors += len(mismatched)


    @inlineCallbacks
    def fixByReinvitingAttendee(self, orgresid, attresid, attendee):
        """
        Fix a mismatch/missing error by having the organizer send a REQUEST for the entire event to the attendee
        to trigger implicit scheduling to resync the attendee event.
        
        We do not have implicit apis in the store, but really want to use store-only apis here to avoid having to create
        "fake" HTTP requests and manipulate HTTP resources. So what we will do is emulate implicit behavior by copying the
        organizer resource to the attendee (filtering it for the attendee's view of the event) and deposit an inbox item
        for the same event. Right now that will wipe out any per-attendee data - notably alarms.
        """
        
        try:
            cuaddr = "urn:uuid:%s" % attendee
    
            # Get the organizer's calendar data
            calendar = (yield self.getCalendar(orgresid))
            calendar = Component(None, pycalendar=calendar)
            
            # Generate an iTip message for the entire event filtered for the attendee's view
            itipmsg = iTipGenerator.generateAttendeeRequest(calendar, (cuaddr,), None)
            
            # Handle the case where the attendee is not actually in the organizer event at all by
            # removing the attendee event instead of re-inviting
            if itipmsg.resourceUID() is None:
                yield self.fixByRemovingEvent(attresid)
                returnValue(True)

            # Convert iTip message into actual calendar data - just remove METHOD
            attendee_calendar = itipmsg.duplicate()
            attendee_calendar.removeProperty(attendee_calendar.getProperty("METHOD"))
            
            # Adjust TRANSP to match PARTSTAT
            self.setTransparencyForAttendee(attendee_calendar, cuaddr)
    
            # Get attendee home store object
            home = (yield self.txn.calendarHomeWithUID(attendee))
            if home is None:
                raise ValueError("Cannot find home")
            inbox = (yield home.calendarWithName("inbox"))
            if inbox is None:
                raise ValueError("Cannot find inbox")
    
            details = {}
            # Replace existing resource data, or create a new one
            if attresid:
                # TODO: transfer over per-attendee data - valarms
                _ignore_homeID, calendarID = yield self.getAllResourceInfoForResourceID(attresid)
                calendar = yield home.childWithID(calendarID)
                calendarObj = yield calendar.objectResourceWithID(attresid)
                calendarObj.scheduleTag = str(uuid.uuid4())
                yield calendarObj.setComponent(attendee_calendar)
                self.results.setdefault("Fix change event", set()).add((home.name(), calendar.name(), attendee_calendar.resourceUID(),))
                
                details["path"] = "/calendars/__uids__/%s/%s/%s" % (home.name(), calendar.name(), calendarObj.name(),)
                details["rid"] = attresid
            else:
                # Find default calendar for VEVENTs
                defaultCalendar = (yield self.defaultCalendarForAttendee(home, inbox))
                if defaultCalendar is None:
                    raise ValueError("Cannot find suitable default calendar")
                new_name = str(uuid.uuid4()) + ".ics"
                calendarObj = (yield defaultCalendar.createCalendarObjectWithName(new_name, attendee_calendar, self.metadata))
                self.results.setdefault("Fix add event", set()).add((home.name(), defaultCalendar.name(), attendee_calendar.resourceUID(),))

                details["path"] = "/calendars/__uids__/%s/%s/%s" % (home.name(), defaultCalendar.name(), new_name,)
                details["rid"] = calendarObj._resourceID

            details["uid"] = attendee_calendar.resourceUID()
            instances = attendee_calendar.expandTimeRanges(self.end)
            for key in instances:
                instance = instances[key]
                if instance.start > self.now:
                    break
            details["start"] = instance.start.adjustTimezone(self.tzid)
            details["title"] = instance.component.propertyValue("SUMMARY")
            
            # Write new itip message to attendee inbox
            yield inbox.createCalendarObjectWithName(str(uuid.uuid4()) + ".ics", itipmsg, self.metadata_inbox)
            self.results.setdefault("Fix add inbox", set()).add((home.name(), itipmsg.resourceUID(),))
     
            yield self.txn.commit()
            self.txn = self.store.newTransaction()
    
            # Need to know whether the attendee is a location or resource with auto-accept set
            record = self.directoryService().recordWithGUID(attendee)
            if record.autoSchedule:
                # Log details about the event so we can have a human manually process
                self.fixedAutoAccepts.append(details)

            returnValue(True)

        except Exception, e:
            print "Failed to fix resource: %d for attendee: %s\n%s" % (orgresid, attendee, e,)
            returnValue(False)
        

    @inlineCallbacks
    def defaultCalendarForAttendee(self, home, inbox):
        
        # Check for property
        default = inbox.properties().get(PropertyName.fromElement(caldavxml.ScheduleDefaultCalendarURL))
        if default:
            defaultName = str(default.children[0]).rstrip("/").split("/")[-1]
            defaultCalendar = (yield home.calendarWithName(defaultName))
            returnValue(defaultCalendar)
        else:
            # Iterate for the first calendar that supports VEVENTs
            calendars = (yield home.calendars())
            for calendar in calendars:
                if calendar.name() != "inbox" and calendar.isSupportedComponent("VEVENT"):
                    returnValue(calendar)
            else:
                returnValue(None)


    @inlineCallbacks
    def fixByRemovingEvent(self, resid):
        """
        Remove the calendar resource specified by resid - this is a force remove - no implicit
        scheduling is required so we use store apis directly.
        """

        try:
            homeID, calendarID = yield self.getAllResourceInfoForResourceID(resid)
            home = yield self.txn.calendarHomeWithResourceID(homeID)
            calendar = yield home.childWithID(calendarID)
            calendarObj = yield calendar.objectResourceWithID(resid)
            objname = calendarObj.name()
            yield calendar._removeObjectResource(calendarObj)
            yield self.txn.commit()
            self.txn = self.store.newTransaction()
            
            self.results.setdefault("Fix remove", set()).add((home.name(), calendar.name(), objname,))

            returnValue(True)
        except Exception, e:
            print "Failed to remove resource whilst fixing: %d\n%s" % (resid, e,)
            returnValue(False)
        

    def addToSummary(self, title, count, total=None):
        if total is not None:
            percent = safePercent(count, total),
        else:
            percent = ""
        self.summary.append((title, count, percent))


    def addSummaryBreak(self):
        self.summary.append(None)


    def printSummary(self):
        # Print summary of results
        table = tables.Table()
        table.addHeader(("Item", "Count", "%"))
        table.setDefaultColumnFormats(
            (
                tables.Table.ColumnFormat("%s", tables.Table.ColumnFormat.LEFT_JUSTIFY), 
                tables.Table.ColumnFormat("%d", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
                tables.Table.ColumnFormat("%.1f%%", tables.Table.ColumnFormat.RIGHT_JUSTIFY),
            )
        )
        for item in self.summary:
            table.addRow(item)

        if self.totalErrors is not None:
            table.addRow(None)
            table.addRow(("Total Errors", self.totalErrors, safePercent(self.totalErrors, self.total),))
        
        self.output.write("\n")
        self.output.write("Overall Summary:\n")
        table.printTable(os=self.output)


    def printAutoAccepts(self):
        # Print summary of results
        table = tables.Table()
        table.addHeader(("Path", "RID", "UID", "Start Time", "Title"))
        for item in sorted(self.fixedAutoAccepts, key=lambda x:x["path"]):
            table.addRow((
                item["path"],
                item["rid"],
                item["uid"],
                item["start"],
                item["title"],
            ))
        
        self.output.write("\n")
        self.output.write("Auto-Accept Fixes:\n")
        table.printTable(os=self.output)


    @inlineCallbacks
    def getCalendar(self, resid, doFix=False):
        co = schema.CALENDAR_OBJECT
        kwds = { "ResourceID" : resid }
        rows = (yield Select(
            [co.ICALENDAR_TEXT],
            From=co,
            Where=(
                co.RESOURCE_ID == Parameter("ResourceID")
            ),
        ).on(self.txn, **kwds))
        try:
            caldata = PyCalendar.parseText(rows[0][0]) if rows else None
        except PyCalendarError:
            caltxt = rows[0][0] if rows else None
            if caltxt:
                caltxt = caltxt.replace("\r\n ", "")
                if caltxt.find("CALENDARSERVER-OLD-CUA=\"//") != -1:
                    if doFix:
                        caltxt = (yield self.fixBadOldCua(resid, caltxt))
                        try:
                            caldata = PyCalendar.parseText(caltxt) if rows else None
                        except PyCalendarError:
                            self.parseError = "No fix bad CALENDARSERVER-OLD-CUA"
                            returnValue(None)
                    else:
                        self.parseError = "Bad CALENDARSERVER-OLD-CUA"
                        returnValue(None)
            
            self.parseError = "Failed to parse"
            returnValue(None)

        self.parseError = None
        returnValue(caldata)


    @inlineCallbacks
    def getCalendarForOwnerByUID(self, owner, uid):
        co = schema.CALENDAR_OBJECT
        cb = schema.CALENDAR_BIND
        ch = schema.CALENDAR_HOME
        
        kwds = { "OWNER" : owner, "UID": uid }
        rows = (yield Select(
            [co.ICALENDAR_TEXT, co.RESOURCE_ID, co.CREATED, co.MODIFIED,],
            From=ch.join(
                cb, type="inner", on=(ch.RESOURCE_ID == cb.CALENDAR_HOME_RESOURCE_ID)).join(
                co, type="inner", on=(cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                    cb.BIND_MODE == _BIND_MODE_OWN).And(
                    cb.CALENDAR_RESOURCE_NAME != "inbox")),
            Where=(ch.OWNER_UID == Parameter("OWNER")).And(co.ICALENDAR_UID == Parameter("UID")),
        ).on(self.txn, **kwds))

        try:
            caldata = PyCalendar.parseText(rows[0][0]) if rows else None
        except PyCalendarError:
            returnValue((None, None, None, None,))

        returnValue((caldata, rows[0][1], rows[0][2], rows[0][3],) if rows else (None, None, None, None,))


    def masterComponent(self, calendar):
        """
        Return the master iCal component in this calendar.
        @return: the L{Component} for the master component,
            or C{None} if there isn't one.
        """
        for component in calendar.getComponents(definitions.cICalComponent_VEVENT):
            if not component.hasProperty("RECURRENCE-ID"):
                return component
        
        return None

    def buildAttendeeStates(self, calendar, start, end, attendee_only=None):
        # Expand events into instances in the start/end range
        results = []
        calendar.getVEvents(
            PyCalendarPeriod(
                start=start,
                end=end,
            ),
            results
        )
    
        # Need to do iCal fake master fixup
        overrides = len(calendar.getComponents(definitions.cICalComponent_VEVENT)) > 1
    
        # Create map of each attendee's instances with the instance id (start time) and attendee part-stat
        attendees = {}
        for item in results:
            
            # Fake master fixup
            if overrides:
                if not item.getOwner().isRecurrenceInstance():
                    if item.getOwner().getRecurrenceSet() is None or not item.getOwner().getRecurrenceSet().hasRecurrence():
                        continue
    
            # Get Status - ignore cancelled events
            status = item.getOwner().loadValueString(definitions.cICalProperty_STATUS)
            cancelled = status == definitions.cICalProperty_STATUS_CANCELLED
    
            # Get instance start
            item.getInstanceStart().adjustToUTC()
            instance_id = item.getInstanceStart().getText()
            
            props = item.getOwner().getProperties().get(definitions.cICalProperty_ATTENDEE, [])
            for prop in props:
                caladdr = prop.getCalAddressValue().getValue()
                if caladdr.startswith("urn:uuid:"):
                    caladdr = caladdr[9:]
                else:
                    continue
                if attendee_only is not None and attendee_only != caladdr:
                    continue
                if cancelled:
                    partstat = "CANCELLED"
                else:
                    if not prop.hasAttribute(definitions.cICalAttribute_PARTSTAT):
                        partstat = definitions.cICalAttribute_PARTSTAT_NEEDSACTION
                    else:
                        partstat = prop.getAttributeValue(definitions.cICalAttribute_PARTSTAT)
    
                attendees.setdefault(caladdr, set()).add((instance_id, partstat))
                    
        return attendees
    
    
    def allCancelled(self, attendeesStatus):
        # Check whether attendees have all instances cancelled
        all_cancelled = True
        for _ignore_guid, states in attendeesStatus.iteritems():
            for _ignore_instance_id, partstat in states:
                if partstat not in ("CANCELLED", "DECLINED",):
                    all_cancelled = False
                    break
            if not all_cancelled:
                break
        return all_cancelled
       

    def setTransparencyForAttendee(self, calendar, attendee):
        """
        Set the TRANSP property based on the PARTSTAT value on matching ATTENDEE properties
        in each component.
        """
        for component in calendar.subcomponents():
            if component.name() in ignoredComponents:
                continue
            prop = component.getAttendeeProperty(attendee)
            addTransp = False
            if prop:
                partstat = prop.parameterValue("PARTSTAT", "NEEDS-ACTION")
                addTransp = partstat in ("NEEDS-ACTION", "DECLINED",)
            component.replaceProperty(Property("TRANSP", "TRANSPARENT" if addTransp else "OPAQUE"))

    def directoryService(self):
        """
        Get an appropriate directory service for this L{CalVerifyService}'s
        configuration, creating one first if necessary.
        """
        if self._directory is None:
            self._directory = getDirectory(self.config) #directoryFromConfig(self.config)
        return self._directory


    def stopService(self):
        """
        Stop the service.  Nothing to do; everything should be finished by this
        time.
        """
        # TODO: stopping this service mid-export should really stop the export
        # loop, but this is not implemented because nothing will actually do it
        # except hitting ^C (which also calls reactor.stop(), so that will exit
        # anyway).



def main(argv=sys.argv, stderr=sys.stderr, reactor=None):
    """
    Do the export.
    """
    if reactor is None:
        from twisted.internet import reactor
    options = CalVerifyOptions()
    options.parseOptions(argv[1:])
    try:
        output = options.openOutput()
    except IOError, e:
        stderr.write("Unable to open output file for writing: %s\n" % (e))
        sys.exit(1)
    def makeService(store):
        from twistedcaldav.config import config
        config.TransactionTimeoutSeconds = 0
        return CalVerifyService(store, options, output, reactor, config)
    utilityMain(options['config'], makeService, reactor)

if __name__ == '__main__':
    main()
