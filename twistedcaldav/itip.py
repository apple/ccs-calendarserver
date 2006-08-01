##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
#
# This file contains Original Code and/or Modifications of Original Code
# as defined in and that are subject to the Apple Public Source License
# Version 2.0 (the 'License'). You may not use this file except in
# compliance with the License. Please obtain a copy of the License at
# http://www.opensource.apple.com/apsl/ and read it before using this
# file.
# 
# The Original Code and all software distributed under the License are
# distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
# EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
# INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
# Please see the License for the specific language governing rights and
# limitations under the License.
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
iTIP (RFC2446) processing.

This is currently used for handling auto-replies to schedule request arriving in an Inbox. It is called in a delayed
fashion via reactor.callLater.

BTW We assume that all the components/calendars we deal with have been determined as being 'valid for CalDAV/iTIP'.
i.e. they contain UIDs, single component types etc.

NB The logic for component matching needs a lot more work as it currently does not know how to deal with overridden instances.
"""

import datetime
import logging
import md5
import os
import time

from twisted.python import log, failure
from twisted.internet.defer import waitForDeferred, deferredGenerator, maybeDeferred
from twisted.web2.dav import davxml
from twisted.web2.dav.method.report import NumberOfMatchesWithinLimits
from twisted.web2.dav.util import joinURL
from twisted.web2.dav.fileop import delete
from twistedcaldav import constants
from twistedcaldav import caldavxml
from twistedcaldav.ical import Property
from twistedcaldav.method import report_common
from twistedcaldav.method.put_common import storeCalendarObjectResource
from twistedcaldav.resource import CalendarPrincipalCollectionResource, isCalendarCollectionResource
from twistedcaldav.static import CalDAVFile

__version__ = "0.0"

__all__ = [
    "handleRequest",
    "canAutoRespond",
]

def handleRequest(request, principal, inbox, calendar, child):
    """
    Handle an iTIP response automatically using a deferredGenerator.

    @param request: the L{Request} for the current request.
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

    return maybeDeferred(deferredGenerator(f), request, principal, inbox, calendar, child)

