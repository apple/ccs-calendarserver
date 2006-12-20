##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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
from twisted.internet.defer import succeed
from twistedcaldav.extensions import ReadOnlyResourceMixIn
from twisted.web2.http import Response

"""
Implements a calendar user proxy principal.
"""

__all__ = [
    "CalendarUserProxyPrincipalResource",
]

from urllib import unquote

from twisted.python import log
from twisted.python.failure import Failure
from twisted.web2 import responsecode
from twisted.web2.http_headers import MimeType
from twisted.web2.dav import davxml
from twisted.web2.dav.util import joinURL

from twistedcaldav.extensions import DAVFile
from twistedcaldav.resource import CalendarPrincipalResource
from twistedcaldav.static import AutoProvisioningFileMixIn

class PermissionsMixIn (ReadOnlyResourceMixIn):
    def defaultAccessControlList(self):
        return authReadACL

    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        # Permissions here are fixed, and are not subject to inherritance rules, etc.
        return succeed(self.defaultAccessControlList())

class CalendarUserProxyPrincipalResource (AutoProvisioningFileMixIn, PermissionsMixIn, CalendarPrincipalResource, DAVFile):
    """
    Calendar user proxy principal resource.
    """
    def __init__(self, path, parent, type):
        """
        @param path: them path to the file which will back this resource.
        @param parent: the parent of this resource.
        @param type: the L{IDirectoryRecord} that this resource represents.
        """
        super(CalendarUserProxyPrincipalResource, self).__init__(path, joinURL(parent.principalURL(), type))

        self.parent = parent
        self.type = type
        self._url = joinURL(parent.principalURL(), type)
        if self.isCollection():
            self._url += "/"

        # Provision in __init__() because principals are used prior to request
        # lookups.
        self.provision()

    def resourceType(self):
        if self.type == "calendar-proxy-read":
            return davxml.ResourceType.calendarproxyread
        elif self.type == "calendar-proxy-write":
            return davxml.ResourceType.calendarproxywrite
        else:
            return super(CalendarUserProxyPrincipalResource, self).resourceType()

    ##
    # HTTP
    ##

    def render(self, request):
        def format_list(method, *args):
            def genlist():
                try:
                    item = None
                    for item in method(*args):
                        yield " -> %s\n" % (item,)
                    if item is None:
                        yield " '()\n"
                except Exception, e:
                    log.err("Exception while rendering: %s" % (e,))
                    Failure().printTraceback()
                    yield "  ** %s **: %s\n" % (e.__class__.__name__, e)
            return "".join(genlist())

        output = [
            """<html>"""
            """<head>"""
            """<title>%(title)s</title>"""
            """<style>%(style)s</style>"""
            """</head>"""
            """<body>"""
            """<div class="directory-listing">"""
            """<h1>Proxy Principal Details</h1>"""
            """<pre><blockquote>"""
            % {
                "title": unquote(request.uri),
                "style": self.directoryStyleSheet(),
            }
        ]

        output.append("".join((
            "Directory Information\n"
            "---------------------\n"
            "Parent Directory GUID: %s\n"  % (self.parent.record.service.guid,),
            "Realm: %s\n"                  % (self.parent.record.service.realmName,),
            "\n"
            "Parent Principal Information\n"
            "---------------------\n"
            "GUID: %s\n"                   % (self.parent.record.guid,),
            "Record type: %s\n"            % (self.parent.record.recordType,),
            "Short name: %s\n"             % (self.parent.record.shortName,),
            "Full name: %s\n"              % (self.parent.record.fullName,),
            "\n"
            "Proxy Principal Information\n"
            "---------------------\n"
            "Principal URL: %s\n"          % (self.principalURL(),),
            "\nAlternate URIs:\n"          , format_list(self.alternateURIs),
            "\nGroup members:\n"           , format_list(self.groupMembers),
        )))

        output.append(
            """</pre></blockquote></div>"""
        )

        output.append(self.getDirectoryTable("Collection Listing"))

        output.append("</body></html>")

        output = "".join(output)
        if type(output) == unicode:
            output = output.encode("utf-8")
            mime_params = {"charset": "utf-8"}
        else:
            mime_params = {}

        response = Response(code=responsecode.OK, stream=output)
        response.headers.setHeader("content-type", MimeType("text", "html", mime_params))

        return response

    ##
    # DAV
    ##

    def displayName(self):
        return self.type

    ##
    # ACL
    ##

    def alternateURIs(self):
        # FIXME: Add API to IDirectoryRecord for getting a record URI?
        return ()

    def principalURL(self):
        return self._url

    def groupMembers(self):
        return ()

    def groupMemberships(self):
        return ()

    def principalCollections(self):
        return self.parent.principalCollections()

##
# Utilities
##

authReadACL = davxml.ACL(
    # Read access for authenticated users.
    davxml.ACE(
        davxml.Principal(davxml.Authenticated()),
        davxml.Grant(davxml.Privilege(davxml.Read())),
        davxml.Protected(),
    ),
)
