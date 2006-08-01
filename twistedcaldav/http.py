##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

__version__ = "0.0"

__all__ = ["ScheduleResponseResponse", "ScheduleResponseQueue"]


from twisted.python import log
from twisted.python.failure import Failure
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.http import errorForFailure, messageForFailure, statusForFailure
from twisted.web2.http import Response
from twisted.web2.http_headers import MimeType

from twistedcaldav import caldavxml

class ScheduleResponseResponse (Response):
    """
    ScheduleResponse L{Response} object.
    Renders itself as a CalDAV:schedule-response XML document.
    """
    def __init__(self, xml_responses, location=None):
        """
        @param xml_responses: an interable of davxml.Response objects.
        @param location:      the value of the location header to return in the response,
                              or None.
         """

        Response.__init__(self, code=responsecode.OK,
                          stream=caldavxml.ScheduleResponse(*xml_responses).toxml())

        self.headers.setHeader("content-type", MimeType("text", "xml"))
    
        if location is not None:
            self.headers.setHeader("location", location)

class ScheduleResponseQueue (object):
    """
    Stores a list of (typically error) responses for use in a
    L{ScheduleResponse}.
    """
    def __init__(self, method, success_response):
        """
        @param method: the name of the method generating the queue.
        @param success_response: the response to return in lieu of a
            L{ScheduleResponse} if no responses are added to this queue.
        """
        self.responses         = []
        self.method            = method
        self.success_response  = success_response
        self.location          = None

    def setLocation(self, location):
        """
        @param location:      the value of the location header to return in the response,
                              or None.
        """
        self.location = location

    def add(self, recipient, what, reqstatus=None, calendar=None):
        """
        Add a response.
        @param recipient: the recipient for this response.
        @param what: a status code or a L{Failure} for the given recipient.
        @param status: the iTIP request-status for the given recipient.
        @param calendar: the calendar data for the given recipient response.
        """
        if type(what) is int:
            code    = what
            error   = None
            message = responsecode.RESPONSES[code]
        elif isinstance(what, Failure):
            code    = statusForFailure(what)
            error   = errorForFailure(what)
            message = messageForFailure(what)
        else:
            raise AssertionError("Unknown data type: %r" % (what,))

        if code > 400: # Error codes only
            log.err("Error during %s for %s: %s" % (self.method, recipient, message))

        children = []
        children.append(caldavxml.Recipient(davxml.HRef.fromString(recipient)))
        children.append(caldavxml.RequestStatus(reqstatus))
        if calendar is not None:
            children.append(caldavxml.CalendarData.fromCalendar(calendar))
        if error is not None:
            children.append(error)
        if message is not None:
            children.append(davxml.ResponseDescription(message))
        self.responses.append(caldavxml.Response(*children))

    def response(self):
        """
        Generate a L{ScheduleResponseResponse} with the responses contained in the
        queue or, if no such responses, return the C{success_response} provided
        to L{__init__}.
        @return: the response.
        """
        if self.responses:
            return ScheduleResponseResponse(self.responses, self.location)
        else:
            return self.success_response

