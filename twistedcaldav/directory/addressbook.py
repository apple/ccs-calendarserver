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
    "DirectoryAddressBookHomeProvisioningResource",
    "DirectoryAddressBookHomeTypeProvisioningResource",
    "DirectoryAddressBookHomeUIDProvisioningResource",
    "DirectoryAddressBookHomeResource",
]

from twext.python.log import Logger
from twext.web2 import responsecode
from twext.web2.dav.util import joinURL
from twext.web2.http import HTTPError
from twext.web2.http_headers import ETag, MimeType

from twistedcaldav.config import config
from twistedcaldav.directory.idirectory import IDirectoryService
from twistedcaldav.directory.resource import DirectoryReverseProxyResource
from twistedcaldav.directory.util import transactionFromRequest
from twistedcaldav.extensions import ReadOnlyResourceMixIn, DAVResource,\
    DAVResourceWithChildrenMixin
from twistedcaldav.resource import AddressBookHomeResource

from uuid import uuid4

log = Logger()

# Use __underbars__ convention to avoid conflicts with directory resource types.
uidsResourceName = "__uids__"

# FIXME: copied from resource.py to avoid circular dependency
class CalDAVComplianceMixIn(object):
    def davComplianceClasses(self):
        return (
            tuple(super(CalDAVComplianceMixIn, self).davComplianceClasses())
            + config.CalDAVComplianceClasses
        )

class DirectoryAddressBookProvisioningResource (
    ReadOnlyResourceMixIn,
    CalDAVComplianceMixIn,
    DAVResourceWithChildrenMixin,
    DAVResource,
):
    def defaultAccessControlList(self):
        return config.ProvisioningResourceACL

    def etag(self):
        return ETag(str(uuid4()))

    def contentType(self):
        return MimeType("httpd", "unix-directory")


class DirectoryAddressBookHomeProvisioningResource (DirectoryAddressBookProvisioningResource):
    """
    Resource which provisions address book home collections as needed.    
    """
    def __init__(self, directory, url, store):
        """
        @param directory: an L{IDirectoryService} to provision address books from.
        @param url: the canonical URL for the resource.
        """
        assert directory is not None
        assert url.endswith("/"), "Collection URL must end in '/'"

        super(DirectoryAddressBookHomeProvisioningResource, self).__init__()

        self.directory = IDirectoryService(directory)
        self._url = url
        self._newStore = store

        # FIXME: Smells like a hack
        directory.addressBookHomesCollection = self

        #
        # Create children
        #
        for recordType in self.directory.recordTypes():
            self.putChild(recordType, DirectoryAddressBookHomeTypeProvisioningResource(self, recordType))

        self.putChild(uidsResourceName, DirectoryAddressBookHomeUIDProvisioningResource(self))

    def url(self):
        return self._url

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

    def homeForDirectoryRecord(self, record, request):
        uidResource = self.getChild(uidsResourceName)
        if uidResource is None:
            return None
        else:
            return uidResource.homeResourceForRecord(record, request)

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    def displayName(self):
        return "addressbooks"


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

        super(DirectoryAddressBookHomeTypeProvisioningResource, self).__init__()

        self.directory = parent.directory
        self.recordType = recordType
        self._parent = parent

    def url(self):
        return joinURL(self._parent.url(), self.recordType)

    def locateChild(self, request, segments):
        name = segments[0]
        if name == "":
            return (self, segments[1:])

        record = self.directory.recordWithShortName(self.recordType, name)
        if record is None:
            return None, []

        return (self._parent.homeForDirectoryRecord(record, request),
                segments[1:])

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

    def makeChild(self, name):
        return None

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    def displayName(self):
        return self.recordType

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

        super(DirectoryAddressBookHomeUIDProvisioningResource, self).__init__()

        self.directory = parent.directory
        self.parent = parent

    def url(self):
        return joinURL(self.parent.url(), uidsResourceName)

    def locateChild(self, request, segments):

        name = segments[0]
        if name == "":
            return (self, ())

        record = self.directory.recordWithUID(name)
        if record:
            return (self.homeResourceForRecord(record, request), segments[1:])
        else:
            return (None, ())

    def getChild(self, name, record=None):
        raise NotImplementedError("DirectoryAddressBookHomeUIDProvisioningResource.getChild no longer exists.")

    def listChildren(self):
        # Not a listable collection
        raise HTTPError(responsecode.FORBIDDEN)

    def homeResourceForRecord(self, record, request):

        transaction = transactionFromRequest(request, self.parent._newStore)

        name = record.uid

        if record is None:
            self.log_msg("No directory record with GUID %r" % (name,))
            return None

        if not record.enabledForAddressBooks:
            self.log_msg("Directory record %r is not enabled for address books" % (record,))
            return None

        assert len(name) > 4, "Directory record has an invalid GUID: %r" % (name,)
        
        if record.locallyHosted():
            child = DirectoryAddressBookHomeResource(self, record, transaction)
        else:
            child = DirectoryReverseProxyResource(self, record)

        return child

    ##
    # DAV
    ##
    
    def isCollection(self):
        return True

    def displayName(self):
        return uidsResourceName

    ##
    # ACL
    ##

    def principalCollections(self):
        return self.parent.principalCollections()

    def principalForRecord(self, record):
        return self.parent.principalForRecord(record)


class DirectoryAddressBookHomeResource (AddressBookHomeResource):
    """
    Address book home collection resource.
    """
    def __init__(self, parent, record, transaction):
        """
        @param path: the path to the file which will back the resource.
        """
        assert parent is not None
        assert record is not None
        assert transaction is not None

        self.record = record
        super(DirectoryAddressBookHomeResource, self).__init__(parent, record.uid, transaction)

    def principalForRecord(self):
        return self.parent.principalForRecord(self.record)
