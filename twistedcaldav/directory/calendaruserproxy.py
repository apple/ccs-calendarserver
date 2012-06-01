# -*- test-case-name: twistedcaldav.directory.test.test_proxyprincipalmembers -*-
##
# Copyright (c) 2006-2012 Apple Inc. All rights reserved.
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
    "ProxyDB",
    "ProxyDBService",
    "ProxySqliteDB",
    "ProxyPostgreSQLDB",
]

import itertools
import time

from twisted.internet.defer import succeed, inlineCallbacks, returnValue
from twext.web2 import responsecode
from twext.web2.http import HTTPError, StatusResponse
from txdav.xml import element as davxml
from txdav.xml.base import dav_namespace
from twext.web2.dav.util import joinURL
from twext.web2.dav.noneprops import NonePropertyStore

from twext.python.log import Logger, LoggingMixIn

from twisted.web.template import XMLFile, Element, renderer
from twisted.python.modules import getModule
from twistedcaldav.extensions import DirectoryElement
from twistedcaldav.directory.principal import formatLink
from twistedcaldav.directory.principal import formatLinks
from twistedcaldav.directory.principal import formatPrincipals

from twistedcaldav.directory.util import normalizeUUID
from twistedcaldav.config import config, fullServerPath
from twistedcaldav.database import AbstractADBAPIDatabase, ADBAPISqliteMixin,\
    ADBAPIPostgreSQLMixin
from twistedcaldav.extensions import DAVPrincipalResource,\
    DAVResourceWithChildrenMixin
from twistedcaldav.extensions import ReadOnlyWritePropertiesResourceMixIn
from twistedcaldav.memcacher import Memcacher
from twistedcaldav.resource import CalDAVComplianceMixIn

thisModule = getModule(__name__)
log = Logger()

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
        aces += tuple((
            davxml.ACE(
                davxml.Principal(davxml.HRef(principal)),
                davxml.Grant(davxml.Privilege(davxml.All())),
                davxml.Protected(),
            )
            for principal in config.AdminPrincipals
        ))

        return davxml.ACL(*aces)


    def accessControlList(self, request, inheritance=True, expanding=False,
                          inherited_aces=None):
        # Permissions here are fixed, and are not subject to inheritance rules, etc.
        return succeed(self.defaultAccessControlList())



class ProxyPrincipalDetailElement(Element):
    """
    A L{ProxyPrincipalDetailElement} is an L{Element} that can render the
    details of a L{CalendarUserProxyPrincipalResource}.
    """

    loader = XMLFile(thisModule.filePath.sibling(
        "calendar-user-proxy-principal-resource.html").open()
    )

    def __init__(self, resource):
        super(ProxyPrincipalDetailElement, self).__init__()
        self.resource = resource


    @renderer
    def principal(self, request, tag):
        """
        Top-level renderer in the template.
        """
        record = self.resource.parent.record
        resource = self.resource
        parent = self.resource.parent
        return tag.fillSlots(
            directoryGUID=record.service.guid,
            realm=record.service.realmName,
            guid=record.guid,
            recordType=record.recordType,
            shortNames=record.shortNames,
            fullName=record.fullName,
            principalUID=parent.principalUID(),
            principalURL=formatLink(parent.principalURL()),
            proxyPrincipalUID=resource.principalUID(),
            proxyPrincipalURL=formatLink(resource.principalURL()),
            alternateURIs=formatLinks(resource.alternateURIs()),
            groupMembers=resource.groupMembers().addCallback(formatPrincipals),
            groupMemberships=resource.groupMemberships().addCallback(
                formatPrincipals
            ),
        )



class ProxyPrincipalElement(DirectoryElement):
    """
    L{ProxyPrincipalElement} is a renderer for a
    L{CalendarUserProxyPrincipalResource}.
    """

    @renderer
    def resourceDetail(self, request, tag):
        """
        Render the proxy principal's details.
        """
        return ProxyPrincipalDetailElement(self.resource)



