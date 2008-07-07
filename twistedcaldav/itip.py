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
from twisted.internet.defer import inlineCallbacks, returnValue, maybeDeferred
from twisted.web2.dav import davxml
from twisted.web2.dav.method.report import NumberOfMatchesWithinLimits
from twisted.web2.dav.util import joinURL
from twisted.web2.dav.fileop import delete
from twisted.web2.dav.resource import AccessDeniedError

from twistedcaldav import caldavxml
from twistedcaldav.accounting import accountingEnabled, emitAccounting
from twistedcaldav.log import Logger
from twistedcaldav.ical import Property, iCalendarProductID
from twistedcaldav.method import report_common
from twistedcaldav.method.put_common import storeCalendarObjectResource
from twistedcaldav.resource import isCalendarCollectionResource

log = Logger()

__version__ = "0.0"

__all__ = [
    "handleRequest",
    "canAutoRespond",
]

class iTipException(Exception):
    pass

def handleRequest(request, principal, inbox, calendar, child):
    """
    Handle an iTIP response automatically.
    @param request: the L{twisted.web2.server.Request} for the current request.
    @param principal: the L{CalendarPrincipalFile} principal resource for the principal we are dealing with.
    @param inbox: the L{ScheduleInboxFile} for the principal's Inbox.
    @param calendar: the L{Component} for the iTIP message we are processing.
    @param child: the L{CalDAVFile} for the iTIP message resource already saved to the Inbox.
    @return: L{Deferred} that is a L{deferredGenerator}
    """
    
    method = calendar.propertyValue("METHOD")
    if method == "REQUEST":
        f = processRequest
    elif method == "ADD":
        f = processAdd
    elif method == "CANCEL":
        f = processCancel

    return f(request, principal, inbox, calendar, child)

