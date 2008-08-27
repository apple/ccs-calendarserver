#
# Copyright (c) 2005-2008 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twistedcaldav.log import Logger
from twistedcaldav.method import report_common
from twisted.web2.dav.fileop import delete
from twistedcaldav.scheduling.itip import iTipProcessing
from hashlib import md5
from twisted.web2.dav.util import joinURL
from twistedcaldav.caldavxml import caldav_namespace
import time

__all__ = [
    "ImplicitProcessor",
    "ImplicitProcessorException",
]

log = Logger()

class ImplicitProcessorException(Exception):
    
    def __init__(self, msg):
        self.msg = msg

class ImplicitProcessor(object):
    
    def __init__(self):
        pass

    @inlineCallbacks
    def doImplicitProcessing(self, request, message, originator, recipient):
        """
        Do implicit processing of a scheduling message, and possibly also auto-process it
        if the recipient has auto-accept on.

        @param message:
        @type message:
        @param originator:
        @type originator:
        @param recipient:
        @type recipient:
        
        @return: a C{tuple} of (C{bool}, C{bool}) indicating whether the message was processed, and if it was whether
            auto-processing has taken place.
        """

        self.request = request
        self.message = message
        self.originator = originator
        self.recipient = recipient
        
        # TODO: for now going to assume that the originator is local - i.e. the scheduling message sent
        # represents the actual organizer's view.
        
        # First see whether this is the organizer or attendee sending the message
        self.extractCalendarData()

        if self.isOrganizerReceivingMessage():
            result = (yield self.doImplicitOrganizer())
        elif self.isAttendeeReceivingMessage():
            result = (yield self.doImplicitAttendee())
        else:
            log.error("METHOD:%s not supported for implicit scheduling." % (self.method,))
            raise ImplicitProcessorException("3.14;Unsupported capability")

        returnValue(result)

    def extractCalendarData(self):
        
        # Some other useful things
        self.method = self.message.propertyValue("METHOD")
        self.uid = self.message.resourceUID()
    
    def isOrganizerReceivingMessage(self):
        return self.method in ("REPLY", "REFRESH")

    def isAttendeeReceivingMessage(self):
        return self.method in ("REQUEST", "ADD", "CANCEL")

    @inlineCallbacks
    def getRecipientsCopy(self):
        """
        Get the Recipient's copy of the event being processed.
        """
        
        self.recipient_calendar = None
        self.recipient_calendar_collection = None
        self.recipient_calendar_name = None
        if self.recipient.principal:
            # Get Recipient's calendar-home
            calendar_home = self.recipient.principal.calendarHome()
            
            # FIXME: because of the URL->resource request mapping thing, we have to force the request
            # to recognize this resource
            self.request._rememberResource(calendar_home, calendar_home.url())
    
            # Run a UID query against the UID

            def queryCalendarCollection(collection, uri):
                rname = collection.index().resourceNameForUID(self.uid)
                if rname:
                    self.recipient_calendar = collection.iCalendar(rname)
                    self.recipient_calendar_name = rname
                    self.recipient_calendar_collection = collection
                    self.recipient_calendar_collection_uri = uri
                    return succeed(False)
                else:
                    return succeed(True)
            
            # NB We are by-passing privilege checking here. That should be OK as the data found is not
            # exposed to the user.
            yield report_common.applyToCalendarCollections(calendar_home, self.request, calendar_home.url(), "infinity", queryCalendarCollection, None)
    
    @inlineCallbacks
    def doImplicitOrganizer(self):

        # Locate the organizer's copy of the event.
        yield self.getRecipientsCopy()
        if self.recipient_calendar is None:
            log.debug("ImplicitProcessing - originator '%s' to recipient '%s' ignoring UID: '%s' - organizer has no copy" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
            returnValue((True, True,))

        # Handle new items differently than existing ones.
        if self.method == "REPLY":
            result = (yield self.doImplicitOrganizerUpdate())
        elif self.method == "REFRESH":
            # With implicit we ignore refreshes.
            # TODO: for iMIP etc we do need to handle them 
            result = (True, True,)

        returnValue(result)

    @inlineCallbacks
    def doImplicitOrganizerUpdate(self):
        
        # Check to see if this is a valid reply
        result, processed_attendees = iTipProcessing.processReply(self.message, self.recipient_calendar)
        if result:
 
            # Update the attendee's copy of the event
            log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:REPLY, UID: '%s' - updating event" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
            recipient_calendar_resource = (yield self.writeCalendarResource(self.recipient_calendar_collection_uri, self.recipient_calendar_collection, self.recipient_calendar_name, self.recipient_calendar))
            result = (True, False,)
            
            self.updateAllAttendeesExceptSome(recipient_calendar_resource, processed_attendees)

        else:
            # Ignore scheduling message
            result = (True, True,)

        returnValue(result)

    def updateAllAttendeesExceptSome(self, resource, attendees):
        """
        Send an update out to all attendees except the specified ones, to refresh the others due to a change
        by that one.
        
        @param attendee: cu-addresses of attendees not to send to
        @type attendee: C{set}
        """
        
        from twistedcaldav.scheduling.implicit import ImplicitScheduler
        scheduler = ImplicitScheduler()
        scheduler.refreshAllAttendeesExceptSome(self.request, resource, self.recipient_calendar, attendees)

    @inlineCallbacks
    def doImplicitAttendee(self):

        # Locate the attendee's copy of the event if it exists.
        yield self.getRecipientsCopy()
        self.new_resource = self.recipient_calendar is None

        # Handle new items differently than existing ones.
        if self.new_resource and self.method == "CANCEL":
            result = (True, True,)
        else:
            result = (yield self.doImplicitAttendeeUpdate())
        
        returnValue(result)

    @inlineCallbacks
    def doImplicitAttendeeUpdate(self):
        
        # Different based on method
        if self.method == "REQUEST":
            result = (yield self.doImplicitAttendeRequest())
        elif self.method == "CANCEL":
            result = (yield self.doImplicitAttendeCancel())
        elif self.method == "ADD":
            # TODO: implement ADD
            result = (False, False,)
            
        returnValue(result)

    @inlineCallbacks
    def doImplicitAttendeRequest(self):

        # If there is no existing copy, then look for default calendar and copy it here
        if self.new_resource:
            
            # Check for default calendar
            default = (yield self.recipient.inbox.readProperty((caldav_namespace, "schedule-default-calendar-URL"), self.request))
            if len(default.children) == 1:
                defaultURL = str(default.children[0])
                default = (yield self.request.locateResource(defaultURL))
            else:
                default = None

            if default:
                log.debug("ImplicitProcessing - originator '%s' to recipient '%s' ignoring METHOD:REQUEST, UID: '%s' - new processed" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                new_calendar = iTipProcessing.processNewRequest(self.message)
                name =  md5(str(new_calendar) + str(time.time()) + default.fp.path).hexdigest() + ".ics"
                yield self.writeCalendarResource(defaultURL, default, name, new_calendar)
                result = (True, False,)
            else:
                log.debug("ImplicitProcessing - originator '%s' to recipient '%s' ignoring METHOD:REQUEST, UID: '%s' - new not processed" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                result = (False, False,)
        else:
            # Processing update to existing event
            new_calendar = iTipProcessing.processRequest(self.message, self.recipient_calendar)
            if new_calendar:
     
                # Update the attendee's copy of the event
                log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:REQUEST, UID: '%s' - updating event" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                yield self.writeCalendarResource(self.recipient_calendar_collection_uri, self.recipient_calendar_collection, self.recipient_calendar_name, new_calendar)
                result = (True, False,)
                
            else:
                # Request needs to be ignored
                log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:REQUEST, UID: '%s' - ignoring" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                result = (True, True,)

        returnValue(result)


    @inlineCallbacks
    def doImplicitAttendeCancel(self):

        # If there is no existing copy, then ignore
        if self.recipient_calendar is None:
            log.debug("ImplicitProcessing - originator '%s' to recipient '%s' ignoring METHOD:CANCEL, UID: '%s' - attendee has no copy" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
            result = (True, True,)
        else:
            # Check to see if this is a cancel of the entire event
            processed_message, delete_original = iTipProcessing.processCancel(self.message, self.recipient_calendar)
            if processed_message:
                if delete_original:
                    
                    # Delete the attendee's copy of the event
                    log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:CANCEL, UID: '%s' - deleting entire event" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                    yield self.deleteCalendarResource(self.recipient_calendar_collection, self.recipient_calendar_name)
                    result = (True, False,)
                    
                else:
         
                    # Update the attendee's copy of the event
                    log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:CANCEL, UID: '%s' - updating event" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                    yield self.writeCalendarResource(self.recipient_calendar_collection_uri, self.recipient_calendar_collection, self.recipient_calendar_name, self.recipient_calendar)
                    result = (True, False,)
            else:
                log.debug("ImplicitProcessing - originator '%s' to recipient '%s' processing METHOD:CANCEL, UID: '%s' - ignoring" % (self.originator.cuaddr, self.recipient.cuaddr, self.uid))
                result = (True, True,)

        returnValue(result)

    @inlineCallbacks
    def writeCalendarResource(self, collURL, collection, name, calendar):
        """
        Write out the calendar resource (iTIP) message to the specified calendar, either over-writing the named
        resource or by creating a new one.
        
        @param collURL: the C{str} containing the URL of the calendar collection.
        @param collection: the L{CalDAVFile} for the calendar collection to store the resource in.
        @param name: the C{str} for the resource name to write into, or {None} to write a new resource.
        @param calendar: the L{Component} calendar to write.
        @return: L{Deferred} -> L{CalDAVFile}
        """
        
        # Create a new name if one was not provided
        if name is None:
            name =  md5(str(calendar) + str(time.time()) + collection.fp.path).hexdigest() + ".ics"
    
        # Get a resource for the new item
        newchildURL = joinURL(collURL, name)
        newchild = yield self.request.locateResource(newchildURL)
        
        # Now write it to the resource
        from twistedcaldav.method.put_common import StoreCalendarObjectResource
        yield StoreCalendarObjectResource(
                     request=self.request,
                     destination = newchild,
                     destination_uri = newchildURL,
                     destinationparent = collection,
                     destinationcal = True,
                     calendar = calendar,
                     isiTIP = False,
                     allowImplicitSchedule = False
                 ).run()
    
        returnValue(newchild)

    @inlineCallbacks
    def deleteCalendarResource(self, collection, name):
        """
        Delete the calendar resource in the specified calendar.
        
        @param collection: the L{CalDAVFile} for the calendar collection to store the resource in.
        @param name: the C{str} for the resource name to write into, or {None} to write a new resource.
        @return: L{Deferred}
        """
        
        delchild = collection.getChild(name)
        index = collection.index()
        index.deleteResource(delchild.fp.basename())
        
        yield delete("", delchild.fp, "0")
        
        # Change CTag on the parent calendar collection
        yield collection.updateCTag()
