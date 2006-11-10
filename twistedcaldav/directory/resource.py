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
Implements a directory-backed principal hierarchy.
"""

__all__ = [
    "DirectoryPrincipalProvisioningResource",
    "DirectoryPrincipalTypeResource",
    "DirectoryPrincipalResource",
]

from twisted.python import log
from twisted.internet.defer import succeed
from twisted.web2 import responsecode
from twisted.web2.http import Response, HTTPError
from twisted.web2.http_headers import MimeType
from twisted.web2.dav.static import DAVFile
from twisted.web2.dav.util import joinURL

from twistedcaldav.extensions import ReadOnlyResourceMixIn
from twistedcaldav.resource import CalendarPrincipalCollectionResource
from twistedcaldav.static import CalendarPrincipalFile
from twistedcaldav.directory.idirectory import IDirectoryService

# FIXME: These should not be tied to DAVFile

class DirectoryPrincipalProvisioningResource (ReadOnlyResourceMixIn, CalendarPrincipalCollectionResource, DAVFile):
    """
    Collection resource which provisions directory principals as its children.
    """
    def __init__(self, path, url, directory):
        """
        @param path: the path to the file which will back the resource.
        @param url: the canonical URL for the resource.
        @param directory: an L{IDirectoryService} to provision principals from.
        """
        CalendarPrincipalCollectionResource.__init__(self, url)
        DAVFile.__init__(self, path)

        self.directory = IDirectoryService(directory)

    def createSimilarFile(self, path):
        raise HTTPError(responsecode.NOT_FOUND)

    def getChild(self, name):
        if name == "":
            return self

        if name not in self.listChildren():
            return None

        child_fp = self.fp.child(name)
        if child_fp.exists():
            assert child_fp.isdir()
        else:
            assert self.exists()
            assert self.isCollection()

            child_fp.makedirs()

        return DirectoryPrincipalTypeResource(child_fp.path, self, name)

    def listChildren(self):
        return self.directory.recordTypes()

    def principalForUser(self, user):
        return self.getChild("user").getChild(user)

    def principalCollections(self, request):
        return succeed((self.principalCollectionURL(),))

class DirectoryPrincipalTypeResource (ReadOnlyResourceMixIn, CalendarPrincipalCollectionResource, DAVFile):
    """
    Collection resource which provisions directory principals of a specific type as its children.
    """
    def __init__(self, path, parent, name):
        CalendarPrincipalCollectionResource.__init__(self, joinURL(parent.principalCollectionURL(), name))
        DAVFile.__init__(self, path)

        self.directory = parent.directory
        self.recordType = name
        self._parent = parent

    def createSimilarFile(self, path):
        raise HTTPError(responsecode.NOT_FOUND)

    def getChild(self, name, record=None):
        if name == "":
            return self

        if record is None:
            record = self.directory.recordWithShortName(self.recordType, name)
            if record is None:
                return None
        else:
            assert name is None
            name = record.shortName

        child_fp = self.fp.child(name)
        if child_fp.exists():
            assert child_fp.isfile()
        else:
            assert self.exists()
            assert self.isCollection()

            child_fp.open("w").close()

        return DirectoryPrincipalResource(child_fp.path, self, record)

    def listChildren(self):
        return [record.shortName for record in self.directory.listRecords(self.recordType)]

    def principalCollections(self, request):
        return self._parent.principalCollections(request)

class DirectoryPrincipalResource (ReadOnlyResourceMixIn, CalendarPrincipalFile):
    """
    Directory principal resource.
    """
    def __init__(self, path, parent, record):
        super(DirectoryPrincipalResource, self).__init__(path, parent.principalCollectionURL())

        self.record = record
        self._parent = parent

    ##
    # HTTP
    ##

    def render(self, request):
        output = (
            "Principal resource\n"
            "------------------\n"
            "\n"
            "Directory service: %(service)s\n"
            "Record type: %(recordType)s\n"
            "GUID: %(guid)s\n"
            "Short name: %(shortName)s\n"
            "Full name: %(fullName)s\n"
            % self.record.__dict__
        )

        if type(output) == unicode:
            output = output.encode("utf-8")
            mime_params = {"charset": "utf-8"}
        else:
            mime_params = {}

        response = Response(code=responsecode.OK, stream=output)
        response.headers.setHeader("content-type", MimeType("text", "plain", mime_params))

        return response

    ##
    # ACL
    ##

    def alternateURIs(self):
        # FIXME: Add API to IDirectoryRecord for getting a record URI?
        return ()

    def groupMembers(self):
        for member in self.record.members():
            if member.recordType == self.record.recordType: 
                yield self._parent.getChild(None, record=member)
            else:
                yield self._parent._parent.getChild(member.recordType).getChild(None, record)

    def groupMemberships(self):
        raise NotImplementedError("DirectoryPrincipalResource.groupMemberships()")

    def principalCollections(self, request):
        return self._parent.principalCollections(request)

    ##
    # CalDAV
    ##

    def principalUID(self):
        return self.record.shortName

    def calendarHomeURLs(self):
        raise NotImplementedError("DirectoryPrincipalResource.calendarHomeURLs()")

    def calendarUserAddresses(self):
        raise NotImplementedError("DirectoryPrincipalResource.calendarUserAddresses()")