@inlineCallbacks
def processRequest(request, principal, inbox, calendar, child):
    """
    Process a METHOD=REQUEST.

    Steps:
    
      1. See if this updates existing ones in Inbox.
          1. If so,
              1. Remove existing ones in Inbox.
              2. See if this updates existing ones in free-busy-set calendars.
              3. Remove existing ones in those calendars.
              4. See if this fits into a free slot:
                  1. If not, send REPLY with failure status
                  2. If so
                      1. send REPLY with success
                      2. add to f-b-s calendar
          2. If not,
              1. remove the one we got - its 'stale'
          3. Delete the request from the Inbox.
    
    @param request: the L{twisted.web2.server.Request} for the current request.
    @param principal: the L{CalendarPrincipalFile} principal resource for the principal we are dealing with.
    @param inbox: the L{ScheduleInboxFile} for the principal's Inbox.
    @param calendar: the L{Component} for the iTIP message we are processing.
    @param child: the L{CalDAVFile} for the iTIP message resource already saved to the Inbox.
    """
    
    log.info("Auto-processing iTIP REQUEST for: %s" % (str(principal),))
    processed = "ignored"

    # First determine whether this is a full or partial update. A full update is one containing the master
    # component in a recurrence set (or non-recurring event). Partial is one where overridden instances only are
    # being changed.
    
    new_master = calendar.masterComponent()

    # Next we want to try and find a match to any components on existing calendars listed as contributing
    # to free-busy as we will need to update those with the new one.
    calmatch, updatecal, calURL = yield findCalendarMatch(request, principal, calendar)
    
    if new_master:
        # So we have a full update. That means we need to delete any existing events completely and
        # replace with the ones provided so long as the new one is newer.
        
        # If we have a match then we need to check whether we are updating etc
        check_reply = False
        if calmatch:
            # See whether the new component is older than any existing ones and throw it away if so
            newinfo = (None,) + getComponentSyncInfo(new_master)
            cal = updatecal.iCalendar(calmatch)
            info = getSyncInfo(calmatch, cal)
            if compareSyncInfo(info, newinfo) < 0:
                # Existing resource is older and will be replaced
                check_reply = True
            else:
                processed = "older"
        else:
            # We have a new request which we can reply to
            check_reply = True
            
        if check_reply:
            # Process the reply by determining PARTSTAT and sending the reply and booking the event.
            doreply, replycal, accepted = yield checkForReply(request, principal, calendar)
            
            try:
                if accepted:
                    if calmatch:
                        newchild = yield writeResource(request, calURL, updatecal, calmatch, calendar)
                        log.info("Replaced calendar component %s with new iTIP message in %s." % (calmatch, calURL))
                    else:
                        newchild = yield writeResource(request, calURL, updatecal, None, calendar)
                        log.info("Added new calendar component in %s." % (calURL,))
                else:
                    if calmatch:
                        yield deleteResource(updatecal, calmatch)
                        log.info("Deleted calendar component %s in %s as update was not accepted." % (calmatch, calURL))
                        
                # Send a reply if needed. 
                if doreply:
                    log.info("Sending iTIP REPLY %s" % (("declined","accepted")[accepted],))
                    newchild = yield writeReply(request, principal, replycal, inbox)
                    newInboxResource(child, newchild)
                processed = "processed"
            except:
                # FIXME: bare except
                log.err("Error while auto-processing iTIP: %s" % (Failure(),))
                raise iTipException()
            
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
            new_components = [component for component in calendar.subcomponents()]
            for component in new_components:
                if component.name() == "VTIMEZONE":
                    continue
                
                newinfo = (None,) + getComponentSyncInfo(component)
                old_component = findMatchingComponent(component, cal)
                if old_component:
                    info = (None,) + getComponentSyncInfo(old_component)
                elif old_master:
                    info = (None,) + getComponentSyncInfo(old_master)
                else:
                    info = None
                    
                if info is None or compareSyncInfo(info, newinfo) < 0:
                    # Existing resource is older and will be replaced
                    check_reply = True
                    processed = "processed"
                else:
                    calendar.removeComponent(component)
        else:
            # We have a new request which we can reply to
            check_reply = True

        if check_reply:
            # Process the reply by determining PARTSTAT and sending the reply and booking the event.
            doreply, replycal, accepted = yield checkForReply(request, principal, calendar)
            
            try:
                if calmatch:
                    # Merge the new instances with the old ones
                    mergeComponents(calendar, cal)
                    newchild = yield writeResource(request, calURL, updatecal, calmatch, cal)
                    log.info("Merged calendar component %s with new iTIP message in %s." % (calmatch, calURL))
                else:
                    if accepted:
                        newchild = yield writeResource(request, calURL, updatecal, None, calendar)
                        log.info("Added new calendar component in %s." % (calURL,))
                        
                # Do reply if needed. 
                if doreply:
                    log.info("Sending iTIP REPLY %s" % (("declined","accepted")[accepted],))
                    newchild = yield writeReply(request, principal, replycal, inbox)
                    newInboxResource(child, newchild)
                    
                processed = "processed"
            except:
                # FIXME: bare except
                log.err("Error while auto-processing iTIP: %s" % (Failure(),))
                raise iTipException()

    # Remove the now processed incoming request.
    try:
        yield deleteResource(inbox, child.fp.basename())
        log.info("Deleted new iTIP message %s in Inbox because it has been %s." % (
                   child.fp.basename(),
                   {
                     "processed": "processed",
                     "older"    : "ignored: older",
                     "ignored"  : "ignored: no match"
                   }[processed]
                ))
    except:
        # FIXME: bare except
        log.err("Error while auto-processing iTIP: %s" % (Failure(),))
        raise iTipException()

def processAdd(request, principal, inbox, calendar, child):
    """
    Process a METHOD=ADD.

    @param request: the L{twisted.web2.server.Request} for the current request.
    @param principal: the L{CalendarPrincipalFile} principal resource for the principal we are dealing with.
    @param inbox: the L{ScheduleInboxFile} for the principal's Inbox.
    @param calendar: the L{Component} for the iTIP message we are processing.
    @param child: the L{CalDAVFile} for the iTIP message resource already saved to the Inbox.
    """
    log.info("Auto-processing iTIP ADD for: %s" % (str(principal),))
    raise NotImplementedError()

