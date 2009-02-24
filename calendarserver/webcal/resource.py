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

"""
Calendar Server Web UI.
"""

__all__ = [
    "WebCalendarResource",
]

from urlparse import urlparse
from cgi import parse_qs

from twisted.web2 import responsecode
from twisted.web2.http import Response
from twisted.web2.http_headers import MimeType
from twisted.web2.stream import MemoryStream
from twisted.web2.dav import davxml
from twisted.web2.dav.static import DAVFile

from twistedcaldav.extensions import ReadOnlyResourceMixIn

class WebCalendarResource (ReadOnlyResourceMixIn, DAVFile):
    def defaultAccessControlList(self):
        return davxml.ACL(
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(
                    davxml.Privilege(davxml.Read()),
                ),
                davxml.Protected(),
            ),
        )

    def etag(self):
        # Can't be calculated here
        return None

    def contentLength(self):
        # Can't be calculated here
        return None

    def lastModified(self):
        return None

    def exists(self):
        return True

    def displayName(self):
        return "Web Calendar"

    def contentType(self):
        return MimeType.fromString("text/html; charset=utf-8");

    def contentEncoding(self):
        return None

    def createSimilarFile(self, path):
        return DAVFile(path)

    def render(self, request):
        if not self.fp.isdir():
            return responsecode.NOT_FOUND

        #
        # Get URL of authenticated principal.
        # Don't need to authenticate here because the ACL will have already required it.
        #
        authenticatedPrincipalURL = str(request.authnUser.childOfType(davxml.HRef))

        def queryValue(arg):
            query = parse_qs(urlparse(request.uri).query, True)
            return query.get(arg, [""])[0]
            
        #
        # Parse debug query arg
        #
        debug = queryValue("debug")
        if debug is not None and debug.lower() in ("1", "true", "yes"):
            debug = "true"
        else:
            debug = "false"

        #
        # Parse TimeZone query arg
        #
        tzid = queryValue("tzid")
        if not tzid:
            tzid = "America/Los_Angeles"

        #
        # Make some HTML
        #
        data = """
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">

<html lang="en">
 <head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <meta name="caldav_principal_path" content="%(principalURL)s">
  <meta name="tzid" content="%(tzid)s">
  <title>Calendar</title>
  <link rel="stylesheet" href="/webcal/calendar/css/calendar_standalone.css" type="text/css" media="screen" charset="utf-8">
  <link rel="stylesheet" href="/webcal/css/required/niftydate.css" type="text/css" media="screen" charset="utf-8">
  <link rel="stylesheet" href="/webcal/css/required/calendar.css" type="text/css" media="screen" charset="utf-8">
  <link rel="stylesheet" href="/webcal/css/required/dialog.css" type="text/css" media="screen" charset="utf-8">
  <link rel="stylesheet" href="/webcal/css/required/forms.css" type="text/css" media="screen" charset="utf-8">
  <link rel="stylesheet" href="/webcal/css/required/search.css" type="text/css" media="screen" charset="utf-8">
  <link rel="stylesheet" href="/webcal/css/required/widgets.css" type="text/css" media="screen" charset="utf-8">
  <link rel="stylesheet" href="/webcal/css/required/tags.css" type="text/css" media="screen" charset="utf-8">
  <link rel="stylesheet" href="/webcal/css/required/tooltip.css" type="text/css" media="screen" charset="utf-8">
  <link rel="stylesheet" href="/webcal/css/required/paginator.css" type="text/css" media="screen" charset="utf-8">
  <script src="/webcal/calendar/temp_exported_locStrings.js" type="text/javascript" charset="utf-8"></script>
  <script src="/webcal/javascript/prototype.js" type="text/javascript" charset="utf-8"></script>
  <script src="/webcal/javascript/md5.js" type="text/javascript" charset="utf-8"></script>
  <script src="/webcal/javascript/effects.js" type="text/javascript" charset="utf-8"></script>
  <script src="/webcal/javascript/builder.js" type="text/javascript" charset="utf-8"></script>
  <script src="/webcal/javascript/locUtils.js" type="text/javascript" charset="utf-8"></script>
  <script src="/webcal/javascript/formatDate.js" type="text/javascript" charset="utf-8"></script>
  <script src="/webcal/javascript/widgets_core.js" type="text/javascript" charset="utf-8"></script>
  <script src="/webcal/javascript/widgets.js" type="text/javascript" charset="utf-8"></script>
  <script src="/webcal/javascript/caldav.js" type="text/javascript" charset="utf-8"></script>
  <script src="/webcal/javascript/calaccess.js" type="text/javascript" charset="utf-8"></script>
  <script type="text/javascript" charset="utf-8">gDebug = %(debug)s;</script>
 </head>
 <body>
  <div id="module_calendars"></div>
  <script type="text/javascript" charset="utf-8">
   setTimeout(function() { if (window.prepare) prepare() }, 10);
  </script>
 </body>
</html>
""" % {
    "tzid": tzid,
    "principalURL": authenticatedPrincipalURL,
    "debug": debug,
}

        response = Response()
        response.stream = MemoryStream(data, start=1)

        for (header, value) in (
            ("content-type", self.contentType()),
            ("content-encoding", self.contentEncoding()),
        ):
            if value is not None:
                response.headers.setHeader(header, value)

        return response
