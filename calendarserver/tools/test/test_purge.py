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
from calendarserver.tools.purge import purgeOldEvents, purgeGUID
from datetime import datetime, timedelta
from twext.python.filepath import CachingFilePath as FilePath
from twext.python.plistlib import readPlistFromString
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, Deferred, returnValue
from twistedcaldav.config import config
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

        testRoot = os.path.join(os.path.dirname(__file__), "deprovision")
        templateName = os.path.join(testRoot, "caldavd.plist")
        templateFile = open(templateName)
        template = templateFile.read()
        templateFile.close()

        newConfig = template % {
            "ServerRoot" : os.path.abspath(config.ServerRoot),
        }
        configFilePath = FilePath(os.path.join(config.ConfigRoot, "caldavd.plist"))
        configFilePath.setContent(newConfig)

        self.configFileName = configFilePath.path
        config.load(self.configFileName)

        os.makedirs(config.DataRoot)
        os.makedirs(config.DocumentRoot)

        origUsersFile = FilePath(os.path.join(os.path.dirname(__file__),
            "deprovision", "users-groups.xml"))
        copyUsersFile = FilePath(os.path.join(config.DataRoot, "accounts.xml"))
        origUsersFile.copyTo(copyUsersFile)

        origResourcesFile = FilePath(os.path.join(os.path.dirname(__file__),
            "deprovision", "resources-locations.xml"))
        copyResourcesFile = FilePath(os.path.join(config.DataRoot, "resources.xml"))
        origResourcesFile.copyTo(copyResourcesFile)

        origAugmentFile = FilePath(os.path.join(os.path.dirname(__file__),
            "deprovision", "augments.xml"))
        copyAugmentFile = FilePath(os.path.join(config.DataRoot, "augments.xml"))
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
    def test_purgeGUID(self):
        # deprovision, add an event

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
        count = (yield purgeGUID("E9E78C86-4829-4520-A35D-70DDADAB2092",
            self.directory, self.rootResource))

        # print config.DocumentRoot
        # import pdb; pdb.set_trace()
        self.assertEquals(count, 3)

        after = {
            "__uids__" : {
                "E9" : {
                    "E7" : {
                        "E9E78C86-4829-4520-A35D-70DDADAB2092" : {
                            "calendar": {
                                ".db.sqlite": {
                                    "@contents" : None, # ignore contents
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


future = (datetime.utcnow() + timedelta(days=1)).strftime("%Y%m%dT%H%M%SZ")
past = (datetime.utcnow() - timedelta(days=1)).strftime("%Y%m%dT%H%M%SZ")

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