def processRequest(request, principal, inbox, calendar, child):
    """
    Process a METHOD=REQUEST.
    This is a deferredGenerator function so use yield whenever we have a deferred.

    TODO: ignore recurrence overrides
    
    Steps:
    
    1. See if this updates existing ones in Inbox.
        1.1 If so,
            1.1.1. Remove existing ones in Inbox.
            1.1.2. See if this updates existing ones in free-busy-set calendars.
            1.1.3. Remove existing ones in those calendars.
            1.1.4. See if this fits into a free slot:
                1.1.4.1. If not, send REPLY with failure status
                1.1.4.2. If so
                    1.1.4.2.1 send REPLY with success
                    1.1.4.2.2 add to f-b-s calendar
        1.2 If not,
            1.2.1 remove the one we got - its 'stale'
    
    @param request: the L{Request} for the current request.
    @param principal: the L{CalendarPrincipalFile} principal resource for the principal we are dealing with.
    @param inbox: the L{ScheduleInboxFile} for the principal's Inbox.
    @param calendar: the L{Component} for the iTIP message we are processing.
    @param child: the L{CalDAVFile} for the iTIP message resource already saved to the Inbox.
    """
    
    logging.info("[ITIP]: Auto-processing iTIP REQUEST for: %s" % (str(principal),))

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
        delete_child = False
        for i in info:
            # For any that are older, delete them.
            if compareSyncInfo(i, newinfo) < 0:
                d = waitForDeferred(deleteResource(inbox, i[0]))
                yield d
                try:
                    d.getResult()
                except:
                    log.err("Error while auto-processing iTIP: %s" % (failure.Failure(),))
                    return
                logging.info("[ITIP]: deleted iTIP message %s in Inbox that was older than the new one." % (i[0],))
            else:
                # For any that are newer or the same, mark the new one to be deleted.
                delete_child = True

        # Delete the new one if so marked.
        if delete_child:
            d = waitForDeferred(deleteResource(inbox, child.fp.basename()))
            yield d
            try:
                d.getResult()
            except:
                log.err("Error while auto-processing iTIP: %s" % (failure.Failure(),))
                return
            logging.info("[ITIP]: deleted new iTIP message %s in Inbox because it was older than existing ones." % (child.fp.basename(),))
            return

        # Next we want to try and find a match to any components on existing calendars listed as contributing
        # to free-busy as we will need to update those with the new one.
        
        # Find the current recipients calendar-free-busy-set
        fbset = principal.calendarFreeBusySet(request)

        # Find the first calendar in the list with a component matching the one we are processing
        calmatch = None
        for href in fbset.children:
            calURL = str(href)
            updatecal = inbox.locateSiblingResource(request, calURL)
            if updatecal is None or not updatecal.exists() or not isCalendarCollectionResource(updatecal):
                # We will ignore missing calendars. If the recipient has failed to
                # properly manage the free busy set that should not prevent us from working.
                continue
            calmatch = matchComponentInCalendar(updatecal, calendar, None)
            if calmatch:
                logging.info("[ITIP]: found calendar component %s matching new iTIP message in %s." % (calmatch[0], calURL))
                break
        
        # If we have a match then we need to check whether we are updating etc
        doreply, replycal, accepted = checkForReply(request, principal, calendar)
        if calmatch:
            # See whether the current component is older than any existing ones and throw it away if so
            cal = updatecal.iCalendar(calmatch[0])
            info = getSyncInfo(calmatch[0], cal)
            if compareSyncInfo(info, newinfo) < 0:
                # Re-write existing resource with new one, if accepted, otherwise delete existing as the
                # update to it was not accepted.
                if accepted:
                    d, newchild = writeResource(request, calURL, updatecal, calmatch[0], calendar)
                    d = waitForDeferred(d)
                else:
                    d = waitForDeferred(deleteResource(updatecal, calmatch[0]))
                yield d
                try:
                    d.getResult()
                except:
                    log.err("Error while auto-processing iTIP: %s" % (failure.Failure(),))
                    return
                if accepted:
                    logging.info("[ITIP]: replaced calendar component %s with new iTIP message in %s." % (calmatch[0], calURL))
                else:
                    logging.info("[ITIP]: deleted calendar component %s in %s as update was not accepted." % (calmatch[0], calURL))
            else:
                # Delete new one in Inbox as it is old
                d = waitForDeferred(deleteResource(inbox, child.fp.basename()))
                yield d
                try:
                    d.getResult()
                except:
                    log.err("Error while auto-processing iTIP: %s" % (failure.Failure(),))
                    return
                logging.info("[ITIP]: deleted new iTIP message %s in Inbox because it was older than %s in %s." % (child.fp.basename(), calmatch[0], calURL))
                return
        else:
            # Write new resource into first calendar in f-b-set
            if len(fbset.children) != 0 and accepted:
                calURL = str(fbset.children[0])
                updatecal = inbox.locateSiblingResource(request, calURL)
                d, newchild = writeResource(request, calURL, updatecal, None, calendar)
                d = waitForDeferred(d)
                yield d
                try:
                    d.getResult()
                except:
                    log.err("Error while auto-processing iTIP: %s" % (failure.Failure(),))
                    return
                logging.info("[ITIP]: added new calendar component in %s." % (calURL,))
        
        # If we get here we have a new iTIP message that we want to process. Any previous ones
        # have been removed (so we won't run in to problems when we check that there is free time
        # to book the new one). 
        if doreply:
            logging.info("[ITIP]: sending iTIP REPLY %s" % (("declined","accepted")[accepted],))
            d, newchild = writeReply(request, principal, replycal, inbox)
            d = waitForDeferred(d)
            if d:
                yield d
                try:
                    d.getResult()
                except:
                    log.err("Error while auto-processing iTIP: %s" % (failure.Failure(),))
                    return
                newInboxResource(child, newchild)
            logging.info("[ITIP]: saving iTIP REPLY %s" % (("declined","accepted")[accepted],))
            d, newchild = saveReply(request, principal, replycal, inbox)
            d = waitForDeferred(d)
            if d:
                yield d
                try:
                    d.getResult()
                except:
                    log.err("Error while auto-processing iTIP: %s" % (failure.Failure(),))
                    return

        # Store CALDAV:schedule-state property
        assert child.fp.exists()
        child.writeDeadProperty(caldavxml.ScheduleState(caldavxml.Processed()))
        return
    else:
        raise NotImplementedError
    
