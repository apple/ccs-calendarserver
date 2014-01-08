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
Implements a directory-backed addressbook hierarchy.
"""

__all__ = [
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

from twisted.internet.defer import inlineCallbacks, returnValue, succeed

from twistedcaldav.config import config
from twistedcaldav.directory.idirectory import IDirectoryService

from twistedcaldav.directory.common import CommonUIDProvisioningResource,\
    uidsResourceName, CommonHomeTypeProvisioningResource

from twistedcaldav.extensions import ReadOnlyResourceMixIn, DAVResource,\
    DAVResourceWithChildrenMixin
from twistedcaldav.resource import AddressBookHomeResource

from uuid import uuid4

log = Logger()


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
        return succeed(ETag(str(uuid4())))

    def contentType(self):
        return MimeType("httpd", "unix-directory")


class DirectoryAddressBookHomeProvisioningResource (
        DirectoryAddressBookProvisioningResource
    ):
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


class DirectoryAddressBookHomeTypeProvisioningResource (
        CommonHomeTypeProvisioningResource,
        DirectoryAddressBookProvisioningResource
    ):
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


class DirectoryAddressBookHomeUIDProvisioningResource (
        CommonUIDProvisioningResource,
        DirectoryAddressBookProvisioningResource
    ):

    homeResourceTypeName = 'addressbooks'

    enabledAttribute = 'enabledForAddressBooks'

    def homeResourceCreator(self, record, transaction):
        return DirectoryAddressBookHomeResource.createHomeResource(
            self, record, transaction)


class DirectoryAddressBookHomeResource (AddressBookHomeResource):
    """
    Address book home collection resource.
    """

    @classmethod
    @inlineCallbacks
    def createHomeResource(cls, parent, record, transaction):
        self = yield super(DirectoryAddressBookHomeResource, cls).createHomeResource(
            parent, record.uid, transaction)
        self.record = record
        returnValue(self)


    def principalForRecord(self):
        return self.parent.principalForRecord(self.record)
