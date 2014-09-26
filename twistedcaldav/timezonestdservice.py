##
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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

"""
Timezone service resource and operations.

This is based on http://tools.ietf.org/html/draft-douglass-timezone-service which is the CalConnect
proposal for a standard timezone service.
"""

__all__ = [
    "TimezoneStdServiceResource",
]

from twext.python.log import Logger
from txweb2 import responsecode
from txweb2.dav.method.propfind import http_PROPFIND
from txweb2.dav.noneprops import NonePropertyStore
from txweb2.http import HTTPError, JSONResponse
from txweb2.http import Response
from txweb2.http_headers import MimeType
from txweb2.stream import MemoryStream
from txdav.xml import element as davxml

from twisted.internet.defer import succeed, inlineCallbacks, returnValue, \
    DeferredList

from twistedcaldav import xmlutil
from twistedcaldav.client.geturl import getURL
from twistedcaldav.config import config
from twistedcaldav.extensions import DAVResource, \
    DAVResourceWithoutChildrenMixin
from twistedcaldav.ical import tzexpandlocal
from twistedcaldav.resource import ReadOnlyNoCopyResourceMixIn
from twistedcaldav.timezones import TimezoneException, TimezoneCache, readVTZ, \
    addVTZ
from twistedcaldav.xmlutil import addSubElement

from pycalendar.icalendar.calendar import Calendar
from pycalendar.datetime import DateTime
from pycalendar.exceptions import InvalidData

import hashlib
import itertools
import json
import os

log = Logger()