class CalendarUserProxyPrincipalResource (
        CalDAVComplianceMixIn, PermissionsMixIn, DAVResourceWithChildrenMixin,
        DAVPrincipalResource, LoggingMixIn):
    """
    Calendar user proxy principal resource.
    """

    def __init__(self, parent, proxyType):
        """
        @param parent: the parent of this resource.
        @param proxyType: a C{str} containing the name of the resource.
        """
        if self.isCollection():
            slash = "/"
        else:
            slash = ""

        url = joinURL(parent.principalURL(), proxyType) + slash

        super(CalendarUserProxyPrincipalResource, self).__init__()
        DAVResourceWithChildrenMixin.__init__(self)

        self.parent          = parent
        self.proxyType       = proxyType
        self._url            = url

        # FIXME: if this is supposed to be public, it needs a better name:
        self.pcollection     = self.parent.parent.parent

        # Principal UID is parent's GUID plus the proxy type; this we can easily
        # map back to a principal.
        self.uid             = "%s#%s" % (self.parent.principalUID(), proxyType)
        self._alternate_urls = tuple(
            joinURL(url, proxyType) + slash
            for url in parent.alternateURIs()
            if url.startswith("/")
        )


    def __str__(self):
        return "%s [%s]" % (self.parent, self.proxyType)


    def _index(self):
        """
        Return the SQL database for this group principal.

        @return: the L{ProxyDB} for the principal collection.
        """
        return ProxyDBService

    def resourceType(self):
        if self.proxyType == "calendar-proxy-read":
            return davxml.ResourceType.calendarproxyread #@UndefinedVariable
        elif self.proxyType == "calendar-proxy-write":
            return davxml.ResourceType.calendarproxywrite #@UndefinedVariable
        else:
            return super(CalendarUserProxyPrincipalResource, self).resourceType()

    def isProxyType(self, read_write):
        if (
            read_write and self.proxyType == "calendar-proxy-write" or
            not read_write and self.proxyType == "calendar-proxy-read"
        ):
            return True
        else:
            return False

    def isCollection(self):
        return True

    def etag(self):
        return succeed(None)

    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties


    def writeProperty(self, property, request):
        assert isinstance(property, davxml.WebDAVElement)

        if property.qname() == (dav_namespace, "group-member-set"):
            return self.setGroupMemberSet(property, request)

        return super(CalendarUserProxyPrincipalResource, self).writeProperty(
            property, request)


    @inlineCallbacks
    def setGroupMemberSet(self, new_members, request):
        # FIXME: as defined right now it is not possible to specify a
        # calendar-user-proxy group as a member of any other group since the
        # directory service does not know how to lookup these special resource
        # UIDs.
        #
        # Really, c-u-p principals should be treated the same way as any other
        # principal, so they should be allowed as members of groups.
        #
        # This implementation now raises an exception for any principal it
        # cannot find.

        # Break out the list into a set of URIs.
        members = [str(h) for h in new_members.children]

        # Map the URIs to principals and a set of UIDs.
        principals = []
        newUIDs = set()
        for uri in members:
            principal = self.pcollection._principalForURI(uri)
            # Invalid principals MUST result in an error.
            if principal is None or principal.principalURL() != uri:
                raise HTTPError(StatusResponse(
                    responsecode.BAD_REQUEST,
                    "Attempt to use a non-existent principal %s "
                    "as a group member of %s." % (uri, self.principalURL(),)
                ))
            principals.append(principal)
            newUIDs.add(principal.principalUID())

        # Get the old set of UIDs
        oldUIDs = (yield self._index().getMembers(self.uid))

        # Change membership
        yield self.setGroupMemberSetPrincipals(principals)

        # Invalidate the primary principal's cache, and any principal's whose
        # membership status changed
        yield self.parent.cacheNotifier.changed()

        changedUIDs = newUIDs.symmetric_difference(oldUIDs)
        for uid in changedUIDs:
            principal = self.pcollection.principalForUID(uid)
            if principal:
                yield principal.cacheNotifier.changed()

        returnValue(True)


    def setGroupMemberSetPrincipals(self, principals):
        # Map the principals to UIDs.
        return self._index().setGroupMembers(
            self.uid,
            [p.principalUID() for p in principals],
        )

    ##
    # HTTP
    ##

    def htmlElement(self):
        """
        Customize HTML display of proxy groups.
        """
        return ProxyPrincipalElement(self)


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
    def _expandMemberUIDs(self, uid=None, relatives=None, uids=None, infinity=False):
        if uid is None:
            uid = self.principalUID()
        if relatives is None:
            relatives = set()
        if uids is None:
            uids = set()

        if uid not in uids:
            from twistedcaldav.directory.principal import DirectoryPrincipalResource
            uids.add(uid)
            principal = self.pcollection.principalForUID(uid)
            if isinstance(principal, CalendarUserProxyPrincipalResource):
                members = yield self._directGroupMembers()
                for member in members:
                    if member.principalUID() not in uids:
                        relatives.add(member)
                        if infinity:
                            yield self._expandMemberUIDs(member.principalUID(), relatives, uids, infinity=infinity)
            elif isinstance(principal, DirectoryPrincipalResource):
                if infinity:
                    members = yield principal.expandedGroupMembers()
                else:
                    members = yield principal.groupMembers()
                relatives.update(members)

        returnValue(relatives)

    @inlineCallbacks
    def _directGroupMembers(self):
        # Get member UIDs from database and map to principal resources
        members = yield self._index().getMembers(self.uid)
        found = []
        for uid in members:
            p = self.pcollection.principalForUID(uid)
            if p:
                found.append(p)
                # Make sure any outstanding deletion timer entries for
                # existing principals are removed
                yield self._index().refreshPrincipal(uid)
            else:
                self.log_warn("Delegate is missing from directory: %s" % (uid,))

        returnValue(found)

    def groupMembers(self):
        return self._expandMemberUIDs()

    @inlineCallbacks
    def expandedGroupMembers(self):
        """
        Return the complete, flattened set of principals belonging to this
        group.
        """
        returnValue((yield self._expandMemberUIDs(infinity=True)))

    def groupMemberships(self):
        # Get membership UIDs and map to principal resources
        d = self._index().getMemberships(self.uid)
        d.addCallback(lambda memberships: [
            p for p
            in [self.pcollection.principalForUID(uid) for uid in memberships]
            if p
        ])
        return d