def processAdd(request, principal, inbox, calendar, child):
    """
    Process a METHOD=ADD.
    This is a deferredGenerator function so use yield whenever we have a deferred.

    @param request: the L{Request} for the current request.
    @param principal: the L{CalendarPrincipalFile} principal resource for the principal we are dealing with.
    @param inbox: the L{ScheduleInboxFile} for the principal's Inbox.
    @param calendar: the L{Component} for the iTIP message we are processing.
    @param child: the L{CalDAVFile} for the iTIP message resource already saved to the Inbox.
    """
    logging.info("[ITIP]: Auto-processing iTIP ADD for: %s" % (str(principal),))

    raise NotImplementedError

def processCancel(request, principal, inbox, calendar, child):
    """
    Process a METHOD=CANCEL.
    This is a deferredGenerator function so use yield whenever we have a deferred.

    Policy find all components that match UID, SEQ and R-ID and remove them.

    Steps:
    
    1. See if this updates existing ones in Inbox.
    2. Remove existing ones in Inbox.
    3. See if this updates existing ones in free-busy-set calendars.
    4. Remove existing ones in those calendars.

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
    
    @param request: the L{Request} for the current request.
    @param principal: the L{CalendarPrincipalFile} principal resource for the principal we are dealing with.
    @param inbox: the L{ScheduleInboxFile} for the principal's Inbox.
    @param calendar: the L{Component} for the iTIP message we are processing.
    @param child: the L{CalDAVFile} for the iTIP message resource already saved to the Inbox.
    """
    
    logging.info("[ITIP]: Auto-processing iTIP CANCEL for: %s" % (str(principal),))

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
        delete_child = False
        for i in info:
            # For any that are older, delete them.
            if compareSyncInfo(i, newinfo) < 0:
                d = waitForDeferred(deleteResource(inbox, i[0]))
                yield d
                try:
                    d.getResult()
                except:
                    log.err("Error while auto-processing iTIP: %s" % (failure.Failure(),))
                    return
                logging.info("[ITIP]: deleted iTIP message %s in Inbox that was older than the new one." % (i[0],))
            else:
                # For any that are newer or the same, mark the new one to be deleted.
                delete_child = True

        # Delete the new one if so marked.
        if delete_child:
            d = waitForDeferred(deleteResource(inbox, child.fp.basename()))
            yield d
            try:
                d.getResult()
            except:
                log.err("Error while auto-processing iTIP: %s" % (failure.Failure(),))
                return
            logging.info("[ITIP]: deleted new iTIP message %s in Inbox because it was older than existing ones." % (child.fp.basename(),))
            return

        # Next we want to try and find a match to any components on existing calendars listed as contributing
        # to free-busy as we will need to update those with the new one.
        
        # Find the current recipients calendar-free-busy-set
        fbset = principal.calendarFreeBusySet(request)

        # Find the first calendar in the list with a component matching the one we are processing
        calmatch = None
        for href in fbset.children:
            calURL = str(href)
            updatecal = inbox.locateSiblingResource(request, calURL)
            if updatecal is None or not updatecal.exists() or not isCalendarCollectionResource(updatecal):
                # We will ignore missing calendars. If the recipient has failed to
                # properly manage the free busy set that should not prevent us from working.
                continue
            calmatch = matchComponentInCalendar(updatecal, calendar, None)
            if calmatch:
                logging.info("[ITIP]: found calendar component %s matching new iTIP message in %s." % (calmatch[0], calURL))
                break
        
        # If we have a match then we need to check whether we are updating etc
        if calmatch:
            # See whether the current component is older than any existing ones and throw it away if so
            cal = updatecal.iCalendar(calmatch[0])
            info = getSyncInfo(calmatch[0], cal)
            if compareSyncInfo(info, newinfo) < 0:
                # Re-write existing resource with new one
                d = waitForDeferred(deleteResource(updatecal, calmatch[0],))
                yield d
                try:
                    d.getResult()
                except:
                    log.err("Error while auto-processing iTIP: %s" % (failure.Failure(),))
                    return
                logging.info("[ITIP]: delete calendar component %s in %s as it was cancelled." % (calmatch[0], calURL))
            else:
                # Delete new one in Inbox as it is old
                d = waitForDeferred(deleteResource(inbox, child.fp.basename()))
                yield d
                try:
                    d.getResult()
                except:
                    log.err("Error while auto-processing iTIP: %s" % (failure.Failure(),))
                    return
                logging.info("[ITIP]: deleted new iTIP message %s in Inbox because it was older than %s in %s." % (child.fp.basename(), calmatch[0], calURL))
                return
        else:
            # Nothing to do
            pass
        
        # If we get here we have a new iTIP message that we want to process. Any previous ones
        # have been removed (so we won't run in to problems when we check that there is free time
        # to book the new one). 

        # Store CALDAV:schedule-state property
        assert child.fp.exists()
        child.writeDeadProperty(caldavxml.ScheduleState(caldavxml.Processed()))
        return
    else:
        raise NotImplementedError