@inlineCallbacks
def processCancel(request, principal, inbox, calendar, child):
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
    
    @param request: the L{twisted.web2.server.Request} for the current request.
    @param principal: the L{CalendarPrincipalFile} principal resource for the principal we are dealing with.
    @param inbox: the L{ScheduleInboxFile} for the principal's Inbox.
    @param calendar: the L{Component} for the iTIP message we are processing.
    @param child: the L{CalDAVFile} for the iTIP message resource already saved to the Inbox.
    """
    
    log.info("Auto-processing iTIP CANCEL for: %s" % (str(principal),))
    processed = "ignored"

    # Get all component info for this iTIP message
    newinfo = getSyncInfo(child.fp.basename(), calendar)
    info = getAllInfo(inbox, calendar, child)

    # First see if we have a recurrence id which will force extra work
    has_rid = False
    if newinfo[4] is not None:
        has_rid = True
    else:
        for i in info:
            if i[4] is not None:
                has_rid = True
                break
            
    if not has_rid:
        # Compare the new one with each existing one.
        delete_child = yield processOthersInInbox(info, newinfo, inbox, child)
        if delete_child:
            return

        # Next we want to try and find a match to any components on existing calendars listed as contributing
        # to free-busy as we will need to update those with the new one.
        calmatch, updatecal, calURL = yield findCalendarMatch(request, principal, calendar)
        
        # If we have a match then we need to check whether we are updating etc
        if calmatch:
            # See whether the current component is older than any existing ones and throw it away if so
            cal = updatecal.iCalendar(calmatch)
            info = getSyncInfo(calmatch, cal)
            if compareSyncInfo(info, newinfo) < 0:
                # Delete existing resource which has been cancelled
                try:
                    yield deleteResource(updatecal, calmatch)
                    log.info("Delete calendar component %s in %s as it was cancelled." % (calmatch, calURL))
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
        # Try and find a match to any components on existing calendars listed as contributing
        # to free-busy as we will need to update those with the new one.
        calmatch, updatecal, calURL = yield findCalendarMatch(request, principal, calendar)
        
        # If we have a match then we need to check whether we are updating etc
        if calmatch:
            # iTIP CANCEL can contain multiple components being cancelled in the RECURRENCE-ID case.
            # So we need to iterate over each iTIP component.

            # Get the existing calendar object
            existing_calendar = updatecal.iCalendar(calmatch)
            existing_master = existing_calendar.masterComponent()
            exdates = []

            for component in calendar.subcomponents():
                if component.name() == "VTIMEZONE":
                    continue
            
                # Find matching component in existing calendar
                old_component = findMatchingComponent(component, existing_calendar)
                
                if old_component:
                    # We are cancelling an overridden component, so we need to check the
                    # SEQUENCE/DTSAMP with the master.
                    if compareComponents(old_component, component) < 0:
                        # Exclude the cancelled instance
                        exdates.append(component.getRecurrenceIDUTC())
                        
                        # Remove the existing component.
                        existing_calendar.removeComponent(old_component)
                elif existing_master:
                    # We are trying to CANCEL a non-overridden instance, so we need to
                    # check SEQUENCE/DTSTAMP with the master.
                    if compareComponents(existing_master, component) < 0:
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
                    yield deleteResource(updatecal, calmatch)
                    log.info("Deleted calendar component %s after cancellations from iTIP message in %s." % (calmatch, calURL))
                else:
                    # Update the existing calendar object
                    newchild = yield writeResource(request, calURL, updatecal, calmatch, existing_calendar)
                    log.info("Updated calendar component %s with cancellations from iTIP message in %s." % (calmatch, calURL))
                processed = "processed"
            else:
                processed = "older"
        else:
            # Nothing to do except delete the inbox item as we have nothing to cancel.
            processed = "ignored"

    # Remove the now processed incoming request.
    try:
        yield deleteResource(inbox, child.fp.basename())
        log.info("Deleted new iTIP message %s in Inbox because it has been %s." % (
                  child.fp.basename(),
                  {
                    "processed": "processed",
                    "older"    : "ignored: older",
                    "ignored"  : "ignored: no match"
                  }[processed]
                ))
    except:
        # FIXME: bare except
        log.err("Error while auto-processing iTIP: %s" % (Failure(),))
        raise iTipException()

@inlineCallbacks
def checkForReply(request, principal, calendar):
    """
    Check whether a reply to the given iTIP message is needed. We will not process a reply
    if RSVP=FALSE. A reply will either be positive (accepted
    invitation) or negative (denied invitation). In addition we will modify calendar to reflect
    any new state (e.g. remove RSVP, set PARTSTAT to ACCEPTED or DECLINED).
    
    BTW The incoming iTIP message may contain multiple components so we need to iterate over all those.
    At the moment we will treat a failure on one instances as a DECLINE of the entire set.

    @param request: the L{twisted.web2.server.Request} for the current request.
    @param principal: the L{CalendarPrincipalFile} principal resource for the principal we are dealing with.
    @param calendar: the L{Component} for the iTIP message we are processing.
    @return: C{True} if a reply is needed, C{False} otherwise.
    """
    
    # We need to figure out whether the specified component will clash with any others in the f-b-set calendars
    accepted = True
        
    # First expand current one to get instances (only go 1 year into the future)
    default_future_expansion_duration = datetime.timedelta(days=356*1)
    expand_max = datetime.date.today() + default_future_expansion_duration
    instances = calendar.expandTimeRanges(expand_max)
    
    # Extract UID from primary component as we want to ignore this one if we match it
    # in any calendars.
    comp = calendar.mainComponent(allow_multiple=True)
    uid = comp.propertyValue("UID")

    # Now compare each instance time-range with the index and see if there is an overlap
    fbset = yield principal.calendarFreeBusyURIs(request)

    for calURL in fbset:
        testcal = yield request.locateResource(calURL)
        
        # First list is BUSY, second BUSY-TENTATIVE, third BUSY-UNAVAILABLE
        fbinfo = ([], [], [])
        
        # Now do search for overlapping time-range
        for instance in instances.instances.itervalues():
            try:
                tr = caldavxml.TimeRange(start="20000101", end="20000101")
                tr.start = instance.start
                tr.end = instance.end
                yield report_common.generateFreeBusyInfo(request, testcal, fbinfo, tr, 0, uid)
                
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
    cuas = principal.calendarUserAddresses()
    attendeeProps = calendar.getAttendeeProperties(cuas)
    if not attendeeProps:
        returnValue((False, None, accepted))

    # Look for specific parameters
    rsvp = True
    for attendeeProp in attendeeProps:
        if "RSVP" in attendeeProp.params():
            if attendeeProp.params()["RSVP"][0] == "FALSE":
                rsvp = False
    
            # Now modify the original component
            del attendeeProp.params()["RSVP"]

    if accepted:
        partstat = "ACCEPTED"
    else:
        partstat = "DECLINED"
    for attendeeProp in attendeeProps:
        if "PARTSTAT" in attendeeProp.params():
            attendeeProp.params()["PARTSTAT"][0] = partstat
        else:
            attendeeProp.params()["PARTSTAT"] = [partstat]
    
    # Now create a new calendar object for the reply
    
    # First get useful props from the original
    replycal = calendar.duplicate()
    
    # Change METHOD
    replycal.getProperty("METHOD").setValue("REPLY")
    
    # Change PRODID to this server
    replycal.getProperty("PRODID").setValue(iCalendarProductID)
    
    # Add REQUEST-STATUS
    for component in replycal.subcomponents():
        if accepted:
            component.addProperty(Property(name="REQUEST-STATUS", value="2.0; Success."))
        else:
            component.addProperty(Property(name="REQUEST-STATUS", value="4.0; Event conflict. Date/time is busy."))

    # Remove all attendees other than ourselves
    for component in replycal.subcomponents():
        if component.name() == "VTIMEZONE":
            continue
        attendeeProp = component.getAttendeeProperty(cuas)
        attendees = tuple(component.properties("ATTENDEE"))
        for attendee in attendees:
            if attendeeProp is None or (attendee.value() != attendeeProp.value()):
                component.removeProperty(attendee)

    returnValue((rsvp, replycal, accepted))

@inlineCallbacks
def writeReply(request, principal, replycal, ainbox):
    """
    Write an iTIP message reply into the specified Inbox.
    
    @param request: the L{twisted.web2.server.Request} for the current request.
    @param principal: the L{CalendarPrincipalFile} principal resource for the principal we are dealing with.
    @param replycal: the L{Component} for the iTIP message reply.
    @param ainbox: the L{ScheduleInboxFile} for the principal's Inbox.
    """
    
    # Get the Inbox of the ORGANIZER
    organizer = replycal.getOrganizer()
    assert organizer is not None
    inboxURL = ainbox.principalForCalendarUserAddress(organizer).scheduleInboxURL()
    assert inboxURL
    
    # Determine whether current principal has CALDAV:schedule right on that Inbox
    inbox = yield request.locateResource(inboxURL)

    try:
        yield inbox.checkPrivileges(request, (caldavxml.Schedule(),), principal=davxml.Principal(davxml.HRef.fromString(principal.principalURL())))
    except AccessDeniedError:
        log.info("Could not send reply as %s does not have CALDAV:schedule permission on %s Inbox." % (principal.principalURL(), organizer))
        returnValue(None)
    
    # Now deposit the new calendar into the inbox
    result = yield writeResource(request, inboxURL, inbox, None, replycal)

    if accountingEnabled("iTIP", principal):
        emitAccounting(
            "iTIP", principal,
            "Originator: %s\nRecipients: %s\n\n%s"
            % (principal.principalURL(), organizer, str(replycal))
        )

    returnValue(result)

@inlineCallbacks
def writeResource(request, collURL, collection, name, calendar):
    """
    Write out the calendar resource (iTIP) message to the specified calendar, either over-writing the named
    resource or by creating a new one.
    
    @param request: the L{IRequest} for the current request.
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
    newchild = yield request.locateResource(newchildURL)
    
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
    try:
        yield storeCalendarObjectResource(
            request=request,
            sourcecal = False,
            destination = newchild,
            destination_uri = newchildURL,
            calendardata = str(calendar),
            destinationparent = collection,
            destinationcal = True,
            isiTIP = itipper
        )
    except:
        # FIXME: bare except
        return
    
    returnValue(newchild)

