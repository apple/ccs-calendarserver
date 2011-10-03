##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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
from twext.web2 import responsecode
from twext.web2.dav import davxml
from twext.web2.dav.http import ErrorResponse
from twext.web2.dav.method.propfind import http_PROPFIND
from twext.web2.dav.noneprops import NonePropertyStore
from twext.web2.http import HTTPError, StatusResponse
from twext.web2.http import Response
from twext.web2.http import XMLResponse
from twext.web2.http_headers import MimeType
from twext.web2.stream import MemoryStream

from twisted.internet.defer import succeed, inlineCallbacks, returnValue

from twistedcaldav import timezonexml, xmlutil
from twistedcaldav.client.geturl import getURL
from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.extensions import DAVResource,\
    DAVResourceWithoutChildrenMixin
from twistedcaldav.ical import tzexpandlocal
from twistedcaldav.resource import ReadOnlyNoCopyResourceMixIn
from twistedcaldav.timezones import TimezoneException, TimezoneCache, readVTZ,\
    addVTZ
from twistedcaldav.xmlutil import addSubElement, readXMLString

from pycalendar.calendar import PyCalendar
from pycalendar.datetime import PyCalendarDateTime
from pycalendar.exceptions import PyCalendarInvalidData

import hashlib
import itertools
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

        if config.TimezoneService.Mode == "primary":
            log.info("Using primary Timezone Service")
            self._initPrimaryService()
        elif config.TimezoneService.Mode == "secondary":
            log.info("Using secondary Timezone Service")
            self._initSecondaryService()
        else:
            raise ValueError("Invalid TimezoneService mode: %s" % (config.TimezoneService.Mode,))
            
    def _initPrimaryService(self):
        tzpath = TimezoneCache.getDBPath()
        xmlfile = os.path.join(tzpath, "timezones.xml")
        self.timezones = PrimaryTimezoneDatabase(tzpath, xmlfile)
        if not os.path.exists(xmlfile):
            self.timezones.createNewDatabase()
        else:
            self.timezones.readDatabase()

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

    def onStartup(self):
        return self.timezones.onStartup()

    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties

    def etag(self):
        return None

    def checkPreconditions(self, request):
        return None

    def checkPrivileges(self, request, privileges, recurse=False, principal=None, inherited_aces=None):
        return succeed(None)

    def defaultAccessControlList(self):
        return davxml.ACL(
            # DAV:Read for all principals (includes anonymous)
            davxml.ACE(
                davxml.Principal(davxml.All()),
                davxml.Grant(
                    davxml.Privilege(davxml.Read()),
                ),
                davxml.Protected(),
            ),
        )

    def contentType(self):
        return MimeType.fromString("text/html; charset=utf-8");

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
                raise HTTPError(StatusResponse(
                    responsecode.BAD_REQUEST,
                    "Invalid action query parameter",
                ))
            action = action[0]
                
            action = {
                "capabilities"  : self.doCapabilities,
                "list"          : self.doList,
                "get"           : self.doGet,
                "expand"        : self.doExpand,
            }.get(action, None)
            
            if action is None:
                raise HTTPError(StatusResponse(
                    responsecode.BAD_REQUEST,
                    "Unknown action query parameter",
                ))
    
            return action(request)
            
        d = self.authorize(request, (davxml.Read(),))
        d.addCallback(_gotResult)
        return d

    def doCapabilities(self, request):
        """
        Return a list of all timezones known to the server.
        """
        
        result = timezonexml.Capabilities(
            
            timezonexml.Operation(
                timezonexml.Action.fromString("capabilities"),
                timezonexml.Description.fromString("Get capabilities of the server"),
            ),
            
            timezonexml.Operation(
                timezonexml.Action.fromString("list"),
                timezonexml.Description.fromString("List timezones on the server"),
                timezonexml.AcceptParameter(
                    timezonexml.Name.fromString("changedsince"),
                    timezonexml.Required.fromString("false"),
                    timezonexml.Multi.fromString("false"),
                ),
            ),
            
            timezonexml.Operation(
                timezonexml.Action.fromString("get"),
                timezonexml.Description.fromString("Get timezones from the server"),
                timezonexml.AcceptParameter(
                    timezonexml.Name.fromString("format"),
                    timezonexml.Required.fromString("false"),
                    timezonexml.Multi.fromString("false"),
                    timezonexml.Value.fromString("text/calendar"),
                    timezonexml.Value.fromString("text/plain"),
                ),
                timezonexml.AcceptParameter(
                    timezonexml.Name.fromString("tzid"),
                    timezonexml.Required.fromString("true"),
                    timezonexml.Multi.fromString("false"),
                ),
            ),
            
            timezonexml.Operation(
                timezonexml.Action.fromString("expand"),
                timezonexml.Description.fromString("Expand timezones from the server"),
                timezonexml.AcceptParameter(
                    timezonexml.Name.fromString("tzid"),
                    timezonexml.Required.fromString("true"),
                    timezonexml.Multi.fromString("false"),
                ),
                timezonexml.AcceptParameter(
                    timezonexml.Name.fromString("start"),
                    timezonexml.Required.fromString("false"),
                    timezonexml.Multi.fromString("false"),
                ),
                timezonexml.AcceptParameter(
                    timezonexml.Name.fromString("end"),
                    timezonexml.Required.fromString("false"),
                    timezonexml.Multi.fromString("false"),
                ),
            ),
        )
        return XMLResponse(responsecode.OK, result)

    def doList(self, request):
        """
        Return a list of all timezones known to the server.
        """
        
        changedsince = request.args.get("changedsince", ())
        if len(changedsince) > 1:
            raise HTTPError(StatusResponse(
                responsecode.BAD_REQUEST,
                "Invalid changedsince query parameter",
            ))
        if len(changedsince) == 1:
            # Validate a date-time stamp
            changedsince = changedsince[0]
            try:
                dt = PyCalendarDateTime.parseText(changedsince)
            except ValueError:
                raise HTTPError(StatusResponse(
                    responsecode.BAD_REQUEST,
                    "Invalid changedsince query parameter value",
                ))
            if not dt.utc():
                raise HTTPError(StatusResponse(
                    responsecode.BAD_REQUEST,
                    "Invalid changedsince query parameter value",
                ))
                

        timezones = []
        for tz in self.timezones.listTimezones(changedsince):
            timezones.append(
                timezonexml.Summary(
                    timezonexml.Tzid.fromString(tz.tzid),
                    timezonexml.LastModified.fromString(tz.dtstamp),
                    *tuple([timezonexml.Alias.fromString(alias) for alias in tz.aliases])
                )
            )
        result = timezonexml.TimezoneList(
            timezonexml.Dtstamp.fromString(self.timezones.dtstamp),
            *timezones
        )
        return XMLResponse(responsecode.OK, result)

    def doGet(self, request):
        """
        Return the specified timezone data.
        """
        
        tzids = request.args.get("tzid", ())
        if len(tzids) != 1:
            raise HTTPError(StatusResponse(
                responsecode.BAD_REQUEST,
                "Invalid tzid query parameter",
            ))

        format = request.args.get("format", ("text/calendar",))
        if len(format) != 1 or format[0] not in ("text/calendar", "text/plain",):
            raise HTTPError(StatusResponse(
                responsecode.BAD_REQUEST,
                "Invalid format query parameter",
            ))
        format = format[0]

        calendar = self.timezones.getTimezone(tzids[0])
        if calendar is None:
            raise HTTPError(ErrorResponse(
                responsecode.NOT_FOUND,
                (calendarserver_namespace, "invalid-tzid"),
                "Tzid could not be found",
            ))

        tzdata = calendar.getText()

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
            raise HTTPError(StatusResponse(
                responsecode.BAD_REQUEST,
                "Invalid tzid query parameter",
            ))

        try:
            start = request.args.get("start", ())
            if len(start) > 1:
                raise ValueError()
            elif len(start) == 1:
                start = PyCalendarDateTime.parseText(start[0])
            else:
                start = PyCalendarDateTime.getToday()
                start.setDay(1)
                start.setMonth(1)
        except ValueError:
            raise HTTPError(ErrorResponse(
                responsecode.BAD_REQUEST,
                (calendarserver_namespace, "valid-start-date"),
                "Invalid start query parameter",
            ))

        try:
            end = request.args.get("end", ())
            if len(end) > 1:
                raise ValueError()
            elif len(end) == 1:
                end = PyCalendarDateTime.parseText(end[0])
            else:
                end = PyCalendarDateTime.getToday()
                end.setDay(1)
                end.setMonth(1)
                end.offsetYear(10)
            if end <= start:
                raise ValueError()
        except ValueError:
            raise HTTPError(ErrorResponse(
                responsecode.BAD_REQUEST,
                (calendarserver_namespace, "valid-end-date"),
                "Invalid end query parameter",
            ))

        results = []
        
        tzid = tzids[0]
        tzdata = self.timezones.getTimezone(tzid)
        if tzdata is None:
            raise HTTPError(ErrorResponse(
                responsecode.NOT_FOUND,
                (calendarserver_namespace, "invalid-tzid"),
                "Tzid could not be found",
            ))
            
        # Now do the expansion (but use a cache to avoid re-calculating TZs)
        observances = self.expandcache.get((tzid, start, end), None)
        if observances is None:
            observances = tzexpandlocal(tzdata, start, end)
            self.expandcache[(tzid, start, end)] = observances

        # Turn into XML
        results.append(timezonexml.Tzdata(
            timezonexml.Tzid.fromString(tzid),
            *[
                timezonexml.Observance(
                    timezonexml.Name(name),
                    timezonexml.Onset(onset),
                    timezonexml.UTCOffsetFrom(utc_offset_from),
                    timezonexml.UTCOffsetTo(utc_offset_to),
                ) for onset, utc_offset_from, utc_offset_to, name in observances
            ]
        ))
        
        result = timezonexml.Timezones(
            timezonexml.Dtstamp.fromString(self.timezones.dtstamp),
            *results
        )
        return XMLResponse(responsecode.OK, result)

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
        for child in root.getchildren():
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
        
        for tzid, tzinfo in sorted(self.timezones.items(), key=lambda x:x[0]):
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
        calendar = PyCalendar()
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
        for _ignore,v in sorted(self.timezones.items(), key=lambda x:x[0]):
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

        self.dtstamp = PyCalendarDateTime.getNowUTC().getText()
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
                alias_from, alias_to = alias.split()
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
        self.dtstamp = PyCalendarDateTime.getNowUTC().getText()
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
        
        result = (yield self._getTimezoneListFromServer())
        if result is None:
            # Nothing changed since last sync
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
        
        # Now apply changes
        for tzid in itertools.chain(newtzids, changedtzids):
            yield self._getTimezoneFromServer(newtimezones[tzid])
            
        self.dtstamp = newdtstamp
        self._dumpTZs()
        self._buildAliases()
        
        returnValue((len(newtzids), len(changedtzids),))
        
    @inlineCallbacks
    def _discoverServer(self):
        """
        Make sure we know the timezone service path
        """
        
        if self.uri is None:
            if config.TimezoneService.SecondaryService.Host:
                self.uri = "https://%s/.well-known/timezone" % (self.config.TimezoneService.SecondaryService.Host,)
            elif config.TimezoneService.SecondaryService.URI:
                self.uri = config.TimezoneService.SecondaryService.URI
        elif not self.uri.startswith("https:") and not self.uri.startswith("http:"):
            self.uri = "https://%s/.well-known/timezone" % (self.uri,)
            
        testURI = "%s?action=capabilities" % (self.uri,)
        response = (yield getURL(testURI))
        if response is None or response.code / 100 != 2:
            self.discovered = False
            returnValue(False)
        
        # Cache the redirect target
        if hasattr(response, "location"):
            self.uri = response.location 

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
        response = (yield getURL(url))
        if response is None or response.code / 100 != 2:
            returnValue(None)
        
        ct = response.headers.getRawHeaders("content-type", ("bogus/type",))[0]
        ct = ct.split(";", 1)
        ct = ct[0]
        if ct not in ("application/xml", "text/xml",):
            returnValue(None)
        
        etroot, _ignore = readXMLString(response.data, timezonexml.TimezoneList.sname())
        dtstamp = etroot.findtext(timezonexml.Dtstamp.sname())
        timezones = {}
        for summary in etroot.findall(timezonexml.Summary.sname()):
            tzid = summary.findtext(timezonexml.Tzid.sname())
            lastmod = summary.findtext(timezonexml.LastModified.sname())
            aliases = tuple([alias_node.text for alias_node in summary.findall(timezonexml.Alias.sname())])
            timezones[tzid] = TimezoneInfo(tzid, aliases, lastmod, None)
        
        returnValue((dtstamp, timezones,))

    @inlineCallbacks
    def _getTimezoneFromServer(self, tzinfo):
        # List all from the server
        response = (yield getURL("%s?action=get&tzid=%s" % (self.uri, tzinfo.tzid,)))
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
            calendar = PyCalendar.parseText(ical)
        except PyCalendarInvalidData:
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