def checkForReply(request, principal, calendar):
    """
    Check whether a reply to the given iTIP message is needed. A reply will be needed if the
    RSVP=TRUE. A reply will either be positive (accepted
    invitation) or negative (denied invitation). In addition we will modify calendar to reflect
    any new state (e.g. remove RSVP, set PART-STAT to ACCEPTED or DECLINED).

    @param request: the L{Request} for the current request.
    @param principal: the L{CalendarPrincipalFile} principal resource for the principal we are dealing with.
    @param calendar: the L{Component} for the iTIP message we are processing.
    @return: C{True} if a reply is needed, C{False} otherwise.
    """
    
    # We need to fugure out whether the specified component will clash with any others in the f-b-set calendars
    accepted = True
        
    # First expand current one to get instances (only go 1 year into the future)
    default_future_expansion_duration = datetime.timedelta(days=356*1)
    expand_max = datetime.date.today() + default_future_expansion_duration
    instances = calendar.expandTimeRanges(expand_max)
    
    # Extract UID from primary component as we want to ignore this one if we match it
    # in any calendars.
    comp = calendar.mainComponent()
    uid = comp.propertyValue("UID")

    # Now compare each instance time-range with the index and see if there is an overlap
    fbset = principal.calendarFreeBusySet(request)
    for href in fbset.children:
        calURL = str(href)
        testcal = principal.locateSiblingResource(request, calURL)
        
        # First list is BUSY, second BUSY-TENTATIVE, third BUSY-UNAVAILABLE
        fbinfo = ([], [], [])
        
        # Now do search for overlapping time-range
        for instance in instances.instances.itervalues():
            try:
                tr = caldavxml.TimeRange(start="20000101", end="20000101")
                tr.start = instance.start
                tr.end = instance.end
                report_common.generateFreeBusyInfo(request, testcal, fbinfo, tr, 0, uid)
                
                # If any fbinfo entries exist we have an overlap
                if len(fbinfo[0]) or len(fbinfo[1]) or len(fbinfo[2]):
                    accepted = False
                    break
            except NumberOfMatchesWithinLimits:
                accepted = False
                logging.info("[ITIP]: exceeded number of matches whilst trying to find free-time.")
                break
            
        if not accepted:
            break
     
    # Extract the ATTENDEE property matching current recipient from the calendar data
    cuas = principal.calendarUserAddressSet()
    attendeeProp = calendar.getAttendeeProperty(cuas)
    if attendeeProp is None:
        return False, None, accepted

    # Look for specific parameters
    if "RSVP" in attendeeProp.params():
        if attendeeProp.params()["RSVP"][0] != "TRUE":
            return False, None, accepted
    else:
        return False, None, accepted
    
    # Now modify the original component
    del attendeeProp.params()["RSVP"]

    if accepted:
        partstat = "ACCEPTED"
    else:
        partstat = "DECLINED"
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
    replycal.getProperty("PRODID").setValue(constants.ICALENDAR_PRODID)
    
    # Add REQUEST-STATUS
    if accepted:
        replycal.mainComponent().addProperty(Property(name="REQUEST-STATUS", value="2.0; Success."))
    else:
        replycal.mainComponent().addProperty(Property(name="REQUEST-STATUS", value="4.0; Event conflict. Date/time is busy."))

    # Remove all attendees other than ourselves
    attendees = replycal.mainComponent().properties("ATTENDEE")
    for attendee in attendees:
        if (attendee.value() != attendeeProp.value()):
            replycal.mainComponent().removeProperty(attendee)

    return True, replycal, accepted