class TimezoneStdServiceResource (ReadOnlyNoCopyResourceMixIn, DAVResourceWithoutChildrenMixin, DAVResource):
    """
    Timezone Service resource. Strictly speaking this is an HTTP-only resource no WebDAV support needed.

    Extends L{DAVResource} to provide timezone service functionality.
    """

    def __init__(self, parent):
        """
        @param parent: the parent resource of this one.
        """
        assert parent is not None

        DAVResource.__init__(self, principalCollections=parent.principalCollections())

        self.parent = parent
        self.expandcache = {}
        self.primary = True
        self.info_source = None

        if config.TimezoneService.Mode == "primary":
            log.info("Using primary Timezone Service")
            self._initPrimaryService()
        elif config.TimezoneService.Mode == "secondary":
            log.info("Using secondary Timezone Service")
            self._initSecondaryService()
        else:
            raise ValueError("Invalid TimezoneService mode: %s" % (config.TimezoneService.Mode,))

        self.formats = []
        self.formats.append("text/calendar")
        self.formats.append("text/plain")
        if config.EnableJSONData:
            self.formats.append("application/calendar+json")


    def _initPrimaryService(self):
        tzpath = TimezoneCache.getDBPath()
        xmlfile = os.path.join(tzpath, "timezones.xml")
        self.timezones = PrimaryTimezoneDatabase(tzpath, xmlfile)
        if not os.path.exists(xmlfile):
            self.timezones.createNewDatabase()
        else:
            self.timezones.readDatabase()
        self.info_source = TimezoneCache.version


    def _initSecondaryService(self):

        # Must have writeable paths
        tzpath = TimezoneCache.getDBPath()
        xmlfile = config.TimezoneService.XMLInfoPath
        if not xmlfile:
            xmlfile = os.path.join(tzpath, "timezones.xml")
        self.timezones = SecondaryTimezoneDatabase(tzpath, xmlfile, None)
        try:
            self.timezones.readDatabase()
        except:
            pass
        self.info_source = "Secondary"
        self.primary = False


    def onStartup(self):
        return self.timezones.onStartup()


    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties


    def etag(self):
        return succeed(None)


    def checkPreconditions(self, request):
        return None


    def checkPrivileges(self, request, privileges, recurse=False, principal=None, inherited_aces=None):
        return succeed(None)


    def defaultAccessControlList(self):
        return succeed(
            davxml.ACL(
                # DAV:Read for all principals (includes anonymous)
                davxml.ACE(
                    davxml.Principal(davxml.All()),
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                    ),
                    davxml.Protected(),
                ),
            )
        )


    def contentType(self):
        return MimeType.fromString("text/html; charset=utf-8")


    def resourceType(self):
        return None


    def isCollection(self):
        return False


    def isCalendarCollection(self):
        return False


    def isPseudoCalendarCollection(self):
        return False


    def render(self, request):
        output = """<html>
<head>
<title>Timezone Standard Service Resource</title>
</head>
<body>
<h1>Timezone Standard Service Resource.</h1>
</body
</html>"""

        response = Response(200, {}, output)
        response.headers.setHeader("content-type", MimeType("text", "html"))
        return response

    http_PROPFIND = http_PROPFIND

    def http_GET(self, request):
        """
        The timezone service POST method.
        """

        # GET and POST do the same thing
        return self.http_POST(request)


    def http_POST(self, request):
        """
        The timezone service POST method.
        """

        # Check authentication and access controls
        def _gotResult(_):

            if not request.args:
                # Do normal GET behavior
                return self.render(request)

            action = request.args.get("action", ("",))
            if len(action) != 1:
                raise HTTPError(JSONResponse(
                    responsecode.BAD_REQUEST,
                    {
                        "error": "invalid-action",
                        "description": "Invalid action query parameter",
                    },
                    pretty=config.TimezoneService.PrettyPrintJSON,
                ))
            action = action[0]

            action = {
                "capabilities"  : self.doCapabilities,
                "list"          : self.doList,
                "get"           : self.doGet,
                "expand"        : self.doExpand,
            }.get(action, None)

            if action is None:
                raise HTTPError(JSONResponse(
                    responsecode.BAD_REQUEST,
                    {
                        "error": "invalid-action",
                        "description": "Unknown action query parameter",
                    },
                    pretty=config.TimezoneService.PrettyPrintJSON,
                ))

            return action(request)

        d = self.authorize(request, (davxml.Read(),))
        d.addCallback(_gotResult)
        return d


    def doCapabilities(self, request):
        """
        Return a list of all timezones known to the server.
        """

        result = {
            "info" : {
                "version": "1",
                "primary-source" if self.primary else "secondary_source": self.info_source,
                "contacts" : [],
            },
            "actions" : [
                {
                    "name": "capabilities",
                    "parameters": [],
                },
                {
                    "name": "list",
                    "parameters": [
                        {"name": "changedsince", "required": False, "multi": False, },
                    ],
                },
                {
                    "name": "get",
                    "parameters": [
                        {"name": "format", "required": False, "multi": False, "values": self.formats, },
                        {"name": "tzid", "required": True, "multi": False, },
                    ],
                },
                {
                    "name": "expand",
                    "parameters": [
                        {"name": "tzid", "required": True, "multi": False, },
                        {"name": "start", "required": False, "multi": False, },
                        {"name": "end", "required": False, "multi": False, },
                    ],
                },
            ]
        }
        return JSONResponse(responsecode.OK, result, pretty=config.TimezoneService.PrettyPrintJSON)


    def doList(self, request):
        """
        Return a list of all timezones known to the server.
        """

        changedsince = request.args.get("changedsince", ())
        if len(changedsince) > 1:
            raise HTTPError(JSONResponse(
                responsecode.BAD_REQUEST,
                {
                    "error": "invalid-changedsince",
                    "description": "Invalid changedsince query parameter",
                },
                pretty=config.TimezoneService.PrettyPrintJSON,
            ))
        if len(changedsince) == 1:
            # Validate a date-time stamp
            changedsince = changedsince[0]
            try:
                dt = DateTime.parseText(changedsince)
            except ValueError:
                raise HTTPError(JSONResponse(
                    responsecode.BAD_REQUEST,
                    {
                        "error": "invalid-changedsince",
                        "description": "Invalid changedsince query parameter",
                    },
                    pretty=config.TimezoneService.PrettyPrintJSON,
                ))
            if not dt.utc():
                raise HTTPError(JSONResponse(
                    responsecode.BAD_REQUEST,
                    {
                        "error": "invalid-changedsince",
                        "description": "Invalid changedsince query parameter - not UTC",
                    },
                    pretty=config.TimezoneService.PrettyPrintJSON,
                ))

        timezones = []
        for tz in self.timezones.listTimezones(changedsince):
            timezones.append({
                "tzid": tz.tzid,
                "last-modified": tz.dtstamp,
                "aliases": tz.aliases,
            })
        result = {
            "dtstamp": self.timezones.dtstamp,
            "timezones": timezones,
        }
        return JSONResponse(responsecode.OK, result, pretty=config.TimezoneService.PrettyPrintJSON)


    def doGet(self, request):
        """
        Return the specified timezone data.
        """

        tzids = request.args.get("tzid", ())
        if len(tzids) != 1:
            raise HTTPError(JSONResponse(
                responsecode.BAD_REQUEST,
                {
                    "error": "invalid-tzid",
                    "description": "Invalid tzid query parameter",
                },
                pretty=config.TimezoneService.PrettyPrintJSON,
            ))

        format = request.args.get("format", ("text/calendar",))
        if len(format) != 1 or format[0] not in self.formats:
            raise HTTPError(JSONResponse(
                responsecode.BAD_REQUEST,
                {
                    "error": "invalid-format",
                    "description": "Invalid format query parameter",
                },
                pretty=config.TimezoneService.PrettyPrintJSON,
            ))
        format = format[0]

        calendar = self.timezones.getTimezone(tzids[0])
        if calendar is None:
            raise HTTPError(JSONResponse(
                responsecode.NOT_FOUND,
                {
                    "error": "tzid-not-found",
                    "description": "Tzid could not be found",
                },
                pretty=config.TimezoneService.PrettyPrintJSON,
            ))

        tzdata = calendar.getText(format=format if format != "text/plain" else None)

        response = Response()
        response.stream = MemoryStream(tzdata)
        response.headers.setHeader("content-type", MimeType.fromString("%s; charset=utf-8" % (format,)))
        return response


    def doExpand(self, request):
        """
        Expand a timezone within specified start/end dates.
        """

        tzids = request.args.get("tzid", ())
        if len(tzids) != 1:
            raise HTTPError(JSONResponse(
                responsecode.BAD_REQUEST,
                {
                    "error": "invalid-tzid",
                    "description": "Invalid tzid query parameter",
                },
                pretty=config.TimezoneService.PrettyPrintJSON,
            ))

        try:
            start = request.args.get("start", ())
            if len(start) > 1:
                raise ValueError()
            elif len(start) == 1:
                start = DateTime.parseText("{}0101".format(int(start[0])))
            else:
                start = DateTime.getToday()
                start.setDay(1)
                start.setMonth(1)
        except ValueError:
            raise HTTPError(JSONResponse(
                responsecode.BAD_REQUEST,
                {
                    "error": "invalid-start",
                    "description": "Invalid start query parameter",
                },
                pretty=config.TimezoneService.PrettyPrintJSON,
            ))

        try:
            end = request.args.get("end", ())
            if len(end) > 1:
                raise ValueError()
            elif len(end) == 1:
                end = DateTime.parseText("{}0101".format(int(end[0])))
            else:
                end = DateTime.getToday()
                end.setDay(1)
                end.setMonth(1)
                end.offsetYear(10)
            if end <= start:
                raise ValueError()
        except ValueError:
            raise HTTPError(JSONResponse(
                responsecode.BAD_REQUEST,
                {
                    "error": "invalid-end",
                    "description": "Invalid end query parameter",
                },
                pretty=config.TimezoneService.PrettyPrintJSON,
            ))

        tzid = tzids[0]
        tzdata = self.timezones.getTimezone(tzid)
        if tzdata is None:
            raise HTTPError(JSONResponse(
                responsecode.NOT_FOUND,
                {
                    "error": "tzid-not-found",
                    "description": "Tzid could not be found",
                },
                pretty=config.TimezoneService.PrettyPrintJSON,
            ))

        # Now do the expansion (but use a cache to avoid re-calculating TZs)
        observances = self.expandcache.get((tzid, start, end), None)
        if observances is None:
            observances = tzexpandlocal(tzdata, start, end)
            self.expandcache[(tzid, start, end)] = observances

        # Turn into JSON
        result = {
            "dtstamp": self.timezones.dtstamp,
            "observances": [
                {
                    "name": name,
                    "onset": onset.getXMLText(),
                    "utc-offset-from": utc_offset_from,
                    "utc-offset-to": utc_offset_to,
                } for onset, utc_offset_from, utc_offset_to, name in observances
            ],
        }
        return JSONResponse(responsecode.OK, result, pretty=config.TimezoneService.PrettyPrintJSON)



