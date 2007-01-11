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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
Implements drop-box functionality. A drop box is an external attachment store that provides
for automatic notification of changes to subscribed users.
"""

__all__ = [
    "DropBoxHomeResource",
    "DropBoxCollectionResource",
    "DropBoxChildResource",
]

import datetime
import md5
import time

from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.python import log
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.http import HTTPError, ErrorResponse, StatusResponse
from twisted.web2.dav.resource import DAVResource, DAVPrincipalResource, TwistedACLInheritable
from twisted.web2.dav.util import davXMLFromStream, parentForURL

from twistedcaldav import customxml
from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace

class DropBoxHomeResource (DAVResource):
    """
    Drop box collection resource.
    """
    def resourceType(self):
        return davxml.ResourceType.dropboxhome

    def isCollection(self):
        return True

class DropBoxCollectionResource (DAVResource):
    """
    Drop box resource.
    """
    def resourceType(self):
        return davxml.ResourceType.dropbox

    def isCollection(self):
        return True

    def writeNewACEs(self, newaces):
        """
        Write a new ACL to the resource's property store. We override this for calendar collections
        and force all the ACEs to be inheritable so that all calendar object resources within the
        calendar collection have the same privileges unless explicitly overridden. The same applies
        to drop box collections as we want all resources (attachments) to have the same privileges as
        the drop box collection.
        
        @param newaces: C{list} of L{ACE} for ACL being set.
        """
        # Add inheritable option to each ACE in the list
        edited_aces = []
        for ace in newaces:
            if TwistedACLInheritable() not in ace.children:
                children = list(ace.children)
                children.append(TwistedACLInheritable())
                edited_aces.append(davxml.ACE(*children))
            else:
                edited_aces.append(ace)
        
        # Do inherited with possibly modified set of aces
        super(DropBoxCollectionResource, self).writeNewACEs(edited_aces)

    def doNotification(self, request, myURI):
        """
        
        @param childURI: URI of the child that changed and triggered the notification.
        """
        # First determine which principals should get notified
        #
        # Procedure:
        #
        # 1. Get the list of auto-subscribed principals from the parent collection property.
        # 2. Expand any group principals in the list into their user principals.
        # 3. Get the list of unsubscribed principals from the parent collection property.
        # 4. Expand any group principals in the list into their user principals.
        # 5. Generate a set from the difference between the subscribed list and unsubscribed list.
        
        def _expandPrincipals(principals):
            result = []
            for principal in principals:

                principal = waitForDeferred(self.resolvePrincipal(principal.children[0], request))
                yield principal
                principal = principal.getResult()
                if principal is None:
                    continue
        
                presource = waitForDeferred(request.locateResource(str(principal)))
                yield presource
                presource = presource.getResult()
        
                if not isinstance(presource, DAVPrincipalResource):
                    continue
                
                # Step 2. Expand groups.
                members = presource.groupMembers()
                
                if members:
                    for member in members:
                        result.append(davxml.Principal(davxml.HRef.fromString(member)))
                else:
                    result.append(davxml.Principal(principal))
            yield result

        _expandPrincipals = deferredGenerator(_expandPrincipals)

        # For drop box we look at the parent collection of the target resource and get the
        # set of subscribed principals.
        if not config.NotificationsEnabled or not self.hasDeadProperty(customxml.Subscribed):
            yield None
            return

        principals = set()
        autosubs = self.readDeadProperty(customxml.Subscribed).children
        d = waitForDeferred(_expandPrincipals(autosubs))
        yield d
        autosubs = d.getResult()
        principals.update(autosubs)
        
        for principal in principals:
            if not isinstance(principal.children[0], davxml.HRef):
                continue
            purl = str(principal.children[0])
            d = waitForDeferred(request.locateResource(purl))
            yield d
            presource = d.getResult()

            collectionURL = presource.notificationsURL()
            if collectionURL is None:
                continue
            d = waitForDeferred(request.locateResource(collectionURL))
            yield d
            collection = d.getResult()

            name = "%s.xml" % (md5.new(str(self) + str(time.time()) + collectionURL).hexdigest(),)
    
            # Create new resource in the collection
            d = waitForDeferred(request.locateChildResource(collection, name))    # This ensures the URI for the resource is mapped
            yield d
            child = d.getResult()

            d = waitForDeferred(child.create(request, datetime.datetime.utcnow(), myURI))
            yield d
            d.getResult()
        
    doNotification = deferredGenerator(doNotification)

    def http_DELETE(self, request):
        #
        # Handle notification of this drop box collection being deleted
        #

        def gotResponse(response):
            if response in (responsecode.OK, responsecode.NO_CONTENT):
                d = self.doNotification(request, request.uri)
                d.addCallback(lambda _: response)
            return d

        d = super(DropBoxCollectionResource, self).http_DELETE(request)
        d.addCallback(gotResponse)
        return d
        
    def http_PUT(self, request):
        return ErrorResponse(
            responsecode.FORBIDDEN,
            (calendarserver_namespace, "valid-drop-box")
        )

    def http_MKCALENDAR (self, request):
        return ErrorResponse(
            responsecode.FORBIDDEN,
            (calendarserver_namespace, "valid-drop-box")
        )

    def http_POST(self, request):
        """
        Handle subscribe/unsubscribe requests only.
        """
        
        # Read request body
        try:
            doc = waitForDeferred(davXMLFromStream(request.stream))
            yield doc
            doc = doc.getResult()
        except ValueError, e:
            error = "Must have valid XML request body for POST on a dropbox: %s" % (e,)
            log.err(error)
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, error))
        
        # Determine whether we are subscribing or unsubscribing and handle that
        if doc is not None:
            root = doc.root_element
            if isinstance(root, customxml.Subscribe):
                action = self.subscribe
            elif isinstance(root, customxml.Unsubscribe):
                action = self.unsubscribe
            else:
                error = "XML request body for POST on a dropbox must contain a single <subscribe> or <unsubscribe> element"
                log.err(error)
                raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, error))
        else:
            # If we get here we got an invalid request
            error = "Must have valid XML request body for POST on a dropbox"
            log.err(error)
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, error))

        d = waitForDeferred(action(request))
        yield d
        result = d.getResult()
        yield result

    http_POST = deferredGenerator(http_POST)

    def subscribe(self, request):
        d = waitForDeferred(self.authorize(request, (davxml.Read(),)))
        yield d
        d.getResult()
        authid = request.authnUser
    
        # Get current list of subscribed principals
        principals = []
        if self.hasDeadProperty(customxml.Subscribed):
            subs = self.readDeadProperty(customxml.Subscribed).children
            principals.extend(subs)
    
        # Error if attempt to subscribe more than once
        if authid in principals:
            log.err("Cannot x_apple_subscribe to resource %s as principal %s is already subscribed" % (request.uri, repr(authid),))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (calendarserver_namespace, "principal-must-not-be-subscribed"))
            )

        principals.append(authid)
        self.writeDeadProperty(customxml.Subscribed(*principals))

        yield responsecode.OK

    subscribe = deferredGenerator(subscribe)

    def unsubscribe(self, request):
        # We do not check any privileges. If a principal is subscribed we always allow them to
        # unsubscribe provided they have at least authenticated.
        d = waitForDeferred(self.authorize(request, ()))
        yield d
        d.getResult()
        authid = request.authnUser
    
        # Get current list of subscribed principals
        principals = []
        if self.hasDeadProperty(customxml.Subscribed):
            subs = self.readDeadProperty(customxml.Subscribed).children
            principals.extend(subs)
    
        # Error if attempt to subscribe more than once
        if authid not in principals:
            log.err("Cannot x_apple_unsubscribe from resource %s as principal %s is not currently subscribed" % (request.uri, repr(authid),))
            raise HTTPError(ErrorResponse(
                responsecode.FORBIDDEN,
                (calendarserver_namespace, "principal-must-be-subscribed"))
            )

        principals.remove(authid)
        self.writeDeadProperty(customxml.Subscribed(*principals))

        yield responsecode.OK

    unsubscribe = deferredGenerator(unsubscribe)

class DropBoxChildResource (DAVResource):
    def http_MKCOL(self, request):
        return ErrorResponse(
            responsecode.FORBIDDEN,
            (calendarserver_namespace, "valid-drop-box-resource")
        )
    def http_MKCALENDAR (self, request):
        return ErrorResponse(
            responsecode.FORBIDDEN,
            (calendarserver_namespace, "valid-drop-box-resource")
        )

    def http_PUT(self, request):
        #
        # Handle notificiations
        #
        parentURL=parentForURL(request.uri)

        def gotParent(parent):
            def gotResponse(response):
                if response.code in (responsecode.OK, responsecode.CREATED, responsecode.NO_CONTENT):
                    d = parent.doNotification(request, parentURL)
                    d.addCallback(lambda _: response)
                    return d

            d = super(DropBoxChildResource, self).http_PUT(request)
            d.addCallback(gotResponse)
            return d

        d = request.locateResource(parentURL)
        d.addCallback(gotParent)
        return d

    def http_DELETE(self, request):
        #
        # Handle notificiations
        #
        parentURL=parentForURL(request.uri)

        def gotParent(parent):
            def gotResponse(response):
                if response in (responsecode.OK, responsecode.NO_CONTENT):
                    d = parent.doNotification(request, parentURL)
                    d.addCallback(lambda _: response)
                    return d

            d = super(DropBoxChildResource, self).http_DELETE(request)
            d.addCallback(gotResponse)
            return d

        d = request.locateResource(parentURL)
        d.addCallback(gotParent)
        return d
        