class ProxyDB(AbstractADBAPIDatabase, LoggingMixIn):
    """
    A database to maintain calendar user proxy group memberships.

    SCHEMA:

    Group Database:

    ROW: GROUPNAME, MEMBER

    """

    schema_version = "5"
    schema_type    = "CALENDARUSERPROXY"

    class ProxyDBMemcacher(Memcacher):

        def __init__(self, namespace):
            super(ProxyDB.ProxyDBMemcacher, self).__init__(namespace, key_normalization=config.Memcached.ProxyDBKeyNormalization)

        def setMembers(self, guid, members):
            return self.set("members:%s" % (str(guid),), str(",".join(members)))

        def setMemberships(self, guid, memberships):
            return self.set("memberships:%s" % (str(guid),), str(",".join(memberships)))

        def getMembers(self, guid):
            def _value(value):
                if value:
                    return set(value.split(","))
                elif value is None:
                    return None
                else:
                    return set()
            d = self.get("members:%s" % (str(guid),))
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
            d = self.get("memberships:%s" % (str(guid),))
            d.addCallback(_value)
            return d

        def deleteMember(self, guid):
            return self.delete("members:%s" % (str(guid),))

        def deleteMembership(self, guid):
            return self.delete("memberships:%s" % (str(guid),))

        def setDeletionTimer(self, guid, delay):
            return self.set("del:%s" % (str(guid),), str(self.getTime()+delay))

        def checkDeletionTimer(self, guid):
            # True means it's overdue, False means it's not, None means no timer
            def _value(value):
                if value:
                    if int(value) <= self.getTime():
                        return True
                    else:
                        return False
                else:
                    return None
            d = self.get("del:%s" % (str(guid),))
            d.addCallback(_value)
            return d

        def clearDeletionTimer(self, guid):
            return self.delete("del:%s" % (str(guid),))

        def getTime(self):
            if hasattr(self, 'theTime'):
                theTime = self.theTime
            else:
                theTime = int(time.time())
            return theTime

    def __init__(self, dbID, dbapiName, dbapiArgs, **kwargs):
        AbstractADBAPIDatabase.__init__(self, dbID, dbapiName, dbapiArgs, True, **kwargs)
        
        self._memcacher = ProxyDB.ProxyDBMemcacher("ProxyDB")

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

        # Find changes
        update_members = set(members)
        remove_members = current_members.difference(update_members)
        add_members = update_members.difference(current_members)

        yield self.changeGroupMembersInDatabase(principalUID, add_members, remove_members)

        # Update cache
        for member in itertools.chain(remove_members, add_members,):
            yield self._memcacher.deleteMembership(member)
        yield self._memcacher.deleteMember(principalUID)

    @inlineCallbacks
    def setGroupMembersInDatabase(self, principalUID, members):
        """
        A blocking call to add a group membership record in the database.

        @param principalUID: the UID of the group principal to add.
        @param members: a list UIDs of principals that are members of this group.
        """
        # Remove what is there, then add it back.
        yield self._delete_from_db(principalUID)
        yield self._add_to_db(principalUID, members)
        
    @inlineCallbacks
    def changeGroupMembersInDatabase(self, principalUID, addMembers, removeMembers):
        """
        A blocking call to add a group membership record in the database.

        @param principalUID: the UID of the group principal to add.
        @param addMembers: a list UIDs of principals to be added as members of this group.
        @param removeMembers: a list UIDs of principals to be removed as members of this group.
        """
        # Remove what is there, then add it back.
        for member in removeMembers:
            yield self._delete_from_db_one(principalUID, member)
        for member in addMembers:
            yield self._add_to_db_one(principalUID, member)
        
    @inlineCallbacks
    def removeGroup(self, principalUID):
        """
        Remove a group membership record.

        @param principalUID: the UID of the group principal to remove.
        """

        # Need to get the members before we do the delete
        members = yield self.getMembers(principalUID)

        yield self._delete_from_db(principalUID)
        
        # Update cache
        if members:
            for member in members:
                yield self._memcacher.deleteMembership(member)
            yield self._memcacher.deleteMember(principalUID)

    @inlineCallbacks
    def removePrincipal(self, principalUID, delay=None):
        """
        Remove a group membership record.

        @param principalUID: the UID of the principal to remove.
        """

        if delay:
            # We are going to remove the principal only after <delay> seconds
            # has passed since we first chose to remove it, to protect against
            # transient directory problems.
            # If <delay> is specified, first see if there was a timer set
            # previously.  If the timer is more than delay seconds old, we
            # go ahead and remove the principal.  Otherwise, do nothing.

            overdue = yield self._memcacher.checkDeletionTimer(principalUID)

            if overdue == False:
                # Do nothing
                returnValue(None)

            elif overdue is None:
                # No timer was previously set
                self.log_debug("Delaying removal of missing proxy principal '%s'"
                               % (principalUID,))
                yield self._memcacher.setDeletionTimer(principalUID, delay=delay)
                returnValue(None)

        self.log_warn("Removing missing proxy principal for '%s'"
                      % (principalUID,))

        for suffix in ("calendar-proxy-read", "calendar-proxy-write",):
            groupUID = "%s#%s" % (principalUID, suffix,)
            yield self._delete_from_db(groupUID)

            # Update cache
            members = yield self.getMembers(groupUID)
            if members:
                for member in members:
                    yield self._memcacher.deleteMembership(member)
                yield self._memcacher.deleteMember(groupUID)

        memberships = (yield self.getMemberships(principalUID))
        for groupUID in memberships:
            yield self._memcacher.deleteMember(groupUID)

        yield self._delete_from_db_member(principalUID)
        yield self._memcacher.deleteMembership(principalUID)
        yield self._memcacher.clearDeletionTimer(principalUID)

    def refreshPrincipal(self, principalUID):
        """
        Bring back to life a principal that was previously deleted.

        @param principalUID:
        @type principalUID:
        """
        
        return self._memcacher.clearDeletionTimer(principalUID)

    def getMembers(self, principalUID):
        """
        Return the list of group member UIDs for the specified principal.

        @return: a deferred returning a C{set} of members.
        """
        def gotCachedMembers(members):
            if members is not None:
                return members

            # Cache miss; compute members and update cache
            def gotMembersFromDB(dbmembers):
                members = set([row[0].encode("utf-8") for row in dbmembers])
                d = self._memcacher.setMembers(principalUID, members)
                d.addCallback(lambda _: members)
                return d

            d =  self.query("select MEMBER from GROUPS where GROUPNAME = :1", (principalUID.decode("utf-8"),))
            d.addCallback(gotMembersFromDB)
            return d

        d = self._memcacher.getMembers(principalUID)
        d.addCallback(gotCachedMembers)
        return d

    def getMemberships(self, principalUID):
        """
        Return the list of group principal UIDs the specified principal is a member of.
        
        @return: a deferred returning a C{set} of memberships.
        """
        def gotCachedMemberships(memberships):
            if memberships is not None:
                return memberships

            # Cache miss; compute memberships and update cache
            def gotMembershipsFromDB(dbmemberships):
                memberships = set([row[0].encode("utf-8") for row in dbmemberships])
                d = self._memcacher.setMemberships(principalUID, memberships)
                d.addCallback(lambda _: memberships)
                return d

            d =  self.query("select GROUPNAME from GROUPS where MEMBER = :1", (principalUID.decode("utf-8"),))
            d.addCallback(gotMembershipsFromDB)
            return d

        d = self._memcacher.getMemberships(principalUID)
        d.addCallback(gotCachedMemberships)
        return d

    @inlineCallbacks
    def _add_to_db(self, principalUID, members):
        """
        Insert the specified entry into the database.

        @param principalUID: the UID of the group principal to add.
        @param members: a list of UIDs or principals that are members of this group.
        """
        for member in members:
            yield self.execute(
                """
                insert into GROUPS (GROUPNAME, MEMBER)
                values (:1, :2)
                """, (principalUID.decode("utf-8"), member,)
            )

    def _add_to_db_one(self, principalUID, memberUID):
        """
        Insert the specified entry into the database.

        @param principalUID: the UID of the group principal to add.
        @param memberUID: the UID of the principal that is being added as a member of this group.
        """
        return self.execute(
            """
            insert into GROUPS (GROUPNAME, MEMBER)
            values (:1, :2)
            """, (principalUID.decode("utf-8"), memberUID.decode("utf-8"),)
        )

    def _delete_from_db(self, principalUID):
        """
        Deletes the specified entry from the database.

        @param principalUID: the UID of the group principal to remove.
        """
        return self.execute("delete from GROUPS where GROUPNAME = :1", (principalUID.decode("utf-8"),))

    def _delete_from_db_one(self, principalUID, memberUID):
        """
        Deletes the specified entry from the database.

        @param principalUID: the UID of the group principal to remove.
        @param memberUID: the UID of the principal that is being removed as a member of this group.
        """
        return self.execute("delete from GROUPS where GROUPNAME = :1 and MEMBER = :2", (principalUID.decode("utf-8"), memberUID.decode("utf-8"),))

    def _delete_from_db_member(self, principalUID):
        """
        Deletes the specified member entry from the database.

        @param principalUID: the UID of the member principal to remove.
        """
        return self.execute("delete from GROUPS where MEMBER = :1", (principalUID.decode("utf-8"),))

    def _db_version(self):
        """
        @return: the schema version assigned to this index.
        """
        return ProxyDB.schema_version

    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return ProxyDB.schema_type

    @inlineCallbacks
    def _db_init_data_tables(self):
        """
        Initialise the underlying database tables.
        @param q:           a database cursor to use.
        """

        #
        # GROUPS table
        #
        yield self._create_table(
            "GROUPS",
            (
                ("GROUPNAME", "text"),
                ("MEMBER",    "text"),
            ),
            ifnotexists=True,
        )

        yield self._create_index(
            "GROUPNAMES",
            "GROUPS",
            ("GROUPNAME",),
            ifnotexists=True,
        )
        yield self._create_index(
            "MEMBERS",
            "GROUPS",
            ("MEMBER",),
            ifnotexists=True,
        )


    @inlineCallbacks
    def _db_upgrade_data_tables(self, old_version):
        """
        Upgrade the data from an older version of the DB.
        @param old_version: existing DB's version number
        @type old_version: str
        """

        # Add index if old version is less than "4"
        if int(old_version) < 4:
            yield self._create_index(
                "GROUPNAMES",
                "GROUPS",
                ("GROUPNAME",),
                ifnotexists=True,
            )
            yield self._create_index(
                "MEMBERS",
                "GROUPS",
                ("MEMBER",),
                ifnotexists=True,
            )

        if int(old_version) < 5:
            for (groupname, member) in (
                    (yield self._db_all_values_for_sql(
                        "select GROUPNAME, MEMBER from GROUPS"))
                ):
                grouplist = groupname.split("#")
                grouplist[0] = normalizeUUID(grouplist[0])
                yield self._db_execute("""
                    update GROUPS set GROUPNAME = :1, MEMBER = :2
                    where GROUPNAME = :3 and MEMBER = :4
                """, ["#".join(grouplist), normalizeUUID(member),
                      groupname, member])


    def _db_empty_data_tables(self):
        """
        Empty the underlying database tables.
        @param q:           a database cursor to use.
        """

        #
        # GROUPS table
        #
        return self._db_execute("delete from GROUPS")

    @inlineCallbacks
    def clean(self):
        
        if not self.initialized:
            yield self.open()

        for group in [row[0] for row in (yield self.query("select GROUPNAME from GROUPS"))]:
            self.removeGroup(group)
        
        yield super(ProxyDB, self).clean()

    @inlineCallbacks
    def getAllMembers(self):
        """
        Retrieve all members that have been directly delegated to
        """
        returnValue([row[0] for row in (yield self.query("select DISTINCT MEMBER from GROUPS"))])

ProxyDBService = None   # Global proxyDB service


class ProxySqliteDB(ADBAPISqliteMixin, ProxyDB):
    """
    Sqlite based proxy database implementation.
    """

    def __init__(self, dbpath):
        
        ADBAPISqliteMixin.__init__(self)
        ProxyDB.__init__(self, "Proxies", "sqlite3", (fullServerPath(config.DataRoot, dbpath),))

class ProxyPostgreSQLDB(ADBAPIPostgreSQLMixin, ProxyDB):
    """
    PostgreSQL based augment database implementation.
    """

    def __init__(self, host, database, user=None, password=None, dbtype=None):
        
        ADBAPIPostgreSQLMixin.__init__(self, )
        ProxyDB.__init__(self, "Proxies", "pgdb", (), host=host, database=database, user=user, password=password,)
        if dbtype:
            ProxyDB.schema_type = dbtype

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
