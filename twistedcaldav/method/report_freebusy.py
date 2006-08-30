##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
CalDAV freebusy report
"""

__version__ = "0.0"

__all__ = ["report_urn_ietf_params_xml_ns_caldav_free_busy_query"]

from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.python import log
from twisted.web2 import responsecode
from twisted.web2.dav.element.base import dav_namespace
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.method.report import NumberOfMatchesWithinLimits
from twisted.web2.http import HTTPError, Response, StatusResponse
from twisted.web2.http_headers import MimeType
from twisted.web2.stream import MemoryStream

from twistedcaldav import caldavxml
from twistedcaldav.method import report_common

def report_urn_ietf_params_xml_ns_caldav_free_busy_query(self, request, freebusy): #@UnusedVariable
    """
    Generate a free-busy REPORT.
    (CalDAV-access-09, section 7.8)
    """
    if not self.isCollection():
        log.err("freebusy report is only allowed on collection resources %s" % (self,))
        raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Not a calendar collection"))

    if freebusy.qname() != (caldavxml.caldav_namespace, "free-busy-query"):
        raise ValueError("{CalDAV:}free-busy-query expected as root element, not %s." % (freebusy.sname(),))

    timerange = freebusy.timerange
    if not timerange.valid():
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "Invalid time-range specified"))

    # First list is BUSY, second BUSY-TENTATIVE, third BUSY-UNAVAILABLE
    fbinfo = ([], [], [])
    
    matchcount = [0]
    def generateFreeBusyInfo(calresource, uri): #@UnusedVariable
        """
        Run a free busy report on the specified calendar collection
        accumulating the free busy info for later processing.
        @param calresource: the L{CalDAVFile} for a calendar collection.
        @param uri: the uri for the calendar collecton resource.
        """
        d = waitForDeferred(report_common.generateFreeBusyInfo(request, calresource, fbinfo, timerange, matchcount[0]))
        yield d
        matchcount[0] = d.getResult()
    
    generateFreeBusyInfo = deferredGenerator(generateFreeBusyInfo)

    # Run report taking depth into account
    try:
        depth = request.headers.getHeader("depth", "0")
        d = waitForDeferred(report_common.applyToCalendarCollections(self, request, request.uri, depth, generateFreeBusyInfo, (caldavxml.ReadFreeBusy(),)))
        yield d
        d.getResult()
    except NumberOfMatchesWithinLimits:
        log.err("Too many matching components in free-busy report")
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (dav_namespace, "number-of-matches-within-limits")))
    
    # Now build a new calendar object with the free busy info we have
    fbcalendar = report_common.buildFreeBusyResult(fbinfo, timerange)
    
    response = Response()
    response.stream = MemoryStream(str(fbcalendar))
    response.headers.setHeader("content-type", MimeType.fromString("text/calendar; charset=utf-8"))

    yield response

report_urn_ietf_params_xml_ns_caldav_free_busy_query = deferredGenerator(report_urn_ietf_params_xml_ns_caldav_free_busy_query)