def writeReply(request, principal, replycal, ainbox):
    """
    Write an iTIP message reply into the specified Inbox.
    
    @param request: the L{Request} for the current request.
    @param principal: the L{CalendarPrincipalFile} principal resource for the principal we are dealing with.
    @param replycal: the L{Component} for the iTIP message reply.
    @param ainbox: the L{ScheduleInboxFile} for the principal's Inbox.
    """
    
    # Get the Inbox of the ORGANIZER
    organizer = replycal.getOrganizer()
    assert organizer is not None
    inboxURL = CalendarPrincipalCollectionResource.inboxForCalendarUser(request, organizer)
    assert inboxURL
    
    # Determine whether current principal has CALDAV:schedule right on that Inbox
    inbox = ainbox.locateSiblingResource(request, inboxURL)

    errors = inbox.checkAccess(request, (caldavxml.Schedule(),), principal=davxml.Principal(davxml.HRef.fromString(principal.principalURL())))
    if errors:
        logging.info("[ITIP]: could not send reply as %s does not have CALDAV:schedule permission on %s Inbox." % (principal.principalURL(), organizer))
        return None, None
    
    # Now deposit the new calendar into the inbox
    return writeResource(request, inboxURL, inbox, None, replycal)
    
def saveReply(request, principal, replycal, ainbox):
    """
    Write an iTIP message reply into the specified principal's Outbox.
    
    @param request: the L{Request} for the current request.
    @param principal: the L{CalendarPrincipalFile} principal resource for the principal we are dealing with.
    @param replycal: the L{Component} for the iTIP message reply.
    @param ainbox: the L{ScheduleInboxFile} for the principal's Inbox.
    """
    
    # Get the Outbox of the principal
    outboxURL = principal.scheduleOutboxURL()
    assert outboxURL
    
    # Determine whether current principal has CALDAV:schedule right on that Outbox
    outbox = ainbox.locateSiblingResource(request, outboxURL)

    errors = outbox.checkAccess(request, (caldavxml.Schedule(),), principal=davxml.Principal(davxml.HRef.fromString(principal.principalURL())))
    if errors:
        logging.info("[ITIP]: could not save reply as %s does not have CALDAV:schedule permission on their Outbox." % (principal.principalURL(),))
        return None, None
    
    # Now deposit the new calendar into the inbox
    return writeResource(request, outboxURL, outbox, None, replycal)
    
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
        newchild = CalDAVFile(os.path.join(collection.fp.path, name))
    else:
        newchild = collection.getChild(name)
    
    # Modify the original calendar data by removing the METHOD property - everything else is left as-is,
    # as any other needed changes (e.g. RSVP/PARTSTAT) will have been updated.
    # NB Only do this when writing to something other than an Inbox or Outbox
    itipper = True
    if collection.isCalendarCollection():
        method = calendar.getProperty("METHOD")
        calendar.removeProperty(method)
        itipper = False
    
    # Now write it to the resource

    # Get a resource for the new item
    newchildURL = joinURL(collURL, name)
    
    # Copy calendar to inbox (doing fan-out)
    d = maybeDeferred(
            storeCalendarObjectResource,
            request=request,
            sourcecal = False,
            destination = newchild,
            destination_uri = newchildURL,
            calendardata = str(calendar),
            destinationparent = collection,
            destinationcal = True,
            isiTIP = itipper
        )
    return d, newchild

