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
from twisted.web2.dav.static import DAVFile
from twisted.web2.dav.util import joinURL

from twistedcaldav.extensions import ReadOnlyResourceMixIn
from twistedcaldav.resource import CalendarPrincipalCollectionResource
from twistedcaldav.static import CalendarPrincipalFile
from twistedcaldav.directory.idirectory import IDirectoryService

# FIXME: These should be tied to DAVFile

class DirectoryPrincipalProvisioningResource (ReadOnlyResourceMixIn, CalendarPrincipalCollectionResource, DAVFile):
    """
    Collection resource which provisions directory principals as its children.
    """
    def __init__(self, path, url, directory):
        """
        @param path: the path to the file which will back the resource.
        @param url: the canonical URL for the resource.
        """
        CalendarPrincipalCollectionResource.__init__(self, url)
        DAVFile.__init__(self, path)

        self.directory = IDirectoryService(directory)

    def createSimilarFile(self, path):
        raise AssertionError("Not allowed.")

    # FIXME: Remove
    def initialize(self, homeuri, home):
        log.msg("*** Get rid of initialize() ***")

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

class DirectoryPrincipalTypeResource (ReadOnlyResourceMixIn, CalendarPrincipalCollectionResource, DAVFile):
    """
    Collection resource which provisions directory principals of a specific type as its children.
    """
    def __init__(self, path, parent, name):
        CalendarPrincipalCollectionResource.__init__(self, joinURL(parent.principalCollectionURL(), name))
        DAVFile.__init__(self, path)

        self.directory = parent.directory
        self.recordType = name

    def createSimilarFile(self, path):
        raise AssertionError("Not allowed.")

    def getChild(self, name):
        if name == "":
            return self

        record = self.directory.recordWithShortName(self.recordType, name)
        if record is None:
            return None

        child_fp = self.fp.child(name)
        if child_fp.exists():
            assert child_fp.isfile()
        else:
            assert self.exists()
            assert self.isCollection()

            child_fp.open("w").close()

        return DirectoryPrincipalResource(child_fp.path, self, name)

    def listChildren(self):
        return self.directory.listRecords(self.recordType)

class DirectoryPrincipalResource (ReadOnlyResourceMixIn, CalendarPrincipalFile):
    """
    Directory principal resource.
    """
    def __init__(self, path, parent, name):
        super(DirectoryPrincipalResource, self).__init__(path, parent.principalCollectionURL())

        self.directory = parent.directory
        self.recordType = parent.recordType
        self.shortName = name

    ##
    # ACL
    ##

    def alternateURIs(self):
        return ()

    def groupMembers(self):
        raise NotImplementedError()

    def groupMemberships(self):
        raise NotImplementedError()

    ##
    # CalDAV
    ##

    def principalUID(self):
        return self.shortName

    def calendarHomeURLs(self):
        raise NotImplementedError()

    def calendarUserAddresses(self):
        raise NotImplementedError()
