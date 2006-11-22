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
from twistedcaldav.directory.apache import BasicDirectoryService

digestRealm = "Test"

basicUserFile  = FilePath(os.path.join(os.path.dirname(__file__), "basic"))
digestUserFile = FilePath(os.path.join(os.path.dirname(__file__), "digest"))
groupFile      = FilePath(os.path.join(os.path.dirname(__file__), "groups"))

# FIXME: Add tests for GUID hooey, once we figure out what that means here

class Basic (twistedcaldav.directory.test.util.BasicTestCase):
    """
    Test Apache-Compatible UserFile/GroupFile directory implementation.
    """
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

    def basicUserFile(self):
        if not hasattr(self, "_basicUserFile"):
            self._basicUserFile = FilePath(self.mktemp())
            basicUserFile.copyTo(self._basicUserFile)
        return self._basicUserFile

    def groupFile(self):
        if not hasattr(self, "_groupFile"):
            self._groupFile = FilePath(self.mktemp())
            groupFile.copyTo(self._groupFile)
        return self._groupFile

    def service(self):
        return BasicDirectoryService(self.basicUserFile(), self.groupFile())

    def test_recordTypes_user(self):
        """
        IDirectoryService.recordTypes(userFile)
        """
        self.assertEquals(set(BasicDirectoryService(basicUserFile).recordTypes()), set(("user",)))

    def test_changedUserFile(self):
        self.basicUserFile().open("w").write("wsanchez:Cytm0Bwm7CPJs\n")
        self.assertEquals(self.recordNames("user"), set(("wsanchez",)))

    def test_changedGroupFile(self):
        self.groupFile().open("w").write("grunts: wsanchez\n")
        self.assertEquals(self.recordNames("group"), set(("grunts",)))
