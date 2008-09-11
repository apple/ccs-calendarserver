##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
iTIP (RFC2446) processing.
"""

#
# This is currently used for handling auto-replies to schedule requests arriving
# in an inbox. It is called in a delayed fashion via reactor.callLater.
#
# We assume that all the components/calendars we deal with have been determined
# as being 'valid for CalDAV/iTIP', i.e. they contain UIDs, single component
# types, etc.
#
# The logic for component matching needs a lot more work as it currently does not
# know how to deal with overridden instances.
#

import datetime
import md5
import time

from twisted.python.failure import Failure
from twisted.internet.defer import inlineCallbacks, returnValue, maybeDeferred,\
    succeed
from twisted.web2.dav import davxml
from twisted.web2.dav.method.report import NumberOfMatchesWithinLimits
from twisted.web2.dav.util import joinURL
from twisted.web2.dav.fileop import delete
from twisted.web2.dav.resource import AccessDeniedError

from twistedcaldav import caldavxml
from twistedcaldav.accounting import accountingEnabled, emitAccounting
from twistedcaldav.log import Logger
from twistedcaldav.ical import Property
from twistedcaldav.memcachelock import MemcacheLock, MemcacheLockTimeoutError
from twistedcaldav.method import report_common
from twistedcaldav.resource import isCalendarCollectionResource

log = Logger()

__version__ = "0.0"

__all__ = [
    "iTipProcessor",
    "iTipGenerator",
]

class iTipException(Exception):
    pass

class iTipProcessor(object):
    
    @inlineCallbacks
    def handleRequest(self, request, principal, inbox, calendar, child):
        """
        Handle an iTIP response automatically.
    
        @param request: the L{twisted.web2.server.Request} for the current request.
        @param principal: the L{CalendarPrincipalFile} principal resource for the principal we are dealing with.
        @param inbox: the L{ScheduleInboxFile} for the principal's Inbox.
        @param calendar: the L{Component} for the iTIP message we are processing.
        @param child: the L{CalDAVFile} for the iTIP message resource already saved to the Inbox.
        @return: L{Deferred}
        """
        
        method = calendar.propertyValue("METHOD")
        if method == "REQUEST":
            f = self.processRequest
        elif method == "ADD":
            f = self.processAdd
        elif method == "CANCEL":
            f = self.processCancel

        self.request = request
        self.principal = principal
        self.inbox = inbox
        self.calendar = calendar
        self.child = child
        if self.child:
            self.childname = self.child.fp.basename()
        else:
            self.childname = ""
 
        # Get a lock on the inbox first
        _lock = MemcacheLock("iTIPAutoProcess", inbox.fp.path, timeout=60.0, retry_interval=1.0, expire_time=300)
        
        try:
            yield _lock.acquire()
            yield f()
            yield _lock.release()
        except MemcacheLockTimeoutError:
            raise
        except Exception, e:
            log.error(e)
            yield _lock.clean()
            raise

    @inlineCallbacks
    def processRequest(self):
        """
        Process a METHOD=REQUEST.
    
        Steps:
        
          1. See if this updates existing ones in Inbox.
              1. If so,
                  1. Remove existing ones in Inbox.
                  2. See if this updates existing ones in free-busy-set calendars.
                  3. Remove existing ones in those calendars.
                  4. See if this fits into a free slot:
                      1. If not, add to f-b-s calendar DECLINED
                      2. If so, add to f-b-s calendar ACCEPTED
              2. If not,
                  1. remove the one we got - its 'stale'
              3. Delete the request from the Inbox.
        
        """
        
        log.info("Auto-processing iTIP REQUEST for: %s" % (str(self.principal),))
        processed = "ignored"
    
        # First determine whether this is a full or partial update. A full update is one containing the master
        # component in a recurrence set (or non-recurring event). Partial is one where overridden instances only are
        # being changed.
        
        new_master = self.calendar.masterComponent()
    
        # Next we want to try and find a match to any components on existing calendars listed as contributing
        # to free-busy as we will need to update those with the new one.
        calmatch, updatecal, calURL = yield self.findCalendarMatch()
        
        if new_master:
            # So we have a full update. That means we need to delete any existing events completely and
            # replace with the ones provided so long as the new one is newer.
            
            # If we have a match then we need to check whether we are updating etc
            check_reply = False
            if calmatch:
                # See whether the new component is older than any existing ones and throw it away if so
                newinfo = (None,) + self.getComponentSyncInfo(new_master)
                cal = updatecal.iCalendar(calmatch)
                info = self.getSyncInfo(calmatch, cal)
                if self.compareSyncInfo(info, newinfo) < 0:
                    # Existing resource is older and will be replaced
                    check_reply = True
                else:
                    processed = "older"
            else:
                # We have a new request which we can reply to
                check_reply = True
                
            if check_reply:
                # Process the reply by determining PARTSTAT and sending the reply and booking the event.
                valid, accepted = yield self.checkForReply()
                
                if valid:
                    try:
                        if calmatch:
                            log.info("Replaced calendar component %s with new iTIP message in %s (%s)." % (calmatch, calURL, accepted,))
                            yield self.writeResource(calURL, updatecal, calmatch, self.calendar)
                        else:
                            log.info("Added new calendar component in %s (%s)." % (calURL, accepted,))
                            yield self.writeResource(calURL, updatecal, None, self.calendar)
    
                        processed = "processed"
                    except:
                        # FIXME: bare except
                        log.err("Error while auto-processing iTIP: %s" % (Failure(),))
                        raise iTipException()
                else:
                    processed = "ignored"
                
        else:
            # So we have a partial update. That means we have to do partial updates to instances in
            # the existing calendar component.
    
            # If we have a match then we need to check whether we are updating etc
            check_reply = False
            if calmatch:
                # Check each component to see whether its new
                cal = updatecal.iCalendar(calmatch)
                old_master = cal.masterComponent()
                processed = "older"
                new_components = [component for component in self.calendar.subcomponents()]
                for component in new_components:
                    if component.name() == "VTIMEZONE":
                        continue
                    
                    newinfo = (None,) + self.getComponentSyncInfo(component)
                    old_component = self.findMatchingComponent(component, cal)
                    if old_component:
                        info = (None,) + self.getComponentSyncInfo(old_component)
                    elif old_master:
                        info = (None,) + self.getComponentSyncInfo(old_master)
                    else:
                        info = None
                        
                    if info is None or self.compareSyncInfo(info, newinfo) < 0:
                        # Existing resource is older and will be replaced
                        check_reply = True
                        processed = "processed"
                    else:
                        self.calendar.removeComponent(component)
            else:
                # We have a new request which we can reply to
                check_reply = True
    
            if check_reply:
                # Process the reply by determining PARTSTAT and sending the reply and booking the event.
                valid, accepted = yield self.checkForReply()
                
                if valid:
                    try:
                        if calmatch:
                            # Merge the new instances with the old ones
                            self.mergeComponents(self.calendar, cal)
                            log.info("Merged calendar component %s with new iTIP message in %s (%s)." % (calmatch, calURL, accepted,))
                            yield self.writeResource(calURL, updatecal, calmatch, cal)
                        else:
                            log.info("Added new calendar component in %s (%s)." % (calURL, accepted,))
                            yield self.writeResource(calURL, updatecal, None, self.calendar)
                            
                        processed = "processed"
                    except:
                        # FIXME: bare except
                        log.err("Error while auto-processing iTIP: %s" % (Failure(),))
                        raise iTipException()
                else:
                    processed = "ignored"
    
        # Remove the now processed incoming request.
        if self.inbox:
            yield self.deleteInboxResource({
                "processed":"processed",
                "older":    "ignored: older",
                "ignored":  "ignored: no match"
            }[processed])

        returnValue(None)

    def processAdd(self):
        """
        Process a METHOD=ADD.
        """
        log.info("Auto-processing iTIP ADD for: %s" % (str(self.principal),))
    
        raise NotImplementedError()
    
    @inlineCallbacks
    def processCancel(self):
        """
        Process a METHOD=CANCEL.
    
        Policy find all components that match UID, SEQ and R-ID and remove them.
    
        Steps:
        
            1. See if this updates existing ones in Inbox.
            2. Remove existing ones in Inbox.
            3. See if this updates existing ones in free-busy-set calendars.
            4. Remove existing ones in those calendars.
            5. Remove the incoming request.
    
        NB Removal can be complex as we need to take RECURRENCE-ID into account - i.e a single
        instance may be cancelled. What we need to do for this is:
        
            1. If the R-ID of iTIP component matches the R-ID of one in Inbox then it is an exact match, so
               delete the old one.
            2. If the R-ID of iTIP does not match an R-ID in Inbox, then we are adding a cancellation as an override, so
               leave the new and existing ones in the Inbox.
            3. If the R-ID of iTIP component matches the R-ID of an overridden component in an f-b-s calendar, then
               remove the overridden component from the f-b-s resource.
            4. Add an EXDATE to the f-b-s resource to 'cancel' that instance.
        
        TODO: Yes, I am going to ignore RANGE= on RECURRENCE-ID for now...
        """
        
        log.info("Auto-processing iTIP CANCEL for: %s" % (str(self.principal),))
        processed = "ignored"
    
        # Get all component info for this iTIP message
        newinfo = self.getSyncInfo(self.childname, self.calendar)
    
        # First see if we have a recurrence id which will force extra work
        has_rid = False
        if newinfo[4] is not None:
            has_rid = True
        else:
            for i in self.getAllInfo(self.inbox, self.calendar, self.child):
                if i[4] is not None:
                    has_rid = True
                    break
                
        # Next we want to try and find a match to any components on existing calendars listed as contributing
        # to free-busy as we will need to update those with the new one.
        calmatch, updatecal, calURL = yield self.findCalendarMatch()
        
        if not has_rid:
            # If we have a match then we need to check whether we are updating etc
            if calmatch:
                # See whether the current component is older than any existing ones and throw it away if so
                cal = updatecal.iCalendar(calmatch)
                info = self.getSyncInfo(calmatch, cal)
                if self.compareSyncInfo(info, newinfo) < 0:
                    # Delete existing resource which has been cancelled
                    try:
                        log.info("Delete calendar component %s in %s as it was cancelled." % (calmatch, calURL))
                        yield self.deleteResource(updatecal, calmatch,)
                    except:
                        # FIXME: bare except
                        log.err("Error while auto-processing iTIP: %s" % (Failure(),))
                        raise iTipException()
                    processed = "processed"
                else:
                    processed = "older"
            else:
                # Nothing to do except delete the inbox item as we have nothing to cancel.
                processed = "ignored"
        else:
            # If we have a match then we need to check whether we are updating etc
            if calmatch:
                # iTIP CANCEL can contain multiple components being cancelled in the RECURRENCE-ID case.
                # So we need to iterate over each iTIP component.
    
                # Get the existing calendar object
                existing_calendar = updatecal.iCalendar(calmatch)
                existing_master = existing_calendar.masterComponent()
                exdates = []
    
                for component in self.calendar.subcomponents():
                    if component.name() == "VTIMEZONE":
                        continue
                
                    # Find matching component in existing calendar
                    old_component = self.findMatchingComponent(component, existing_calendar)
                    
                    if old_component:
                        # We are cancelling an overridden component, so we need to check the
                        # SEQUENCE/DTSAMP with the master.
                        if self.compareComponents(old_component, component) < 0:
                            # Exclude the cancelled instance
                            exdates.append(component.getRecurrenceIDUTC())
                            
                            # Remove the existing component.
                            existing_calendar.removeComponent(old_component)
                    elif existing_master:
                        # We are trying to CANCEL a non-overridden instance, so we need to
                        # check SEQUENCE/DTSTAMP with the master.
                        if self.compareComponents(existing_master, component) < 0:
                            # Exclude the cancelled instance
                            exdates.append(component.getRecurrenceIDUTC())
    
                # If we have any EXDATEs lets add them to the existing calendar object and write
                # it back.
                if exdates:
                    if existing_master:
                        existing_master.addProperty(Property("EXDATE", exdates))
    
                    # See if there are still components in the calendar - we might have deleted the last overridden instance
                    # in which case the calendar object is empty (except for VTIMEZONEs).
                    if existing_calendar.mainType() is None:
                        # Delete the now empty calendar object
                        log.info("Deleted calendar component %s after cancellations from iTIP message in %s." % (calmatch, calURL))
                        yield self.deleteResource(updatecal, calmatch)
                    else:
                        # Update the existing calendar object
                        log.info("Updated calendar component %s with cancellations from iTIP message in %s." % (calmatch, calURL))
                        yield self.writeResource(calURL, updatecal, calmatch, existing_calendar)
                    processed = "processed"
                else:
                    processed = "older"
            else:
                # Nothing to do except delete the inbox item as we have nothing to cancel.
                processed = "ignored"
    
        # Remove the now processed incoming request.
        if self.inbox:
            yield self.deleteInboxResource({
                "processed":"processed",
                "older":    "ignored: older",
                "ignored":  "ignored: no match"
            }[processed])

        returnValue(None)
    
    @inlineCallbacks
    def checkForReply(self):
        """
        Check whether a reply to the given iTIP message is needed. We will not process a reply
        if RSVP=FALSE. A reply will either be positive (accepted
        invitation) or negative (denied invitation). In addition we will modify calendar to reflect
        any new state (e.g. remove RSVP, set PARTSTAT to ACCEPTED or DECLINED).
        
        BTW The incoming iTIP message may contain multiple components so we need to iterate over all those.
        At the moment we will treat a failure on one instance as a DECLINE of the entire set.

        @return: a C{tuple} of C{bool} indicating whether a valid iTIP was received, and C{str} new partstat.
        """
        
        # We need to figure out whether the specified component will clash with any others in the f-b-set calendars
        accepted = True
            
        # First expand current one to get instances (only go 1 year into the future)
        default_future_expansion_duration = datetime.timedelta(days=356*1)
        expand_max = datetime.date.today() + default_future_expansion_duration
        instances = self.calendar.expandTimeRanges(expand_max)
        
        # Extract UID from primary component as we want to ignore this one if we match it
        # in any calendars.
        comp = self.calendar.mainComponent(allow_multiple=True)
        uid = comp.propertyValue("UID")
    
        # Now compare each instance time-range with the index and see if there is an overlap
        calendars = yield self.getCalendarsToMatch()
    
        for calURL in calendars:
            testcal = yield self.request.locateResource(calURL)
            
            # First list is BUSY, second BUSY-TENTATIVE, third BUSY-UNAVAILABLE
            fbinfo = ([], [], [])
            
            # Now do search for overlapping time-range
            for instance in instances.instances.itervalues():
                try:
                    tr = caldavxml.TimeRange(start="20000101", end="20000101")
                    tr.start = instance.start
                    tr.end = instance.end
                    yield report_common.generateFreeBusyInfo(self.request, testcal, fbinfo, tr, 0, uid)
                    
                    # If any fbinfo entries exist we have an overlap
                    if len(fbinfo[0]) or len(fbinfo[1]) or len(fbinfo[2]):
                        accepted = False
                        break
                except NumberOfMatchesWithinLimits:
                    accepted = False
                    log.info("Exceeded number of matches whilst trying to find free-time.")
                    break
                
            if not accepted:
                break
         
        # Extract the ATTENDEE property matching current recipient from the calendar data
        cuas = self.principal.calendarUserAddresses()
        attendeeProps = self.calendar.getAttendeeProperties(cuas)
        if not attendeeProps:
            returnValue((False, "",))
    
        if accepted:
            partstat = "ACCEPTED"
        else:
            partstat = "DECLINED"
            
            # Make sure declined events are TRANSPARENT on the calendar
            self.calendar.replacePropertyInAllComponents(Property("TRANSP", "TRANSPARENT"))

        for attendeeProp in attendeeProps:
            attendeeProp.params()["PARTSTAT"] = [partstat]
        
        returnValue((True, partstat,))
    
    @inlineCallbacks
    def writeReply(self, replycal):
        """
        Write an iTIP message reply into the specified Inbox.

        @param replycal: the L{Component} for the iTIP message reply.
        """
        
        # Get the Inbox of the ORGANIZER
        organizer = replycal.getOrganizer()
        assert organizer is not None
        inboxURL = self.inbox.principalForCalendarUserAddress(organizer).scheduleInboxURL()
        assert inboxURL
        
        # Determine whether current principal has CALDAV:schedule right on that Inbox
        writeinbox = yield self.request.locateResource(inboxURL)
    
        try:
            yield writeinbox.checkPrivileges(self.request, (caldavxml.Schedule(),), principal=davxml.Principal(davxml.HRef.fromString(self.principal.principalURL())))
        except AccessDeniedError:
            log.info("Could not send reply as %s does not have CALDAV:schedule permission on %s Inbox." % (self.principal.principalURL(), organizer))
            returnValue(None)
        
        # Now deposit the new calendar into the inbox
        newchild = yield self.writeResource(inboxURL, writeinbox, None, replycal)

        self.newInboxResource(self.child, newchild)
        
        if accountingEnabled("iTIP", self.principal):
            emitAccounting(
                "iTIP", self.principal,
                "Originator: %s\nRecipients: %s\n\n%s"
                % (self.principal.principalURL(), organizer, str(replycal))
            )

        returnValue(newchild)
    
    @inlineCallbacks
    def writeResource(self, collURL, collection, name, calendar):
        """
        Write out the calendar resource (iTIP) message to the specified calendar, either over-writing the named
        resource or by creating a new one.
        
        @param collURL: the C{str} containing the URL of the calendar collection.
        @param collection: the L{CalDAVFile} for the calendar collection to store the resource in.
        @param name: the C{str} for the resource name to write into, or {None} to write a new resource.
        @param calendar: the L{Component} calendar to write.
        @return: C{tuple} of L{Deferred}, L{CalDAVFile}
        """
        
        # Create a new name if one was not provided
        if name is None:
            name =  md5.new(str(calendar) + str(time.time()) + collection.fp.path).hexdigest() + ".ics"
    
        # Get a resource for the new item
        newchildURL = joinURL(collURL, name)
        newchild = yield self.request.locateResource(newchildURL)
        
        # Modify the original calendar data by removing the METHOD property - everything else is left as-is,
        # as any other needed changes (e.g. RSVP/PARTSTAT) will have been updated.
        # NB Only do this when writing to something other than an Inbox or Outbox
        itipper = True
        if collection.isCalendarCollection():
            method = calendar.getProperty("METHOD")
            if method:
                calendar.removeProperty(method)
            itipper = False
        
        # Now write it to the resource
        from twistedcaldav.method.put_common import StoreCalendarObjectResource
        yield StoreCalendarObjectResource(
                     request=self.request,
                     destination = newchild,
                     destination_uri = newchildURL,
                     destinationparent = collection,
                     destinationcal = True,
                     calendar = calendar,
                     isiTIP = itipper,
                     internal_request=True,
                 ).run()
        
        returnValue(newchild)
    
    def newInboxResource(self, child, newchild):
        """
        Copy recipient and organizer properties from one iTIP resource, to another,
        switching them as appropriate for a reply, and also set the state.
        
        @param child: the L{CalDAVFile} for the original iTIP message.
        @param newchild: the L{CalDAVFile} for the iTIP message reply.
        """
        # Make previous Recipient the new Originator
        if child.hasDeadProperty(caldavxml.Recipient):
            recip = child.readDeadProperty(caldavxml.Recipient)
            if recip.children:
                # Store CALDAV:originator property
                newchild.writeDeadProperty(caldavxml.Originator(davxml.HRef.fromString(str(recip.children[0]))))
        
        # Make previous Originator the new Recipient
        if child.hasDeadProperty(caldavxml.Originator):
            orig = child.readDeadProperty(caldavxml.Originator)
            if orig.children:
                # Store CALDAV:originator property
                newchild.writeDeadProperty(caldavxml.Recipient(davxml.HRef.fromString(str(orig.children[0]))))
    
    @inlineCallbacks
    def deleteInboxResource(self, processed_state):
        # Remove the now processed incoming request.
        try:
            log.info("Deleting new iTIP message %s in Inbox because it has been %s." %
                (self.childname, processed_state,))
            yield self.deleteResource(self.inbox, self.childname)
        except:
            # FIXME: bare except
            log.err("Error while auto-processing iTIP: %s" % (Failure(),))
            raise iTipException()

    def deleteResource(self, collection, name):
        """
        Delete the calendar resource in the specified calendar.
        
        @param collection: the L{CalDAVFile} for the calendar collection to store the resource in.
        @param name: the C{str} for the resource name to write into, or {None} to write a new resource.
        @return: L{Deferred}
        """
        
        delchild = collection.getChild(name)
        
        # Sometimes the resource might already be gone...
        if delchild is None:
            log.warn("Nothing to delete: %s in %s is missing." % (name, collection))
            return succeed(None)

        index = collection.index()
        index.deleteResource(delchild.fp.basename())
        
        def _deletedResourced(result):
            # Change CTag on the parent calendar collection
            return collection.updateCTag().addCallback(lambda _: result)
    
        d = maybeDeferred(delete, "", delchild.fp, "0")
        d.addCallback(_deletedResourced)
        return d
    
    @staticmethod
    def canAutoRespond(calendar):
        """
        Check whether the METHOD of this iTIP calendar object is one we can process. Also,
        we will only handle VEVENTs right now.
    
        @param calendar: L{Component} for calendar to examine.
        @return: C{True} if we can auto-respond, C{False} if not.
        """
    
        try:
            method = calendar.propertyValue("METHOD")
            if method not in ("REQUEST", "ADD", "CANCEL"):
                return False
            if calendar.mainType() not in ("VEVENT"):
                return False
        except ValueError:
            return False
        
        return True
    
    @inlineCallbacks
    def findCalendarMatch(self):
        # Try and find a match to any components on existing calendars listed as contributing
        # to free-busy as we will need to update those with the new one.
        
        # Find the current recipients calendar-free-busy-set
        calendars = yield self.getCalendarsToMatch()
    
        # Find the first calendar in the list with a component matching the one we are processing
        calmatch = None
        updatecal = None
        calURL = None
        for calURL in calendars:
            updatecal = yield self.request.locateResource(calURL)
            if updatecal is None or not updatecal.exists() or not isCalendarCollectionResource(updatecal):
                # We will ignore missing calendars. If the recipient has failed to
                # properly manage the free busy set that should not prevent us from working.
                continue
            calmatch = self.matchComponentInCalendar(updatecal, self.calendar)
            if calmatch:
                log.info("Found calendar component %s matching new iTIP message in %s." % (calmatch, calURL))
                break
        
        if calmatch is None and len(calendars):
            calURL = calendars[0]
            updatecal = yield self.request.locateResource(calURL)
    
        returnValue((calmatch, updatecal, calURL))
    
    def getCalendarsToMatch(self):
        # Determine the set of calendar URIs for a principal need to be searched.
        
        # Find the current recipients calendar-free-busy-set
        return self.principal.calendarFreeBusyURIs(self.request)

    def matchComponentInCalendar(self, collection, calendar):
        """
        See if the component in the provided iTIP calendar object matches any in the specified calendar
        collection.
        
        @param collection: L{CalDAVFile} for the calendar collection to examine.
        @param calendar: L{Component} for calendar to examine.
        @return: C{list} of resource names found.
        """
    
        try:
            # Extract UID from primary component (note we allow multiple components to be present
            # because CANCEL requests can have multiple components).
            comp = calendar.mainComponent(allow_multiple=True)
            uid = comp.propertyValue("UID")
            
            # Now use calendar collection index to find all other resources with the same UID
            index = collection.index()
            result = index.resourceNamesForUID(uid)
            
            # There can be only one
            if len(result) > 0: 
                return result[0]
            else:
                return None
        except ValueError:
            return None
    
    def findMatchingComponent(self, component, calendar):
        """
        See if any overridden component in the provided iTIP calendar object matches the specified component.
        
        @param component: the component to try and match.
        @type component: L{Component}
        @param calendar: the calendar to find a match in.
        @type calendar: L{Component}
        @return: L{Component} for matching component,
            or C{None} if not found.
        """
    
        # Extract RECURRENCE-ID value from component
        rid = component.getRecurrenceIDUTC()
        
        # Return the one that matches in the calendar
        return calendar.overriddenComponent(rid)
    
    def mergeComponents(self, newcal, oldcal):
        """
        Merge the overridden instance components in newcal into oldcal replacing any
        matching components there.
    
        @param newcal: the new overridden instances to use.
        @type newcal: L{Component}
        @param oldcal: the component to merge into.
        @type oldcal: L{Component}
        """
        
        # FIXME: going to ignore VTIMEZONE - i.e. will assume that the component being added
        # use a TZID that is already specified in the old component set.
    
        # We will update the SEQUENCE on the master to the highest value of the current one on the master
        # or the ones in the components we are changing.
    
        for component in newcal.subcomponents():
            if component.name() == "VTIMEZONE":
                continue
            
            rid = component.getRecurrenceIDUTC()
            old_component = oldcal.overriddenComponent(rid)
            if old_component:
                oldcal.removeComponent(old_component)
            oldcal.addComponent(component)
    
    def getAllInfo(self, collection, calendar, ignore):
        """
        Find each component in the calendar collection that has a matching UID with
        the supplied component, and get useful synchronization details from it, ignoring
        the one with the supplied resource name.
    
        @param collection: the L{CalDAVFile} for the calendar collection.
        @param calendar: the L{Component} for the component being compared with.
        @param ignore: the C{str} containing the name of a resource to ignore,
            or C{None} if none to ignore.
        @return: C{list} of synchronization information for each resource found.
        """
        names = []
        try:
            # Extract UID from primary component (note we allow multiple components to be present
            # because CANCEL requests can have multiple components).
            comp = calendar.mainComponent(allow_multiple=True)
            uid = comp.propertyValue("UID")
            
            # Now use calendar collection index to find all other resources with the same UID
            index = collection.index()
            names = index.resourceNamesForUID(uid)
            
            # Remove the one we want to ignore
            if ignore is not None:
                names = [name for name in names if name != ignore.fp.basename()]
        except ValueError:
            return []
        
        # Now get info for each name
        result = []
        for name in names:
            cal = collection.iCalendar(name)
            result.append(self.getSyncInfo(name, cal))
    
        return result
        
    def getSyncInfo(self, name, calendar):
        """
        Get property value details needed to synchronize iTIP components.
        
        @param calendar: L{Component} for calendar to check.
        @return: C{tuple} of (uid, seq, dtstamp, r-id) some of which may be C{None} if property does not exist
        """
        try:
            # Extract components from primary component (note we allow multiple components to be present
            # because CANCEL requests can have multiple components).
            comp = calendar.mainComponent(allow_multiple=True)
            uid, seq, dtstamp, rid = self.getComponentSyncInfo(comp)
            
        except ValueError:
            return (name, None, None, None, None)
        
        return (name, uid, seq, dtstamp, rid)
    
    def getComponentSyncInfo(self, component):
        """
        Get property value details needed to synchronize iTIP components.
        
        @param component: L{Component} to check.
        @return: C{tuple} of (uid, seq, dtstamp, r-id) some of which may be C{None} if property does not exist
        """
        try:
            # Extract items from component
            uid = component.propertyValue("UID")
            seq = component.propertyValue("SEQUENCE")
            if seq:
                seq = int(seq)
            dtstamp = component.propertyValue("DTSTAMP")
            rid = component.propertyValue("RECURRENCE-ID")
            
        except ValueError:
            return (None, None, None, None)
        
        return (uid, seq, dtstamp, rid)
    
    def compareComponents(self, component1, component2):
        """
        Compare synchronization information for two components to see if they match according to iTIP.
    
        @param component1: first component to check.
        @type component1: L{Component}
        @param component2: second component to check.
        @type component2: L{Component}
        
        @return: 0, 1, -1 as per compareSyncInfo.
        """
        info1 = (None,) + self.getComponentSyncInfo(component1)
        info2 = (None,) + self.getComponentSyncInfo(component2)
        return self.compareSyncInfo(info1, info2)
    
    def compareSyncInfo(self, info1, info2):
        """
        Compare two synchronization information records.
        
        @param info1: a C{tuple} as returned by L{getSyncInfo}.
        @param info2: a C{tuple} as returned by L{getSyncInfo}.
        @return: 1 if info1 > info2, 0 if info1 == info2, -1 if info1 < info2
        """
        # UIDs MUST match
        assert info1[1] == info2[1]
        
        # Look for sequence
        if (info1[2] is not None) and (info2[2] is not None):
            if info1[2] > info2[2]:
                return 1
            if info1[2] < info2[2]:
                return -1
        elif (info1[2] is not None) and (info2[2] is None):
            return 1
        elif (info1[2] is None) and (info2[2] is not None):
            return -1
    
        # Look for DTSTAMP
        if (info1[3] is not None) and (info2[3] is not None):
            if info1[3] > info2[3]:
                return 1
            if info1[3] < info2[3]:
                return -1
        elif (info1[3] is not None) and (info2[3] is None):
            return 1
        elif (info1[3] is None) and (info2[3] is not None):
            return -1
    
        return 0
