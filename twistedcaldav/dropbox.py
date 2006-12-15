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
Implements drop-box functionality. A drop box is an external attachment store that provides
for automatic notification of changes to subscribed users.
"""

__all__ = [
    "DropBoxHomeResource",
]

from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.python import log
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.http import HTTPError, ErrorResponse
from twisted.web2.dav.resource import DAVResource, TwistedACLInheritable
from twisted.web2.dav.util import parentForURL

from twistedcaldav import customxml
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.notifications import Notification

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

    def http_DELETE(self, request):
        #
        # Handle notificiations
        #
        parentURL=parentForURL(request.uri)

        def gotParent(parent):
            def gotResponse(response):
                notification = Notification(parentURL=parentURL)
                d = notification.doNotification(request, parent)
                d.addCallback(lambda _: response)
                return d

            d = super(DropBoxCollectionResource, self).http_DELETE(request)
            d.addCallback(gotResponse)
            return d

        d = request.locateResource(parentURL)
        d.addCallback(gotParent)
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

    def http_X_APPLE_SUBSCRIBE(self, request):
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

    http_X_APPLE_SUBSCRIBE = deferredGenerator(http_X_APPLE_SUBSCRIBE)

    def http_X_APPLE_UNSUBSCRIBE(self, request):
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

    http_X_APPLE_UNSUBSCRIBE = deferredGenerator(http_X_APPLE_UNSUBSCRIBE)

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
                    notification = Notification(parentURL=parentForURL(request.uri))
                    d = notification.doNotification(request, parent)
                    d.addCallback(lambda _: response)
                    return d

            d = super(DropBoxChildResource, self).http_PUT(request)
            d.addCallback(gotResponse)
            return d

        d = request.locateResource(parentURL)
        d.addCallback(gotParent)
        return d