def newInboxResource(child, newchild):
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
  
def deleteResource(collection, name):
    """
    Delete the calendar resource in the specified calendar.
    
    @param collection: the L{CalDAVFile} for the calendar collection to store the resource in.
    @param name: the C{str} for the resource name to write into, or {None} to write a new resource.
    @return: L{Deferred}
    """
    
    delchild = collection.getChild(name)
    index = collection.index()
    index.deleteResource(delchild.fp.basename())
    
    def _deletedResourced(result):
        # Change CTag on the parent calendar collection
        return collection.updateCTag().addCallback(lambda _: result)

    d = maybeDeferred(delete, "", delchild.fp, "0")
    d.addCallback(_deletedResourced)
    return d

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
def processOthersInInbox(info, newinfo, inbox, child):
    # Compare the new one with each existing one.
    delete_child = False
    for i in info:
        # For any that are older, delete them.
        if compareSyncInfo(i, newinfo) < 0:
            try:
                yield deleteResource(inbox, i[0])
                log.info("Deleted iTIP message %s in Inbox that was older than the new one." % (i[0],))
            except:
                # FIXME: bare except
                log.err("Error while auto-processing iTIP: %s" % (Failure(),))
                raise iTipException()
        else:
            # For any that are newer or the same, mark the new one to be deleted.
            delete_child = True

    # Delete the new one if so marked.
    if delete_child:
        try:
            yield deleteResource(inbox, child.fp.basename())
            log.info("Deleted new iTIP message %s in Inbox because it was older than existing ones." % (child.fp.basename(),))
        except:
            # FIXME: bare except
            log.err("Error while auto-processing iTIP: %s" % (Failure(),))
            raise iTipException()
    
    returnValue(delete_child)

