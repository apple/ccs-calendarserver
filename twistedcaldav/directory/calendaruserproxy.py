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
##

"""
Implements a calendar user proxy principal.
"""

__all__ = [
    "CalendarUserProxyPrincipalResource",
]

from twisted.internet.defer import returnValue
from twisted.internet.defer import succeed, inlineCallbacks
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.element.base import dav_namespace
from twisted.web2.dav.util import joinURL
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav.config import config
from twistedcaldav.extensions import DAVFile, DAVPrincipalResource
from twistedcaldav.extensions import ReadOnlyWritePropertiesResourceMixIn
from twistedcaldav.memcacher import Memcacher
from twistedcaldav.resource import CalDAVComplianceMixIn
from twistedcaldav.sql import AbstractSQLDatabase
from twistedcaldav.sql import db_prefix
from twistedcaldav.static import AutoProvisioningFileMixIn

import itertools
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

class CalendarUserProxyPrincipalResource (CalDAVComplianceMixIn, AutoProvisioningFileMixIn, PermissionsMixIn, DAVPrincipalResource, DAVFile):
    """
    Calendar user proxy principal resource.
    """

    def __init__(self, path, parent, proxyType):
        """
        @param path: the path to the file which will back this resource.
        @param parent: the parent of this resource.
        @param proxyType: a C{str} containing the name of the resource.
        """
        if self.isCollection():
            slash = "/"
        else:
            slash = ""

        url = joinURL(parent.principalURL(), proxyType) + slash

        super(CalendarUserProxyPrincipalResource, self).__init__(path, url)

        self.parent      = parent
        self.proxyType   = proxyType
        self.pcollection = self.parent.parent.parent # FIXME: if this is supposed to be public, it needs a better name
        self._url        = url

        # Not terribly useful at present because we don't have a way
        # to map a GUID back to the correct principal.
        #self.guid = uuidFromName(self.parent.principalUID(), proxyType)

        # Principal UID is parent's GUID plus the proxy type; this we
        # can easily map back to a principal.
        self.uid = "%s#%s" % (self.parent.principalUID(), proxyType)

        self._alternate_urls = tuple(
            joinURL(url, proxyType) + slash
            for url in parent.alternateURIs()
            if url.startswith("/")
        )

        # Provision in __init__() because principals are used prior to request
        # lookups.
        self.provision()

    def __str__(self):
        return "%s [%s]" % (self.parent, self.proxyType)

    def _index(self):
        """
        Return the SQL database for this group principal.

        @return: the L{CalendarUserProxyDatabase} for the principal collection.
        """

        # The db is located in the principal collection root
        if not hasattr(self.pcollection, "calendar_user_proxy_db"):
            setattr(self.pcollection, "calendar_user_proxy_db", CalendarUserProxyDatabase(self.pcollection.fp.path))
        return self.pcollection.calendar_user_proxy_db

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

    @inlineCallbacks
    def setGroupMemberSet(self, new_members, request):
        # FIXME: as defined right now it is not possible to specify a calendar-user-proxy group as
        # a member of any other group since the directory service does not know how to lookup
        # these special resource UIDs.
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
            if principal is None or principal.principalURL() != uri:
                raise HTTPError(StatusResponse(
                    responsecode.BAD_REQUEST,
                    "Attempt to use a non-existent principal %s as a group member of %s." % (uri, self.principalURL(),)
                ))
            principals.append(principal)
            yield principal.cacheNotifier.changed()

        # Map the principals to UIDs.
        uids = [p.principalUID() for p in principals]

        yield self._index().setGroupMembers(self.uid, uids)
        yield self.parent.cacheNotifier.changed()
        returnValue(True)

    ##
    # HTTP
    ##

    def renderDirectoryBody(self, request):
        # FIXME: Too much code duplication here from principal.py
        from twistedcaldav.directory.principal import format_list, format_principals, format_link

        closure = {}

        d = super(CalendarUserProxyPrincipalResource, self).renderDirectoryBody(request)
        d.addCallback(lambda output: closure.setdefault("output", output))

        d.addCallback(lambda _: self.groupMembers())
        d.addCallback(lambda members: closure.setdefault("members", members))

        d.addCallback(lambda _: self.groupMemberships())
        d.addCallback(lambda memberships: closure.setdefault("memberships", memberships))
        
        d.addCallback(
            lambda _: "".join((
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
                """Principal URL: %s\n"""          % (format_link(self.parent.principalURL()),),
                """\n"""
                """Proxy Principal Information\n"""
                """---------------------\n"""
               #"""GUID: %s\n"""                   % (self.guid,),
                """Principal UID: %s\n"""          % (self.principalUID(),),
                """Principal URL: %s\n"""          % (format_link(self.principalURL()),),
                """\nAlternate URIs:\n"""          , format_list(format_link(u) for u in self.alternateURIs()),
                """\nGroup members (%s):\n""" % ({False:"Locked", True:"Editable"}[self.hasEditableMembership()])
                                                   , format_principals(closure["members"]),
                """\nGroup memberships:\n"""       , format_principals(closure["memberships"]),
                """</pre></blockquote></div>""",
                closure["output"]
            ))
        )

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
        return self._alternate_urls

    def principalURL(self):
        return self._url

    def principalUID(self):
        return self.uid

    def principalCollections(self):
        return self.parent.principalCollections()

    @inlineCallbacks
    def _expandMemberUIDs(self, uid=None, relatives=None, uids=None):
        if uid is None:
            uid = self.principalUID()
        if relatives is None:
            relatives = set()
        if uids is None:
            uids = set()

        if uid not in uids:
            from twistedcaldav.directory.principal import DirectoryPrincipalResource
            uids.add(uid)
            principal = self.parent.parent.principalForUID(uid)
            if isinstance(principal, CalendarUserProxyPrincipalResource):
                members = yield self._directGroupMembers()
                for member in members:
                    if member.principalUID() not in uids:
                        relatives.add(member)
                        yield self._expandMemberUIDs(member.principalUID(), relatives, uids)
            elif isinstance(principal, DirectoryPrincipalResource):
                members = yield principal.groupMembers()
                relatives.update(members)

        returnValue(relatives)

    @inlineCallbacks
    def _directGroupMembers(self):
        if self.hasEditableMembership():
            # Get member UIDs from database and map to principal resources
            members = yield self._index().getMembers(self.uid)
            returnValue([p for p in [self.pcollection.principalForUID(uid) for uid in members] if p])
        else:
            # Fixed proxies
            if self.proxyType == "calendar-proxy-write":
                returnValue(self.parent.proxies())
            else:
                returnValue(self.parent.readOnlyProxies())

    def groupMembers(self):
        return self._expandMemberUIDs()

    @inlineCallbacks
    def groupMemberships(self):
        # Get membership UIDs and map to principal resources
        memberships = yield self._index().getMemberships(self.uid)
        returnValue([p for p in [self.pcollection.principalForUID(uid) for uid in memberships] if p])

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
    dbFilename = db_prefix + "calendaruserproxy"
    dbFormatVersion = "4"

    class ProxyDBMemcacher(Memcacher):
        
        def setMembers(self, guid, members):
            return self.set("members:%s" % (guid,), str(",".join(members)))

        def setMemberships(self, guid, memberships):
            return self.set("memberships:%s" % (guid,), str(",".join(memberships)))

        def getMembers(self, guid):
            def _value(value):
                if value:
                    return set(value.split(","))
                elif value is None:
                    return None
                else:
                    return set()
            d = self.get("members:%s" % (guid,))
            d.addCallback(_value)
            return d

        def getMemberships(self, guid):
            def _value(value):
                if value:
                    return set(value.split(","))
                elif value is None:
                    return None
                else:
                    return set()
            d = self.get("memberships:%s" % (guid,))
            d.addCallback(_value)
            return d

        def deleteMember(self, guid):
            return self.delete("members:%s" % (guid,))

        def deleteMembership(self, guid):
            return self.delete("memberships:%s" % (guid,))

    def __init__(self, path):
        path = os.path.join(path, CalendarUserProxyDatabase.dbFilename)
        super(CalendarUserProxyDatabase, self).__init__(path, True)
        
        self._memcacher = CalendarUserProxyDatabase.ProxyDBMemcacher("proxyDB")

    @inlineCallbacks
    def setGroupMembers(self, principalUID, members):
        """
        Add a group membership record.

        @param principalUID: the UID of the group principal to add.
        @param members: a list UIDs of principals that are members of this group.
        """

        # Get current members before we change them
        current_members = yield self.getMembers(principalUID)
        if current_members is None:
            current_members = ()
        current_members = set(current_members)

        # Remove what is there, then add it back.
        self._delete_from_db(principalUID)
        self._add_to_db(principalUID, members)
        self._db_commit()
        
        # Update cache
        update_members = set(members)
        
        remove_members = current_members.difference(update_members)
        add_members = update_members.difference(current_members)
        for member in itertools.chain(remove_members, add_members,):
            _ignore = yield self._memcacher.deleteMembership(member)
        _ignore = yield self._memcacher.deleteMember(principalUID)

    @inlineCallbacks
    def removeGroup(self, principalUID):
        """
        Remove a group membership record.

        @param principalUID: the UID of the group principal to remove.
        """

        self._delete_from_db(principalUID)
        self._db_commit()
        
        # Update cache
        members = yield self.getMembers(principalUID)
        if members:
            for member in members:
                yield self._memcacher.deleteMembership(member)
            yield self._memcacher.deleteMember(principalUID)

    @inlineCallbacks
    def getMembers(self, principalUID):
        """
        Return the list of group member UIDs for the specified principal.
        
        @return: a deferred returning a C{set} of members.
        """

        def _members():
            members = set()
            for row in self._db_execute("select MEMBER from GROUPS where GROUPNAME = :1", principalUID):
                members.add(row[0])
            return members

        # Pull from cache
        result = yield self._memcacher.getMembers(principalUID)
        if result is None:
            result = _members()
            yield self._memcacher.setMembers(principalUID, result)
        returnValue(result)

    @inlineCallbacks
    def getMemberships(self, principalUID):
        """
        Return the list of group principal UIDs the specified principal is a member of.
        
        @return: a deferred returning a C{set} of memberships.
        """

        def _members():
            members = set()
            for row in self._db_execute("select GROUPNAME from GROUPS where MEMBER = :1", principalUID):
                members.add(row[0])
            return members

        # Pull from cache
        result = yield self._memcacher.getMemberships(principalUID)
        if result is None:
            result = _members()
            yield self._memcacher.setMemberships(principalUID, result)
        returnValue(result)

    def _add_to_db(self, principalUID, members):
        """
        Insert the specified entry into the database.

        @param principalUID: the UID of the group principal to add.
        @param members: a list of UIDs or principals that are members of this group.
        """
        for member in members:
            self._db_execute(
                """
                insert into GROUPS (GROUPNAME, MEMBER)
                values (:1, :2)
                """, principalUID, member
            )

    def _delete_from_db(self, principalUID):
        """
        Deletes the specified entry from the database.

        @param principalUID: the UID of the group principal to remove.
        """
        self._db_execute("delete from GROUPS where GROUPNAME = :1", principalUID)

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
        q.execute(
            """
            create index GROUPNAMES on GROUPS (GROUPNAME)
            """
        )
        q.execute(
            """
            create index MEMBERS on GROUPS (MEMBER)
            """
        )

    def _db_upgrade_data_tables(self, q, old_version):
        """
        Upgrade the data from an older version of the DB.
        @param q: a database cursor to use.
        @param old_version: existing DB's version number
        @type old_version: str
        """

        # Add index if old version is less than "4"
        if int(old_version) < 4:
            q.execute(
                """
                create index GROUPNAMES on GROUPS (GROUPNAME)
                """
            )
            q.execute(
                """
                create index MEMBERS on GROUPS (MEMBER)
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
