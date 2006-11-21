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
Implements a directory-backed principal hierarchy.
"""

__all__ = [
    "DirectoryPrincipalProvisioningResource",
    "DirectoryPrincipalTypeResource",
    "DirectoryPrincipalResource",
]

from twisted.python import log
from twisted.python.failure import Failure
from twisted.internet.defer import succeed
from twisted.web2 import responsecode
from twisted.web2.http import Response, HTTPError
from twisted.web2.http_headers import MimeType
from twisted.web2.dav import davxml
from twisted.web2.dav.resource import TwistedACLInheritable
from twisted.web2.dav.static import DAVFile
from twisted.web2.dav.util import joinURL

from twistedcaldav.extensions import ReadOnlyResourceMixIn
from twistedcaldav.resource import CalendarPrincipalCollectionResource
from twistedcaldav.static import CalDAVFile, CalendarPrincipalFile
from twistedcaldav.directory.idirectory import IDirectoryService

# FIXME: These should not be tied to DAVFile

class DirectoryPrincipalProvisioningResource (ReadOnlyResourceMixIn, CalDAVFile):
    """
    Collection resource which provisions directory principals as its children.
    """
    def __init__(self, path, url, directory):
        """
        @param path: the path to the file which will back the resource.
        @param url: the canonical URL for the resource.
        @param directory: an L{IDirectoryService} to provision principals from.
        """
        CalDAVFile.__init__(self, path)

        self._url = url
        self.directory = IDirectoryService(directory)
        self.directory.setProvisioningResource(self)

        # Create children
        for name in self.directory.recordTypes():
            child_fp = self.fp.child(name)
            if child_fp.exists():
                assert child_fp.isdir()
            else:
                assert self.exists()
                assert self.isCollection()

                child_fp.makedirs()

            self.putChild(name, DirectoryPrincipalTypeResource(child_fp.path, self, name))

    def createSimilarFile(self, path):
        raise HTTPError(responsecode.NOT_FOUND)

    def getChild(self, name):
        # This avoids finding case variants of put children on case-insensitive filesystems.
        if name not in self.putChildren and name.lower() in (x.lower() for x in self.putChildren):
            return None
        else:
            return self.putChildren.get(name, None)

    def listChildren(self):
        return self.putChildren.keys()

    def principalForUser(self, user):
        return self.getChild("user").getChild(user)

    def principalForRecord(self, record):
        typeResource = self.getChild(record.recordType)
        if typeResource is None:
            return None
        return typeResource.getChild(record.shortName)

    def collectionURL(self):
        return self._url

    ##
    # ACL
    ##

    def defaultAccessControlList(self):
        return davxml.ACL(
            # Read access for authenticated users.
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(davxml.Privilege(davxml.Read())),
                davxml.Protected(),
            ),
        )

class DirectoryPrincipalTypeResource (ReadOnlyResourceMixIn, CalendarPrincipalCollectionResource, DAVFile):
    """
    Collection resource which provisions directory principals of a specific type as its children.
    """
    def __init__(self, path, parent, recordType):
        """
        @param path: the path to the file which will back the resource.
        @param directory: an L{IDirectoryService} to provision calendars from.
        @param recordType: the directory record type to provision.
        """
        CalendarPrincipalCollectionResource.__init__(self, joinURL(parent.collectionURL(), recordType))
        DAVFile.__init__(self, path)

        self.directory = parent.directory
        self.recordType = recordType
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
        return (record.shortName for record in self.directory.listRecords(self.recordType))

    def principalForUser(self, user):
        return self._parent.principalForUser(user)

    ##
    # ACL
    ##

    def defaultAccessControlList(self):
        return davxml.ACL(
            # Read access for authenticated users.
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(davxml.Privilege(davxml.Read())),
                davxml.Protected(),
            ),
        )

class DirectoryPrincipalResource (ReadOnlyResourceMixIn, CalendarPrincipalFile):
    """
    Directory principal resource.
    """
    def __init__(self, path, parent, record):
        super(DirectoryPrincipalResource, self).__init__(path, joinURL(parent.principalCollectionURL(), record.shortName))

        self.record = record
        self._parent = parent

    ##
    # HTTP
    ##

    def render(self, request):
        def format_list(method, *args):
            def genlist():
                try:
                    item = None
                    for item in method(*args):
                        yield " -> %s\n" % (item,)
                    if item is None:
                        yield " '()\n"
                except Exception, e:
                    log.err("Exception while rendering: %s" % (e,))
                    Failure().printTraceback()
                    yield "  ** %s **: %s\n" % (e.__class__.__name__, e)
            return "".join(genlist())

        output = ("".join((
            "Principal resource\n"
            "------------------\n"
            "\n"
            "Directory service: %(service)s\n"
            "Record type: %(recordType)s\n"
            "GUID: %(guid)s\n"
            "Short name: %(shortName)s\n"
            "Full name: %(fullName)s\n"
            % self.record.__dict__,
            "Principal UID: %s\n" % self.principalUID(),
            "Principal URL: %s\n" % self.principalURL(),
            "\nAlternate URIs:\n"         , format_list(self.alternateURIs),
            "\nGroup members:\n"          , format_list(self.groupMembers),
            "\nGroup memberships:\n"      , format_list(self.groupMemberships),
            "\nCalendar homes:\n"         , format_list(self.calendarHomeURLs),
            "\nCalendar user addresses:\n", format_list(self.calendarUserAddresses),
        )))

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

    def _getRelatives(self, method, record=None, relatives=None, records=None):
        if record is None:
            record = self.record
        if relatives is None:
            relatives = set()
        if records is None:
            records = set()

        if record not in records:
            records.add(record)
            myRecordType = self.record.recordType
            for relative in getattr(record, method)():
                if relative not in records:
                    if relative.recordType == myRecordType: 
                        relatives.add(self._parent.getChild(None, record=relative))
                    else:
                        relatives.add(self._parent._parent.getChild(relative.recordType).getChild(None, record=relative))
                    self._getRelatives(method, relative, relatives, records)

        return relatives

    def groupMembers(self):
        return self._getRelatives("members")

    def groupMemberships(self):
        return self._getRelatives("groups")

    def displayName(self):
        return self.record.fullName

    ##
    # CalDAV
    ##

    def principalUID(self):
        return self.record.shortName

    def calendarHomeURLs(self):
        # FIXME: self.directory.calendarHomesCollection smells like a hack
        # See CalendarHomeProvisioningFile.__init__()
        return (
            self.record.service.calendarHomesCollection.homeForDirectoryRecord(self.record).url(),
        )

    def calendarUserAddresses(self):
        return (
            # Principal URL
            self.principalURL(),

            # Need to implement GUID->record->principal resource lookup first
            #"urn:uuid:%s" % (self.record.guid,)

            # Need to add email attribute to records if we want this
            #"mailto:%s" % (self.record.emailAddress)

            # This one needs a valid scheme.  If we make up our own, need to check the RFC for character rules.
            #"urn:calendarserver.macosforge.org:webdav:principal:%s:%s" % (self.record.recordType, self.record.shortName),
        )
