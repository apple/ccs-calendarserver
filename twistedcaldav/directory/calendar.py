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
##

"""
Implements a directory-backed calendar hierarchy.
"""

__all__ = [
    "uidsResourceName",
    "DirectoryCalendarHomeProvisioningResource",
    "DirectoryCalendarHomeTypeProvisioningResource",
    "DirectoryCalendarHomeUIDProvisioningResource",
    "DirectoryCalendarHomeResource",
]

from twisted.internet.defer import succeed
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.http import HTTPError
from twisted.web2.dav.util import joinURL
from twisted.web2.dav.resource import TwistedACLInheritable, TwistedQuotaRootProperty

from twistedcaldav import caldavxml
from twistedcaldav.config import config
from twistedcaldav.dropbox import DropBoxHomeResource
from twistedcaldav.extensions import ReadOnlyResourceMixIn, DAVResource
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.schedule import ScheduleInboxResource, ScheduleOutboxResource
from twistedcaldav.directory.idirectory import IDirectoryService
from twistedcaldav.directory.resource import AutoProvisioningResourceMixIn

# Use __underbars__ convention to avoid conflicts with directory resource types.
uidsResourceName = "__uids__"

class DirectoryCalendarHomeProvisioningResource (AutoProvisioningResourceMixIn, ReadOnlyResourceMixIn, DAVResource):
    """
    Resource which provisions calendar home collections as needed.    
    """
    def __init__(self, directory, url):
        """
        @param directory: an L{IDirectoryService} to provision calendars from.
        @param url: the canonical URL for the resource.
        """
        assert directory is not None
        assert url.endswith("/"), "Collection URL must end in '/'"

        DAVResource.__init__(self)

        self.directory = IDirectoryService(directory)
        self._url = url

        # FIXME: Smells like a hack
        directory.calendarHomesCollection = self

        #
        # Create children
        #
        def provisionChild(name):
            self.putChild(name, self.provisionChild(name))

        for recordType in self.directory.recordTypes():
            provisionChild(recordType)

        provisionChild(uidsResourceName)

    def provisionChild(self, recordType):
        raise NotImplementedError("Subclass must implement provisionChild()")

    def url(self):
        return self._url

    def getChild(self, name):
        return self.putChildren.get(name, None)

    def listChildren(self):
        return self.directory.recordTypes()

    def principalCollections(self):
        # FIXME: directory.principalCollection smells like a hack
        # See DirectoryPrincipalProvisioningResource.__init__()
        return self.directory.principalCollection.principalCollections()

    def principalForRecord(self, record):
        # FIXME: directory.principalCollection smells like a hack
        # See DirectoryPrincipalProvisioningResource.__init__()
        return self.directory.principalCollection.principalForRecord(record)

    def homeForDirectoryRecord(self, record):
        uidResource = self.getChild(uidsResourceName)
        if uidResource is None:
            return None
        else:
            return uidResource.getChild(record.guid)

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    ##
    # ACL
    ##

    def defaultAccessControlList(self):
        return readOnlyACL

class DirectoryCalendarHomeTypeProvisioningResource (AutoProvisioningResourceMixIn, ReadOnlyResourceMixIn, DAVResource):
    """
    Resource which provisions calendar home collections of a specific
    record type as needed.
    """
    def __init__(self, parent, recordType):
        """
        @param parent: the parent of this resource
        @param recordType: the directory record type to provision.
        """
        assert parent is not None
        assert recordType is not None

        DAVResource.__init__(self)

        self.directory = parent.directory
        self.recordType = recordType
        self._parent = parent

    def url(self):
        return joinURL(self._parent.url(), self.recordType)

    def getChild(self, name, record=None):
        self.provision()
        if name == "":
            return self

        if record is None:
            record = self.directory.recordWithShortName(self.recordType, name)
            if record is None:
                return None

        return self._parent.homeForDirectoryRecord(record)

    def listChildren(self):
        return (
            record.shortName
            for record in self.directory.listRecords(self.recordType)
            if record.enabledForCalendaring
        )

    def createSimilarFile(self, path):
        raise HTTPError(responsecode.NOT_FOUND)

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    ##
    # ACL
    ##

    def defaultAccessControlList(self):
        return readOnlyACL

    def principalCollections(self):
        return self._parent.principalCollections()

    def principalForRecord(self, record):
        return self._parent.principalForRecord(record)


class DirectoryCalendarHomeUIDProvisioningResource (AutoProvisioningResourceMixIn, ReadOnlyResourceMixIn, DAVResource):
    def __init__(self, parent):
        """
        @param parent: the parent of this resource
        """
        assert parent is not None

        DAVResource.__init__(self)

        self.directory = parent.directory
        self.parent = parent

    def url(self):
        return joinURL(self.parent.url(), uidsResourceName)

    def getChild(self, name, record=None):
        self.provision()
        if name == "":
            return self

        if record is None:
            record = self.directory.recordWithGUID(name)
            if record is None:
                return None

        return self.provisionChild(name)

    def listChildren(self):
        # Not a listable collection
        raise HTTPError(responsecode.FORBIDDEN)

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    ##
    # ACL
    ##

    def defaultAccessControlList(self):
        return readOnlyACL

    def principalCollections(self):
        return self.parent.principalCollections()

    def principalForRecord(self, record):
        return self.parent.principalForRecord(record)


