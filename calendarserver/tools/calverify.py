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

from calendarserver.tap.util import directoryFromConfig
from calendarserver.tools import tables
from calendarserver.tools.cmdline import utilityMain
from pycalendar import definitions
from pycalendar.calendar import PyCalendar
from pycalendar.datetime import PyCalendarDateTime
from pycalendar.exceptions import PyCalendarError
from pycalendar.period import PyCalendarPeriod
from twext.enterprise.dal.syntax import Select, Parameter, Count
from twisted.application.service import Service
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.python import log
from twisted.python.text import wordWrap
from twisted.python.usage import Options
from twistedcaldav.dateops import pyCalendarTodatetime
from twistedcaldav.ical import Component
from twistedcaldav.stdconfig import DEFAULT_CONFIG_FILE
from txdav.common.datastore.sql_tables import schema, _BIND_MODE_OWN
from txdav.common.icommondatastore import InternalDataStoreError
import collections
import os
import sys
import time

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


description = '\n'.join(
    wordWrap(
        """
        Usage: calendarserver_calverify [options] [input specifiers]\n
        """,
        int(os.environ.get('COLUMNS', '80'))
    )
)

class CalVerifyOptions(Options):
    """
    Command-line options for 'calendarserver_calverify'
    """

    synopsis = description

    optFlags = [
        ['ical', 'i', "Calendar data check."],
        ['fix', 'x', "Fix problems."],
        ['missing', 'm', "Show 'orphaned' homes."],
        ['verbose', 'v', "Verbose logging."],
    ]

    optParameters = [
        ['config', 'f', DEFAULT_CONFIG_FILE, "Specify caldavd.plist configuration path."],
        ['data', 'd', "./calverify-data", "Path where ancillary data is stored."],
        ['uuid', 'u', "", "Only check this user."],
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

    def __init__(self, store, options, output, reactor, config):
        super(CalVerifyService, self).__init__()
        self.store   = store
        self.options = options
        self.output  = output
        self.reactor = reactor
        self.config = config
        self._directory = None


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
        try:
            if self.options["missing"]:
                yield self.doOrphans()
            yield self.doScan(self.options["ical"], self.options["fix"])

            self.output.close()
        except:
            log.err()

        self.reactor.stop()


    @inlineCallbacks
    def doOrphans(self):
        """
        Report on home collections for which there are no directory records. 
        """
        print "\n---- Finding calendar homes with no directory record ----"
        self.txn = self.store.newTransaction()

        if self.options["verbose"]:
            t = time.time()
        uids = yield self.getAllHomeUIDs()
        if self.options["verbose"]:
            print "getAllHomeUIDs time: %.1fs" % (time.time() - t,)
        missing = []
        uids_len = len(uids)
        uids_div = 1 if uids_len < 100 else uids_len / 100

        for ctr, uid in enumerate(uids):
            if self.options["verbose"] and divmod(ctr, uids_div)[1] == 0:
                print "%d of %d (%d%%)" % (
                    ctr+1,
                    uids_len,
                    ((ctr+1) * 100 / uids_len),
                )

            if self.directoryService().recordWithGUID(uid[0]) is None:
                contents = yield self.countHomeContents(uid)
                missing.append((uid[0], contents,))
            
            # To avoid holding locks on all the rows scanned, commit every 100 resources
            if divmod(ctr, 100)[1] == 0:
                yield self.txn.commit()
                self.txn = self.store.newTransaction()

        yield self.txn.commit()
        self.txn = None
        
        # Print table of results
        table = tables.Table()
        table.addHeader(("Owner UID", "Calendar Objects"))
        for uid, count in missing:
            table.addRow((
                uid,
                count,
            ))
        
        self.output.write("\n")
        self.output.write("Homes without a matching directory record (total=%d):\n" % (len(missing),))
        table.printTable(os=self.output)
        

    @inlineCallbacks
    def getAllHomeUIDs(self):
        ch = schema.CALENDAR_HOME
        rows = (yield Select(
            [ch.OWNER_UID,],
            From=ch,
        ).on(self.txn))
        returnValue(tuple(rows))


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
    def doScan(self, ical, fix):
        
        print "\n---- Scanning calendar data ----"

        self.start = PyCalendarDateTime.getToday()
        self.start.setDateOnly(False)
        self.end = self.start.duplicate()
        self.end.offsetYear(1)
        self.fix = fix

        self.txn = self.store.newTransaction()

        if self.options["verbose"]:
            t = time.time()
        if ical:
            if self.options["uuid"]:
                rows = yield self.getAllResourceInfoWithUUID(self.options["uuid"])
            else:
                rows = yield self.getAllResourceInfo()
        else:
            rows = yield self.getAllResourceInfoTimeRange(self.start)

        yield self.txn.commit()
        self.txn = None

        if self.options["verbose"]:
            print "getAllResourceInfoTimeRange time: %.1fs" % (time.time() - t,)
        print "Number of events to process: %s" % (len(rows,))
        
        # Split into organizer events and attendee events
        self.organized = []
        self.organized_byuid = {}
        self.attended = []
        self.attended_byuid = collections.defaultdict(list)
        self.matched_attendee_to_organizer = collections.defaultdict(set)
        for owner, resid, uid, md5, organizer in rows:
            if organizer.startswith("urn:uuid:") and owner == organizer[9:]:
                self.organized.append((owner, resid, uid, md5, organizer,))
                self.organized_byuid[uid] = (owner, resid, uid, md5, organizer,)
            else:
                self.attended.append((owner, resid, uid, md5, organizer,))
                self.attended_byuid[uid].append((owner, resid, uid, md5, organizer,))
                
        print "Number of organizer events to process: %s" % (len(self.organized),)
        print "Number of attendee events to process: %s" % (len(self.attended,))

        if ical:
            yield self.calendarDataCheck(rows)
        else:
            yield self.verifyAllAttendeesForOrganizer()
            yield self.verifyAllOrganizersForAttendee()
        
        yield succeed(None)


    @inlineCallbacks
    def getAllResourceInfo(self):
        co = schema.CALENDAR_OBJECT
        cb = schema.CALENDAR_BIND
        ch = schema.CALENDAR_HOME
        kwds = {}
        rows = (yield Select(
            [ch.OWNER_UID, co.RESOURCE_ID, co.ICALENDAR_UID, co.MD5, co.ORGANIZER,],
            From=ch.join(
                cb, type="inner", on=(ch.RESOURCE_ID == cb.CALENDAR_HOME_RESOURCE_ID)).join(
                co, type="inner", on=(cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                    cb.BIND_MODE == _BIND_MODE_OWN).And(
                    cb.CALENDAR_RESOURCE_NAME != "inbox")),
            GroupBy=(ch.OWNER_UID, co.RESOURCE_ID, co.ICALENDAR_UID, co.MD5, co.ORGANIZER,),
        ).on(self.txn, **kwds))
        returnValue(tuple(rows))


    @inlineCallbacks
    def getAllResourceInfoWithUUID(self, uuid):
        co = schema.CALENDAR_OBJECT
        cb = schema.CALENDAR_BIND
        ch = schema.CALENDAR_HOME
        kwds = {"uuid": uuid}
        rows = (yield Select(
            [ch.OWNER_UID, co.RESOURCE_ID, co.ICALENDAR_UID, co.MD5, co.ORGANIZER,],
            From=ch.join(
                cb, type="inner", on=(ch.RESOURCE_ID == cb.CALENDAR_HOME_RESOURCE_ID)).join(
                co, type="inner", on=(cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                    cb.BIND_MODE == _BIND_MODE_OWN).And(
                    cb.CALENDAR_RESOURCE_NAME != "inbox")),
            Where=(ch.OWNER_UID == Parameter("uuid")),
            GroupBy=(ch.OWNER_UID, co.RESOURCE_ID, co.ICALENDAR_UID, co.MD5, co.ORGANIZER,),
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
            [ch.OWNER_UID, co.RESOURCE_ID, co.ICALENDAR_UID, co.MD5, co.ORGANIZER,],
            From=ch.join(
                cb, type="inner", on=(ch.RESOURCE_ID == cb.CALENDAR_HOME_RESOURCE_ID)).join(
                co, type="inner", on=(cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                    cb.BIND_MODE == _BIND_MODE_OWN).And(
                    cb.CALENDAR_RESOURCE_NAME != "inbox").And(
                    co.ORGANIZER != "")).join(
                tr, type="left", on=(co.RESOURCE_ID == tr.CALENDAR_OBJECT_RESOURCE_ID)),
            Where=(tr.START_DATE >= Parameter("Start")).Or(co.RECURRANCE_MAX == Parameter("Max")),
            GroupBy=(ch.OWNER_UID, co.RESOURCE_ID, co.ICALENDAR_UID, co.MD5, co.ORGANIZER,),
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
                    cb.BIND_MODE == _BIND_MODE_OWN).And(
                    cb.CALENDAR_RESOURCE_NAME != "inbox")),
            Where=(co.RESOURCE_ID == Parameter("resid")),
        ).on(self.txn, **kwds))
        returnValue(rows[0])


    @inlineCallbacks
    def calendarDataCheck(self, rows):
        """
        Check each calendar resource for valid iCalendar data.
        """

        print "\n---- Verifying each calendar object resource ----"
        self.txn = self.store.newTransaction()

        if self.options["verbose"]:
            t = time.time()

        results_bad = []
        count = 0
        total = len(rows)
        badlen = 0
        for owner, resid, uid, _ignore_md5, _ignore_organizer in rows:
            result, message = yield self.validCalendarData(resid)
            if not result:
                results_bad.append((owner, uid, resid, message))
                badlen += 1
            count += 1
            if self.options["verbose"]:
                if count == 1:
                    print "Bad/Current/Total"
                if divmod(count, 100)[1] == 0:
                    print "%s/%s/%s" % (badlen, count, total,)
            
            # To avoid holding locks on all the rows scanned, commit every 100 resources
            if divmod(count, 100)[1] == 0:
                yield self.txn.commit()
                self.txn = self.store.newTransaction()

        yield self.txn.commit()
        self.txn = None
        
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
         
        if self.options["verbose"]:
            diff_time = time.time() - t
            print "Time: %.2f s  Average: %.1f ms/resource" % (
                diff_time,
                (1000.0 * diff_time) / total,
            )

    errorPrefix = "Calendar data had unfixable problems:\n  "

    @inlineCallbacks
    def validCalendarData(self, resid):
        """
        Check the calendar resource for valid iCalendar data.
        """

        caldata = yield self.getCalendar(resid)
        if caldata is None:
            returnValue((False, "Failed to parse"))

        component = Component(None, pycalendar=caldata)
        result = True
        message = ""
        try:
            component.validCalendarData(doFix=False, validateRecurrences=True)
            component.validCalendarForCalDAV(methodAllowed=False)
            component.validOrganizerForScheduling(doFix=False)
        except ValueError, e:
            result = False
            message = str(e)
            if message.startswith(self.errorPrefix):
                message = message[len(self.errorPrefix):]
            lines = message.splitlines()
            message = lines[0] + (" ++" if len(lines) > 1 else "")
            if self.fix:
                fixresult, fixmessage = yield self.fixCalendarData(resid)
                if fixresult:
                    message = "Fixed: " + message
                else:
                    message = fixmessage + message

        returnValue((result, message,))


    @inlineCallbacks
    def fixCalendarData(self, resid):
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
            component.validCalendarData(doFix=True, validateRecurrences=True)
            component.validCalendarForCalDAV(methodAllowed=False)
            component.validOrganizerForScheduling(doFix=True)
        except ValueError:
            result = False
            message = "Failed fix: "
        
        if result:
            # Write out fix, commit and get a new transaction
            component = yield calendarObj.setComponent(component)
            #yield self.txn.commit()
            #self.txn = self.store.newTransaction()

        returnValue((result, message,))


    @inlineCallbacks
    def verifyAllAttendeesForOrganizer(self):
        """
        Make sure that for each organizer, each referenced attendee has a consistent view of the organizer's event.
        We will look for events that an organizer has and are missing for the attendee, and events that an organizer's
        view of attendee status does not match the attendee's view of their own status.
        """
        
        print "\n---- Verifying Organizer events against Attendee copies ----"
        self.txn = self.store.newTransaction()

        results_missing = []
        results_mismatch = []
        attendeeResIDs = {}
        organized_len = len(self.organized)
        organizer_div = 1 if organized_len < 100 else organized_len / 100

        # Test organized events
        for ctr, organizerEvent in enumerate(self.organized):
            
            if self.options["verbose"] and divmod(ctr, organizer_div)[1] == 0:
                print "%d of %d (%d%%) Missing: %d  Mismatched: %s" % (
                    ctr+1,
                    organized_len,
                    ((ctr+1) * 100 / organized_len),
                    len(results_missing),
                    len(results_mismatch),
                )

            # To avoid holding locks on all the rows scanned, commit every 100 resources
            if divmod(ctr, 100)[1] == 0:
                yield self.txn.commit()
                self.txn = self.store.newTransaction()

            # Get the organizer's view of attendee states            
            organizer, resid, uid, _ignore_md5, _ignore_organizer = organizerEvent
            calendar = yield self.getCalendar(resid)
            if calendar is None:
                continue
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
            for attendeeEvent in self.attended_byuid.get(uid, ()):
                owner, resid, uid, _ignore_md5, _ignore_organizer = attendeeEvent
                calendar = yield self.getCalendar(resid)
                if calendar is None:
                    continue
                eachAttendeesOwnStatus[owner] = self.buildAttendeeStates(calendar, self.start, self.end, attendee_only=owner)
                attendeeResIDs[(owner, uid)] = resid
            
            # Look at each attendee in the organizer's meeting
            for organizerAttendee, organizerViewOfStatus in organizerViewOfAttendees.iteritems():
                broken = False

                self.matched_attendee_to_organizer[uid].add(organizerAttendee)
                
                attendeeRecord = self.directoryService().recordWithGUID(organizerAttendee)
                if attendeeRecord is None or not attendeeRecord.thisServer():
                    continue

                # If an entry for the attendee exists, then check whether attendee status matches
                if organizerAttendee in eachAttendeesOwnStatus:
                    attendeeOwnStatus = eachAttendeesOwnStatus[organizerAttendee].get(organizerAttendee, set())

                    if organizerViewOfStatus != attendeeOwnStatus:
                        # Check that the difference is only cancelled or declined on the organizers side
                        for _ignore_organizerInstance, partstat in organizerViewOfStatus.difference(attendeeOwnStatus):
                            if partstat not in ("DECLINED", "CANCELLED"):
                                results_mismatch.append((uid, resid, organizer, organizerAttendee))
                                broken = True
                                break
                        # Check that the difference is only cancelled on the attendees side
                        for _ignore_attendeeInstance, partstat in attendeeOwnStatus.difference(organizerViewOfStatus):
                            if partstat not in ("CANCELLED",):
                                if not broken:
                                    results_mismatch.append((uid, resid, organizer, organizerAttendee))
                                broken = True
                                break

                # Check that the status for this attendee is always declined which means a missing copy of the event is OK
                else:
                    for _ignore_instance_id, partstat in organizerViewOfStatus:
                        if partstat not in ("DECLINED", "CANCELLED"):
                            results_missing.append((uid, resid, organizer, organizerAttendee,))
                            broken = True
                            break
                
                # If there was a problem we can fix it
                if broken and self.fix:
                    # TODO: This is where we attempt a fix
                    #self.fixEvent(organizer, organizerAttendee, eventpath, attendeePaths.get(organizerAttendee, None))
                    pass

        yield self.txn.commit()
        self.txn = None
                
        # Print table of results
        table = tables.Table()
        table.addHeader(("Organizer", "Attendee", "Event UID", "Organizer RID",))
        for item in results_missing:
            uid, resid, organizer, attendee = item
            organizer_record = self.directoryService().recordWithGUID(organizer)
            attendee_record = self.directoryService().recordWithGUID(attendee)
            table.addRow((
                "%s/%s (%s)" % (organizer_record.recordType if organizer_record else "-", organizer_record.shortNames[0] if organizer_record else "-", organizer,),
                "%s/%s (%s)" % (attendee_record.recordType if attendee_record else "-", attendee_record.shortNames[0] if attendee_record else "-", attendee,),
                uid,
                resid,
            ))
        
        self.output.write("\n")
        self.output.write("Events missing from Attendee's calendars (total=%d):\n" % (len(results_missing),))
        table.printTable(os=self.output)
            
        # Print table of results
        table = tables.Table()
        table.addHeader(("Organizer", "Attendee", "Event UID", "Organizer RID", "Attendee RID",))
        for item in results_mismatch:
            uid, org_resid, organizer, attendee = item
            organizer_record = self.directoryService().recordWithGUID(organizer)
            attendee_record = self.directoryService().recordWithGUID(attendee)
            table.addRow((
                "%s/%s (%s)" % (organizer_record.recordType if organizer_record else "-", organizer_record.shortNames[0] if organizer_record else "-", organizer,),
                "%s/%s (%s)" % (attendee_record.recordType if attendee_record else "-", attendee_record.shortNames[0] if attendee_record else "-", attendee,),
                uid,
                org_resid,
                attendeeResIDs[(attendee, uid)],
            ))
        
        self.output.write("\n")
        self.output.write("Events mismatched between Organizer's and Attendee's calendars (total=%d):\n" % (len(results_mismatch),))
        table.printTable(os=self.output)


    @inlineCallbacks
    def verifyAllOrganizersForAttendee(self):
        """
        Make sure that for each attendee, there is a matching event for the organizer.
        """

        print "\n---- Verifying Attendee events against Organizer copies ----"
        self.txn = self.store.newTransaction()

        # Now try to match up each attendee event
        missing = []
        mismatched = []
        attended_len = len(self.attended)
        attended_div = 1 if attended_len < 100 else attended_len / 100

        for ctr, attendeeEvent in enumerate(self.attended):
            
            if self.options["verbose"] and divmod(ctr, attended_div)[1] == 0:
                print "%d of %d (%d%%) Missing: %d  Mismatched: %s" % (
                    ctr+1,
                    attended_len,
                    ((ctr+1) * 100 / attended_len),
                    len(missing),
                    len(mismatched),
                )

            # To avoid holding locks on all the rows scanned, commit every 100 resources
            if divmod(ctr, 100)[1] == 0:
                yield self.txn.commit()
                self.txn = self.store.newTransaction()

            attendee, resid, uid, _ignore_md5, organizer = attendeeEvent
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

            organizerRecord = self.directoryService().recordWithGUID(organizer)
            if organizerRecord is None or not organizerRecord.thisServer():
                continue

            if uid not in self.organized_byuid:

                # Check whether attendee has all instances cancelled
                if self.allCancelled(eachAttendeesOwnStatus):
                    continue
                
                missing.append((uid, attendee, organizer, resid,))
                
                # If there is a miss we fix by removing the attendee data
                if self.fix:
                    # TODO: This is where we attempt a fix
                    pass

            elif attendee not in self.matched_attendee_to_organizer[uid]:
                # Check whether attendee has all instances cancelled
                if self.allCancelled(eachAttendeesOwnStatus):
                    continue

                mismatched.append((uid, attendee, organizer, resid,))
                
                # If there is a mismatch we fix by re-inviting the attendee
                if self.fix:
                    # TODO: This is where we attempt a fix
                    pass

        yield self.txn.commit()
        self.txn = None

        # Print table of results
        table = tables.Table()
        table.addHeader(("Organizer", "Attendee", "UID", "Attendee RID",))
        missing.sort()
        unique_set = set()
        for item in missing:
            uid, attendee, organizer, resid = item
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
            ))
        
        self.output.write("\n")
        self.output.write("Attendee events missing in Organizer's calendar (total=%d, unique=%d):\n" % (len(missing), len(unique_set),))
        table.printTable(os=self.output)

        # Print table of results
        table = tables.Table()
        table.addHeader(("Organizer", "Attendee", "UID", "Organizer RID", "Attendee RID",))
        mismatched.sort()
        for item in mismatched:
            uid, attendee, organizer, resid = item
            if organizer:
                organizerRecord = self.directoryService().recordWithGUID(organizer)
                organizer = "%s/%s (%s)" % (organizerRecord.recordType if organizerRecord else "-", organizerRecord.shortNames[0] if organizerRecord else "-", organizer,)
            attendeeRecord = self.directoryService().recordWithGUID(attendee)
            table.addRow((
                organizer,
                "%s/%s (%s)" % (attendeeRecord.recordType if attendeeRecord else "-", attendeeRecord.shortNames[0] if attendeeRecord else "-", attendee,),
                uid,
                self.organized_byuid[uid][1],
                resid,
            ))
        
        self.output.write("\n")
        self.output.write("Attendee events mismatched in Organizer's calendar (total=%d):\n" % (len(mismatched),))
        table.printTable(os=self.output)


    @inlineCallbacks
    def getCalendar(self, resid):
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
            caldata = None
        returnValue(caldata)


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
                if partstat not in ("CANCELLED",):
                    all_cancelled = False
                    break
            if not all_cancelled:
                break
        return all_cancelled
       

    def directoryService(self):
        """
        Get an appropriate directory service for this L{CalVerifyService}'s
        configuration, creating one first if necessary.
        """
        if self._directory is None:
            self._directory = directoryFromConfig(self.config)
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
        return CalVerifyService(store, options, output, reactor, config)
    utilityMain(options['config'], makeService, reactor)

if __name__ == '__main__':
    main()