def newInboxResource(child, newchild):
    """
    Copy recipient and orgnaizer properties from one iTIP resource, to another,
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
    
    # Store CALDAV:schedule-state property
    newchild.writeDeadProperty(caldavxml.ScheduleState(caldavxml.NotProcessed()))
  
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
    d = maybeDeferred(delete, "", delchild.fp, "0")
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
    except:
        return False
    
    return True

def matchComponentInCalendar(collection, calendar, ignore):
    """
    See if the component in the provided iTIP calendar object matches any in the specified calendar
    collectrion, excluding the resource provided.
    
    @param collection: L{CalDAVFile} for the calendar collection to examine.
    @param calendar: L{Component} for calendar to examine.
    @param ignore: L{CalDAVFile} to ignore if found, or C{None} if none to ignore.
    @return: C{list} of resource names found.
    """

    result = []
    try:
        # Extract UID from primary component
        comp = calendar.mainComponent()
        uid = comp.propertyValue("UID")
        
        # Now use calendar collection index to find all other resources with the same UID
        index = collection.index()
        result = index.resourceNamesForUID(uid)
        
        # Remove the one we want to ignore
        if ignore is not None:
            result = [name for name in result if name != ignore.fp.basename()]
    except:
        return []
    
    return result

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
        # Extract UID from primary component
        comp = calendar.mainComponent()
        uid = comp.propertyValue("UID")
        
        # Now use calendar collection index to find all other resources with the same UID
        index = collection.index()
        names = index.resourceNamesForUID(uid)
        
        # Remove the one we want to ignore
        if ignore is not None:
            names = [name for name in names if name != ignore.fp.basename()]
    except:
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
        # Extract items from primary component
        comp = calendar.mainComponent()
        uid = comp.propertyValue("UID")
        seq = comp.propertyValue("SEQUENCE")
        dtstamp = comp.propertyValue("DTSTAMP")
        rid = comp.propertyValue("RECURRENCE-ID")
        
    except:
        return (name, None, None, None, None)
    
    return (name, uid, seq, dtstamp, rid)

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

def updating(collection, names, calendar):
    """
    Check whether the specified calendar object is an iTIP message that is "newer" than the
    others listed, or does not match the component type listed.
    
    @param collection: L{CalDAVFile} for the calendar collection to examine.
    @param names: C{list} of C{str} for names of resources in the collection to check against.
    @param calendar: L{Component} for calendar to check.
    @return: C{True} if new component is an update and valid, C{False} otherwise.
    """
    
    # First get useful sync-related info from existing component
    uid, seq, dtstamp, rid = getSyncInfo(calendar)
    
    # Now get info from each named component and compare
    for name in names:
        cal = collection.iCalendar(name)
        cuid, cseq, cdtstamp, crid = getSyncInfo(cal)
        
        # UIDs MUST match
        assert uid == cuid
        
        # Look for sequence
        if (cseq is not None) and (seq is not None):
            if cseq > seq:
                return False
            if cseq < seq:
                continue
        elif (cseq is not None) and (seq is None):
            return False
        elif (cseq is None) and (seq is not None):
            continue

        # Look for DTSTAMP
        if (cdtstamp is not None) and (dtstamp is not None):
            if cdtstamp > dtstamp:
                return False
            if cdtstamp < dtstamp:
                continue
        elif (cdtstamp is not None) and (dtstamp is None):
            return False
        elif (cdtstamp is None) and (dtstamp is not None):
            continue
        
    return True
            