class TimezoneInfo(object):
    """
    Maintains information from an on-disk store of timezone files.
    """

    def __init__(self, tzid, aliases, dtstamp, md5):
        self.tzid = tzid
        self.aliases = aliases
        self.dtstamp = dtstamp
        self.md5 = md5


    @classmethod
    def readXML(cls, node):
        """
        Parse XML data.
        """
        if node.tag != "timezone":
            return None
        tzid = node.findtext("tzid")
        dtstamp = node.findtext("dtstamp")
        aliases = tuple([alias_node.text for alias_node in node.findall("alias")])
        md5 = node.findtext("md5")
        return cls(tzid, aliases, dtstamp, md5)


    def generateXML(self, parent):
        """
        Generate the XML element for this timezone info.
        """
        node = xmlutil.addSubElement(parent, "timezone")
        xmlutil.addSubElement(node, "tzid", self.tzid)
        xmlutil.addSubElement(node, "dtstamp", self.dtstamp)
        for alias in self.aliases:
            xmlutil.addSubElement(node, "alias", alias)
        xmlutil.addSubElement(node, "md5", self.md5)



class CommonTimezoneDatabase(object):
    """
    Maintains the database of timezones read from an XML file.
    """

    def __init__(self, basepath, xmlfile):
        self.basepath = basepath
        self.xmlfile = xmlfile
        self.dtstamp = None
        self.timezones = {}
        self.aliases = {}


    def onStartup(self):
        return succeed(None)


    def readDatabase(self):
        """
        Read in XML data.
        """
        _ignore, root = xmlutil.readXML(self.xmlfile, "timezones")
        self.dtstamp = root.findtext("dtstamp")
        for child in root:
            if child.tag == "timezone":
                tz = TimezoneInfo.readXML(child)
                if tz:
                    self.timezones[tz.tzid] = tz
                    for alias in tz.aliases:
                        self.aliases[alias] = tz.tzid


    def listTimezones(self, changedsince):
        """
        List timezones (not aliases) possibly changed since a particular dtstamp.
        """

        for tzid, tzinfo in sorted(self.timezones.items(), key=lambda x: x[0]):
            # Ignore those that are aliases
            if tzid in self.aliases:
                continue

            # Detect timestamp changes
            if changedsince and tzinfo.dtstamp <= changedsince:
                continue

            yield tzinfo


    def getTimezone(self, tzid):
        """
        Generate a PyCalendar containing the requested timezone.
        """
        # We will just use our existing TimezoneCache here
        calendar = Calendar()
        try:
            vtz = readVTZ(tzid)
            calendar.addComponent(vtz.getComponents()[0].duplicate())
        except TimezoneException:

            # Check if an alias exists and create data for that
            if tzid in self.aliases:
                try:
                    vtz = readVTZ(self.aliases[tzid])
                except TimezoneException:
                    log.error("Failed to find timezone data for alias: %s" % (tzid,))
                    return None
                else:
                    vtz = vtz.duplicate()
                    vtz.getComponents()[0].getProperties("TZID")[0].setValue(tzid)
                    addVTZ(tzid, vtz)
                    calendar.addComponent(vtz.getComponents()[0].duplicate())
            else:
                log.error("Failed to find timezone data for: %s" % (tzid,))
                return None

        return calendar


    def _dumpTZs(self):

        _ignore, root = xmlutil.newElementTreeWithRoot("timezones")
        addSubElement(root, "dtstamp", self.dtstamp)
        for _ignore, v in sorted(self.timezones.items(), key=lambda x: x[0]):
            v.generateXML(root)
        xmlutil.writeXML(self.xmlfile, root)


    def _buildAliases(self):
        """
        Rebuild aliases mappings from current tzinfo.
        """

        self.aliases = {}
        for tzinfo in self.timezones.values():
            for alias in tzinfo.aliases:
                self.aliases[alias] = tzinfo.tzid



