# -*- test-case-name: twistedcaldav.directory.test.test_calendar -*-
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
Implements a directory-backed calendar hierarchy.
"""

__all__ = [
    "DirectoryCalendarHomeProvisioningResource",
    "DirectoryCalendarHomeTypeProvisioningResource",
    "DirectoryCalendarHomeUIDProvisioningResource",
    "DirectoryCalendarHomeResource",
]

from twext.python.log import Logger
from txweb2 import responsecode
from txweb2.dav.util import joinURL
from txweb2.http import HTTPError
from txweb2.http_headers import ETag, MimeType

from twisted.internet.defer import succeed, inlineCallbacks, returnValue

from twistedcaldav.config import config
from twistedcaldav.directory.idirectory import IDirectoryService
from twistedcaldav.directory.common import uidsResourceName, \
    CommonUIDProvisioningResource, CommonHomeTypeProvisioningResource

from twistedcaldav.directory.wiki import getWikiACL
from twistedcaldav.extensions import ReadOnlyResourceMixIn, DAVResource, \
    DAVResourceWithChildrenMixin
from twistedcaldav.resource import CalendarHomeResource

from uuid import uuid4

log = Logger()

# FIXME: copied from resource.py to avoid circular dependency
class CalDAVComplianceMixIn(object):
    def davComplianceClasses(self):
        return (
            tuple(super(CalDAVComplianceMixIn, self).davComplianceClasses())
            + config.CalDAVComplianceClasses
        )



class DirectoryCalendarProvisioningResource (
    ReadOnlyResourceMixIn,
    CalDAVComplianceMixIn,
    DAVResourceWithChildrenMixin,
    DAVResource,
):
    def defaultAccessControlList(self):
        return succeed(config.ProvisioningResourceACL)


    def etag(self):
        return succeed(ETag(str(uuid4())))


    def contentType(self):
        return MimeType("httpd", "unix-directory")



class DirectoryCalendarHomeProvisioningResource (DirectoryCalendarProvisioningResource):
    """
    Resource which provisions calendar home collections as needed.
    """
    def __init__(self, directory, url, store):
        """
        @param directory: an L{IDirectoryService} to provision calendars from.
        @param url: the canonical URL for the resource.
        """
        assert directory is not None
        assert url.endswith("/"), "Collection URL must end in '/'"

        super(DirectoryCalendarHomeProvisioningResource, self).__init__()

        # MOVE2WHO
        self.directory = directory  # IDirectoryService(directory)
        self._url = url
        self._newStore = store

        # FIXME: Smells like a hack
        directory.calendarHomesCollection = self

        #
        # Create children
        #
        # MOVE2WHO
        for name, recordType in [(r.name + "s", r) for r in self.directory.recordTypes()]:
            self.putChild(name, DirectoryCalendarHomeTypeProvisioningResource(self, name, recordType))

        self.putChild(uidsResourceName, DirectoryCalendarHomeUIDProvisioningResource(self))


    def url(self):
        return self._url


    def listChildren(self):
        # MOVE2WHO
        return [r.name + "s" for r in self.directory.recordTypes()]


    def principalCollections(self):
        # FIXME: directory.principalCollection smells like a hack
        # See DirectoryPrincipalProvisioningResource.__init__()
        return self.directory.principalCollection.principalCollections()


    def principalForRecord(self, record):
        # FIXME: directory.principalCollection smells like a hack
        # See DirectoryPrincipalProvisioningResource.__init__()
        return self.directory.principalCollection.principalForRecord(record)


    @inlineCallbacks
    def homeForDirectoryRecord(self, record, request):
        uidResource = yield self.getChild(uidsResourceName)
        if uidResource is None:
            returnValue(None)
        else:
            returnValue((yield uidResource.homeResourceForRecord(record, request)))


    ##
    # DAV
    ##

    def isCollection(self):
        return True


    def displayName(self):
        return "calendars"



class DirectoryCalendarHomeTypeProvisioningResource(
        CommonHomeTypeProvisioningResource,
        DirectoryCalendarProvisioningResource
    ):
    """
    Resource which provisions calendar home collections of a specific
    record type as needed.
    """
    def __init__(self, parent, name, recordType):
        """
        @param parent: the parent of this resource
        @param recordType: the directory record type to provision.
        """
        assert parent is not None
        assert name is not None
        assert recordType is not None

        super(DirectoryCalendarHomeTypeProvisioningResource, self).__init__()

        self.directory = parent.directory
        self.name = name
        self.recordType = recordType
        self._parent = parent


    def url(self):
        return joinURL(self._parent.url(), self.name)


    def listChildren(self):
        if config.EnablePrincipalListings:

            def _recordShortnameExpand():
                for record in self.directory.listRecords(self.recordType):
                    if record.enabledForCalendaring:
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
        return self.name


    ##
    # ACL
    ##

    def principalCollections(self):
        return self._parent.principalCollections()


    def principalForRecord(self, record):
        return self._parent.principalForRecord(record)



class DirectoryCalendarHomeUIDProvisioningResource (
        CommonUIDProvisioningResource,
        DirectoryCalendarProvisioningResource
    ):

    homeResourceTypeName = 'calendars'

    enabledAttribute = 'enabledForCalendaring'

    def homeResourceCreator(self, record, transaction):
        return DirectoryCalendarHomeResource.createHomeResource(
            self, record, transaction)



class DirectoryCalendarHomeResource (CalendarHomeResource):
    """
    Calendar home collection resource.
    """

    @classmethod
    @inlineCallbacks
    def createHomeResource(cls, parent, record, transaction):
        self = yield super(DirectoryCalendarHomeResource, cls).createHomeResource(
            parent, record.uid, transaction)
        self.record = record
        returnValue(self)


    # Special ACLs for Wiki service
    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        def gotACL(wikiACL):
            if wikiACL is not None:
                # ACL depends on wiki server...
                log.debug("Wiki ACL: %s" % (wikiACL.toxml(),))
                return succeed(wikiACL)
            else:
                # ...otherwise permissions are fixed, and are not subject to
                # inheritance rules, etc.
                return self.defaultAccessControlList()

        d = getWikiACL(self, request)
        d.addCallback(gotACL)
        return d


    def principalForRecord(self):
        return self.parent.principalForRecord(self.record)
