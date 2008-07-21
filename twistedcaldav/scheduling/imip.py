##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks

from twisted.mail.smtp import messageid
from twisted.mail.smtp import rfc822date
from twisted.mail.smtp import sendmail

from twisted.python.failure import Failure

from twisted.web2 import responsecode
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.http import HTTPError

from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.config import config
from twistedcaldav.log import Logger
from twistedcaldav.scheduling.delivery import DeliveryService

import MimeWriter
import base64
import cStringIO
import datetime

"""
Class that handles delivery of scheduling messages via iMIP.
"""

__all__ = [
    "ScheduleViaIMip",
]

log = Logger()

class ScheduleViaIMip(DeliveryService):
    
    @classmethod
    def serviceType(cls):
        return DeliveryService.serviceType_imip

    @inlineCallbacks
    def generateSchedulingResponses(self):
        
        # Generate an HTTP client request
        try:
            # We do not do freebusy requests via iMIP
            if self.freebusy:
                raise ValueError("iMIP VFREEBUSY REQUESTs not supported.")

            message = self._generateTemplateMessage(self.scheduler.calendar)
            fromAddr = self.scheduler.originator.cuaddr
            if not fromAddr.startswith("mailto:"):
                raise ValueError("ORGANIZER address '%s' must be mailto: for iMIP operation." % (fromAddr,))
            fromAddr = fromAddr[7:]
            message = message.replace("${fromaddress}", fromAddr)
            
            for recipient in self.recipients:
                try:
                    toAddr = recipient.cuaddr
                    if not toAddr.startswith("mailto:"):
                        raise ValueError("ATTENDEE address '%s' must be mailto: for iMIP operation." % (toAddr,))
                    toAddr = toAddr[7:]
                    sendit = message.replace("${toaddress}", toAddr)
                    log.debug("Sending iMIP message To: '%s', From :'%s'\n%s" % (toAddr, fromAddr, sendit,))
                    yield sendmail(config.Scheduling[self.serviceType()]["Sending"]["Server"], fromAddr, toAddr, sendit, port=config.Scheduling[self.serviceType()]["Sending"]["Port"])
        
                except Exception, e:
                    # Generated failed response for this recipient
                    log.err("Could not do server-to-imip request : %s %s" % (self, e))
                    err = HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-failed")))
                    self.responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus="5.1;Service unavailable")
                
                else:
                    self.responses.add(recipient.cuaddr, responsecode.OK, reqstatus="2.0;Success")

        except Exception, e:
            # Generated failed responses for each recipient
            log.err("Could not do server-to-imip request : %s %s" % (self, e))
            for recipient in self.recipients:
                err = HTTPError(ErrorResponse(responsecode.FORBIDDEN, (caldav_namespace, "recipient-failed")))
                self.responses.add(recipient.cuaddr, Failure(exc_value=err), reqstatus="5.1;Service unavailable")

    def _generateTemplateMessage(self, calendar):

        caldata = str(calendar)
        data = cStringIO.StringIO()
        writer = MimeWriter.MimeWriter(data)
    
        writer.addheader("From", "${fromaddress}")
        writer.addheader("To", "${toaddress}")
        writer.addheader("Date", rfc822date())
        writer.addheader("Subject", "DO NOT REPLY: calendar invitation test")
        writer.addheader("Message-ID", messageid())
        writer.addheader("Mime-Version", "1.0")
        writer.flushheaders()
    
        writer.startmultipartbody("mixed")
    
        # message body
        part = writer.nextpart()
        body = part.startbody("text/plain")
        body.write("""Hi,
You've been invited to a cool event by CalendarServer's new iMIP processor.

%s
""" % (self._generateCalendarSummary(calendar),))
    
        part = writer.nextpart()
        encoding = "7bit"
        for i in caldata:
            if ord(i) > 127:
                encoding = "base64"
                caldata = base64.encodestring(caldata)
                break
        part.addheader("Content-Transfer-Encoding", encoding)
        body = part.startbody("text/calendar; charset=utf-8")
        body.write(caldata.replace("\r", ""))
    
        # finish
        writer.lastpart()

        return data.getvalue()

    def _generateCalendarSummary(self, calendar):

        # Get the most appropriate component
        component = calendar.masterComponent()
        if component is None:
            component = calendar.mainComponent(True)
            
        organizer = component.getOrganizerProperty()
        if "CN" in organizer.params():
            organizer = "%s <%s>" % (organizer.params()["CN"][0], organizer.value(),)
        else:
            organizer = organizer.value()
            
        dtinfo = self._getDateTimeInfo(component)
        
        summary = component.propertyValue("SUMMARY")
        if summary is None:
            summary = ""

        description = component.propertyValue("DESCRIPTION")
        if description is None:
            description = ""

        return """---- Begin Calendar Event Summary ----

Organizer:   %s
Summary:     %s
%sDescription: %s

----  End Calendar Event Summary  ----
""" % (organizer, summary, dtinfo, description,)

    def _getDateTimeInfo(self, component):
        
        dtstart = component.propertyNativeValue("DTSTART")
        tzid_start = component.getProperty("DTSTART").params().get("TZID", "UTC")

        dtend = component.propertyNativeValue("DTEND")
        if dtend:
            tzid_end = component.getProperty("DTEND").params().get("TZID", "UTC")
            duration = dtend - dtstart
        else:
            duration = component.propertyNativeValue("DURATION")
            if duration:
                dtend = dtstart + duration
                tzid_end = tzid_start
            else:
                if isinstance(dtstart, datetime.date):
                    dtend = None
                    duration = datetime.timedelta(days=1)
                else:
                    dtend = dtstart + datetime.timedelta(days=1)
                    dtend.hour = dtend.minute = dtend.second = 0
                    duration = dtend - dtstart
        result = "Starts:      %s\n" % (self._getDateTimeText(dtstart, tzid_start),)
        if dtend is not None:
            result += "Ends:        %s\n" % (self._getDateTimeText(dtend, tzid_end),)
        result += "Duration:    %s\n" % (self._getDurationText(duration),)
        
        if not isinstance(dtstart, datetime.datetime):
            result += "All Day\n"
        
        for property_name in ("RRULE", "RDATE", "EXRULE", "EXDATE", "RECURRENCE-ID",):
            if component.hasProperty(property_name):
                result += "Recurring\n"
                break
            
        return result

    def _getDateTimeText(self, dtvalue, tzid):
        
        if isinstance(dtvalue, datetime.datetime):
            timeformat = "%A, %B %e, %Y %I:%M %p"
        elif isinstance(dtvalue, datetime.date):
            timeformat = "%A, %B %e, %Y"
            tzid = ""
        if tzid:
            tzid = " (%s)" % (tzid,)

        return "%s%s" % (dtvalue.strftime(timeformat), tzid,)
        
    def _getDurationText(self, duration):
        
        result = ""
        if duration.days > 0:
            result += "%d %s" % (
                duration.days,
                self._pluralize(duration.days, "day", "days")
            )

        hours = duration.seconds / 3600
        minutes = divmod(duration.seconds / 60, 60)[1]
        seconds = divmod(duration.seconds, 60)[1]
        
        if hours > 0:
            if result:
                result += ", "
            result += "%d %s" % (
                hours,
                self._pluralize(hours, "hour", "hours")
            )
        
        if minutes > 0:
            if result:
                result += ", "
            result += "%d %s" % (
                minutes,
                self._pluralize(minutes, "minute", "minutes")
            )
        
        if seconds > 0:
            if result:
                result += ", "
            result += "%d %s" % (
                seconds,
                self._pluralize(seconds, "second", "seconds")
            )

        return result

    def _pluralize(self, number, unit1, unitS):
        return unit1 if number == 1 else unitS
