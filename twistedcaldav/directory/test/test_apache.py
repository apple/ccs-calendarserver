##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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

import os

from twisted.python.filepath import FilePath

import twistedcaldav.directory.test.util
from twistedcaldav.directory.apache import BasicDirectoryService, DigestDirectoryService

digestRealm = "Test"

basicUserFile  = FilePath(os.path.join(os.path.dirname(__file__), "basic"))
digestUserFile = FilePath(os.path.join(os.path.dirname(__file__), "digest"))
groupFile      = FilePath(os.path.join(os.path.dirname(__file__), "groups"))

# FIXME: Add tests for GUID hooey, once we figure out what that means here

class Apache (object):
    recordTypes = set(("user", "group"))

    users = {
        "wsanchez": "foo",
        "cdaboo"  : "bar",
        "dreid"   : "baz",
        "lecroy"  : "quux",
    }

    groups = {
        "managers"   : ("lecroy",),
        "grunts"     : ("wsanchez", "cdaboo", "dreid"),
        "right_coast": ("cdaboo",),
        "left_coast" : ("wsanchez", "dreid", "lecroy"),
    }

    def service(self):
        return self.serviceClass(self.userFile(), self.groupFile())

    userFileName = None

    def userFile(self):
        if not hasattr(self, "_userFile"):
            if self.userFileName is None:
                raise NotImplementedError("Test subclass needs to specify userFileName.")
            self._userFile = FilePath(self.mktemp())
            basicUserFile.copyTo(self._userFile)
        return self._userFile

    def groupFile(self):
        if not hasattr(self, "_groupFile"):
            self._groupFile = FilePath(self.mktemp())
            groupFile.copyTo(self._groupFile)
        return self._groupFile

    def test_changedGroupFile(self):
        self.groupFile().open("w").write("grunts: wsanchez\n")
        self.assertEquals(self.recordNames("group"), set(("grunts",)))

    def test_recordTypes_user(self):
        """
        IDirectoryService.recordTypes(userFile)
        """
        self.assertEquals(set(self.serviceClass(self.userFile()).recordTypes()), set(("user",)))

    userEntry = None

    def test_changedUserFile(self):
        if self.userEntry is None:
            raise NotImplementedError("Test subclass needs to specify userEntry.")
        self.userFile().open("w").write(self.userEntry[1])
        self.assertEquals(self.recordNames("user"), set((self.userEntry[0],)))

class Basic (Apache, twistedcaldav.directory.test.util.BasicTestCase):
    """
    Test Apache-Compatible UserFile/GroupFile directory implementation.
    """
    serviceClass = BasicDirectoryService

    userFileName = basicUserFile
    userEntry = ("wsanchez", "wsanchez:Cytm0Bwm7CPJs\n")

class Digest (Apache, twistedcaldav.directory.test.util.DigestTestCase):
    """
    Test Apache-Compatible DigestFile/GroupFile directory implementation.
    """
    serviceClass = DigestDirectoryService

    userFileName = digestUserFile
    userEntry = ("wsanchez", "wsanchez:Test:decbe233ab3d997cacc2fc058b19db8c\n")

    def test_verifyCredentials_digest(self):
        raise NotImplementedError() # Use super's implementation
    test_verifyCredentials_digest.todo = "unimplemented"
