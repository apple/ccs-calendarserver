##
# Copyright (c) 2008-2009 Aymeric Augustin. All rights reserved.
# Copyright (c) 2006-2011 Apple Inc. All rights reserved.
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
LDAP directory service implementation.  Supports principal-property-search
and restrictToGroup features.

The following attributes from standard schemas are used:
* Core (RFC 4519):
    . cn | commonName
    . givenName
    . member (if not using NIS groups)
    . ou
    . sn | surname
    . uid | userid (if using NIS groups)
* COSINE (RFC 4524):
    . mail
* InetOrgPerson (RFC 2798):
    . displayName (if cn is unavailable)
* NIS (RFC):
    . gecos (if cn is unavailable)
    . memberUid (if using NIS groups)
"""

__all__ = [
    "LdapDirectoryService",
]

import ldap
try:
    # Note: PAM support is currently untested
    import PAM
    pamAvailable = True
except ImportError:
    pamAvailable = False

import time
from twisted.cred.credentials import UsernamePassword
from twistedcaldav.directory.cachingdirectory import (CachingDirectoryService,
    CachingDirectoryRecord)
from twistedcaldav.directory import augment
from twistedcaldav.directory.directory import DirectoryConfigurationError
from twisted.internet.defer import succeed

class LdapDirectoryService(CachingDirectoryService):
    """
    LDAP based implementation of L{IDirectoryService}.
    """
    baseGUID = "5A871574-0C86-44EE-B11B-B9440C3DC4DD"

    def __repr__(self):
        return "<%s %r: %r>" % (self.__class__.__name__, self.realmName,
            self.uri)

    def __init__(self, params):
        """
        @param params: a dictionary containing the following keys:
            cacheTimeout, realmName, uri, tls, tlsCACertFile, tlsCACertDir,
            tlsRequireCert, crendentials, rdnSchema, groupSchema
        """

        defaults = {
            "augmentService" : None,
            "cacheTimeout": 1,
            "negativeCaching": False,
            "restrictEnabledRecords": False,
            "restrictToGroup": "",
            "recordTypes": ("users", "groups"),
            "uri": "ldap://localhost/",
            "tls": False,
            "tlsCACertFile": None,
            "tlsCACertDir": None,
            "tlsRequireCert": None, # never, allow, try, demand, hard
            "credentials": {
                "dn": None,
                "password": None,
            },
            "authMethod": "LDAP",
            "rdnSchema": {
                "base": "dc=example,dc=com",
                "guidAttr": None,
                "users": {
                    "rdn": "ou=People",
                    "attr": "uid", # used only to synthesize email address
                    "emailSuffix": None, # used only to synthesize email address
                    "filter": None, # additional filter for this type
                    "recordName": "uid", # uniquely identifies user records
                },
                "groups": {
                    "rdn": "ou=Group",
                    "attr": "cn", # used only to synthesize email address
                    "emailSuffix": None, # used only to synthesize email address
                    "filter": None, # additional filter for this type
                    "recordName": "cn", # uniquely identifies group records
                },
                "locations": {
                    "rdn": "ou=Locations",
                    "attr": "cn", # used only to synthesize email address
                    "emailSuffix": None, # used only to synthesize email address
                    "filter": None, # additional filter for this type
                    "recordName": "cn", # uniquely identifies location records
                },
                "resources": {
                    "rdn": "ou=Resources",
                    "attr": "cn", # used only to synthesize email address
                    "emailSuffix": None, # used only to synthesize email address
                    "filter": None, # additional filter for this type
                    "recordName": "cn", # uniquely identifies resource records
                },
            },
            "groupSchema": {
                "membersAttr": "member", # how members are specified
                "nestedGroupsAttr": None, # how nested groups are specified
                "memberIdAttr": None, # which attribute the above refer to
            },
            "attributeMapping": { # maps internal record names to LDAP
                "fullName" : "cn",
                "emailAddresses" : "mail",
                "firstName" : "givenName",
                "lastName" : "sn",
            },
        }
        ignored = None
        params = self.getParams(params, defaults, ignored)

        self._recordTypes = params["recordTypes"]

        super(LdapDirectoryService, self).__init__(params["cacheTimeout"],
                                                   params["negativeCaching"])

        self.augmentService = params["augmentService"]
        self.realmName = params["uri"]
        self.uri = params["uri"]
        self.tls = params["tls"]
        self.tlsCACertFile = params["tlsCACertFile"]
        self.tlsCACertDir = params["tlsCACertDir"]
        self.tlsRequireCert = params["tlsRequireCert"]
        self.credentials = params["credentials"]
        self.authMethod = params["authMethod"]
        self.rdnSchema = params["rdnSchema"]
        self.groupSchema = params["groupSchema"]
        self.attributeMapping = params["attributeMapping"]

        self.base = ldap.dn.str2dn(self.rdnSchema["base"])

        # Certain attributes (such as entryUUID) may be hidden and not
        # returned by default when queried for all attributes. Therefore it is
        # necessary to explicitly pass all the possible attributes list
        # for ldap searches
        attrSet = set(["mail", "uid", "userid", "cn", "commonName",
                       "displayName", "gecos", "givenName", "sn", "surname"])
        if self.rdnSchema["guidAttr"]:
            attrSet.add(self.rdnSchema["guidAttr"])
        for recordType in self.recordTypes():
            if self.rdnSchema[recordType]["attr"]:
                attrSet.add(self.rdnSchema[recordType]["attr"])
        if self.groupSchema["membersAttr"]:
            attrSet.add(self.groupSchema["membersAttr"])
        if self.groupSchema["nestedGroupsAttr"]:
            attrSet.add(self.groupSchema["nestedGroupsAttr"])
        if self.groupSchema["memberIdAttr"]:
            attrSet.add(self.groupSchema["memberIdAttr"])
        self.attrList = list(attrSet)

        self.typeRDNs = {}
        for recordType in self.recordTypes():
            self.typeRDNs[recordType] = ldap.dn.str2dn(
                self.rdnSchema[recordType]["rdn"]
            )

        # Create LDAP connection
        self.log_info("Connecting to LDAP %s" % (repr(self.uri),))

        self.ldap = self.createLDAPConnection()
        if self.credentials.get("dn", ""):
            try:
                self.log_info("Binding to LDAP %s" %
                    (repr(self.credentials.get("dn")),))
                self.ldap.simple_bind_s(self.credentials.get("dn"),
                    self.credentials.get("password"))
            except ldap.INVALID_CREDENTIALS:
                msg = "Can't bind to LDAP %s: check credentials" % (self.uri,)
                self.log_error(msg)
                raise DirectoryConfigurationError(msg)

        # Separate LDAP connection used solely for authenticating clients
        self.authLDAP = None

        # Restricting access by directory group
        self.restrictEnabledRecords = params['restrictEnabledRecords']
        self.restrictToGroup = params['restrictToGroup']
        self.restrictedTimestamp = 0


    def recordTypes(self):
        return self._recordTypes


    def createLDAPConnection(self):
        """
        Create and configure LDAP connection
        """
        cxn = ldap.ldapobject.ReconnectLDAPObject(self.uri)

        if self.tlsCACertFile:
            cxn.set_option(ldap.OPT_X_TLS_CACERTFILE, self.tlsCACertFile)
        if self.tlsCACertDir:
            cxn.set_option(ldap.OPT_X_TLS_CACERTDIR, self.tlsCACertDir)

        if self.tlsRequireCert == "never":
            cxn.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_NEVER)
        elif self.tlsRequireCert == "allow":
            cxn.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_ALLOW)
        elif self.tlsRequireCert == "try":
            cxn.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_TRY)
        elif self.tlsRequireCert == "demand":
            cxn.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_DEMAND)
        elif self.tlsRequireCert == "hard":
            cxn.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_HARD)

        if self.tls:
            cxn.start_tls_s()

        return cxn


    def authenticate(self, dn, password):
        """
        Perform simple bind auth, raising ldap.INVALID_CREDENTIALS if
        bad password
        """
        if self.authLDAP is None:
            self.log_debug("Creating authentication connection to LDAP")
            self.authLDAP = self.createLDAPConnection()
        self.log_debug("Authenticating %s" % (dn,))
        self.authLDAP.bind_s(dn, password)


    @property
    def restrictedGUIDs(self):
        """
        Look up (and cache) the set of guids that are members of the
        restrictToGroup.  If restrictToGroup is not set, return None to
        indicate there are no group restrictions.

        guidAttr must also be specified in config for restrictToGroups to work.
        """
        if self.restrictEnabledRecords and self.rdnSchema["guidAttr"]:

            if time.time() - self.restrictedTimestamp > self.cacheTimeout:
                # fault in the members of group of name self.restrictToGroup

                recordType = self.recordType_groups
                base = self.typeRDNs[recordType] + self.base
                filter = "(cn=%s)" % (self.restrictToGroup,)
                self.log_info("Retrieving ldap record with base %s and filter %s." %
                    (ldap.dn.dn2str(base), filter))
                result = self.ldap.search_s(ldap.dn.dn2str(base),
                    ldap.SCOPE_SUBTREE, filter, self.attrList)

                if len(result) == 1:
                    dn, attrs = result[0]
                    if self.groupSchema["membersAttr"]:
                        members = self._getMultipleLdapAttributes(attrs,
                            self.groupSchema["membersAttr"])
                    if self.groupSchema["nestedGroupsAttr"]:
                        nestedGroups = self._getMultipleLdapAttributes(attrs,
                            self.groupSchema["nestedGroupsAttr"])

                else:
                    members = []
                    nestedGroups = []

                self._cachedRestrictedGUIDs = set(self._expandGroupMembership(members, nestedGroups, returnGroups=True))
                self.log_debug("Got %d restricted group members" % (len(self._cachedRestrictedGUIDs),))
                self.restrictedTimestamp = time.time()
            return self._cachedRestrictedGUIDs
        else:
            # No restrictions
            return None


    def _expandGroupMembership(self, members, nestedGroups,
        processedGUIDs=None, returnGroups=False):

        if processedGUIDs is None:
            processedGUIDs = set()

        if isinstance(members, str):
            members = [members]

        if isinstance(nestedGroups, str):
            nestedGroups = [nestedGroups]

        for memberGUID in members:
            if memberGUID not in processedGUIDs:
                processedGUIDs.add(memberGUID)
                yield memberGUID

        for groupGUID in nestedGroups:
            if groupGUID in processedGUIDs:
                continue

            recordType = self.recordType_groups
            base = self.typeRDNs[recordType] + self.base
            filter = "(%s=%s)" % (self.rdnSchema["guidAttr"], groupGUID)

            self.log_info("Retrieving ldap record with base %s and filter %s." %
                (ldap.dn.dn2str(base), filter))
            result = self.ldap.search_s(ldap.dn.dn2str(base),
                ldap.SCOPE_SUBTREE, filter, self.attrList)

            if len(result) == 0:
                continue

            if len(result) == 1:
                dn, attrs = result[0]
                if self.groupSchema["membersAttr"]:
                    subMembers = self._getMultipleLdapAttributes(attrs,
                        self.groupSchema["membersAttr"])
                else:
                    subMembers = []

                if self.groupSchema["nestedGroupsAttr"]:
                    subNestedGroups = self._getMultipleLdapAttributes(attrs,
                        self.groupSchema["nestedGroupsAttr"])
                else:
                    subNestedGroups = []

            processedGUIDs.add(groupGUID)
            if returnGroups:
                yield groupGUID

            for GUID in self._expandGroupMembership(subMembers,
                subNestedGroups, processedGUIDs, returnGroups):
                yield GUID


    def _getUniqueLdapAttribute(self, attrs, *keys):
        """
        Get the first value for one or several attributes
        Useful when attributes have aliases (e.g. sn vs. surname)
        """
        for key in keys:
            values = attrs.get(key)
            if values is not None:
                return values[0]
        return None


    def _getMultipleLdapAttributes(self, attrs, *keys):
        """
        Get all values for one or several attributes
        """
        results = []
        for key in keys:
            values = attrs.get(key)
            if values is not None:
                results += values
        return set(results)


    def _ldapResultToRecord(self, dn, attrs, recordType):
        """
        Convert the attrs returned by a LDAP search into a LdapDirectoryRecord
        object.

        Mappings are hardcoded below but the most standard LDAP schemas were
        used to define them
        """

        guid = None
        shortNames = ()
        authIDs = set()
        fullName = None
        firstName = None
        lastName = None
        emailAddresses = set()
        calendarUserAddresses = set()
        enabledForCalendaring = None
        uid = None

        # First check for and add guid
        guidAttr = self.rdnSchema["guidAttr"]
        if guidAttr:
            guid = self._getUniqueLdapAttribute(attrs, guidAttr)

        # Find or build email
        emailAddresses = self._getMultipleLdapAttributes(attrs, "mail")
        emailSuffix = self.rdnSchema[recordType]["emailSuffix"]

        if len(emailAddresses) == 0 and emailSuffix is not None:
            emailPrefix = self._getUniqueLdapAttribute(attrs,
                self.rdnSchema[recordType]["attr"])
            emailAddresses.add(emailPrefix + emailSuffix)

        # LDAP attribute -> principal matchings
        shortNames = (self._getUniqueLdapAttribute(attrs, self.rdnSchema[recordType]["recordName"]),)
        if recordType == self.recordType_users:
            fullName = self._getUniqueLdapAttribute(attrs, "cn", "commonName",
                "displayName", "gecos")
            firstName = self._getUniqueLdapAttribute(attrs, "givenName")
            lastName = self._getUniqueLdapAttribute(attrs, "sn", "surname")
            calendarUserAddresses = emailAddresses
            enabledForCalendaring = True
        elif recordType == self.recordType_groups:
            fullName = self._getUniqueLdapAttribute(attrs, "cn")
            enabledForCalendaring = False
        elif recordType in (self.recordType_resources,
            self.recordType_locations):
            fullName = self._getUniqueLdapAttribute(attrs, "cn")
            calendarUserAddresses = emailAddresses
            enabledForCalendaring = True

        record = LdapDirectoryRecord(
            service                 = self,
            recordType              = recordType,
            guid                    = guid,
            shortNames              = shortNames,
            authIDs                 = authIDs,
            fullName                = fullName,
            firstName               = firstName,
            lastName                = lastName,
            emailAddresses          = emailAddresses,
            calendarUserAddresses   = calendarUserAddresses,
            enabledForCalendaring   = enabledForCalendaring,
            uid                     = uid,
            dn                      = dn,
            attrs                   = attrs,
        )

        # Look up augment information
        # TODO: this needs to be deferred but for now we hard code the
        # deferred result because we know it is completing immediately.
        d = self.augmentService.getAugmentRecord(record.guid,
            recordType)
        d.addCallback(lambda x:record.addAugmentInformation(x))

        return record


    def queryDirectory(self, recordTypes, indexType, indexKey):
        """
        Queries the LDAP directory for the record which has an attribute value
        matching the indexType and indexKey parameters.

        recordTypes is a list of record types to limit the search to.
        indexType specifies one of the CachingDirectoryService contstants
            identifying which attribute to search on.
        indexKey is the value to search for.

        Nothing is returned -- the resulting record (if any) is placed in
        the cache.
        """
        self.log_debug("LDAP query for types %s, indexType %s and indexKey %s"
            % (recordTypes, indexType, indexKey))

        for recordType in recordTypes:
            # Build base for this record Type
            base = self.typeRDNs[recordType] + self.base

            # Build filter
            filter = "(!(objectClass=organizationalUnit))"
            typeFilter = self.rdnSchema[recordType]["filter"]
            if typeFilter:
                filter = "(&%s%s)" % (filter, typeFilter)

            if indexType == self.INDEX_TYPE_GUID:
                # Query on guid only works if guid attribute has been defined.
                # Support for query on guid even if is auto-generated should
                # be added.
                guidAttr = self.rdnSchema["guidAttr"]
                if not guidAttr: return
                filter = "(&%s(%s=%s))" % (filter, guidAttr, indexKey)

            elif indexType == self.INDEX_TYPE_SHORTNAME:
                filter = "(&%s(%s=%s))" % (
                    filter,
                    self.rdnSchema[recordType]["recordName"],
                    indexKey
                )

            elif indexType == self.INDEX_TYPE_CUA:
                # indexKey is of the form "mailto:test@example.net"
                email = indexKey[7:] # strip "mailto:"
                emailSuffix = self.rdnSchema[recordType]["emailSuffix"]
                if emailSuffix is not None and email.partition("@")[2] == emailSuffix:
                    filter = "(&%s(|(&(!(mail=*))(%s=%s))(mail=%s)))" % (
                        filter,
                        self.rdnSchema[recordType]["attr"],
                        email.partition("@")[0],
                        email
                    )
                else:
                    filter = "(&%s(mail=%s))" % (filter, email)

            elif indexType == self.INDEX_TYPE_AUTHID:
                return

            # Query the LDAP server
            self.log_info("Retrieving ldap record with base %s and filter %s." %
                (ldap.dn.dn2str(base), filter))
            result = self.ldap.search_s(ldap.dn.dn2str(base),
                ldap.SCOPE_SUBTREE, filter, self.attrList)

            if result:
                dn, attrs = result.pop()

                unrestricted = True
                if self.restrictedGUIDs is not None:
                    guidAttr = self.rdnSchema["guidAttr"]
                    if guidAttr:
                        guid = self._getUniqueLdapAttribute(attrs, guidAttr)
                        if guid not in self.restrictedGUIDs:
                            unrestricted = False

                record = self._ldapResultToRecord(dn, attrs, recordType)
                self.log_debug("Got LDAP record %s" % (record,))
                self.recordCacheForType(recordType).addRecord(record,
                    indexType, indexKey
                )

                if not unrestricted:
                    self.log_debug("%s is not enabled because it's not a member of group: %s" % (guid, self.restrictToGroup))
                    record.enabledForCalendaring = False
                    record.enabledForAddressBooks = False

                record.applySACLs()

    def recordsMatchingFields(self, fields, operand="or", recordType=None):
        """
        Carries out the work of a principal-property-search against LDAP
        Returns a deferred list of directory records.
        """

        records = []

        recordTypes = [recordType] if recordType else self.recordTypes()
        for recordType in recordTypes:
            filter = buildFilter(self.attributeMapping, fields, operand=operand)

            if filter is not None:

                # Query the LDAP server
                base = self.typeRDNs[recordType] + self.base

                self.log_debug("LDAP search %s %s" %
                    (ldap.dn.dn2str(base), filter))
                results = self.ldap.search_s(ldap.dn.dn2str(base),
                    ldap.SCOPE_SUBTREE, filter, self.attrList)

                for dn, attrs in results:
                    # Skip if group restriction is in place and guid is not
                    # a member
                    if self.restrictedGUIDs is not None:
                        guidAttr = self.rdnSchema["guidAttr"]
                        if guidAttr:
                            guid = self._getUniqueLdapAttribute(attrs, guidAttr)
                            if guid not in self.restrictedGUIDs:
                                continue

                    record = self._ldapResultToRecord(dn, attrs, recordType)
                    records.append(record)

        return succeed(records)


def buildFilter(mapping, fields, operand="or"):
    """
    Create an LDAP filter string from a list of tuples representing directory
    attributes to search

    mapping is a dict mapping internal directory attribute names to ldap names.
    fields is a list of tuples...
        (directory field name, value to search, caseless (ignored), matchType)
    ...where matchType is one of "starts-with", "contains", "exact"
    """

    converted = []
    for field, value, caseless, matchType in fields:
        ldapField = mapping.get(field, None)
        if ldapField:
            if matchType == "starts-with":
                value = "%s*" % (value,)
            elif matchType == "contains":
                value = "*%s*" % (value,)
            # otherwise it's an exact match
            converted.append("(%s=%s)" % (ldapField, value))

    if len(converted) == 0:
        filter = None
    elif len(converted) == 1:
        filter = converted[0]
    else:
        operand = ("|" if operand == "or" else "&")
        filter = "(%s%s)" % (operand, "".join(converted))

    return filter


class LdapDirectoryRecord(CachingDirectoryRecord):
    """
    LDAP implementation of L{IDirectoryRecord}.
    """
    def __init__(
        self, service, recordType,
        guid, shortNames, authIDs, fullName,
        firstName, lastName, emailAddresses,
        calendarUserAddresses, enabledForCalendaring, uid,
        dn, attrs
    ):
        super(LdapDirectoryRecord, self).__init__(
            service               = service,
            recordType            = recordType,
            guid                  = guid,
            shortNames            = shortNames,
            authIDs               = authIDs,
            fullName              = fullName,
            firstName             = firstName,
            lastName              = lastName,
            emailAddresses        = emailAddresses,
            calendarUserAddresses = calendarUserAddresses,
            enabledForCalendaring = enabledForCalendaring,
            uid                   = uid,
        )

        # Save attributes of dn and attrs in case you might need them later
        self.dn = dn
        self.attrs = attrs

        # Identifiers of the members of this record if it is a group
        membersAttrs = []
        if self.service.groupSchema["membersAttr"]:
            membersAttrs.append(self.service.groupSchema["membersAttr"])
        if self.service.groupSchema["nestedGroupsAttr"]:
            membersAttrs.append(self.service.groupSchema["nestedGroupsAttr"])
        self._memberIds = self.service._getMultipleLdapAttributes(attrs,
            *membersAttrs)

        # Identifier of this record as a group member
        memberIdAttr = self.service.groupSchema["memberIdAttr"]
        if memberIdAttr:
            self._memberId = self.service._getUniqueLdapAttribute(attrs,
                memberIdAttr)
        else:
            self._memberId = self.dn


    def members(self):
        """ Return the records representing members of this group """

        try:
            return self._members_storage
        except AttributeError:
            self._members_storage = self._members()
            return self._members_storage

    def _members(self):
        """ Fault in records for the members of this group """

        memberIdAttr = self.service.groupSchema["memberIdAttr"]
        results = []

        for memberId in self._memberIds:

            for recordType in self.service.recordTypes():

                if memberIdAttr:
                    base = self.service.base
                    filter = "(%s=%s)" % (memberIdAttr, memberId)
                    self.log_debug("Retrieving subtree of %s with filter %s" %
                        (ldap.dn.dn2str(base), filter),
                        system="LdapDirectoryService")
                    result = self.service.ldap.search_s(ldap.dn.dn2str(base),
                        ldap.SCOPE_SUBTREE, filter, self.service.attrList)

                else:
                    self.log_debug("Retrieving %s." % memberId,
                        system="LdapDirectoryService")
                    result = self.service.ldap.search_s(memberId,
                        ldap.SCOPE_BASE, attrlist=self.service.attrList)

                if result:
                    # TODO: what about duplicates?

                    dn, attrs = result.pop()

                    if recordType == self.service.recordType_users:
                        shortName = self.service._getUniqueLdapAttribute(attrs,
                            "uid", "userid")
                    elif recordType in (
                        self.service.recordType_groups,
                        self.service.recordType_resources,
                        self.service.recordType_locations
                    ):
                        shortName = self.service._getUniqueLdapAttribute(attrs,
                            "cn")

                    record = self.service.recordWithShortName(recordType,
                        shortName)
                    if record:
                        results.append(record)
                        break

        return results

    def groups(self):
        """ Return the records representing groups this record is a member of """
        try:
            return self._groups_storage
        except AttributeError:
            self._groups_storage = self._groups()
            return self._groups_storage

    def _groups(self):
        """ Fault in the groups of which this record is a member """

        recordType = self.service.recordType_groups
        base = self.service.typeRDNs[recordType] + self.service.base

        membersAttrs = []
        if self.service.groupSchema["membersAttr"]:
            membersAttrs.append(self.service.groupSchema["membersAttr"])
        if self.service.groupSchema["nestedGroupsAttr"]:
            membersAttrs.append(self.service.groupSchema["nestedGroupsAttr"])

        if len(membersAttrs) == 1:
            filter = "(%s=%s)" % (membersAttrs[0], self._memberId)
        else:
            filter = "(|%s)" % ( "".join(
                    ["(%s=%s)" % (a, self._memberId) for a in membersAttrs]
                ),
            )
        self.log_debug("Finding groups containing %s" % (self._memberId,))
        groups = []

        try:
            results = self.service.ldap.search_s(ldap.dn.dn2str(base),
                ldap.SCOPE_SUBTREE, filter, self.service.attrList)

            for dn, attrs in results:
                shortName = self.service._getUniqueLdapAttribute(attrs, "cn")
                self.log_debug("%s is a member of %s" % (self._memberId, shortName))
                groups.append(self.service.recordWithShortName(recordType,
                    shortName))
        except ldap.PROTOCOL_ERROR, e:
            self.log_warn(str(e))

        return groups


    def verifyCredentials(self, credentials):
        """ Supports PAM or simple LDAP bind for username+password """

        if isinstance(credentials, UsernamePassword):

            # TODO: investigate:
            # Check that the username supplied matches one of the shortNames
            # (The DCS might already enforce this constraint, not sure)
            if credentials.username not in self.shortNames:
                return False

            # Check cached password
            try:
                if credentials.password == self.password:
                    return True
            except AttributeError:
                pass

            if self.service.authMethod.upper() == "PAM":
                # Authenticate against PAM (UNTESTED)

                if not pamAvailable:
                    msg = "PAM module is not installed"
                    self.log_error(msg)
                    raise DirectoryConfigurationError(msg)

                def pam_conv(auth, query_list, userData):
                    return [(credentials.password, 0)]

                auth = PAM.pam()
                auth.start("caldav")
                auth.set_item(PAM.PAM_USER, credentials.username)
                auth.set_item(PAM.PAM_CONV, pam_conv)
                try:
                    auth.authenticate()
                except PAM.error:
                    return False
                else:
                    # Cache the password to avoid further LDAP queries
                    self.password = credentials.password
                    return True

            elif self.service.authMethod.upper() == "LDAP":

                # Authenticate against LDAP
                try:
                    self.service.authenticate(self.dn, credentials.password)
                    # Cache the password to avoid further LDAP queries
                    self.password = credentials.password
                    return True

                except ldap.INVALID_CREDENTIALS:
                    self.log_info("Invalid credentials for %s" %
                        (repr(self.dn),), system="LdapDirectoryService")
                    return False

            else:
                msg = "Unknown Authentication Method '%s'" % (
                    self.service.authMethod.upper(),)
                self.log_error(msg)
                raise DirectoryConfigurationError(msg)

        return super(LdapDirectoryRecord, self).verifyCredentials(credentials)
