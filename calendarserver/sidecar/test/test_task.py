##
# Copyright (c) 2009 Apple Inc. All rights reserved.
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

import os, zlib

from calendarserver.sidecar.task import CalDAVTaskServiceMaker, CalDAVTaskOptions, Task
from os.path import dirname, abspath
from twext.python.plistlib import writePlist
from twisted.python.usage import Options
from twistedcaldav.config import config, ConfigDict
from twistedcaldav.stdconfig import DEFAULT_CONFIG
from twistedcaldav.test.util import TestCase, todo
from twisted.internet.defer import inlineCallbacks

# Points to top of source tree.
sourceRoot = dirname(dirname(dirname(dirname(abspath(__file__)))))


class CalDAVTaskServiceTest(TestCase):
    """
    Test various parameters of our usage.Options subclass
    """
    def setUp(self):
        """
        Set up our options object, giving it a parent, and forcing the
        global config to be loaded from defaults.
        """
        TestCase.setUp(self)
        self.options = CalDAVTaskOptions()
        self.options.parent = Options()
        self.options.parent["uid"] = 0
        self.options.parent["gid"] = 0
        self.options.parent["nodaemon"] = False

        self.config = ConfigDict(DEFAULT_CONFIG)

        accountsFile = os.path.join(sourceRoot, "twistedcaldav/directory/test/accounts.xml")
        self.config["DirectoryService"] = {
            "params": {"xmlFile": accountsFile},
            "type": "twistedcaldav.directory.xmlfile.XMLDirectoryService"
        }

        self.config.DocumentRoot   = self.mktemp()
        self.config.DataRoot       = self.mktemp()
        self.config.ProcessType    = "Single"
        self.config.Memcached.ClientEnabled = False
        self.config.Memcached.ServerEnabled = False


        pemFile = os.path.join(sourceRoot, "twistedcaldav/test/data/server.pem")
        self.config.SSLPrivateKey = pemFile
        self.config.SSLCertificate = pemFile

        os.mkdir(self.config.DocumentRoot)
        os.mkdir(self.config.DataRoot)

        self.configFile = self.mktemp()

        self.writeConfig()

    def writeConfig(self):
        """
        Flush self.config out to self.configFile
        """
        writePlist(self.config, self.configFile)

    def tearDown(self):
        config.setDefaults(DEFAULT_CONFIG)
        config.reload()

    def makeService(self):
        self.options.parseOptions(["-f", self.configFile])
        return CalDAVTaskServiceMaker().makeService(self.options)

    @todo("FIXME: fix after new store changes")
    @inlineCallbacks
    def test_taskService(self):
        service = self.makeService()

        structure = {
            "calendars" : {
                "__uids__" : {
                    "64" : {
                        "23" : {
                            "6423F94A-6B76-4A3A-815B-D52CFD77935D" : {
                                "calendar": {
                                    "@xattrs" :
                                    {
                                        "WebDAV:{DAV:}resourcetype" : zlib.compress("<?xml version='1.0' encoding='UTF-8'?>\r\n<resourcetype xmlns='DAV:'>\r\n<collection/>\r\n<calendar xmlns='urn:ietf:params:xml:ns:caldav'/>\r\n</resourcetype>\r\n"),
                                    },
                                },
                                "inbox": {
                                    "unprocessed.ics": {
                                        "@contents" : unprocessed,
                                    }
                                },
                            }
                        }
                    }
                }
            },
        }

        self.createHierarchy(structure, root=self.config.DocumentRoot)

        structure = {
            "tasks" : {
                "incoming" : { },
                "processing" : {
                    "scheduleinboxes.task" : {
                        "@contents" : os.path.join(
                            self.config.DocumentRoot,
                            "calendars",
                            "__uids__",
                            "64",
                            "23",
                            "6423F94A-6B76-4A3A-815B-D52CFD77935D",
                            "inbox",
                            "unprocessed.ics"
                        ),
                    },
                },
            },
        }

        self.createHierarchy(structure, root=self.config.DataRoot)

        task = Task(service, "scheduleinboxes.task")
        yield task.run()

        # Aftwards we want to see a .ics file in calendar and inbox
        structure = {
            "calendars" : {
                "__uids__" : {
                    "64" : {
                        "23" : {
                            "6423F94A-6B76-4A3A-815B-D52CFD77935D" : {
                                "calendar": {
                                    ".db.sqlite" : {
                                        "@contents" : None,
                                    },
                                    "*.ics": {
                                        "@contents" : None,
                                    },
                                },
                                "inbox": {
                                    ".db.sqlite" : {
                                        "@contents" : None,
                                    },
                                    "*.ics": {
                                        "@contents" : None,
                                    },
                                },
                            }
                        }
                    }
                }
            },
        }
        self.assertTrue(self.verifyHierarchy(self.config.DocumentRoot, structure))

unprocessed = """BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:REQUEST
PRODID:-//Apple Inc.//iCal 4.0.1//EN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
TZNAME:PST
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
TZNAME:PDT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:A40F4892-B40F-4C0F-B8D0-F4EB2C97F4B9
DTSTART;TZID=US/Pacific:20091209T120000
DTEND;TZID=US/Pacific:20091209T130000
ATTENDEE;CN=Wilfredo Sanchez;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=N
 EEDS-ACTION;EMAIL=wsanchez@example.com;RSVP=TRUE:/principals/__uids__/6423F94
 A-6B76-4A3A-815B-D52CFD77935D/
ATTENDEE;CUTYPE=INDIVIDUAL;CN=Morgen Sagen;PARTSTAT=ACCEPTED:mailto:sagen@exam
 ple.com
CREATED:20091209T183541Z
DTSTAMP:20091209T183612Z
ORGANIZER;CN=Morgen Sagen:mailto:sagen@example.com
SEQUENCE:6
SUMMARY:Test
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

