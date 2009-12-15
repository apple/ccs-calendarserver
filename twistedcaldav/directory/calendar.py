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
Implements a directory-backed calendar hierarchy.
"""

__all__ = [
    "uidsResourceName",
   #"DirectoryCalendarProvisioningResource",
    "DirectoryCalendarHomeProvisioningResource",
    "DirectoryCalendarHomeTypeProvisioningResource",
    "DirectoryCalendarHomeUIDProvisioningResource",
    "DirectoryCalendarHomeResource",
]

from twisted.internet.defer import succeed, fail, inlineCallbacks, returnValue, gatherResults
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.http import HTTPError
from twisted.web2.dav.util import joinURL
from twisted.web2.dav.resource import TwistedACLInheritable

from twistedcaldav import caldavxml
from twistedcaldav.config import config
from twistedcaldav.dropbox import DropBoxHomeResource
from twistedcaldav.extensions import ReadOnlyResourceMixIn, DAVResource
from twistedcaldav.freebusyurl import FreeBusyURLResource
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.schedule import ScheduleInboxResource, ScheduleOutboxResource
from twistedcaldav.directory.idirectory import IDirectoryService
from twistedcaldav.directory.wiki import getWikiACL
from twistedcaldav.directory.resource import AutoProvisioningResourceMixIn

from twistedcaldav.log import Logger
log = Logger()

# Use __underbars__ convention to avoid conflicts with directory resource types.
uidsResourceName = "__uids__"


class DirectoryCalendarProvisioningResource (
    AutoProvisioningResourceMixIn,
    ReadOnlyResourceMixIn,
    DAVResource,
):
    def defaultAccessControlList(self):
        return succeed(config.ProvisioningResourceACL)


class DirectoryCalendarHomeProvisioningResource (DirectoryCalendarProvisioningResource):
    """
    Resource which provisions calendar home collections as needed.    
    """

    @classmethod
    @inlineCallbacks
    def fetch(cls, *a, **kw):
        self = (yield super(DirectoryCalendarHomeProvisioningResource, cls).fetch(*a, **kw))
        #
        # Create children
        #

        @inlineCallbacks
        def _provisionChild(name):
            provisioned = (yield self.provisionChild(name))
            self.putChild(name, provisioned)

        for recordType in self.directory.recordTypes():
            (yield _provisionChild(recordType))

        (yield _provisionChild(uidsResourceName))
        returnValue(self)

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


    def provisionChild(self, recordType):
        raise NotImplementedError("Subclass must implement provisionChild()")

    def url(self):
        return self._url

    def getChild(self, name):
        return succeed(self.putChildren.get(name, None))

    def listChildren(self):
        return succeed(self.directory.recordTypes())

    def principalCollections(self):
        # FIXME: directory.principalCollection smells like a hack
        # See DirectoryPrincipalProvisioningResource.__init__()
        return self.directory.principalCollection.principalCollections()

    # Deferred
    def principalForRecord(self, record):
        # FIXME: directory.principalCollection smells like a hack
        # See DirectoryPrincipalProvisioningResource.__init__()
        return self.directory.principalCollection.principalForRecord(record)

    @inlineCallbacks
    def homeForDirectoryRecord(self, record):
        uidResource = (yield self.getChild(uidsResourceName))
        if uidResource is None:
            returnValue(None)
        else:
            returnValue((yield uidResource.getChild(record.uid)))

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True


class DirectoryCalendarHomeTypeProvisioningResource (DirectoryCalendarProvisioningResource):
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

    @inlineCallbacks
    def getChild(self, name, record=None):
        yield self.provision()
        if name == "":
            returnValue(self)

        if record is None:
            record = (yield self.directory.recordWithShortName(self.recordType, name))
            if record is None:
                returnValue(None)

        returnValue((yield self._parent.homeForDirectoryRecord(record)))

    @inlineCallbacks
    def listChildren(self):
        if config.EnablePrincipalListings:

            results = []
            for record in (yield self.directory.listRecords(self.recordType)):
                if record.enabledForCalendaring:
                    for shortName in record.shortNames:
                        results.append(shortName)

            returnValue(results)
        else:
            # Not a listable collection
            raise HTTPError(responsecode.FORBIDDEN)

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

    def principalCollections(self):
        return self._parent.principalCollections()

    # Deferred
    def principalForRecord(self, record):
        return self._parent.principalForRecord(record)


class DirectoryCalendarHomeUIDProvisioningResource (DirectoryCalendarProvisioningResource):
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

    @inlineCallbacks
    def getChild(self, name, record=None):
        yield self.provision()
        if name == "":
            returnValue(self)

        if record is None:
            record = (yield self.directory.recordWithUID(name))
            if record is None:
                returnValue(None)

        returnValue((yield self.provisionChild(name)))

    def listChildren(self):
        # Not a listable collection
        return fail(HTTPError(responsecode.FORBIDDEN))

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    ##
    # ACL
    ##

    def principalCollections(self):
        return self.parent.principalCollections()

    # Deferred
    def principalForRecord(self, record):
        return self.parent.principalForRecord(record)


class DirectoryCalendarHomeResource (AutoProvisioningResourceMixIn, CalDAVResource):
    """
    Calendar home collection resource.
    """
    @classmethod
    def fetch(cls, *a, **kw):
        d = super(DirectoryCalendarHomeResource, cls).fetch(*a, **kw)
        def _populateChildren(self):
            # Cache children which must be of a specific type
            childlist = (
                ("inbox" , ScheduleInboxResource ),
                ("outbox", ScheduleOutboxResource),
            )
            if config.EnableDropBox:
                childlist += (
                    ("dropbox", DropBoxHomeResource),
                )
            if config.FreeBusyURL.Enabled:
                childlist += (
                    ("freebusy", FreeBusyURLResource),
                )
            ds = []
            for name, cls in childlist:
                d = self.provisionChild(name)
                def _newChild(child):
                    assert isinstance(child, cls), "Child %r is not a %s: %r" % (name, cls.__name__, child)
                    self.putChild(name, child)
                d.addCallback(_newChild)
                ds.append(d)
            return gatherResults(ds).addCallback(lambda _: self)

        return d.addCallback(_populateChildren)

    def __init__(self, parent, record):
        """
        @param path: the path to the file which will back the resource.
        """
        assert parent is not None
        assert record is not None

        CalDAVResource.__init__(self)

        self.record = record
        self.parent = parent


    @inlineCallbacks
    def provisionDefaultCalendars(self):

        # Disable notifications during provisioning
        if hasattr(self, "clientNotifier"):
            self.clientNotifier.disableNotify()

        try:
            yield self.provision()

            childName = "calendar"
            childURL = joinURL(self.url(), childName)
            child = (yield self.provisionChild(childName))
            
            assert isinstance(child, CalDAVResource), "Child %r is not a %s: %r" % (childName, CalDAVResource.__name__, child)
            yield child.createCalendarCollection()
            yield child.writeDeadProperty(caldavxml.ScheduleCalendarTransp(caldavxml.Opaque()))

            # FIXME: Shouldn't have to call provision() on another resource
            # We cheat here because while inbox will auto-provision itself when located,
            # we need to write a dead property to it pre-emptively.
            # This will go away once we remove the free-busy-set property on inbox.

            # Set calendar-free-busy-set on inbox
            inbox = (yield self.getChild("inbox"))
            yield inbox.provision()
            yield inbox.processFreeBusyCalendar(childURL, True)

            # Default calendar is marked as the default for scheduling
            yield inbox.writeDeadProperty(caldavxml.ScheduleDefaultCalendarURL(davxml.HRef(childURL)))

        finally:
            if hasattr(self, "clientNotifier"):
                self.clientNotifier.enableNotify(None)


    def provisionChild(self, name):
        raise NotImplementedError("Subclass must implement provisionChild()")

    def url(self):
        return joinURL(self.parent.url(), self.record.uid, "/")

    def canonicalURL(self, request):
        return succeed(self.url())

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    def http_COPY(self, request):
        return responsecode.FORBIDDEN

    ##
    # ACL
    ##

    @inlineCallbacks
    def owner(self, request):
        principal = (yield self.principalForRecord())
        returnValue(davxml.HRef(principal.principalURL()))

    # Deferred
    def ownerPrincipal(self, request):
        return self.principalForRecord()

    @inlineCallbacks
    def defaultAccessControlList(self):
        myPrincipal = (yield self.principalForRecord())

        aces = (
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

        # Give read access to config.ReadPrincipals
        aces += config.ReadACEs

        # Give all access to config.AdminPrincipals
        aces += config.AdminACEs
        
        if config.EnableProxyPrincipals:
            aces += (
                # DAV:read/DAV:read-current-user-privilege-set access for this principal's calendar-proxy-read users.
                davxml.ACE(
                    davxml.Principal(davxml.HRef(joinURL(myPrincipal.principalURL(), "calendar-proxy-read/"))),
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                        davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                    ),
                    davxml.Protected(),
                    TwistedACLInheritable(),
                ),
                # DAV:read/DAV:read-current-user-privilege-set/DAV:write access for this principal's calendar-proxy-write users.
                davxml.ACE(
                    davxml.Principal(davxml.HRef(joinURL(myPrincipal.principalURL(), "calendar-proxy-write/"))),
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                        davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                        davxml.Privilege(davxml.Write()),
                    ),
                    davxml.Protected(),
                    TwistedACLInheritable(),
                ),
            )

        returnValue(davxml.ACL(*aces))

    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        def gotACL(wikiACL):
            if wikiACL is not None:
                # ACL depends on wiki server...
                log.debug("Wiki ACL: %s" % (wikiACL.toxml(),))
                return succeed(wikiACL)
            else:
                # ...otherwise permissions are fixed, and are not subject to
                # inheritance rules, etc.
                return succeed(self.defaultAccessControlList())

        wikiACL = (yield getWikiACL(self, request))
        if wikiACL is not None:
            # ACL depends on wiki server...
            log.debug("Wiki ACL: %s" % (wikiACL.toxml(),))
            returnValue(wikiACL)
        else:
            # ...otherwise permissions are fixed, and are not subject to
            # inheritance rules, etc.
            returnValue((yield self.defaultAccessControlList()))

    def principalCollections(self):
        return self.parent.principalCollections()

    # Deferred
    def principalForRecord(self):
        return self.parent.principalForRecord(self.record)

    ##
    # Quota
    ##

    def hasQuotaRoot(self, request):
        """
        Always get quota root value from config.

        @return: a C{True} if this resource has quota root, C{False} otherwise.
        """
        return succeed(config.UserQuota != 0)
    
    def quotaRoot(self, request):
        """
        Always get quota root value from config.

        @return: a C{int} containing the maximum allowed bytes if this collection
            is quota-controlled, or C{None} if not quota controlled.
        """
        return succeed(config.UserQuota if config.UserQuota != 0 else None)
