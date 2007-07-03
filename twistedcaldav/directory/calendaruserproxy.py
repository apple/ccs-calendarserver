##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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

from twisted.internet.defer import succeed
from twisted.python import log
from twisted.python.failure import Failure
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.element.base import dav_namespace
from twisted.web2.dav.util import joinURL
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav.config import config
from twistedcaldav.extensions import DAVFile, DAVPrincipalResource
from twistedcaldav.extensions import ReadOnlyWritePropertiesResourceMixIn
from twistedcaldav.sql import AbstractSQLDatabase
from twistedcaldav.static import AutoProvisioningFileMixIn
from twistedcaldav.directory.util import uuidFromName

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
        
        # Add admins
        aces += tuple([davxml.ACE(
                    davxml.Principal(davxml.HRef(principal)),
                    davxml.Grant(davxml.Privilege(davxml.All())),
                    davxml.Protected(),
                 ) for principal in config.AdminPrincipals
                ])

        return davxml.ACL(*aces)

    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        # Permissions here are fixed, and are not subject to inherritance rules, etc.
        return succeed(self.defaultAccessControlList())

class CalendarUserProxyPrincipalResource (AutoProvisioningFileMixIn, PermissionsMixIn, DAVPrincipalResource, DAVFile):
    """
    Calendar user proxy principal resource.
    """

    guidMapper = {}    # dict to map a GUID to a proxy principal

    def davComplianceClasses(self):
        return tuple(super(CalendarUserProxyPrincipalResource, self).davComplianceClasses()) + (
            "calendar-access",
            "calendar-schedule",
            "calendar-availability",
        )

    def __init__(self, path, parent, proxyType):
        """
        @param path: the path to the file which will back this resource.
        @param parent: the parent of this resource.
        @param proxyType: a C{str} containing the name of the resource.
        """
        super(CalendarUserProxyPrincipalResource, self).__init__(path, joinURL(parent.principalURL(), proxyType))

        self.parent = parent
        self.pcollection = self.parent.parent.parent
        self.proxyType = proxyType
        self._url = joinURL(parent.principalURL(), proxyType)
        if self.isCollection():
            self._url += "/"
        self.guid = uuidFromName(self.parent.principalUID(), proxyType)
        self.guidMapper[self.guid] = self

        # Provision in __init__() because principals are used prior to request
        # lookups.
        self.provision()

    def _index(self):
        """
        Return the SQL database for this group principal.
        
        @return: the L{CalendarUserProxyDatabase} for the principal collection.
        """
        
        # The db is located in the principal collection root
        if not hasattr(self.pcollection, "calendar_user_proxy_db"):
            setattr(self.pcollection, "calendar_user_proxy_db", CalendarUserProxyDatabase(self.pcollection.fp.path))
        return self.pcollection.calendar_user_proxy_db

    @classmethod
    def principalForGUID(cls, guid):
        return cls.guidMapper.get(guid)

    def resourceType(self):
        if self.proxyType == "calendar-proxy-read":
            return davxml.ResourceType.calendarproxyread
        elif self.proxyType == "calendar-proxy-write":
            return davxml.ResourceType.calendarproxywrite
        else:
            return super(CalendarUserProxyPrincipalResource, self).resourceType()

    def isCollection(self):
        return True

    def writeProperty(self, property, request):
        assert isinstance(property, davxml.WebDAVElement)

        if property.qname() == (dav_namespace, "group-member-set"):
            if self.hasEditableMembership():
                return self.setGroupMemberSet(property, request)
            else:
                raise HTTPError(
                    StatusResponse(
                        responsecode.FORBIDDEN,
                        "Proxies cannot be changed."
                    )
                )

        return super(CalendarUserProxyPrincipalResource, self).writeProperty(property, request)

    def setGroupMemberSet(self, new_members, request):
        # FIXME: as defined right now it is not possible to specify a calendar-user-proxy group as
        # a member of any other group since the directory service does not know how to lookup
        # these special resource GUIDs.
        #
        # Really, c-u-p principals should be treated the same way as any other principal, so
        # they should be allowed as members of groups.
        #
        # This implementation now raises an exception for any principal it cannot find.

        # Break out the list into a set of URIs.
        members = [str(h) for h in new_members.children]
        
        # Map the URIs to principals.
        principals = []
        for uri in members:
            principal = self.pcollection._principalForURI(uri)
            # Invalid principals MUST result in an error.
            if principal is None:
                raise HTTPError(StatusResponse(
                    responsecode.BAD_REQUEST,
                    "Attempt to use a non-existent principal %s as a group member of %s." % (uri, self.principalURL(),)
                ))
            principals.append(principal)
        
        # Map the principals to GUIDs.
        guids = [p.principalUID() for p in principals]

        self._index().setGroupMembers(self.guid, guids)
        return succeed(True)

    ##
    # HTTP
    ##

    def renderDirectoryBody(self, request):
        def format_list(items, *args):
            def genlist():
                try:
                    item = None
                    for item in items:
                        yield " -> %s\n" % (item,)
                    if item is None:
                        yield " '()\n"
                except Exception, e:
                    log.err("Exception while rendering: %s" % (e,))
                    Failure().printTraceback()
                    yield "  ** %s **: %s\n" % (e.__class__.__name__, e)
            return "".join(genlist())

        def link(url):
            return """<a href="%s">%s</a>""" % (url, url)

        def gotSuper(output):
            return "".join((
                """<div class="directory-listing">"""
                """<h1>Principal Details</h1>"""
                """<pre><blockquote>"""
                """Directory Information\n"""
                """---------------------\n"""
                """Directory GUID: %s\n"""         % (self.parent.record.service.guid,),
                """Realm: %s\n"""                  % (self.parent.record.service.realmName,),
                """\n"""
                """Parent Principal Information\n"""
                """---------------------\n"""
                """GUID: %s\n"""                   % (self.parent.record.guid,),
                """Record type: %s\n"""            % (self.parent.record.recordType,),
                """Short name: %s\n"""             % (self.parent.record.shortName,),
                """Full name: %s\n"""              % (self.parent.record.fullName,),
                """Principal UID: %s\n"""          % (self.parent.principalUID(),),
                """Principal URL: %s\n"""          % (link(self.parent.principalURL()),),
                """\n"""
                """Proxy Principal Information\n"""
                """---------------------\n"""
                """GUID: %s\n"""                   % (self.guid,),
                """Principal UID: %s\n"""          % (self.principalUID(),),
                """Principal URL: %s\n"""          % (link(self.principalURL()),),
                """\nAlternate URIs:\n"""          , format_list(self.alternateURIs()),
                """\nGroup members (%s):\n"""      % ({False:"Locked", True:"Editable"}[self.hasEditableMembership()]), format_list(link(p.principalURL()) for p in self.groupMembers()),
                """\nGroup memberships:\n"""       , format_list(link(p.principalURL()) for p in self.groupMemberships()),
                """</pre></blockquote></div>""",
                output
            ))

        d = super(CalendarUserProxyPrincipalResource, self).renderDirectoryBody(request)
        d.addCallback(gotSuper)
        return d

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

    def principalUID(self):
        return self.guid

    def principalCollections(self):
        return self.parent.principalCollections()

    def groupMembers(self):
        if self.hasEditableMembership():
            # Get member GUIDs from database and map to principal resources
            members = self._index().getMembers(self.guid)
            return [self.pcollection.principalForGUID(guid) for guid in members]
        else:
            # Fixed proxies are only for read-write - the read-only list is empty
            if self.proxyType == "calendar-proxy-write":
                return self.parent.proxies()
            else:
                return ()

    def groupMemberships(self):
        # Get membership GUIDs and map to principal resources
        memberships = self._index().getMemberships(self.guid)
        return [self.pcollection.principalForGUID(guid) for guid in memberships]

    def hasEditableMembership(self):
        return self.parent.hasEditableProxyMembership()
        
