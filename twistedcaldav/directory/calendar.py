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
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
Implements a directory-backed calendar hierarchy.
"""

__all__ = [
    "DirectoryCalendarHomeProvisioningResource",
    "DirectoryCalendarHomeTypeProvisioningResource",
    "DirectoryCalendarHomeResource",
]

from twisted.web2.dav import davxml
from twisted.web2.dav.util import joinURL
from twisted.web2.dav.resource import TwistedACLInheritable, TwistedQuotaRootProperty

from twistedcaldav import caldavxml
from twistedcaldav.extensions import ReadOnlyResourceMixIn, DAVResource
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.schedule import ScheduleInboxResource, ScheduleOutboxResource
from twistedcaldav.directory.idirectory import IDirectoryService

class DirectoryCalendarHomeProvisioningResource (ReadOnlyResourceMixIn, DAVResource):
    """
    Resource which provisions calendar home collections as needed.    
    """
    def __init__(self, directory, url):
        """
        @param directory: an L{IDirectoryService} to provision calendars from.
        @param url: the canonical URL for the resource.
        """
        assert url.endswith("/"), "Collection URL must end in '/'"

        DAVResource.__init__(self)

        self.directory = IDirectoryService(directory)
        self._url = url

        # FIXME: Smells like a hack
        directory.calendarHomesCollection = self

    def provision(self):
        if not self.putChildren:
            # Create children
            for recordType in self.directory.recordTypes():
                self.putChild(recordType, self.provisionChild(recordType))

    def provisionChild(self, recordType):
        raise NotImplementedError("Subclass must implement provisionChild()")

    def url(self):
        return self._url

    def getChild(self, name):
        self.provision()

        return self.putChildren.get(name, None)

    def listChildren(self):
        return self.directory.recordTypes()

    def principalCollections(self):
        # FIXME: directory.principalCollection smells like a hack
        # See DirectoryPrincipalProvisioningResource.__init__()
        return self.directory.principalCollection.principalCollections()

    def homeForDirectoryRecord(self, record):
        typeResource = self.getChild(record.recordType)
        if typeResource is None:
            return None
        else:
            return typeResource.getChild(record.shortName)

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

class DirectoryCalendarHomeTypeProvisioningResource (ReadOnlyResourceMixIn, DAVResource):
    """
    Resource which provisions calendar home collections of a specific
    record type as needed.
    """
    def __init__(self, parent, recordType):
        """
        @param path: the path to the file which will back the resource.
        @param directory: an L{IDirectoryService} to provision calendars from.
        @param recordType: the directory record type to provision.
        """
        DAVResource.__init__(self)

        self.directory = parent.directory
        self.recordType = recordType
        self._parent = parent

    def provision(self):
        pass

    def provisionChild(self, record):
        raise NotImplementedError("Subclass must implement provisionChild()")

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
        else:
            assert name is None
            name = record.shortName

        return self.provisionChild(record)

    def listChildren(self):
        return (record.shortName for record in self.directory.listRecords(self.recordType))

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

class DirectoryCalendarHomeResource (CalDAVResource):
    """
    Calendar home collection resource.
    """
    # A global quota limit for all calendar homes. Either a C{int} (size in bytes) to limit
    # quota to that size, or C{None} for no limit.
    quotaLimit = None

    def __init__(self, parent, record):
        """
        @param path: the path to the file which will back the resource.
        """
        CalDAVResource.__init__(self)

        self.record = record
        self._parent = parent

        # Cache children which must be of a specific type
        for name, cls in (
            ("inbox" , ScheduleInboxResource ),
            ("outbox", ScheduleOutboxResource),
        ):
            child = self.provisionChild(name)
            assert isinstance(child, cls), "Child %r is not a %s: %r" % (name, cls.__name__, child)
            self.putChild(name, child)

    def provision(self):
        return self.provisionDefaultCalendars()

    def provisionDefaultCalendars(self):
        # Create a calendar collection

        childName = "calendar"
        childURL = joinURL(self.url(), childName)
        child = self.provisionChild(childName)
        assert isinstance(child, CalDAVResource), "Child %r is not a %s: %r" % (childName, CalDAVResource.__name__, child)

        def setupChild(_):
            # Grant read-free-busy access to authenticated users
            child.setAccessControlList(
                davxml.ACL(
                    davxml.ACE(
                        davxml.Principal(davxml.Authenticated()),
                        davxml.Grant(davxml.Privilege(caldavxml.ReadFreeBusy())),
                        TwistedACLInheritable(),
                    ),
                )
            )

            # Set calendar-free-busy-set on inbox
            inbox = self.getChild("inbox")
            inbox.provision()
            inbox.writeDeadProperty(caldavxml.CalendarFreeBusySet(davxml.HRef(childURL)))

        d = child.createCalendarCollection()
        d.addCallback(setupChild)
        return d

    def provisionChild(self, name):
        raise NotImplementedError("Subclass must implement provisionChild()")

    def url(self):
        return joinURL(self._parent.url(), self.record.shortName)

    def locateChild(self, path, segments):
        d = self.provision()
        d.addCallback(lambda _: super(DirectoryCalendarHomeResource, self).locateChild(path, segments))
        return d

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    ##
    # ACL
    ##

    def defaultAccessControlList(self):
        # FIXME: directory.principalCollection smells like a hack
        # See DirectoryPrincipalProvisioningResource.__init__()
        myPrincipal = self._parent._parent.directory.principalCollection.principalForRecord(self.record)

        return davxml.ACL(
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
        )

    def principalCollections(self):
        return self._parent.principalCollections()

    ##
    # Quota
    ##

    def hasQuotaRoot(self, request):
        """
        @return: a C{True} if this resource has quota root, C{False} otherwise.
        """
        return self.hasDeadProperty(TwistedQuotaRootProperty) or DirectoryCalendarHomeResource.quotaLimit is not None
    
    def quotaRoot(self, request):
        """
        @return: a C{int} containing the maximum allowed bytes if this collection
            is quota-controlled, or C{None} if not quota controlled.
        """
        if self.hasDeadProperty(TwistedQuotaRootProperty):
            return int(str(self.readDeadProperty(TwistedQuotaRootProperty)))
        else:
            return DirectoryCalendarHomeResource.quotaLimit

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
