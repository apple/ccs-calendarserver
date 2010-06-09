##
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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

from calendarserver.tap.util import getRootResource
from calendarserver.tools.principals import addProxy
from calendarserver.tools.purge import purgeOldEvents, purgeGUID, purgeProxyAssignments
from datetime import datetime, timedelta
from twext.python.filepath import CachingFilePath as FilePath
from twext.python.plistlib import readPlistFromString
from twext.web2.dav import davxml
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, Deferred, returnValue
from twistedcaldav.config import config
from twistedcaldav.directory.directory import DirectoryRecord
from twistedcaldav.test.util import TestCase, CapturingProcessProtocol
import os
import xml
import zlib

resourceAttr = "WebDAV:{DAV:}resourcetype"
collectionType = zlib.compress("""<?xml version='1.0' encoding='UTF-8'?>
<resourcetype xmlns='DAV:'>
    <collection/>
    <calendar xmlns='urn:ietf:params:xml:ns:caldav'/>
</resourcetype>
""")


class PurgeOldEventsTestCase(TestCase):

    def setUp(self):
        super(PurgeOldEventsTestCase, self).setUp()

        config.DirectoryService.params['xmlFile'] = os.path.join(os.path.dirname(__file__), "purge", "accounts.xml")
        self.rootResource = getRootResource(config)
        self.directory = self.rootResource.getDirectory()

    @inlineCallbacks
    def test_purgeOldEvents(self):
        before = {
            "calendars" : {
                "__uids__" : {
                    "64" : {
                        "23" : {
                            "6423F94A-6B76-4A3A-815B-D52CFD77935D" : {
                                "calendar": {
                                    "@xattrs" :
                                    {
                                        resourceAttr : collectionType,
                                    },
                                    "oneshot.ics": {
                                        "@contents" : OLD_ICS,
                                    },
                                    "endless.ics": {
                                        "@contents" : ENDLESS_ICS,
                                    },
                                    "awhile.ics": {
                                        "@contents" : REPEATING_AWHILE_ICS,
                                    },
                                    "straddling.ics": {
                                        "@contents" : STRADDLING_ICS,
                                    },
                                    "recent.ics": {
                                        "@contents" : RECENT_ICS,
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
        self.createHierarchy(before, config.DocumentRoot)

        count = (yield purgeOldEvents(self.directory, self.rootResource,
            "20100303T000000Z"))

        self.assertEquals(count, 2)

        after = {
            "__uids__" : {
                "64" : {
                    "23" : {
                        "6423F94A-6B76-4A3A-815B-D52CFD77935D" : {
                            "calendar": {
                                ".db.sqlite": {
                                    "@contents" : None, # ignore contents
                                },
                                ".db.sqlite-journal": {
                                    "@contents" : None, # ignore contents
                                },
                                "endless.ics": {
                                    "@contents" : ENDLESS_ICS,
                                },
                                "straddling.ics": {
                                    "@contents" : STRADDLING_ICS,
                                },
                                "recent.ics": {
                                    "@contents" : RECENT_ICS,
                                },
                            },
                        },
                    },
                },
            },
        }
        self.assertTrue(self.verifyHierarchy(
            os.path.join(config.DocumentRoot, "calendars"),
            after)
        )




OLD_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;UNTIL=20061029T090000Z;BYMONTH=10;BYDAY=-1SU
DTSTART:19621028T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;UNTIL=20060402T100000Z;BYMONTH=4;BYDAY=1SU
DTSTART:19870405T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20100303T181216Z
UID:685BC3A1-195A-49B3-926D-388DDACA78A6
DTEND;TZID=US/Pacific:20000307T151500
TRANSP:OPAQUE
SUMMARY:Ancient event
DTSTART;TZID=US/Pacific:20000307T111500
DTSTAMP:20100303T181220Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

ENDLESS_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;UNTIL=20061029T090000Z;BYMONTH=10;BYDAY=-1SU
DTSTART:19621028T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;UNTIL=20060402T100000Z;BYMONTH=4;BYDAY=1SU
DTSTART:19870405T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20100303T194654Z
UID:9FDE0E4C-1495-4CAF-863B-F7F0FB15FE8C
DTEND;TZID=US/Pacific:20000308T151500
RRULE:FREQ=YEARLY;INTERVAL=1
TRANSP:OPAQUE
SUMMARY:Ancient Repeating Endless
DTSTART;TZID=US/Pacific:20000308T111500
DTSTAMP:20100303T194710Z
SEQUENCE:4
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

REPEATING_AWHILE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;UNTIL=20061029T090000Z;BYMONTH=10;BYDAY=-1SU
DTSTART:19621028T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;UNTIL=20060402T100000Z;BYMONTH=4;BYDAY=1SU
DTSTART:19870405T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20100303T194716Z
UID:76236B32-2BC4-4D78-956B-8D42D4086200
DTEND;TZID=US/Pacific:20000309T151500
RRULE:FREQ=YEARLY;INTERVAL=1;COUNT=3
TRANSP:OPAQUE
SUMMARY:Ancient Repeat Awhile
DTSTART;TZID=US/Pacific:20000309T111500
DTSTAMP:20100303T194747Z
SEQUENCE:6
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

STRADDLING_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20100303T213643Z
UID:1C219DAD-D374-4822-8C98-ADBA85E253AB
DTEND;TZID=US/Pacific:20090508T121500
RRULE:FREQ=MONTHLY;INTERVAL=1;UNTIL=20100509T065959Z
TRANSP:OPAQUE
SUMMARY:Straddling cut-off
DTSTART;TZID=US/Pacific:20090508T111500
DTSTAMP:20100303T213704Z
SEQUENCE:5
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")

RECENT_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iCal 4.0.1//EN
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:US/Pacific
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
DTSTART:20070311T020000
TZNAME:PDT
TZOFFSETTO:-0700
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
DTSTART:20071104T020000
TZNAME:PST
TZOFFSETTO:-0800
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
CREATED:20100303T195159Z
UID:F2F14D94-B944-43D9-8F6F-97F95B2764CA
DTEND;TZID=US/Pacific:20100304T141500
TRANSP:OPAQUE
SUMMARY:Recent
DTSTART;TZID=US/Pacific:20100304T120000
DTSTAMP:20100303T195203Z
SEQUENCE:2
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")




class DeprovisionTestCase(TestCase):

    def setUp(self):
        super(DeprovisionTestCase, self).setUp()

        testRootPath = FilePath(__file__).sibling("deprovision")
        template = testRootPath.child("caldavd.plist").getContent()

        newConfig = template % {
            "ServerRoot" : os.path.abspath(config.ServerRoot),
        }
        configFilePath = FilePath(os.path.join(config.ConfigRoot, "caldavd.plist"))
        configFilePath.setContent(newConfig)

        self.configFileName = configFilePath.path
        config.load(self.configFileName)

        origUsersFile = FilePath(__file__).sibling(
            "deprovision").child("users-groups.xml")
        copyUsersFile = FilePath(config.DataRoot).child("accounts.xml")
        origUsersFile.copyTo(copyUsersFile)

        origResourcesFile = FilePath(__file__).sibling(
            "deprovision").child("resources-locations.xml")
        copyResourcesFile = FilePath(config.DataRoot).child("resources.xml")
        origResourcesFile.copyTo(copyResourcesFile)

        origAugmentFile = FilePath(__file__).sibling(
            "deprovision").child("augments.xml")
        copyAugmentFile = FilePath(config.DataRoot).child("augments.xml")
        origAugmentFile.copyTo(copyAugmentFile)

        self.rootResource = getRootResource(config)
        self.directory = self.rootResource.getDirectory()

        # Make sure trial puts the reactor in the right state, by letting it
        # run one reactor iteration.  (Ignore me, please.)
        d = Deferred()
        reactor.callLater(0, d.callback, True)
        return d

    @inlineCallbacks
    def runCommand(self, command, error=False):
        """
        Run the given command by feeding it as standard input to
        calendarserver_deprovision in a subprocess.
        """
        sourceRoot = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        python = os.path.join(sourceRoot, "python")
        script = os.path.join(sourceRoot, "bin", "calendarserver_purge_guid")

        args = [python, script, "-f", self.configFileName]
        if error:
            args.append("--error")

        cwd = sourceRoot

        deferred = Deferred()
        reactor.spawnProcess(CapturingProcessProtocol(deferred, command), python, args, env=os.environ, path=cwd)
        output = yield deferred
        try:
            plist = readPlistFromString(output)
        except xml.parsers.expat.ExpatError, e:
            print "Error (%s) parsing (%s)" % (e, output)
            raise

        returnValue(plist)


    @inlineCallbacks
    def test_purgeProxies(self):

        # Set up fake user
        purging = "5D6ABA3C-3446-4340-8083-7E37C5BC0B26"
        record = DirectoryRecord(self.directory, "users", purging,
            shortNames=(purging,), enabledForCalendaring=True)
        record.enabled = True # Enabling might not be required here
        self.directory._tmpRecords["shortNames"][purging] = record
        self.directory._tmpRecords["guids"][purging] = record
        pc = self.directory.principalCollection
        purgingPrincipal = pc.principalForRecord(record)

        keeping = "291C2C29-B663-4342-8EA1-A055E6A04D65"
        keepingPrincipal = pc.principalForUID(keeping)

        def getProxies(principal, proxyType):
            subPrincipal = principal.getChild("calendar-proxy-" + proxyType)
            return subPrincipal.readProperty(davxml.GroupMemberSet, None)

        # Add purgingPrincipal as a proxy for keepingPrincipal
        (yield addProxy(keepingPrincipal, "write", purgingPrincipal))

        # Add keepingPrincipal as a proxy for purgingPrincipal
        (yield addProxy(purgingPrincipal, "write", keepingPrincipal))

        # Verify the proxy assignments
        membersProperty = (yield getProxies(keepingPrincipal, "write"))
        self.assertEquals(len(membersProperty.children), 1)
        self.assertEquals(membersProperty.children[0],
            "/principals/__uids__/5D6ABA3C-3446-4340-8083-7E37C5BC0B26/")
        membersProperty = (yield getProxies(keepingPrincipal, "read"))
        self.assertEquals(len(membersProperty.children), 0)

        membersProperty = (yield getProxies(purgingPrincipal, "write"))
        self.assertEquals(len(membersProperty.children), 1)
        self.assertEquals(membersProperty.children[0],
            "/principals/__uids__/291C2C29-B663-4342-8EA1-A055E6A04D65/")
        membersProperty = (yield getProxies(purgingPrincipal, "read"))
        self.assertEquals(len(membersProperty.children), 0)

        # Purging the guid should clear out proxy assignments

        assignments = (yield purgeProxyAssignments(purgingPrincipal))
        self.assertTrue(("5D6ABA3C-3446-4340-8083-7E37C5BC0B26", "write", "291C2C29-B663-4342-8EA1-A055E6A04D65") in assignments)
        self.assertTrue(("291C2C29-B663-4342-8EA1-A055E6A04D65", "write", "5D6ABA3C-3446-4340-8083-7E37C5BC0B26") in assignments)

        membersProperty = (yield getProxies(keepingPrincipal, "write"))
        self.assertEquals(len(membersProperty.children), 0)
        membersProperty = (yield getProxies(purgingPrincipal, "write"))
        self.assertEquals(len(membersProperty.children), 0)

    @inlineCallbacks
    def test_purgeExistingGUID(self):

        # Deprovisioned user is E9E78C86-4829-4520-A35D-70DDADAB2092
        # Keeper user is        291C2C29-B663-4342-8EA1-A055E6A04D65

        before = {
            "calendars" : {
                "__uids__" : {
                    "E9" : {
                        "E7" : {
                            "E9E78C86-4829-4520-A35D-70DDADAB2092" : {
                                "calendar": {
                                    "@xattrs" :
                                    {
                                        resourceAttr : collectionType,
                                    },
                                    "noninvite.ics": {
                                        "@contents" : NON_INVITE_ICS,
                                    },
                                    "organizer.ics": {
                                        "@contents" : ORGANIZER_ICS,
                                    },
                                    "attendee.ics": {
                                        "@contents" : ATTENDEE_ICS,
                                    },
                                },
                            },
                        },
                    },
                    "29" : {
                        "1C" : {
                            "291C2C29-B663-4342-8EA1-A055E6A04D65" : {
                                "calendar": {
                                    "@xattrs" :
                                    {
                                        resourceAttr : collectionType,
                                    },
                                    "organizer.ics": {
                                        "@contents" : ORGANIZER_ICS,
                                    },
                                    "attendee.ics": {
                                        "@contents" : ATTENDEE_ICS,
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
        self.createHierarchy(before, config.DocumentRoot)
        count, assignments = (yield purgeGUID(
            "E9E78C86-4829-4520-A35D-70DDADAB2092",
            self.directory, self.rootResource))

        self.assertEquals(count, 2)

        after = {
            "__uids__" : {
                "E9" : {
                    "E7" : {
                        "E9E78C86-4829-4520-A35D-70DDADAB2092" : {
                            "calendar": {
                                ".db.sqlite": {
                                    "@contents" : None, # ignore contents
                                },
                                ".db.sqlite-journal": {
                                    "@contents" : None, # ignore contents
                                },
                                "noninvite.ics": {
                                    "@contents" : NON_INVITE_ICS,
                                },
                            },
                        },
                    },
                },
                "29" : {
                    "1C" : {
                        "291C2C29-B663-4342-8EA1-A055E6A04D65" : {
                            "inbox": {
                                ".db.sqlite": {
                                    "@contents" : None, # ignore contents
                                },
                                ".db.sqlite-journal": {
                                    "@contents" : None, # ignore contents
                                },
                                "*.ics/UID:7ED97931-9A19-4596-9D4D-52B36D6AB803": {
                                    "@contents" : (
                                        "METHOD:CANCEL",
                                        ),
                                },
                                "*.ics/UID:1974603C-B2C0-4623-92A0-2436DEAB07EF": {
                                    "@contents" : (
                                        "METHOD:REPLY",
                                        "ATTENDEE;CN=Deprovisioned User;CUTYPE=INDIVIDUAL;PARTSTAT=DECLINED:urn:uui\r\n d:E9E78C86-4829-4520-A35D-70DDADAB2092",
                                        ),
                                },
                            },
                            "calendar": {
                                ".db.sqlite": {
                                    "@contents" : None, # ignore contents
                                },
                                ".db.sqlite-journal": {
                                    "@contents" : None, # ignore contents
                                },
                                "organizer.ics": {
                                    "@contents" : (
                                        "STATUS:CANCELLED",
                                    ),
                                },
                                "attendee.ics": {
                                    "@contents" : (
                                        "ATTENDEE;CN=Deprovisioned User;CUTYPE=INDIVIDUAL;PARTSTAT=DECLINED;SCHEDUL\r\n E-STATUS=2.0:urn:uuid:E9E78C86-4829-4520-A35D-70DDADAB2092",
                                        ),
                                },
                            },
                        },
                    },
                },
            },
        }
        self.assertTrue(self.verifyHierarchy(
            os.path.join(config.DocumentRoot, "calendars"),
            after)
        )


    @inlineCallbacks
    def test_purgeNonExistentGUID(self):

        before = {
            "calendars" : {
                "__uids__" : {
                    "1C" : {
                        "B4" : {
                            "1CB4378B-DD76-462D-B4D4-BD131FE89243" : {
                                "calendar": {
                                    "@xattrs" :
                                    {
                                        resourceAttr : collectionType,
                                    },
                                    # non-repeating, non-invite, in the past
                                    # = untouched
                                    "noninvite_past.ics": {
                                        "@contents" : NON_INVITE_PAST_ICS,
                                    },
                                    # non-repeating, non-invite, in the future
                                    # = removed
                                    "noninvite_future.ics": {
                                        "@contents" : NON_INVITE_FUTURE_ICS,
                                    },
                                    "organizer.ics": {
                                        "@contents" : ORGANIZER_ICS_2,
                                    },
                                    "attendee.ics": {
                                        "@contents" : ATTENDEE_ICS_2,
                                    },
                                    "repeating_organizer.ics": {
                                        "@contents" : REPEATING_ORGANIZER_ICS,
                                    },
                                },
                            },
                        },
                    },
                    "29" : {
                        "1C" : {
                            "291C2C29-B663-4342-8EA1-A055E6A04D65" : {
                                "calendar": {
                                    "@xattrs" :
                                    {
                                        resourceAttr : collectionType,
                                    },
                                    "organizer.ics": {
                                        "@contents" : ORGANIZER_ICS_2,
                                    },
                                    "attendee.ics": {
                                        "@contents" : ATTENDEE_ICS_2,
                                    },
                                    "repeating_organizer.ics": {
                                        "@contents" : REPEATING_ORGANIZER_ICS,
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
        self.createHierarchy(before, config.DocumentRoot)
        count, assignments = (yield purgeGUID(
            "1CB4378B-DD76-462D-B4D4-BD131FE89243",
            self.directory, self.rootResource))

        self.assertEquals(count, 4)

        after = {
            "__uids__" : {
                "1C" : {
                    "B4" : {
                        "1CB4378B-DD76-462D-B4D4-BD131FE89243" : {
                            "calendar": {
                                ".db.sqlite": {
                                    "@contents" : None, # ignore contents
                                },
                                ".db.sqlite-journal": {
                                    "@contents" : None, # ignore contents
                                },
                                "noninvite_past.ics": {
                                    "@contents" : NON_INVITE_PAST_ICS,
                                },
                            },
                        },
                    },
                },
                "29" : {
                    "1C" : {
                        "291C2C29-B663-4342-8EA1-A055E6A04D65" : {
                            "inbox": {
                                ".db.sqlite": {
                                    "@contents" : None, # ignore contents
                                },
                                ".db.sqlite-journal": {
                                    "@contents" : None, # ignore contents
                                },
                                "*.ics/UID:7ED97931-9A19-4596-9D4D-52B36D6AB803": {
                                    "@contents" : (
                                        "METHOD:CANCEL",
                                        ),
                                },
                                "*.ics/UID:1974603C-B2C0-4623-92A0-2436DEAB07EF": {
                                    "@contents" : (
                                        "METHOD:REPLY",
                                        "ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=DECLINED:urn:uuid:1CB4378B-DD76-462D-B\r\n 4D4-BD131FE89243",
                                        ),
                                },
                                "*.ics/UID:8ED97931-9A19-4596-9D4D-52B36D6AB803": {
                                    "@contents" : (
                                        "METHOD:CANCEL",
                                        ),
                                },
                            },
                            "calendar": {
                                ".db.sqlite": {
                                    "@contents" : None, # ignore contents
                                },
                                ".db.sqlite-journal": {
                                    "@contents" : None, # ignore contents
                                },
                                "organizer.ics": {
                                    "@contents" : (
                                        "STATUS:CANCELLED",
                                    ),
                                },
                                "attendee.ics": {
                                    "@contents" : (
                                        "ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=DECLINED;SCHEDULE-STATUS=2.0:urn:uuid:\r\n 1CB4378B-DD76-462D-B4D4-BD131FE89243",
                                        ),
                                },
                                "repeating_organizer.ics": {
                                    "@contents" : (
                                        "STATUS:CANCELLED",
                                    ),
                                },
                            },
                        },
                    },
                },
            },
        }
        self.assertTrue(self.verifyHierarchy(
            os.path.join(config.DocumentRoot, "calendars"),
            after)
        )



    @inlineCallbacks
    def test_purgeMultipleNonExistentGUIDs(self):

        before = {
            "calendars" : {
                "__uids__" : {
                    "76" : { # Non-existent
                        "7F" : {
                            "767F9EB0-8A58-4F61-8163-4BE0BB72B873" : {
                                "calendar": {
                                    "@xattrs" :
                                    {
                                        resourceAttr : collectionType,
                                    },
                                    "noninvite.ics": {
                                        "@contents" : NON_INVITE_ICS_3,
                                    },
                                    "organizer.ics": {
                                        "@contents" : ORGANIZER_ICS_3,
                                    },
                                    "attendee.ics": {
                                        "@contents" : ATTENDEE_ICS_3,
                                    },
                                    "attendee2.ics": {
                                        "@contents" : ATTENDEE_ICS_4,
                                    },
                                },
                            },
                        },
                    },
                    "42" : { # Non-existent
                        "EB" : {
                            "42EB074A-F859-4E8F-A4D0-7F0ADCB73D87" : {
                                "calendar": {
                                    "@xattrs" :
                                    {
                                        resourceAttr : collectionType,
                                    },
                                    "organizer.ics": {
                                        "@contents" : ORGANIZER_ICS_3,
                                    },
                                    "attendee.ics": {
                                        "@contents" : ATTENDEE_ICS_3,
                                    },
                                    "attendee2.ics": {
                                        "@contents" : ATTENDEE_ICS_4,
                                    },
                                },
                            },
                        },
                    },
                    "29" : { # Existing
                        "1C" : {
                            "291C2C29-B663-4342-8EA1-A055E6A04D65" : {
                                "calendar": {
                                    "@xattrs" :
                                    {
                                        resourceAttr : collectionType,
                                    },
                                    "organizer.ics": {
                                        "@contents" : ORGANIZER_ICS_3,
                                    },
                                    "attendee.ics": {
                                        "@contents" : ATTENDEE_ICS_3,
                                    },
                                    "attendee2.ics": {
                                        "@contents" : ATTENDEE_ICS_4,
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
        self.createHierarchy(before, config.DocumentRoot)
        count, assignments = (yield purgeGUID(
            "767F9EB0-8A58-4F61-8163-4BE0BB72B873",
            self.directory, self.rootResource))

        self.assertEquals(count, 3)

        after = {
            "__uids__" : {
                "76" : { # Non-existent
                    "7F" : {
                        "767F9EB0-8A58-4F61-8163-4BE0BB72B873" : {
                            "calendar": {
                                ".db.sqlite": {
                                    "@contents" : None, # ignore contents
                                },
                                ".db.sqlite-journal": {
                                    "@contents" : None, # ignore contents
                                },
                                "noninvite.ics": { # event in the past
                                    "@contents" : NON_INVITE_ICS_3,
                                },
                            },
                        },
                    },
                },
                "42" : { # Non-existent -- untouched
                    "EB" : {
                        "42EB074A-F859-4E8F-A4D0-7F0ADCB73D87" : {
                            "calendar": {
                                "@xattrs" :
                                {
                                    resourceAttr : collectionType,
                                },
                                "organizer.ics": {
                                    "@contents" : ORGANIZER_ICS_3,
                                },
                                "attendee.ics": {
                                    "@contents" : ATTENDEE_ICS_3,
                                },
                                "attendee2.ics": {
                                    "@contents" : ATTENDEE_ICS_4,
                                },
                            },
                        },
                    },
                },
                "29" : {
                    "1C" : {
                        "291C2C29-B663-4342-8EA1-A055E6A04D65" : {
                            "inbox": {
                                ".db.sqlite": {
                                    "@contents" : None, # ignore contents
                                },
                                ".db.sqlite-journal": {
                                    "@contents" : None, # ignore contents
                                },
                                "*.ics/UID:7ED97931-9A19-4596-9D4D-52B36D6AB803": {
                                    "@contents" : (
                                        "METHOD:CANCEL",
                                        ),
                                },
                                "*.ics/UID:79F26B10-6ECE-465E-9478-53F2A9FCAFEE": {
                                    "@contents" : (
                                        "METHOD:REPLY",
                                        "ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=DECLINED:urn:uuid:767F9EB0-8A58-4F61-8\r\n 163-4BE0BB72B873",
                                        ),
                                },
                            },
                            "calendar": {
                                ".db.sqlite": {
                                    "@contents" : None, # ignore contents
                                },
                                ".db.sqlite-journal": {
                                    "@contents" : None, # ignore contents
                                },
                                "organizer.ics": {
                                    # Purging non-existent organizer; has non-existent
                                    # and existent attendees
                                    "@contents" : (
                                        "STATUS:CANCELLED",
                                    ),
                                },
                                "attendee.ics": {
                                    # (Note: implicit scheduler doesn't update this)
                                    # Purging non-existent attendee; has non-existent
                                    # organizer and existent attendee
                                    "@contents" : ATTENDEE_ICS_3,
                                },
                                "attendee2.ics": {
                                    # Purging non-existent attendee; has non-existent
                                    # attendee and existent organizer
                                    "@contents" : (
                                        "ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=DECLINED;SCHEDULE-STATUS=2.0:urn:uuid:\r\n 767F9EB0-8A58-4F61-8163-4BE0BB72B873",
                                    )
                                },
                            },
                        },
                    },
                },
            },
        }
        self.assertTrue(self.verifyHierarchy(
            os.path.join(config.DocumentRoot, "calendars"),
            after)
        )


future = (datetime.utcnow() + timedelta(days=1)).strftime("%Y%m%dT%H%M%SZ")
past = (datetime.utcnow() - timedelta(days=1)).strftime("%Y%m%dT%H%M%SZ")

# For test_purgeExistingGUID

# No organizer/attendee
NON_INVITE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:151AFC76-6036-40EF-952B-97D1840760BF
SUMMARY:Non Invitation
DTSTART:%s
DURATION:PT1H
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (past,)

# Purging existing organizer; has existing attendee
ORGANIZER_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:7ED97931-9A19-4596-9D4D-52B36D6AB803
SUMMARY:Organizer
DTSTART:%s
DURATION:PT1H
ORGANIZER:urn:uuid:E9E78C86-4829-4520-A35D-70DDADAB2092
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:E9E78C86-4829-4520-A35D-70DDADAB2092
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:291C2C29-B663-4342-8EA1-A055E6A04D65
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)

# Purging existing attendee; has existing organizer
ATTENDEE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1974603C-B2C0-4623-92A0-2436DEAB07EF
SUMMARY:Attendee
DTSTART:%s
DURATION:PT1H
ORGANIZER:urn:uuid:291C2C29-B663-4342-8EA1-A055E6A04D65
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:E9E78C86-4829-4520-A35D-70DDADAB2092
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:291C2C29-B663-4342-8EA1-A055E6A04D65
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)


# For test_purgeNonExistentGUID

# No organizer/attendee, in the past
NON_INVITE_PAST_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:151AFC76-6036-40EF-952B-97D1840760BF
SUMMARY:Non Invitation
DTSTART:%s
DURATION:PT1H
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (past,)

# No organizer/attendee, in the future
NON_INVITE_FUTURE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:251AFC76-6036-40EF-952B-97D1840760BF
SUMMARY:Non Invitation
DTSTART:%s
DURATION:PT1H
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)


# Purging non-existent organizer; has existing attendee
ORGANIZER_ICS_2 = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:7ED97931-9A19-4596-9D4D-52B36D6AB803
SUMMARY:Organizer
DTSTART:%s
DURATION:PT1H
ORGANIZER:urn:uuid:1CB4378B-DD76-462D-B4D4-BD131FE89243
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:1CB4378B-DD76-462D-B4D4-BD131FE89243
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:291C2C29-B663-4342-8EA1-A055E6A04D65
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)

# Purging non-existent attendee; has existing organizer
ATTENDEE_ICS_2 = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1974603C-B2C0-4623-92A0-2436DEAB07EF
SUMMARY:Attendee
DTSTART:%s
DURATION:PT1H
ORGANIZER:urn:uuid:291C2C29-B663-4342-8EA1-A055E6A04D65
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:1CB4378B-DD76-462D-B4D4-BD131FE89243
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:291C2C29-B663-4342-8EA1-A055E6A04D65
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)

# Purging non-existent organizer; has existing attendee; repeating
REPEATING_ORGANIZER_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:8ED97931-9A19-4596-9D4D-52B36D6AB803
SUMMARY:Repeating Organizer
DTSTART:%s
DURATION:PT1H
RRULE:FREQ=DAILY;COUNT=400
ORGANIZER:urn:uuid:1CB4378B-DD76-462D-B4D4-BD131FE89243
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:1CB4378B-DD76-462D-B4D4-BD131FE89243
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:291C2C29-B663-4342-8EA1-A055E6A04D65
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (past,)


# For test_purgeMultipleNonExistentGUIDs

# No organizer/attendee
NON_INVITE_ICS_3 = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:151AFC76-6036-40EF-952B-97D1840760BF
SUMMARY:Non Invitation
DTSTART:%s
DURATION:PT1H
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (past,)

# Purging non-existent organizer; has non-existent and existent attendees
ORGANIZER_ICS_3 = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:7ED97931-9A19-4596-9D4D-52B36D6AB803
SUMMARY:Organizer
DTSTART:%s
DURATION:PT1H
ORGANIZER:urn:uuid:767F9EB0-8A58-4F61-8163-4BE0BB72B873
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:767F9EB0-8A58-4F61-8163-4BE0BB72B873
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:42EB074A-F859-4E8F-A4D0-7F0ADCB73D87
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:291C2C29-B663-4342-8EA1-A055E6A04D65
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)

# Purging non-existent attendee; has non-existent organizer and existent attendee
# (Note: Implicit scheduling doesn't update this at all for the existing attendee)
ATTENDEE_ICS_3 = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1974603C-B2C0-4623-92A0-2436DEAB07EF
SUMMARY:Attendee
DTSTART:%s
DURATION:PT1H
ORGANIZER:urn:uuid:42EB074A-F859-4E8F-A4D0-7F0ADCB73D87
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:767F9EB0-8A58-4F61-8163-4BE0BB72B873
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:291C2C29-B663-4342-8EA1-A055E6A04D65
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:42EB074A-F859-4E8F-A4D0-7F0ADCB73D87
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)

# Purging non-existent attendee; has non-existent attendee and existent organizer
ATTENDEE_ICS_4 = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:79F26B10-6ECE-465E-9478-53F2A9FCAFEE
SUMMARY:2 non-existent attendees
DTSTART:%s
DURATION:PT1H
ORGANIZER:urn:uuid:291C2C29-B663-4342-8EA1-A055E6A04D65
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:291C2C29-B663-4342-8EA1-A055E6A04D65
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:767F9EB0-8A58-4F61-8163-4BE0BB72B873
ATTENDEE;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED:urn:uuid:42EB074A-F859-4E8F-A4D0-7F0ADCB73D87
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % (future,)

