##
# Copyright (c) 2006-2010 Apple Inc. All rights reserved.
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
Implements a directory-backed addressbook hierarchy.
"""

__all__ = [
    "uidsResourceName",
   #"DirectoryAddressBookProvisioningResource",
    "DirectoryAddressBookHomeProvisioningResource",
    "DirectoryAddressBookHomeTypeProvisioningResource",
    "DirectoryAddressBookHomeUIDProvisioningResource",
    "DirectoryAddressBookHomeResource",
    "GlobalAddressBookResource",
]

from twext.python.log import Logger
from twext.web2 import responsecode
from twext.web2.dav import davxml
from twext.web2.dav.resource import TwistedACLInheritable
from twext.web2.dav.util import joinURL
from twext.web2.http import HTTPError

from twisted.internet.defer import succeed

from twistedcaldav.config import config
from twistedcaldav.directory.idirectory import IDirectoryService
from twistedcaldav.directory.resource import AutoProvisioningResourceMixIn
from twistedcaldav.extensions import ReadOnlyResourceMixIn, DAVResource
from twistedcaldav.notifications import NotificationCollectionResource
from twistedcaldav.resource import CalDAVResource, CalDAVComplianceMixIn

log = Logger()

# Use __underbars__ convention to avoid conflicts with directory resource types.
uidsResourceName = "__uids__"


class DirectoryAddressBookProvisioningResource (
    AutoProvisioningResourceMixIn,
    ReadOnlyResourceMixIn,
    CalDAVComplianceMixIn,
    DAVResource,
):
    def defaultAccessControlList(self):
        return config.ProvisioningResourceACL


class DirectoryAddressBookHomeProvisioningResource (DirectoryAddressBookProvisioningResource):
    """
    Resource which provisions address book home collections as needed.    
    """
    def __init__(self, directory, url):
        """
        @param directory: an L{IDirectoryService} to provision address books from.
        @param url: the canonical URL for the resource.
        """
        assert directory is not None
        assert url.endswith("/"), "Collection URL must end in '/'"

        DAVResource.__init__(self)

        self.directory = IDirectoryService(directory)
        self._url = url

        # FIXME: Smells like a hack
        directory.addressBookHomesCollection = self

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


class DirectoryAddressBookHomeTypeProvisioningResource (DirectoryAddressBookProvisioningResource):
    """
    Resource which provisions address book home collections of a specific
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
        if config.EnablePrincipalListings:

            def _recordShortnameExpand():
                for record in self.directory.listRecords(self.recordType):
                    if record.enabledForAddressBooks:
                        for shortName in record.shortNames:
                            yield shortName

            return _recordShortnameExpand()
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

    def principalForRecord(self, record):
        return self._parent.principalForRecord(record)


class DirectoryAddressBookHomeUIDProvisioningResource (DirectoryAddressBookProvisioningResource):
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
            record = self.directory.recordWithUID(name)
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

    def principalCollections(self):
        return self.parent.principalCollections()

    def principalForRecord(self, record):
        return self.parent.principalForRecord(record)


class DirectoryAddressBookHomeResource (AutoProvisioningResourceMixIn, CalDAVResource):
    """
    Address book home collection resource.
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

        childlist = ()
        if config.Sharing.Enabled and config.Sharing.Calendars.Enabled:
            childlist += (
                ("notification", NotificationCollectionResource),
            )
        for name, cls in childlist:
            child = self.provisionChild(name)
            assert isinstance(child, cls), "Child %r is not a %s: %r" % (name, cls.__name__, child)
            self.putChild(name, child)

    def provisionDefaultAddressBooks(self):

        # Disable notifications during provisioning
        if hasattr(self, "clientNotifier"):
            self.clientNotifier.disableNotify()

        try:
            self.provision()
    
            childName = "addressbook"
            child = self.provisionChild(childName)
            assert isinstance(child, CalDAVResource), "Child %r is not a %s: %r" % (childName, CalDAVResource.__name__, child) #@UndefinedVariable

            d = child.createAddressBookCollection()
        except:
            # We want to make sure to re-enable notifications, so do so
            # if there is an immediate exception above, or via errback, below
            if hasattr(self, "clientNotifier"):
                self.clientNotifier.enableNotify(None)
            raise

        # Re-enable notifications
        if hasattr(self, "clientNotifier"):
            d.addCallback(self.clientNotifier.enableNotify)
            d.addErrback(self.clientNotifier.enableNotify)

        return d

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

    def owner(self, request):
        return succeed(davxml.HRef(self.principalForRecord().principalURL()))

    def ownerPrincipal(self, request):
        return succeed(self.principalForRecord())

    def resourceOwnerPrincipal(self, request):
        return succeed(self.principalForRecord())

    def defaultAccessControlList(self):
        myPrincipal = self.principalForRecord()

        aces = (
            # Inheritable DAV:all access for the resource's associated principal.
            davxml.ACE(
                davxml.Principal(davxml.HRef(myPrincipal.principalURL())),
                davxml.Grant(davxml.Privilege(davxml.All())),
                davxml.Protected(),
                TwistedACLInheritable(),
            ),
        )

        # Give read access to config.ReadPrincipals
        aces += config.ReadACEs

        # Give all access to config.AdminPrincipals
        aces += config.AdminACEs
        
        return davxml.ACL(*aces)

    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        # Permissions here are fixed, and are not subject to inheritance rules, etc.
        return succeed(self.defaultAccessControlList())

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
        return config.UserQuota != 0
    
    def quotaRoot(self, request):
        """
        @return: a C{int} containing the maximum allowed bytes if this collection
            is quota-controlled, or C{None} if not quota controlled.
        """
        return config.UserQuota if config.UserQuota != 0 else None

class GlobalAddressBookResource (CalDAVResource):
    """
    Global address book. All we care about is making sure permissions are setup.
    """

    def resourceType(self, request):
        return succeed(davxml.ResourceType.sharedaddressbook)

    def url(self):
        return joinURL("/", config.GlobalAddressBook.Name, "/")

    def canonicalURL(self, request):
        return succeed(self.url())

    def defaultAccessControlList(self):

        aces = (
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(
                    davxml.Privilege(davxml.Read()),
                    davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                    davxml.Privilege(davxml.Write()),
                ),
                davxml.Protected(),
                TwistedACLInheritable(),
           ),
        )
        
        if config.GlobalAddressBook.EnableAnonymousReadAccess:
            aces += (
                davxml.ACE(
                    davxml.Principal(davxml.Unauthenticated()),
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                    ),
                    davxml.Protected(),
                    TwistedACLInheritable(),
               ),
            )
        return davxml.ACL(*aces)

    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        # Permissions here are fixed, and are not subject to inheritance rules, etc.
        return succeed(self.defaultAccessControlList())
