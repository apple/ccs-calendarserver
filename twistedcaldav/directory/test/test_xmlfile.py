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
from twistedcaldav.directory.xmlfile import XMLDirectoryService

xmlFile = FilePath(os.path.join(os.path.dirname(__file__), "accounts.xml"))

# FIXME: Add tests for GUID hooey, once we figure out what that means here

class XMLFileBase(object):
    recordTypes = set(("user", "group", "resource"))

    users = {
        "admin"   : { "password": "nimda",    "guid": None, "addresses": () },
        "proxy"   : { "password": "yxorp",    "guid": None, "addresses": () },
        "wsanchez": { "password": "zehcnasw", "guid": None, "addresses": () },
        "cdaboo"  : { "password": "oobadc",   "guid": None, "addresses": () },
        "lecroy"  : { "password": "yorcel",   "guid": None, "addresses": () },
        "dreid"   : { "password": "dierd",    "guid": None, "addresses": () },
        "user01"  : { "password": "01user",   "guid": None, "addresses": () },
        "user02"  : { "password": "02user",   "guid": None, "addresses": () },
    }

    groups = {
        "managers"   : { "password": "managers",    "members": ("lecroy",),                     "guid": None, "addresses": () },
        "grunts"     : { "password": "grunts",      "members": ("wsanchez", "cdaboo", "dreid"), "guid": None, "addresses": () },
        "right_coast": { "password": "right_coast", "members": ("cdaboo",),                     "guid": None, "addresses": () },
        "left_coast" : { "password": "left_coast",  "members": ("wsanchez", "dreid", "lecroy"), "guid": None, "addresses": () },
    }

    resources = {
        "mercury": { "password": "mercury", "guid": None, "addresses": () },
        "gemini" : { "password": "gemini",  "guid": None, "addresses": () },
        "apollo" : { "password": "apollo",  "guid": None, "addresses": () },
    }

    def xmlFile(self):
        if not hasattr(self, "_xmlFile"):
            self._xmlFile = FilePath(self.mktemp())
            xmlFile.copyTo(self._xmlFile)
        return self._xmlFile

class XMLFile (
    XMLFileBase,
    twistedcaldav.directory.test.util.BasicTestCase,
    twistedcaldav.directory.test.util.DigestTestCase
):
    """
    Test XML file based directory implementation.
    """
    def service(self):
        return XMLDirectoryService(self.xmlFile())

    def test_changedXML(self):
        self.xmlFile().open("w").write(
"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE accounts SYSTEM "accounts.dtd">
<accounts>
  <user>
    <uid>admin</uid>
    <pswd>nimda</pswd>
    <name>Super User</name>
  </user>
</accounts>
"""
        )
        for recordType, expectedRecords in (
            ( "user"     , ("admin",) ),
            ( "group"    , ()         ),
            ( "resource" , ()         ),
        ):
            self.assertEquals(
                set(r.shortName for r in self.service().listRecords(recordType)),
                set(expectedRecords)
            )