@inlineCallbacks
def findCalendarMatch(request, principal, calendar):
    # Try and find a match to any components on existing calendars listed as contributing
    # to free-busy as we will need to update those with the new one.
    
    # Find the current recipients calendar-free-busy-set
    fbset = yield principal.calendarFreeBusyURIs(request)

    # Find the first calendar in the list with a component matching the one we are processing
    calmatch = None
    updatecal = None
    calURL = None
    for calURL in fbset:
        updatecal = yield request.locateResource(calURL)
        if updatecal is None or not updatecal.exists() or not isCalendarCollectionResource(updatecal):
            # We will ignore missing calendars. If the recipient has failed to
            # properly manage the free busy set that should not prevent us from working.
            continue
        calmatch = matchComponentInCalendar(updatecal, calendar)
        if calmatch:
            log.info("Found calendar component %s matching new iTIP message in %s." % (calmatch, calURL))
            break
    
    if calmatch is None and len(fbset):
        calURL = fbset[0]
        updatecal = yield request.locateResource(calURL)

    returnValue((calmatch, updatecal, calURL))

def matchComponentInCalendar(collection, calendar):
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

def findMatchingComponent(component, calendar):
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

def mergeComponents(newcal, oldcal):
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

def getAllInfo(collection, calendar, ignore):
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
        result.append(getSyncInfo(name, cal))

    return result
    
def getSyncInfo(name, calendar):
    """
    Get property value details needed to synchronize iTIP components.
    
    @param calendar: L{Component} for calendar to check.
    @return: C{tuple} of (uid, seq, dtstamp, r-id) some of which may be C{None} if property does not exist
    """
    try:
        # Extract components from primary component (note we allow multiple components to be present
        # because CANCEL requests can have multiple components).
        comp = calendar.mainComponent(allow_multiple=True)
        uid, seq, dtstamp, rid = getComponentSyncInfo(comp)
        
    except ValueError:
        return (name, None, None, None, None)
    
    return (name, uid, seq, dtstamp, rid)

def getComponentSyncInfo(component):
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

def compareComponents(component1, component2):
    """
    Compare synchronization information for two components to see if they match according to iTIP.

    @param component1: first component to check.
    @type component1: L{Component}
    @param component2: second component to check.
    @type component2: L{Component}
    
    @return: 0, 1, -1 as per compareSyncInfo.
    """
    info1 = (None,) + getComponentSyncInfo(component1)
    info2 = (None,) + getComponentSyncInfo(component2)
    return compareSyncInfo(info1, info2)

def compareSyncInfo(info1, info2):
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