class CalendarUserProxyDatabase(AbstractSQLDatabase):
    """
    A database to maintain calendar user proxy group memberships.

    SCHEMA:
    
    Group Database:
    
    ROW: GROUPNAME, MEMBER
    
    """
    
    dbType = "CALENDARUSERPROXY"
    dbFilename = ".db.calendaruserproxy"
    dbFormatVersion = "3"

    def __init__(self, path):
        path = os.path.join(path, CalendarUserProxyDatabase.dbFilename)
        super(CalendarUserProxyDatabase, self).__init__(path)

    def setGroupMembers(self, principalGUID, members):
        """
        Add a group membership record.
    
        @param principalGUID: the principalGUID of the group principal to add.
        @param members: the list of principalGUIDs that are members of this group.
        """
        
        # Remove what is there, then add it back.
        self._delete_from_db(principalGUID)
        self._add_to_db(principalGUID, members)
        self._db_commit()

    def removeGroup(self, principalGUID):
        """
        Remove a group membership record.
    
        @param principalGUID: the principalGUID of the group principal to remove.
        """
        self._delete_from_db(principalGUID)
        self._db_commit()
    
    def getMembers(self, principalGUID):
        """
        Return the list of group member GUIDs for the specified principal.
        """
        members = set()
        for row in self._db_execute("select MEMBER from GROUPS where GROUPNAME = :1", principalGUID):
            members.add(row[0])
        return members
    
    def getMemberships(self, principalGUID):
        """
        Return the list of group principal GUIDs the specified principal is a member of.
        """
        members = set()
        for row in self._db_execute("select GROUPNAME from GROUPS where MEMBER = :1", principalGUID):
            members.add(row[0])
        return members

    def _add_to_db(self, principalGUID, members):
        """
        Insert the specified entry into the database.

        @param principalGUID: the principalGUID of the group principal to add.
        @param members: the list of principalGUIDs that are members of this group.
        """
        for member in members:
            self._db_execute(
                """
                insert into GROUPS (GROUPNAME, MEMBER)
                values (:1, :2)
                """, principalGUID, member
            )
       
    def _delete_from_db(self, principalGUID):
        """
        Deletes the specified entry from the database.

        @param principalGUID: the principalGUID of the group principal to remove.
        """
        self._db_execute("delete from GROUPS where GROUPNAME = :1", principalGUID)
    
    def _db_version(self):
        """
        @return: the schema version assigned to this index.
        """
        return CalendarUserProxyDatabase.dbFormatVersion
        
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