class DirectoryCalendarHomeResource (AutoProvisioningResourceMixIn, CalDAVResource):
    """
    Calendar home collection resource.
    """
    def __init__(self, parent, record):
        """
        @param path: the path to the file which will back the resource.
        """
        assert parent is not None
        assert record is not None

        CalDAVResource.__init__(self)

        self.record = record
        self.parent = parent

        # Cache children which must be of a specific type
        childlist = (
            ("inbox" , ScheduleInboxResource ),
            ("outbox", ScheduleOutboxResource),
        )
        if config.EnableDropBox:
            childlist += (
                ("dropbox", DropBoxHomeResource),
            )
        for name, cls in childlist:
            child = self.provisionChild(name)
            assert isinstance(child, cls), "Child %r is not a %s: %r" % (name, cls.__name__, child)
            self.putChild(name, child)

#    def provision(self):
#        # If an ACL property does not currently exist, create one from
#        # the defaultACL
#        if not self.hasDeadProperty(davxml.ACL):
#            self.writeDeadProperty(self.defaultAccessControlList())
#        
#        super(DirectoryCalendarHomeResource, self).provision()

    def provisionDefaultCalendars(self):
        self.provision()

        childName = "calendar"
        childURL = joinURL(self.url(), childName)
        child = self.provisionChild(childName)
        assert isinstance(child, CalDAVResource), "Child %r is not a %s: %r" % (childName, CalDAVResource.__name__, child)

        def setupChild(_):
            # Set calendar-free-busy-set on inbox
            inbox = self.getChild("inbox")
            # FIXME: Shouldn't have to call provision() on another resource
            # We cheat here because while inbox will auto-provision itself when located,
            # we need to write a dead property to it pre-emptively.
            # Possible fix: store the free/busy set property on this resource instead.
            inbox.provision()
            inbox.writeDeadProperty(caldavxml.CalendarFreeBusySet(davxml.HRef(childURL)))

            return self

        d = child.createCalendarCollection()
        d.addCallback(setupChild)
        return d

    def provisionChild(self, name):
        raise NotImplementedError("Subclass must implement provisionChild()")

    def url(self):
        return joinURL(self.parent.url(), self.record.guid)
        ##
        ## While the underlying primary location is GUID-based, we want
        ## the canonical user-facing location to be recordType &
        ## shortName-based, because that's friendlier.
        ##
        #return joinURL(self.parent.parent.getChild(self.record.recordType).url(), self.record.shortName)

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    ##
    # ACL
    ##

    def owner(self, request):
        return succeed(davxml.HRef(self.principalForRecord().principalURL()))

    def defaultAccessControlList(self):
        myPrincipal = self.principalForRecord()

        aces = (
            # DAV:read access for authenticated users.
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(davxml.Privilege(davxml.Read())),
            ),
            # Inheritable DAV:all access for the resource's associated principal.
            davxml.ACE(
                davxml.Principal(davxml.HRef(myPrincipal.principalURL())),
                davxml.Grant(davxml.Privilege(davxml.All())),
                davxml.Protected(),
                TwistedACLInheritable(),
            ),
            # Inheritable CALDAV:read-free-busy access for authenticated users.
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(davxml.Privilege(caldavxml.ReadFreeBusy())),
                TwistedACLInheritable(),
            ),
        )
        
        if config.EnableProxyPrincipals:
            aces += (
                # DAV:read access for this principal's calendar-proxy-read users.
                davxml.ACE(
                    davxml.Principal(davxml.HRef(joinURL(myPrincipal.principalURL(), "calendar-proxy-read/"))),
                    davxml.Grant(davxml.Privilege(davxml.Read())),
                    davxml.Protected(),
                    TwistedACLInheritable(),
                ),
                # DAV:read/DAV:write access for this principal's calendar-proxy-write users.
                davxml.ACE(
                    davxml.Principal(davxml.HRef(joinURL(myPrincipal.principalURL(), "calendar-proxy-write/"))),
                    davxml.Grant(davxml.Privilege(davxml.Read()), davxml.Privilege(davxml.Write())),
                    davxml.Protected(),
                    TwistedACLInheritable(),
                ),
            )

        return davxml.ACL(*aces)

    def principalCollections(self):
        return self.parent.principalCollections()

    def principalForRecord(self):
        return self.parent.principalForRecord(self.record)

    ##
    # Quota
    ##

    def hasQuotaRoot(self, request):
        """
        @return: a C{True} if this resource has quota root, C{False} otherwise.
        """
        return self.hasDeadProperty(TwistedQuotaRootProperty) or config.UserQuota
    
    def quotaRoot(self, request):
        """
        @return: a C{int} containing the maximum allowed bytes if this collection
            is quota-controlled, or C{None} if not quota controlled.
        """
        if self.hasDeadProperty(TwistedQuotaRootProperty):
            return int(str(self.readDeadProperty(TwistedQuotaRootProperty)))
        else:
            return config.UserQuota

##
# Utilities
##

# DAV:read access for authenticated users.
readOnlyACL = davxml.ACL(
    davxml.ACE(
        davxml.Principal(davxml.Authenticated()),
        davxml.Grant(davxml.Privilege(davxml.Read())),
        davxml.Protected(),
    ),
)