class PrimaryTimezoneDatabase(CommonTimezoneDatabase):
    """
    Maintains the database of timezones read from an XML file.
    """

    def __init__(self, basepath, xmlfile):
        super(PrimaryTimezoneDatabase, self).__init__(basepath, xmlfile)


    def createNewDatabase(self):
        """
        Create a new DB xml file from scratch by scanning zoneinfo.
        """

        self.dtstamp = DateTime.getNowUTC().getXMLText()
        self._scanTZs("")
        self._dumpTZs()


    def _scanTZs(self, path, checkIfChanged=False):
        # Read in all timezone files first
        for item in os.listdir(os.path.join(self.basepath, path)):
            fullPath = os.path.join(self.basepath, path, item)
            if item.find('.') == -1:
                self._scanTZs(os.path.join(path, item), checkIfChanged)
            elif item.endswith(".ics"):
                # Build TimezoneInfo object
                tzid = os.path.join(path, item[:-4])
                try:
                    md5 = hashlib.md5(open(fullPath).read()).hexdigest()
                except IOError:
                    log.error("Unable to read timezone file: %s" % (fullPath,))
                    continue

                if checkIfChanged:
                    oldtz = self.timezones.get(tzid)
                    if oldtz != None and oldtz.md5 == md5:
                        continue
                    self.changeCount += 1
                    self.changed.add(tzid)
                self.timezones[tzid] = TimezoneInfo(tzid, (), self.dtstamp, md5)

        # Try links (aliases) file
        try:
            aliases = open(os.path.join(self.basepath, "links.txt")).read()
        except IOError, e:
            log.error("Unable to read links.txt file: %s" % (str(e),))
            aliases = ""

        try:
            for alias in aliases.splitlines():
                alias_from, alias_to = alias.split("\t")
                tzinfo = self.timezones.get(alias_to)
                if tzinfo:
                    if alias_from != alias_to:
                        if alias_from not in tzinfo.aliases:
                            tzinfo.aliases += (alias_from,)
                        self.aliases[alias_from] = alias_to
                else:
                    log.error("Missing alias from '%s' to '%s'" % (alias_from, alias_to,))
        except ValueError:
            log.error("Unable to parse links.txt file: %s" % (str(e),))


    def updateDatabase(self):
        """
        Update existing DB info by comparing md5's.
        """
        self.dtstamp = DateTime.getNowUTC().getXMLText()
        self.changeCount = 0
        self.changed = set()
        self._scanTZs("", checkIfChanged=True)
        if self.changeCount:
            self._dumpTZs()



