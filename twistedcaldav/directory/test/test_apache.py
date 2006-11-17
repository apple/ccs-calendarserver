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

import twistedcaldav.directory.test.util
from twistedcaldav.directory.apache import BasicDirectoryService

digestRealm = "Test"

basicUserFile  = os.path.join(os.path.dirname(__file__), "basic")
digestUserFile = os.path.join(os.path.dirname(__file__), "digest")
groupFile      = os.path.join(os.path.dirname(__file__), "groups")

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

    def service(self):
        return BasicDirectoryService(basicUserFile, groupFile)

    def test_recordTypes_user(self):
        """
        IDirectoryService.recordTypes(userFile)
        """
        self.assertEquals(set(BasicDirectoryService(basicUserFile).recordTypes()), set(("user",)))
