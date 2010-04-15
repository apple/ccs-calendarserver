##
# Copyright (c) 2006-2009 Apple Inc. All rights reserved.
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
CardDAV multiget report
"""

__all__ = ["report_urn_ietf_params_xml_ns_carddav_addressbook_multiget"]

from urllib import unquote

from twisted.internet.defer import inlineCallbacks, returnValue

from twext.python.log import Logger
from twext.web2 import responsecode
from twext.web2.dav import davxml
from twext.web2.dav.element.base import dav_namespace
from twext.web2.dav.http import ErrorResponse, MultiStatusResponse
from twext.web2.dav.resource import AccessDeniedError
from twext.web2.dav.util import joinURL
from twext.web2.http import HTTPError, StatusResponse

from twistedcaldav import carddavxml
from twistedcaldav.config import config
from twistedcaldav.carddavxml import carddav_namespace
from twistedcaldav.method import report_common

log = Logger()

max_number_of_addressbook_multigets = 5000

@inlineCallbacks
def report_urn_ietf_params_xml_ns_carddav_addressbook_multiget(self, request, multiget):
    """
    Generate a multiget REPORT.
    (CardDAV, section 8.7)
    """

    # Verify root element
    if multiget.qname() != (carddav_namespace, "addressbook-multiget"):
        raise ValueError("{CardDAV:}addressbook-multiget expected as root element, not %s." % (multiget.sname(),))

    # Make sure target resource is of the right type
    if not self.isCollection():
        parent = (yield self.locateParent(request, request.uri))
        if not parent.isAddressBookCollection():
            log.err("addressbook-multiget report is not allowed on a resource outside of an address book collection %s" % (self,))
            raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Must be address book resource"))

    responses = []

    propertyreq = multiget.property
    resources  = multiget.resources
    
    if not hasattr(request, "extendedLogItems"):
        request.extendedLogItems = {}
    request.extendedLogItems["rcount"] = len(resources)
    
    # Check size of results is within limit
    if len(resources) > max_number_of_addressbook_multigets:
        log.err("Too many results in multiget report: %d" % len(resources))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, davxml.NumberOfMatchesWithinLimits()))

    if propertyreq.qname() == ("DAV:", "allprop"):
        propertiesForResource = report_common.allPropertiesForResource

    elif propertyreq.qname() == ("DAV:", "propname"):
        propertiesForResource = report_common.propertyNamesForResource

    elif propertyreq.qname() == ("DAV:", "prop"):
        propertiesForResource = report_common.propertyListForResource
        
        # Verify that any address-data element matches what we can handle
        result, message, _ignore = report_common.validPropertyListAddressDataTypeVersion(propertyreq)
        if not result:
            log.err(message)
            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (carddav_namespace, "supported-address-data")))
    else:
        raise AssertionError("We shouldn't be here")

    # Check size of results is within limit
    if len(resources) > config.MaxAddressBookMultigetHrefs:
        log.err("Too many results in multiget report: %d" % len(resources))
        raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (dav_namespace, "number-of-matches-within-limits")))

    """
    Three possibilities exist:
        
        1. The request-uri is an address book collection, in which case all the hrefs
        MUST be one-level below that collection and must be address book object resources.
        
        2. The request-uri is a regular collection, in which case all the hrefs
        MUST be children of that (at any depth) but MUST also be address book object
        resources (i.e. immediate child of an address book collection).
        
        3. The request-uri is a resource, in which case there MUST be
        a single href equal to the request-uri, and MUST be an address book
        object resource.
    """

    disabled = False
    if self.isAddressBookCollection():
        requestURIis = "addressbook"

        # Do some optimisation of access control calculation by determining any inherited ACLs outside of
        # the child resource loop and supply those to the checkPrivileges on each child.
        filteredaces = (yield self.inheritedACEsforChildren(request))
    
        # Check for disabled access
        if filteredaces is None:
            disabled = True

    elif self.isCollection():
        requestURIis = "collection"
        filteredaces = None
        lastParent = None
    else:
        requestURIis = "resource"
        filteredaces = None

    if not disabled:
        
        @inlineCallbacks
        def doAddressBookResponse():
            
            directoryAddressBookLock = None
            try: 
                # for directory address book, get requested resources
                done = False
                if self.isDirectoryBackedAddressBookCollection() and self.directory.liveQuery:
                    
                    # Verify that requested resources are immediate children of the request-URI
                    # and get vCardFilters ;similar to "normal" case below but do not call getChild()
                    vCardFilters = []
                    valid_hrefs = []
                    for href in resources:
                        resource_uri = str(href)
                        resource_name = unquote(resource_uri[resource_uri.rfind("/") + 1:])
                        if self._isChildURI(request, resource_uri) and resource_name.endswith(".vcf") and len(resource_name) > 4:
                            valid_hrefs.append(href)
                            vCardFilters.append(carddavxml.PropertyFilter(
                                                    carddavxml.TextMatch.fromString(resource_name[:-4]), 
                                                    name="UID", # attributes
                                                ))
                        elif not self.directory.cacheQuery:
                            responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                           
                    # exit if not valid           
                    if not vCardFilters or not valid_hrefs:
                        returnValue( None )
                         
                    addressBookFilter = carddavxml.Filter( *vCardFilters )
                    if self.directory.cacheQuery:
                        # add vcards to directory address book and run "normal case" below
                        limit = 0 #config.MaxAddressBookMultigetHrefs
                        directoryAddressBookLock, limited = (yield  self.directory.cacheVCardsForAddressBookQuery(addressBookFilter, propertyreq, limit) )
                        if limited:
                            log.err("Too many results in multiget report: %d" % len(resources))
                            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (dav_namespace, "number-of-matches-within-limits")))
                    else:
                        #get vCards and filter
                        limit = 0 #config.MaxAddressBookMultigetHrefs
                        vCardRecords, limited = (yield self.directory.vCardRecordsForAddressBookQuery( addressBookFilter, propertyreq, limit ))
                        if limited:
                            log.err("Too many results in multiget report: %d" % len(resources))
                            raise HTTPError(ErrorResponse(responsecode.FORBIDDEN, (dav_namespace, "number-of-matches-within-limits")))
                       
                        for href in valid_hrefs:
                            matchingRecord = None
                            for vCardRecord in vCardRecords:
                                if href == vCardRecord.hRef(): # might need to compare urls instead - also case sens ok?
                                    matchingRecord = vCardRecord
                                    break;

                            if matchingRecord:
                                yield report_common.responseForHrefAB(request, responses, href, matchingRecord, propertiesForResource, propertyreq, vcard=matchingRecord.vCard())
                            else:
                                responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                        # done with live, noncaching directoryBackedAddressBook query
                        done = True
                        
                if not done: 
                    # "normal" case
                    
                    # Verify that requested resources are immediate children of the request-URI
                    valid_names = []
                    for href in resources:
                        resource_uri = str(href)
                        name = unquote(resource_uri[resource_uri.rfind("/") + 1:])
                        if not self._isChildURI(request, resource_uri) or self.getChild(name) is None:
                            responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                        else:
                            valid_names.append(name)
                    if not valid_names:
                        returnValue( None )
                
                    # Verify that valid requested resources are address book objects
                    exists_names = tuple(self.index().resourcesExist(valid_names))
                    checked_names = []
                    for name in valid_names:
                        if name not in exists_names:
                            href = davxml.HRef.fromString(joinURL(request.uri, name))
                            responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                        else:
                            checked_names.append(name)
                    if not checked_names:
                        returnValue( None )
                    
                    # Now determine which valid resources are readable and which are not
                    ok_resources = []
                    bad_resources = []
                    yield self.findChildrenFaster(
                        "1",
                        request,
                        lambda x, y: ok_resources.append((x, y)),
                        lambda x, y: bad_resources.append((x, y)),
                        checked_names,
                        (davxml.Read(),),
                        inherited_aces=filteredaces
                    )
        
                    # Get properties for all valid readable resources
                    for resource, href in ok_resources:
                        try:
                            yield report_common.responseForHrefAB(request, responses, davxml.HRef.fromString(href), resource, propertiesForResource, propertyreq)
                        except ValueError:
                            log.err("Invalid address resource during multiget: %s" % (href,))
                            responses.append(davxml.StatusResponse(davxml.HRef.fromString(href), davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                        except IOError:
                            # This can happen because of a race-condition between the
                            # time we determine which resources exist and the deletion
                            # of one of these resources in another request.  In this
                            # case, return a 404 for the now missing resource rather
                            # than raise an error for the entire report.
                            log.err("Missing calendar resource during multiget: %s" % (href,))
                            responses.append(davxml.StatusResponse(davxml.HRef.fromString(href), davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                                        
                            # Indicate error for all valid non-readable resources
                            for ignore_resource, href in bad_resources: #@UnusedVariable
                                responses.append(davxml.StatusResponse(davxml.HRef.fromString(href), davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
            
            finally:
                if directoryAddressBookLock:
                    yield directoryAddressBookLock.release()
    

        if requestURIis == "addressbook":
            yield doAddressBookResponse()
        else:
            for href in resources:
    
                resource_uri = str(href)
    
                # Do href checks
                if requestURIis == "addressbook":
                    pass
        
                # TODO: we can optimize this one in a similar manner to the address book case
                elif requestURIis == "collection":
                    name = unquote(resource_uri[resource_uri.rfind("/") + 1:])
                    if not self._isChildURI(request, resource_uri, False):
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                        continue
     
                    child = (yield request.locateResource(resource_uri))
    
                    if not child or not child.exists():
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                        continue
    
                    parent = (yield child.locateParent(request, resource_uri))
    
                    if not parent.isAddressBookCollection() or not parent.index().resourceExists(name):
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                        continue
                    
                    # Check privileges on parent - must have at least DAV:read
                    try:
                        yield parent.checkPrivileges(request, (davxml.Read(),))
                    except AccessDeniedError:
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                        continue
                    
                    # Cache the last parent's inherited aces for checkPrivileges optimization
                    if lastParent != parent:
                        lastParent = parent
                
                        # Do some optimisation of access control calculation by determining any inherited ACLs outside of
                        # the child resource loop and supply those to the checkPrivileges on each child.
                        filteredaces = (yield parent.inheritedACEsforChildren(request))
        
                else:
                    name = unquote(resource_uri[resource_uri.rfind("/") + 1:])
                    if (resource_uri != request.uri) or not self.exists():
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.NOT_FOUND)))
                        continue
    
                    parent = (yield self.locateParent(request, resource_uri))
    
                    if not parent.isAddressBookCollection() or not parent.index().resourceExists(name):
                        responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                        continue
                    child = self
            
                    # Do some optimisation of access control calculation by determining any inherited ACLs outside of
                    # the child resource loop and supply those to the checkPrivileges on each child.
                    filteredaces = (yield parent.inheritedACEsforChildren(request))
        
                # Check privileges - must have at least DAV:read
                try:
                    yield child.checkPrivileges(request, (davxml.Read(),), inherited_aces=filteredaces)
                except AccessDeniedError:
                    responses.append(davxml.StatusResponse(href, davxml.Status.fromResponseCode(responsecode.FORBIDDEN)))
                    continue
        
                yield report_common.responseForHrefAB(request, responses, href, child, propertiesForResource, propertyreq)

    returnValue(MultiStatusResponse(responses))
