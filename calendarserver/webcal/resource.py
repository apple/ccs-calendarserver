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

from twisted.web2 import responsecode
from twisted.web2.http import Response
from twisted.web2.http_headers import MimeType
from twisted.web2.static import File as FileResource
from twisted.web2.stream import MemoryStream

class WebCalendarResource (FileResource):
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
        return FileResource(path)

    def render(self, request):
        if not self.fp.isdir():
            return responsecode.NOT_FOUND

        data = """
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">

<html lang="en">
 <head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <meta name="caldav_principal_path" content="$(timeZone)s">
  <meta name="tzid" content="%(principalURL)s">
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
  <script src="temp_exported_locStrings.js" type="text/javascript" charset="utf-8"></script>
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
    "timeZone": "America/Los_Angeles",
    "principalURL": "/principals/users/admin/",
    "debug": "true",
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
