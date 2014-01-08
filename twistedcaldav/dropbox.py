##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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
Implements drop-box functionality. A drop box is an external attachment store.
"""

__all__ = [
    "DropBoxHomeResource",
    "DropBoxCollectionResource",
]

from twext.python.log import Logger
from twext.web2 import responsecode
from txdav.xml import element as davxml
from twext.web2.dav.http import ErrorResponse
from twext.web2.dav.resource import DAVResource, TwistedACLInheritable
from twext.web2.dav.util import joinURL

from twisted.internet.defer import inlineCallbacks, returnValue

from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace

log = Logger()

class DropBoxHomeResource (DAVResource):
    """
    Drop box collection resource.
    """
    def resourceType(self):
        return davxml.ResourceType.dropboxhome #@UndefinedVariable

    def isCollection(self):
        return True

    def http_PUT(self, request):
        return responsecode.FORBIDDEN

    @inlineCallbacks
    def accessControlList(self, request, *args, **kwargs):
        """
        Override this to give write proxies DAV:write-acl privilege so they can add attachments too.
        """

        acl = (yield super(DropBoxHomeResource, self).accessControlList(request, *args, **kwargs))
        
        if config.EnableProxyPrincipals:
            owner = (yield self.ownerPrincipal(request))

            newaces = tuple(acl.children)
            newaces += (
                # DAV:write-acl access for this principal's calendar-proxy-write users.
                davxml.ACE(
                    davxml.Principal(davxml.HRef(joinURL(owner.principalURL(), "calendar-proxy-write/"))),
                    davxml.Grant(
                        davxml.Privilege(davxml.WriteACL()),
                    ),
                    davxml.Protected(),
                    TwistedACLInheritable(),
                ),
            )

            returnValue(davxml.ACL(*newaces))
        
        else:
            returnValue(acl)

class DropBoxCollectionResource (DAVResource):
    """
    Drop box resource.
    """

    def resourceType(self):
        return davxml.ResourceType.dropbox #@UndefinedVariable


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
        return super(DropBoxCollectionResource, self).writeNewACEs(edited_aces)


    def http_PUT(self, request):
        return ErrorResponse(
            responsecode.FORBIDDEN,
            (calendarserver_namespace, "valid-drop-box"),
            "Cannot store resources in dropbox",
        )