class SecondaryTimezoneDatabase(CommonTimezoneDatabase):
    """
    Caches a database of timezones from another timezone service.
    """

    def __init__(self, basepath, xmlfile, uri):
        super(SecondaryTimezoneDatabase, self).__init__(basepath, xmlfile)
        self.uri = uri
        self.discovered = False
        self._url = None

        log.debug("Configuring secondary server with basepath: %s" % (self.basepath,))

        if not os.path.exists(self.basepath):
            os.makedirs(self.basepath)

        # Paths need to be writeable
        if not os.access(basepath, os.W_OK):
            raise ValueError("Secondary Timezone Service needs writeable zoneinfo path at: %s" % (basepath,))
        if os.path.exists(xmlfile) and not os.access(xmlfile, os.W_OK):
            raise ValueError("Secondary Timezone Service needs writeable xmlfile path at: %s" % (xmlfile,))


    def onStartup(self):
        return self.syncWithServer()


    @inlineCallbacks
    def syncWithServer(self):
        """
        Sync local data with that from the server we are replicating.
        """

        log.debug("Sync'ing with secondary server")
        result = (yield self._getTimezoneListFromServer())
        if result is None:
            # Nothing changed since last sync
            log.debug("No changes on secondary server")
            returnValue(None)
        newdtstamp, newtimezones = result

        # Compare timezone infos

        # New ones on the server
        newtzids = set(newtimezones.keys()) - set(self.timezones.keys())

        # Check for changes
        changedtzids = set()
        for tzid in set(newtimezones.keys()) & set(self.timezones.keys()):
            if self.timezones[tzid].dtstamp < newtimezones[tzid].dtstamp:
                changedtzids.add(tzid)

        log.debug("Fetching %d new, %d changed timezones on secondary server" % (len(newtzids), len(changedtzids),))

        # Now apply changes - do requests in parallel for speedier fetching
        BATCH = 5
        tzids = list(itertools.chain(newtzids, changedtzids))
        tzids.sort()
        while tzids:
            yield DeferredList([self._getTimezoneFromServer(newtimezones[tzid]) for tzid in tzids[0:BATCH]])
            tzids = tzids[BATCH:]

        self.dtstamp = newdtstamp
        self._dumpTZs()
        self._buildAliases()

        log.debug("Sync with secondary server complete")

        returnValue((len(newtzids), len(changedtzids),))


    @inlineCallbacks
    def _discoverServer(self):
        """
        Make sure we know the timezone service path
        """

        if self.uri is None:
            if config.TimezoneService.SecondaryService.Host:
                self.uri = "https://%s/.well-known/timezone" % (config.TimezoneService.SecondaryService.Host,)
            elif config.TimezoneService.SecondaryService.URI:
                self.uri = config.TimezoneService.SecondaryService.URI
        elif not self.uri.startswith("https:") and not self.uri.startswith("http:"):
            self.uri = "https://%s/.well-known/timezone" % (self.uri,)

        testURI = "%s?action=capabilities" % (self.uri,)
        log.debug("Discovering secondary server: %s" % (testURI,))
        response = (yield getURL(testURI))
        if response is None or response.code / 100 != 2:
            log.error("Unable to discover secondary server: %s" % (testURI,))
            self.discovered = False
            returnValue(False)

        # Cache the redirect target
        if hasattr(response, "location"):
            self.uri = response.location
            log.debug("Redirected secondary server to: %s" % (self.uri,))

        # TODO: Ignoring the data from capabilities for now

        self.discovered = True
        returnValue(True)


    @inlineCallbacks
    def _getTimezoneListFromServer(self):
        """
        Retrieve the timezone list from the specified server
        """

        # Make sure we have the server
        if not self.discovered:
            result = (yield self._discoverServer())
            if not result:
                returnValue(None)

        # List all from the server
        url = "%s?action=list" % (self.uri,)
        if self.dtstamp:
            url = "%s&changedsince=%s" % (url, self.dtstamp,)
        log.debug("Getting timezone list from secondary server: %s" % (url,))
        response = (yield getURL(url))
        if response is None or response.code / 100 != 2:
            returnValue(None)

        ct = response.headers.getRawHeaders("content-type", ("bogus/type",))[0]
        ct = ct.split(";", 1)
        ct = ct[0]
        if ct not in ("application/json",):
            returnValue(None)

        try:
            jroot = json.loads(response.data)
            dtstamp = jroot["dtstamp"]
            timezones = {}
            for timezone in jroot["timezones"]:
                tzid = timezone["tzid"]
                lastmod = timezone["last-modified"]
                aliases = timezone.get("aliases", ())
                timezones[tzid] = TimezoneInfo(tzid, aliases, lastmod, None)
        except (ValueError, KeyError):
            log.debug("Failed to parse JSON timezone list response: %s" % (response.data,))
            returnValue(None)
        log.debug("Got %s timezones from secondary server" % (len(timezones),))

        returnValue((dtstamp, timezones,))


    @inlineCallbacks
    def _getTimezoneFromServer(self, tzinfo):
        # List all from the server
        url = "%s?action=get&tzid=%s" % (self.uri, tzinfo.tzid,)
        log.debug("Getting timezone from secondary server: %s" % (url,))
        response = (yield getURL(url))
        if response is None or response.code / 100 != 2:
            returnValue(None)

        ct = response.headers.getRawHeaders("content-type", ("bogus/type",))[0]
        ct = ct.split(";", 1)
        ct = ct[0]
        if ct not in ("text/calendar",):
            log.error("Invalid content-type '%s' for tzid : %s" % (ct, tzinfo.tzid,))
            returnValue(None)

        ical = response.data
        try:
            calendar = Calendar.parseText(ical)
        except InvalidData:
            log.error("Invalid calendar data for tzid: %s" % (tzinfo.tzid,))
            returnValue(None)
        ical = calendar.getText()

        tzinfo.md5 = hashlib.md5(ical).hexdigest()

        try:
            tzpath = os.path.join(self.basepath, tzinfo.tzid) + ".ics"
            if not os.path.exists(os.path.dirname(tzpath)):
                os.makedirs(os.path.dirname(tzpath))
            f = open(tzpath, "w")
            f.write(ical)
            f.close()
        except IOError, e:
            log.error("Unable to write calendar file for %s: %s" % (tzinfo.tzid, str(e),))
        else:
            self.timezones[tzinfo.tzid] = tzinfo


    def _removeTimezone(self, tzid):
        tzpath = os.path.join(self.basepath, tzid) + ".ics"
        try:
            os.remove(tzpath)
            del self.timezones[tzid]
        except IOError, e:
            log.error("Unable to write calendar file for %s: %s" % (tzid, str(e),))
