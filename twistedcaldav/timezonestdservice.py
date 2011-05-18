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

from twisted.internet.defer import succeed

from twistedcaldav import timezonexml, xmlutil
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.extensions import DAVResource,\
    DAVResourceWithoutChildrenMixin
from twistedcaldav.ical import tzexpandlocal
from twistedcaldav.resource import ReadOnlyNoCopyResourceMixIn
from twistedcaldav.timezones import TimezoneException, TimezoneCache, readVTZ
from twistedcaldav.xmlutil import addSubElement

from pycalendar.calendar import PyCalendar
from pycalendar.datetime import PyCalendarDateTime

import getopt
import hashlib
import os
import sys

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

        tzpath = TimezoneCache.getDBPath()
        xmlfile = os.path.join(tzpath, "timezones.xml")
        self.timezones = PrimaryTimezoneDatabase(tzpath, xmlfile)
        if not os.path.exists(xmlfile):
            self.timezones.createNewDatabase()
        else:
            self.timezones.readDatabase()

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
        return None

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
                    timezonexml.Name.fromString("changesince"),
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
                    timezonexml.Multi.fromString("true"),
                ),
            ),
            
            timezonexml.Operation(
                timezonexml.Action.fromString("expand"),
                timezonexml.Description.fromString("Expand timezones from the server"),
                timezonexml.AcceptParameter(
                    timezonexml.Name.fromString("tzid"),
                    timezonexml.Required.fromString("true"),
                    timezonexml.Multi.fromString("true"),
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
        
        changesince = request.args.get("changesince", ())
        if len(changesince) > 1:
            raise HTTPError(StatusResponse(
                responsecode.BAD_REQUEST,
                "Invalid changesince query parameter",
            ))
        if len(changesince) == 1:
            # Validate a date-time stamp
            changesince = changesince[0]
            try:
                dt = PyCalendarDateTime.parseText(changesince)
            except ValueError:
                raise HTTPError(StatusResponse(
                    responsecode.BAD_REQUEST,
                    "Invalid changesince query parameter value",
                ))
            if not dt.utc():
                raise HTTPError(StatusResponse(
                    responsecode.BAD_REQUEST,
                    "Invalid changesince query parameter value",
                ))
                

        timezones = []
        for _ignore, tz in sorted(self.timezones.timezones.items(), key=lambda x:x[0]):
            if changesince and tz.dtstamp <= changesince:
                continue
            timezones.append(
                timezonexml.Summary(
                    timezonexml.Tzid.fromString(tz.tzid),
                    timezonexml.LastModified.fromString(tz.dtstamp),
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
        if len(tzids) == 0:
            raise HTTPError(StatusResponse(
                responsecode.BAD_REQUEST,
                "Invalid tzid query parameter",
            ))
        if "*" in tzids:
            if len(tzids) != 1:
                raise HTTPError(StatusResponse(
                    responsecode.BAD_REQUEST,
                    "Invalid tzid query parameter",
                ))
            tzids = self.timezones.timezones.keys()

        format = request.args.get("format", ("text/calendar",))
        if len(format) != 1 or format[0] not in ("text/calendar", "text/plain",):
            raise HTTPError(StatusResponse(
                responsecode.BAD_REQUEST,
                "Invalid format query parameter",
            ))
        format = format[0]

        calendar = self.timezones.getTimezones(tzids)
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
        if len(tzids) == 0:
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
        
        for tzid in tzids:
            
            tzdata = self.timezones.getTimezones((tzid,))
            if tzdata is None:
                continue

            # Now do the expansion (but use a expandcache to avoid re-calculating TZs)
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
    
    def __init__(self, tzid, dtstamp, md5):
        self.tzid = tzid
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
        md5 = node.findtext("md5")
        return cls(tzid, dtstamp, md5)
    
    def generateXML(self, parent):
        """
        Generate the XML element for this timezone info.
        """
        node = xmlutil.addSubElement(parent, "timezone")
        xmlutil.addSubElement(node, "tzid", self.tzid)
        xmlutil.addSubElement(node, "dtstamp", self.dtstamp)
        xmlutil.addSubElement(node, "md5", self.md5)

class PrimaryTimezoneDatabase(object):
    """
    Maintains the database of timezones read from an XML file.
    """
    
    def __init__(self, basepath, xmlfile):
        self.basepath = basepath
        self.xmlfile = xmlfile
        self.dtstamp = None
        self.timezones = {}

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
                self.timezones[tzid] = TimezoneInfo(tzid, self.dtstamp, md5)
    
    def _dumpTZs(self):
        
        _ignore, root = xmlutil.newElementTreeWithRoot("timezones")
        addSubElement(root, "dtstamp", self.dtstamp)
        for _ignore,v in sorted(self.timezones.items(), key=lambda x:x[0]):
            v.generateXML(root)
        xmlutil.writeXML(self.xmlfile, root)
        
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

    def getTimezones(self, tzids):
        """
        Generate a PyCalendar containing the requested timezones.
        """
        calendar = PyCalendar()
        for tzid in sorted(tzids):
            # We will just use our existing TimezoneCache here
            try:
                vtz = readVTZ(tzid)
                calendar.addComponent(vtz.getComponents()[0].duplicate())
            except TimezoneException:
                pass

        return calendar

def usage(error_msg=None):
    if error_msg:
        print error_msg
        print

    print """Usage: timezonestdservice [options]
Options:
    -h            Print this help and exit
    -v            Be verbose
    -f            XML file path
    -z            zoneinfo file path
    --create      create new XML file
    --update      update XML file
    --list        list timezones in XML file
    --changed     changed since timestamp

Description:
    This utility will create, update or list an XML timezone database
    summary file.

"""

    if error_msg:
        raise ValueError(error_msg)
    else:
        sys.exit(0)

if __name__ == '__main__':
    
    action = None
    tzpath = None
    xmlfile = None
    changed = None
    
    # Get options
    options, args = getopt.getopt(
        sys.argv[1:],
        "hvf:z:",
        [
            "create",
            "update",
            "list",
            "changed="
        ]
    )

    for option, value in options:
        if option == "-h":
            usage()
        elif option == "-v":
            verbose = True
        elif option == "-f":
            xmlfile = value
        elif option == "-z":
            tzpath = value
        elif option == "--create":
            action = "create"
        elif option == "--update":
            action = "update"
        elif option == "--list":
            action = "list"
        elif option == "--changed":
            action = "changed"
            changed = value
        else:
            usage("Unrecognized option: %s" % (option,))
    
    if action is None:
        action = "list"
    if tzpath is None:
        try:
            import pkg_resources
        except ImportError:
            tzpath = os.path.join(os.path.dirname(__file__), "zoneinfo")
        else:
            tzpath = pkg_resources.resource_filename("twistedcaldav", "zoneinfo") #@UndefinedVariable
    xmlfile = os.path.expanduser("~/tz.xml")
    
    if not os.path.isdir(tzpath):
        usage("Invalid zoneinfo path: %s" % (tzpath,))
    if not os.path.isfile(xmlfile) and action != "create":
        usage("Invalid XML file path: %s" % (xmlfile,))

    tzdb = PrimaryTimezoneDatabase(tzpath, xmlfile)
    if action == "create":
        print "Creating new XML file at: %s" % (xmlfile,)
        tzdb.createNewDatabase()
        print "Current total: %d" % (len(tzdb.timezones),)
    elif action == "update":
        print "Updating XML file at: %s" % (xmlfile,)
        tzdb.readDatabase()
        tzdb.updateDatabase()
        print "Current total: %d" % (len(tzdb.timezones),)
        print "Total Changed: %d" % (tzdb.changeCount,)
        if tzdb.changeCount:
            print "Changed:"
            for k in sorted(tzdb.changed):
                print "  %s" % (k,)
    elif action == "list":
        print "Listing XML file at: %s" % (xmlfile,)
        tzdb.readDatabase()
        print "Current timestamp: %s" % (tzdb.dtstamp,)
        print "Timezones:"
        for k in sorted(tzdb.timezones.keys()):
            print "  %s" % (k,)
    elif action == "changed":
        print "Changes from XML file at: %s" % (xmlfile,)
        tzdb.readDatabase()
        print "Check timestamp: %s" % (changed,)
        print "Current timestamp: %s" % (tzdb.dtstamp,)
        results = [k for k, v in tzdb.timezones.items() if v.dtstamp > changed]
        print "Total Changed: %d" % (len(results),)
        if results:
            print "Changed:"
            for k in sorted(results):
                print "  %s" % (k,)
    else:
        usage("Invalid action: %s" % (action,))

    