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
from twistedcaldav.directory.xmlfile import XMLDirectoryService

xmlFile = os.path.join(os.path.dirname(__file__), "accounts.xml")

# FIXME: Add tests for GUID hooey, once we figure out what that means here

class Basic (twistedcaldav.directory.test.util.BasicTestCase):
    """
    Test XML file based directory implementation.
    """
    recordTypes = set(("user", "group", "resource"))

    users = {
        "admin"   : "nimda",
        "proxy"   : "yxorp",
        "wsanchez": "zehcnasw",
        "cdaboo"  : "oobadc",
        "lecroy"  : "yorcel",
        "dreid"   : "dierd",
        "user01"  : "01user",
        "user02"  : "02user",
    }

    groups = {
        "managers"   : ("lecroy",),
        "grunts"     : ("wsanchez", "cdaboo", "dreid"),
        "right_coast": ("cdaboo",),
        "left_coast" : ("wsanchez", "dreid", "lecroy"),
    }

    resources = set((
        "mercury",
        "gemini",
        "apollo",
    ))

    def service(self):
        return XMLDirectoryService(xmlFile)
