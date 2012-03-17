##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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
DAV sync-collection report
"""

__all__ = ["report_DAV__sync_collection"]

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.failure import Failure

from twext.python.log import Logger
from txdav.xml import element
from twext.web2.dav.http import ErrorResponse
from twext.web2 import responsecode
from twext.web2.dav.http import MultiStatusResponse, statusForFailure
from twext.web2.dav.method.prop_common import responseForHref
from twext.web2.dav.method.propfind import propertyName
from twext.web2.dav.util import joinURL
from twext.web2.http import HTTPError, StatusResponse

from twistedcaldav.config import config

from txdav.common.icommondatastore import ConcurrentModification

import functools

log = Logger()

@inlineCallbacks
def report_DAV__sync_collection(self, request, sync_collection):
    """
    Generate a sync-collection REPORT.
    """
    
    # These resource support the report
    if not config.EnableSyncReport or element.Report(element.SyncCollection(),) not in self.supportedReports():
        log.err("sync-collection report is only allowed on calendar/inbox/addressbook/notification collection resources %s" % (self,))
        raise HTTPError(ErrorResponse(
            responsecode.FORBIDDEN,
            element.SupportedReport(),
            "Report not supported on this resource",
        ))
   
    responses = []

    # Process Depth and sync-level for backwards compatibility
    # Use sync-level if present and ignore Depth, else use Depth
    if sync_collection.sync_level:
        depth = sync_collection.sync_level
        descriptor = "DAV:sync-level"
    else:
        depth = request.headers.getHeader("depth", None)
        descriptor = "Depth header without DAV:sync-level"
    
    if depth not in ("1", "infinity"):
        log.err("sync-collection report with invalid depth header: %s" % (depth,))
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "Invalid %s value" % (descriptor,)))
        
    propertyreq = sync_collection.property.children if sync_collection.property else None 
    
    @inlineCallbacks
    def _namedPropertiesForResource(request, props, resource, forbidden=False):
        """
        Return the specified properties on the specified resource.
        @param request: the L{IRequest} for the current request.
        @param props: a list of property elements or qname tuples for the properties of interest.
        @param resource: the L{DAVResource} for the targeted resource.
        @return: a map of OK and NOT FOUND property values.
        """
        properties_by_status = {
            responsecode.OK        : [],
            responsecode.FORBIDDEN : [],
            responsecode.NOT_FOUND : [],
        }
        
        for property in props:
            if isinstance(property, element.WebDAVElement):
                qname = property.qname()
            else:
                qname = property

            if forbidden:
                properties_by_status[responsecode.FORBIDDEN].append(propertyName(qname))
            else:
                props = (yield resource.listProperties(request))
                if qname in props:
                    try:
                        prop = (yield resource.readProperty(qname, request))
                        properties_by_status[responsecode.OK].append(prop)
                    except:
                        f = Failure()
                        log.err("Error reading property %r for resource %s: %s" % (qname, request.uri, f.value))
                        status = statusForFailure(f, "getting property: %s" % (qname,))
                        if status not in properties_by_status: properties_by_status[status] = []
                        properties_by_status[status].append(propertyName(qname))
                else:
                    properties_by_status[responsecode.NOT_FOUND].append(propertyName(qname))
        
        returnValue(properties_by_status)
    
    # Do some optimization of access control calculation by determining any inherited ACLs outside of
    # the child resource loop and supply those to the checkPrivileges on each child.
    filteredaces = (yield self.inheritedACEsforChildren(request))

    changed, removed, notallowed, newtoken = yield self.whatchanged(sync_collection.sync_token, depth)

    # Now determine which valid resources are readable and which are not
    ok_resources = []
    forbidden_resources = []
    if changed:
        yield self.findChildrenFaster(
            depth,
            request,
            lambda x, y: ok_resources.append((x, y)),
            lambda x, y: forbidden_resources.append((x, y)),
            changed,
            (element.Read(),),
            inherited_aces=filteredaces
        )

    for child, child_uri in ok_resources:
        href = element.HRef.fromString(child_uri)
        try:
            yield responseForHref(
                request,
                responses,
                href,
                child,
                functools.partial(_namedPropertiesForResource, forbidden=False) if propertyreq else None,
                propertyreq)
        except ConcurrentModification:
            # This can happen because of a race-condition between the
            # time we determine which resources exist and the deletion
            # of one of these resources in another request.  In this
            # case, we ignore the now missing resource rather
            # than raise an error for the entire report.
            log.err("Missing resource during sync: %s" % (href,))

    for child, child_uri in forbidden_resources:
        href = element.HRef.fromString(child_uri)
        try:
            yield responseForHref(
                request,
                responses,
                href,
                child,
                functools.partial(_namedPropertiesForResource, forbidden=True) if propertyreq else None,
                propertyreq)
        except ConcurrentModification:
            # This can happen because of a race-condition between the
            # time we determine which resources exist and the deletion
            # of one of these resources in another request.  In this
            # case, we ignore the now missing resource rather
            # than raise an error for the entire report.
            log.err("Missing resource during sync: %s" % (href,))

    for name in removed:
        href = element.HRef.fromString(joinURL(request.uri, name))
        responses.append(element.StatusResponse(element.HRef.fromString(href), element.Status.fromResponseCode(responsecode.NOT_FOUND)))
    
    for name in notallowed:
        href = element.HRef.fromString(joinURL(request.uri, name))
        responses.append(element.StatusResponse(element.HRef.fromString(href), element.Status.fromResponseCode(responsecode.NOT_ALLOWED)))
    
    if not hasattr(request, "extendedLogItems"):
        request.extendedLogItems = {}
    request.extendedLogItems["responses"] = len(responses)

    responses.append(element.SyncToken.fromString(newtoken))

    returnValue(MultiStatusResponse(responses))
