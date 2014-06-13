# -*- test-case-name: twistedcaldav.directory.test.test_proxyprincipalmembers -*-
##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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
import uuid

from twext.python.log import Logger
from twext.who.idirectory import RecordType as BaseRecordType
from twisted.internet.defer import succeed, inlineCallbacks, returnValue
from twisted.python.modules import getModule
from twisted.web.template import XMLFile, Element, renderer
from twistedcaldav.config import config, fullServerPath
from twistedcaldav.database import (
    AbstractADBAPIDatabase, ADBAPISqliteMixin, ADBAPIPostgreSQLMixin
)
from twistedcaldav.directory.util import normalizeUUID
from twistedcaldav.directory.util import (
    formatLink, formatLinks, formatPrincipals
)

from twistedcaldav.extensions import (
    DAVPrincipalResource, DAVResourceWithChildrenMixin
)
from twistedcaldav.extensions import DirectoryElement
from twistedcaldav.extensions import ReadOnlyWritePropertiesResourceMixIn
from twistedcaldav.memcacher import Memcacher
from twistedcaldav.resource import CalDAVComplianceMixIn
from txdav.who.delegates import RecordType as DelegateRecordType
from txdav.xml import element as davxml
from txdav.xml.base import dav_namespace
from txweb2 import responsecode
from txweb2.dav.noneprops import NonePropertyStore
from txweb2.dav.util import joinURL
from txweb2.http import HTTPError, StatusResponse

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

        return succeed(davxml.ACL(*aces))


    def accessControlList(self, request, inheritance=True, expanding=False,
                          inherited_aces=None):
        # Permissions here are fixed, and are not subject to inheritance rules, etc.
        return self.defaultAccessControlList()



