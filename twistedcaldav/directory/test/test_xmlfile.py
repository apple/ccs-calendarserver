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
    recordTypes = set(("user", "group", "location", "resource"))

    users = {
        "admin"   : { "password": "nimda",    "guid": None, "addresses": () },
        "proxy"   : { "password": "yxorp",    "guid": None, "addresses": () },
        "wsanchez": { "password": "zehcnasw", "guid": None, "addresses": ("mailto:wsanchez@example.com",) },
        "cdaboo"  : { "password": "oobadc",   "guid": None, "addresses": ("mailto:cdaboo@example.com",)   },
        "lecroy"  : { "password": "yorcel",   "guid": None, "addresses": ("mailto:lecroy@example.com",)   },
        "dreid"   : { "password": "dierd",    "guid": None, "addresses": ("mailto:dreid@example.com",)    },
        "user01"  : { "password": "01user",   "guid": None, "addresses": () },
        "user02"  : { "password": "02user",   "guid": None, "addresses": () },
    }

    groups = {
        "admin"      : { "password": "admin",       "guid": None, "addresses": (), "members": (("group", "managers"),)                                      },
        "managers"   : { "password": "managers",    "guid": None, "addresses": (), "members": (("user", "lecroy"),)                                         },
        "grunts"     : { "password": "grunts",      "guid": None, "addresses": (), "members": (("user", "wsanchez"), ("user", "cdaboo"), ("user", "dreid")) },
        "right_coast": { "password": "right_coast", "guid": None, "addresses": (), "members": (("user", "cdaboo"),)                                         },
        "left_coast" : { "password": "left_coast",  "guid": None, "addresses": (), "members": (("user", "wsanchez"), ("user", "dreid"), ("user", "lecroy")) },
        "both_coasts": { "password": "both_coasts", "guid": None, "addresses": (), "members": (("group", "right_coast"), ("group", "left_coast"))           },
    }

    locations = {
        "mercury": { "password": "mercury", "guid": None, "addresses": ("mailto:mercury@example.com",) },
        "gemini" : { "password": "gemini",  "guid": None, "addresses": ("mailto:gemini@example.com",)  },
        "apollo" : { "password": "apollo",  "guid": None, "addresses": ("mailto:apollo@example.com",)  },
    }

    resources = {
        "transporter": { "password": "transporter", "guid": None, "addresses": ("mailto:transporter@example.com",) },
        "ftlcpu"     : { "password": "ftlcpu",      "guid": None, "addresses": ("mailto:ftlcpu@example.com",)      },
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
<accounts realm="Test Realm">
  <user>
    <uid>admin</uid>
    <password>nimda</password>
    <name>Super User</name>
  </user>
</accounts>
"""
        )
        for recordType, expectedRecords in (
            ( "user"     , ("admin",) ),
            ( "group"    , ()         ),
            ( "location" , ()         ),
            ( "resource" , ()         ),
        ):
            self.assertEquals(
                set(r.shortName for r in self.service().listRecords(recordType)),
                set(expectedRecords)
            )
