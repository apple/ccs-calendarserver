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

"""
Implements a calendar user proxy principal.
"""

__all__ = [
    "CalendarUserProxyPrincipalResource",
]

from urllib import unquote

from twisted.internet.defer import succeed
from twisted.python import log
from twisted.python.failure import Failure
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.element.base import dav_namespace
from twisted.web2.dav.util import joinURL
from twisted.web2.http import Response
from twisted.web2.http_headers import MimeType

from twistedcaldav.extensions import DAVFile
from twistedcaldav.extensions import ReadOnlyWritePropertiesResourceMixIn
from twistedcaldav.resource import CalendarPrincipalResource
from twistedcaldav.sql import AbstractSQLDatabase
from twistedcaldav.static import AutoProvisioningFileMixIn

import os

class PermissionsMixIn (ReadOnlyWritePropertiesResourceMixIn):
    def defaultAccessControlList(self):
        aces = (
            # DAV:read access for authenticated users.
            davxml.ACE(
                davxml.Principal(davxml.Authenticated()),
                davxml.Grant(davxml.Privilege(davxml.Read())),
            ),
            # Inheritable DAV:all access for the resource's associated principal.
            davxml.ACE(
                davxml.Principal(davxml.HRef(self.parent.principalURL())),
                davxml.Grant(davxml.Privilege(davxml.WriteProperties())),
                davxml.Protected(),
            ),
        )
        
        return davxml.ACL(*aces)

    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        # Permissions here are fixed, and are not subject to inherritance rules, etc.
        return succeed(self.defaultAccessControlList())

class CalendarUserProxyPrincipalResource (AutoProvisioningFileMixIn, PermissionsMixIn, CalendarPrincipalResource, DAVFile):
    """
    Calendar user proxy principal resource.
    """
    def __init__(self, path, parent, proxyType):
        """
        @param path: the path to the file which will back this resource.
        @param parent: the parent of this resource.
        @param proxyType: a C{str} containing the name of the resource.
        """
        super(CalendarUserProxyPrincipalResource, self).__init__(path, joinURL(parent.principalURL(), proxyType))

        self.parent = parent
        self.proxyType = proxyType
        self._url = joinURL(parent.principalURL(), proxyType)
        if self.isCollection():
            self._url += "/"

        # Provision in __init__() because principals are used prior to request
        # lookups.
        self.provision()

    def _index(self):
        """
        Return the SQL database for this group principal.
        
        @return: the L{CalendarUserProxyDatabase} for the principal collection.
        """
        
        # Get the principal collection we are contained in
        pcollection = self.parent.parent.parent
        
        # The db is located in the principal collection root
        if not hasattr(pcollection, "calendar_user_proxy_db"):
            setattr(pcollection, "calendar_user_proxy_db", CalendarUserProxyDatabase(pcollection.fp.path))
        return pcollection.calendar_user_proxy_db

    def resourceType(self):
        if self.proxyType == "calendar-proxy-read":
            return davxml.ResourceType.calendarproxyread
        elif self.proxyType == "calendar-proxy-write":
            return davxml.ResourceType.calendarproxywrite
        else:
            return super(CalendarUserProxyPrincipalResource, self).resourceType()

    def writeProperty(self, property, request):
        assert isinstance(property, davxml.WebDAVElement)

        if property.qname() == (dav_namespace, "group-member-set"):
            return self.setGroupMemberSet(property, request)

        return super(CalendarUserProxyPrincipalResource, self).writeProperty(property, request)

    def setGroupMemberSet(self, new_members, request):
        
        # Break out the list into a set of URIs.
        members = [str(h) for h in new_members.children]
        self._index().setGroupMembers(self._url, members)
        return succeed(True)

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
        return self.proxyType

    ##
    # ACL
    ##

    def alternateURIs(self):
        # FIXME: Add API to IDirectoryRecord for getting a record URI?
        return ()

    def principalURL(self):
        return self._url

    def principalCollections(self):
        return self.parent.principalCollections()

    def groupMembers(self):
        return self._index().getMembers(self._url)

    def groupMemberships(self):
        return self._index().getMemberships(self._url)


class CalendarUserProxyDatabase(AbstractSQLDatabase):
    """
    A database to maintain calendar user proxy group memberships.

    SCHEMA:
    
    Group Database:
    
    ROW: GROUPNAME, MEMBER
    
    """
    
    dbType = "CALENDARUSERPROXY"
    dbFilename = ".db.calendaruserproxy"
    dbFormatVersion = "1"

    def __init__(self, path):
        path = os.path.join(path, CalendarUserProxyDatabase.dbFilename)
        super(CalendarUserProxyDatabase, self).__init__(path, CalendarUserProxyDatabase.dbFormatVersion)

    def setGroupMembers(self, principalURI, members):
        """
        Add a group membership record.
    
        @param principalURI: the principalURI of the group principal to add.
        @param members: the list of principalURIs that are members of this group.
        """
        
        # Remove what is there, then add it back.
        self._delete_from_db(principalURI)
        self._add_to_db(principalURI, members)
        self._db_commit()

    def removeGroup(self, principalURI):
        """
        Remove a group membership record.
    
        @param principalURI: the principalURI of the group principal to add.
        """
        self._delete_from_db(principalURI)
        self._db_commit()
    
    def getMembers(self, principalURI):
        """
        Return the list of group members for the specified principal.
        """
        members = set()
        for row in self._db_execute("select MEMBER from GROUPS where GROUPNAME = :1", principalURI):
            members.add(row[0])
        return members
    
    def getMemberships(self, principalURI):
        """
        Return the list of groups the specified principal is a member of.
        """
        members = set()
        for row in self._db_execute("select GROUPNAME from GROUPS where MEMBER = :1", principalURI):
            members.add(row[0])
        return members

    def _add_to_db(self, principalURI, members):
        """
        Insert the specified entry into the database.

        @param principalURI: the principalURI of the group principal to remove.
        @param members: the list of principalURIs that are members of this group.
        """
        for member in members:
            self._db_execute(
                """
                insert into GROUPS (GROUPNAME, MEMBER)
                values (:1, :2)
                """, principalURI, member
            )
       
    def _delete_from_db(self, principalURI):
        """
        Deletes the specified entry from the database.

        @param principalURI: the principalURI of the group principal to remove.
        """
        self._db_execute("delete from GROUPS where GROUPNAME = :1", principalURI)
    
    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return CalendarUserProxyDatabase.dbType
        
    def _db_init_data_tables(self, q):
        """
        Initialise the underlying database tables.
        @param q:           a database cursor to use.
        """

        #
        # GROUPS table
        #
        q.execute(
            """
            create table GROUPS (
                GROUPNAME   text,
                MEMBER      text
            )
            """
        )

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
