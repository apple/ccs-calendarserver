##
# Copyright (c) 2009 Apple Inc. All rights reserved.
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
Calendar Server Web Admin helper.
"""

__all__ = [
    "ResourceWrapper",
]


import os

from calendarserver.provision.root import RootResource

from twistedcaldav import memcachepool
from twistedcaldav.log import setLogLevelForNamespace
from twistedcaldav.static import CalendarHomeProvisioningFile

from twisted.internet.address import IPv4Address
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.reflect import namedClass
from twisted.web2.dav import davxml


@inlineCallbacks
def search(directory, searchStr):
    fields = []
    for fieldName in ("fullName", "firstName", "lastName", "emailAddresses"):
        fields.append((fieldName, searchStr, True, "contains"))
    
    records = list((yield directory.recordsMatchingFields(fields)))
    returnValue(records)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

class ResourceWrapper(object):

    def __init__(self, resource):
        self.resource = resource

    def readProperty(self, prop):
        return self.resource.readProperty(prop, FakeRequest())

    def writeProperty(self, prop):
        return self.resource.writeProperty(prop, FakeRequest())

    def lookupResource(self, specifier):
        # For now, support GUID lookup
        return self.getChild("principals/__uids__/%s" % (specifier,))

    def getChild(self, path):
        resource = self.resource
        segments = path.strip("/").split("/")
        for segment in segments:
            resource = resource.getChild(segment)
            if resource is None:
                return None
        return ResourceWrapper(resource)

    @inlineCallbacks
    def removeDelegate(self, delegate, permission):
        subPrincipalName = "calendar-proxy-%s" % (permission,)
        subPrincipal = self.getChild(subPrincipalName)
        if subPrincipal is None:
            abort("No proxy subprincipal found for %s" % (self.resource,))

        namespace, name = davxml.dav_namespace, "group-member-set"
        prop = (yield subPrincipal.readProperty((namespace, name)))
        newChildren = []
        for child in prop.children:
            if str(child) != delegate.url():
                newChildren.append(child)

        if len(prop.children) == len(newChildren):
            # Nothing to do -- the delegate wasn't there
            returnValue(False)

        newProp = davxml.GroupMemberSet(*newChildren)
        result = (yield subPrincipal.writeProperty(newProp))
        returnValue(result)

    @inlineCallbacks
    def addDelegate(self, delegate, permission):

        opposite = "read" if permission == "write" else "write"
        result = (yield self.removeDelegate(delegate, opposite))

        subPrincipalName = "calendar-proxy-%s" % (permission,)
        subPrincipal = self.getChild(subPrincipalName)
        if subPrincipal is None:
            abort("No proxy subprincipal found for %s" % (self.resource,))

        namespace, name = davxml.dav_namespace, "group-member-set"
        prop = (yield subPrincipal.readProperty((namespace, name)))
        for child in prop.children:
            if str(child) == delegate.url():
                # delegate is already in the group
                break
        else:
            # delegate is not already in the group
            newChildren = list(prop.children)
            newChildren.append(davxml.HRef(delegate.url()))
            newProp = davxml.GroupMemberSet(*newChildren)
            result = (yield subPrincipal.writeProperty(newProp))
            returnValue(result)

    @inlineCallbacks
    def getDelegates(self, permission):

        subPrincipalName = "calendar-proxy-%s" % (permission,)
        subPrincipal = self.getChild(subPrincipalName)
        if subPrincipal is None:
            abort("No proxy subprincipal found for %s" % (self.resource,))

        namespace, name = davxml.dav_namespace, "group-member-set"
        prop = (yield subPrincipal.readProperty((namespace, name)))
        result = []
        for child in prop.children:
            result.append(str(child))
        returnValue(result)

    def setAutoSchedule(self, autoSchedule):
        return self.resource.setAutoSchedule(autoSchedule)

    def getAutoSchedule(self):
        return self.resource.getAutoSchedule()

    def url(self):
        return self.resource.url()

class FakeRequest(object):
    pass

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