class ProxyPrincipalDetailElement(Element):
    """
    A L{ProxyPrincipalDetailElement} is an L{Element} that can render the
    details of a L{CalendarUserProxyPrincipalResource}.
    """

    loader = XMLFile(thisModule.filePath.sibling(
        "calendar-user-proxy-principal-resource.html")
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
        try:
            if isinstance(record.guid, uuid.UUID):
                guid = str(record.guid).upper()
            else:
                guid = record.guid
        except AttributeError:
            guid = ""
        return tag.fillSlots(
            directoryGUID=record.service.guid,
            realm=record.service.realmName,
            guid=guid,
            recordType=record.service.recordTypeToOldName(record.recordType),
            shortNames=record.shortNames,
            fullName=record.displayName,
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
        DAVPrincipalResource):
    """
    Calendar user proxy principal resource.
    """
    log = Logger()

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

        self.parent = parent
        self.proxyType = proxyType
        self._url = url

        # FIXME: if this is supposed to be public, it needs a better name:
        self.pcollection = self.parent.parent.parent

        # Principal UID is parent's GUID plus the proxy type; this we can easily
        # map back to a principal.
        self.uid = "%s#%s" % (self.parent.principalUID(), proxyType)
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
            return davxml.ResourceType.calendarproxyread  # @UndefinedVariable
        elif self.proxyType == "calendar-proxy-write":
            return davxml.ResourceType.calendarproxywrite  # @UndefinedVariable
        elif self.proxyType == "calendar-proxy-read-for":
            return davxml.ResourceType.calendarproxyreadfor  # @UndefinedVariable
        elif self.proxyType == "calendar-proxy-write-for":
            return davxml.ResourceType.calendarproxywritefor  # @UndefinedVariable
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
            principal = yield self.pcollection._principalForURI(uri)
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
        # oldUIDs = (yield self._index().getMembers(self.uid))
        oldPrincipals = yield self.groupMembers()
        oldUIDs = [p.principalUID() for p in oldPrincipals]

        # Change membership
        yield self.setGroupMemberSetPrincipals(principals)

        # Invalidate the primary principal's cache, and any principal's whose
        # membership status changed
        yield self.parent.cacheNotifier.changed()

        changedUIDs = newUIDs.symmetric_difference(oldUIDs)
        for uid in changedUIDs:
            principal = yield self.pcollection.principalForUID(uid)
            if principal:
                yield principal.cacheNotifier.changed()

        returnValue(True)


    @inlineCallbacks
    def setGroupMemberSetPrincipals(self, principals):

        # Find our pseudo-record
        record = yield self.parent.record.service.recordWithShortName(
            self._recordTypeFromProxyType(),
            self.parent.principalUID()
        )
        # Set the members
        memberRecords = [p.record for p in principals]
        yield record.setMembers(memberRecords)


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
    def _expandMemberPrincipals(self, uid=None, relatives=None, uids=None, infinity=False):
        if uid is None:
            uid = self.principalUID()
        if relatives is None:
            relatives = set()
        if uids is None:
            uids = set()

        if uid not in uids:
            from twistedcaldav.directory.principal import DirectoryPrincipalResource
            uids.add(uid)
            principal = yield self.pcollection.principalForUID(uid)
            if isinstance(principal, CalendarUserProxyPrincipalResource):
                members = yield self._directGroupMembers()
                for member in members:
                    if member.principalUID() not in uids:
                        relatives.add(member)
                        if infinity:
                            yield self._expandMemberPrincipals(member.principalUID(), relatives, uids, infinity=infinity)
            elif isinstance(principal, DirectoryPrincipalResource):
                if infinity:
                    members = yield principal.expandedGroupMembers()
                else:
                    members = yield principal.groupMembers()
                relatives.update(members)

        returnValue(relatives)


    def _recordTypeFromProxyType(self):
        return {
            "calendar-proxy-read": DelegateRecordType.readDelegateGroup,
            "calendar-proxy-write": DelegateRecordType.writeDelegateGroup,
            "calendar-proxy-read-for": DelegateRecordType.readDelegatorGroup,
            "calendar-proxy-write-for": DelegateRecordType.writeDelegatorGroup,
        }.get(self.proxyType)


    @inlineCallbacks
    def _directGroupMembers(self):
        """
        Fault in the record representing the sub principal for this proxy type
        (either read-only or read-write), then fault in the direct members of
        that record.
        """
        memberPrincipals = []
        record = yield self.parent.record.service.recordWithShortName(
            self._recordTypeFromProxyType(),
            self.parent.principalUID()
        )
        if record is not None:
            memberRecords = yield record.members()
            for record in memberRecords:
                if record is not None:
                    principal = yield self.pcollection.principalForRecord(
                        record
                    )
                    if principal is not None:
                        if (
                            principal.record.loginAllowed or
                            principal.record.recordType is BaseRecordType.group
                        ):
                            memberPrincipals.append(principal)
        returnValue(memberPrincipals)


    def groupMembers(self):
        return self._expandMemberPrincipals()


    @inlineCallbacks
    def expandedGroupMembers(self):
        """
        Return the complete, flattened set of principals belonging to this
        group.
        """
        returnValue((yield self._expandMemberPrincipals(infinity=True)))


    def groupMemberships(self):
        # Unlikely to ever want to put a subprincipal into a group
        return succeed([])


    @inlineCallbacks
    def containsPrincipal(self, principal):
        """
        Uses proxyFor information to turn the "contains principal" question around;
        rather than expanding this principal's groups to see if the other principal
        is a member, ask the other principal if they are a proxy for this principal's
        parent resource, since this principal is a proxy principal.

        @param principal: The principal to check
        @type principal: L{DirectoryCalendarPrincipalResource}
        @return: True if principal is a proxy (of the correct type) of our parent
        @rtype: C{boolean}
        """
        readWrite = self.isProxyType(True)  # is read-write
        if principal and self.parent in (yield principal.proxyFor(readWrite)):
            returnValue(True)
        returnValue(False)



class ProxyDB(AbstractADBAPIDatabase):
    """
    A database to maintain calendar user proxy group memberships.

    SCHEMA:

    Group Database:

    ROW: GROUPNAME, MEMBER
    """
    log = Logger()

    schema_version = "4"
    schema_type = "CALENDARUSERPROXY"

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

            d = self.query("select MEMBER from GROUPS where GROUPNAME = :1", (principalUID.decode("utf-8"),))
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

            d = self.query("select GROUPNAME from GROUPS where MEMBER = :1", (principalUID.decode("utf-8"),))
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
                ("MEMBER", "text"),
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
    def open(self):
        """
        Open the database, normalizing all UUIDs in the process if necessary.
        """
        result = yield super(ProxyDB, self).open()
        yield self._maybeNormalizeUUIDs()
        returnValue(result)


    @inlineCallbacks
    def _maybeNormalizeUUIDs(self):
        """
        Normalize the UUIDs in the proxy database so they correspond to the
        normalized UUIDs in the main calendar database.
        """
        alreadyDone = yield self._db_value_for_sql(
            "select VALUE from CALDAV where KEY = 'UUIDS_NORMALIZED'"
        )
        if alreadyDone is None:
            for (groupname, member) in (
                (yield self._db_all_values_for_sql(
                    "select GROUPNAME, MEMBER from GROUPS"))
            ):
                grouplist = groupname.split("#")
                grouplist[0] = normalizeUUID(grouplist[0])
                newGroupName = "#".join(grouplist)
                newMemberName = normalizeUUID(member)
                if newGroupName != groupname or newMemberName != member:
                    yield self._db_execute("""
                        update GROUPS set GROUPNAME = :1, MEMBER = :2
                        where GROUPNAME = :3 and MEMBER = :4
                    """, [newGroupName, newMemberName,
                          groupname, member])
            yield self._db_execute(
                """
                insert or ignore into CALDAV (KEY, VALUE)
                values ('UUIDS_NORMALIZED', 'YES')
                """
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

        ADBAPIPostgreSQLMixin.__init__(self,)
        ProxyDB.__init__(self, "Proxies", "pgdb", (), host=host, database=database, user=user, password=password,)
        if dbtype:
            ProxyDB.schema_type = dbtype


    def _maybeNormalizeUUIDs(self):
        """
        Don't bother normalizing UUIDs for postgres yet; users of postgres
        databases for proxy data are even less likely to have UUID
        case-normalization issues than the general population.
        """
        return succeed(None)



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
