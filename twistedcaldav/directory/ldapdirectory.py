##
# Copyright (c) 2008-2009 Aymeric Augustin. All rights reserved.
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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

import ldap, ldap.async
from ldap.filter import escape_filter_chars as ldapEsc

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
from twistedcaldav.directory.directory import DirectoryConfigurationError
from twistedcaldav.directory.augment import AugmentRecord
from twistedcaldav.directory.util import splitIntoBatches, normalizeUUID
from twisted.internet.defer import succeed, inlineCallbacks, returnValue
from twisted.internet.threads import deferToThread
from twext.python.log import Logger
from twext.web2.http import HTTPError, StatusResponse
from twext.web2 import responsecode

class LdapDirectoryService(CachingDirectoryService):
    """
    LDAP based implementation of L{IDirectoryService}.
    """
    log = Logger()

    baseGUID = "5A871574-0C86-44EE-B11B-B9440C3DC4DD"

    def __repr__(self):
        return "<%s %r: %r>" % (self.__class__.__name__, self.realmName,
            self.uri)

    def __init__(self, params):
        """
        @param params: a dictionary containing the following keys:
            cacheTimeout, realmName, uri, tls, tlsCACertFile, tlsCACertDir,
            tlsRequireCert, credentials, rdnSchema, groupSchema, resourceSchema
            partitionSchema
        """

        defaults = {
            "augmentService" : None,
            "groupMembershipCache" : None,
            "cacheTimeout": 1, # Minutes
            "negativeCaching": False,
            "warningThresholdSeconds": 3,
            "batchSize": 500, # for splitting up large queries
            "requestTimeoutSeconds" : 10,
            "requestResultsLimit" : 200,
            "optimizeMultiName" : False,
            "queryLocationsImplicitly": True,
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
                "guidAttr": "entryUUID",
                "users": {
                    "rdn": "ou=People",
                    "attr": "uid", # used only to synthesize email address
                    "emailSuffix": None, # used only to synthesize email address
                    "filter": None, # additional filter for this type
                    "loginEnabledAttr" : "", # attribute controlling login
                    "loginEnabledValue" : "yes", # "True" value of above attribute
                    "calendarEnabledAttr" : "", # attribute controlling enabledForCalendaring
                    "calendarEnabledValue" : "yes", # "True" value of above attribute
                    "mapping" : { # maps internal record names to LDAP
                        "recordName": "uid",
                        "fullName" : "cn",
                        "emailAddresses" : ["mail"], # multiple LDAP fields supported
                        "firstName" : "givenName",
                        "lastName" : "sn",
                    },
                },
                "groups": {
                    "rdn": "ou=Group",
                    "attr": "cn", # used only to synthesize email address
                    "emailSuffix": None, # used only to synthesize email address
                    "filter": None, # additional filter for this type
                    "mapping" : { # maps internal record names to LDAP
                        "recordName": "cn",
                        "fullName" : "cn",
                        "emailAddresses" : ["mail"], # multiple LDAP fields supported
                        "firstName" : "givenName",
                        "lastName" : "sn",
                    },
                },
                "locations": {
                    "rdn": "ou=Places",
                    "attr": "cn", # used only to synthesize email address
                    "emailSuffix": None, # used only to synthesize email address
                    "filter": None, # additional filter for this type
                    "calendarEnabledAttr" : "", # attribute controlling enabledForCalendaring
                    "calendarEnabledValue" : "yes", # "True" value of above attribute
                    "mapping" : { # maps internal record names to LDAP
                        "recordName": "cn",
                        "fullName" : "cn",
                        "emailAddresses" : ["mail"], # multiple LDAP fields supported
                        "firstName" : "givenName",
                        "lastName" : "sn",
                    },
                },
                "resources": {
                    "rdn": "ou=Resources",
                    "attr": "cn", # used only to synthesize email address
                    "emailSuffix": None, # used only to synthesize email address
                    "filter": None, # additional filter for this type
                    "calendarEnabledAttr" : "", # attribute controlling enabledForCalendaring
                    "calendarEnabledValue" : "yes", # "True" value of above attribute
                    "mapping" : { # maps internal record names to LDAP
                        "recordName": "cn",
                        "fullName" : "cn",
                        "emailAddresses" : ["mail"], # multiple LDAP fields supported
                        "firstName" : "givenName",
                        "lastName" : "sn",
                    },
                },
            },
            "groupSchema": {
                "membersAttr": "member", # how members are specified
                "nestedGroupsAttr": None, # how nested groups are specified
                "memberIdAttr": None, # which attribute the above refer to (None means use DN)
            },
            "resourceSchema": {
                # Either set this attribute to retrieve the plist version
                # of resource-info, as in a Leopard OD server, or...
                "resourceInfoAttr": None,
                # ...set the above to None and instead specify these
                # individually:
                "autoScheduleAttr": None,
                "autoScheduleEnabledValue": "yes",
                "proxyAttr": None, # list of GUIDs
                "readOnlyProxyAttr": None, # list of GUIDs
                "autoAcceptGroupAttr": None, # single group GUID
            },
            "partitionSchema": {
                "serverIdAttr": None, # maps to augments server-id
                "partitionIdAttr": None, # maps to augments partition-id
            },
        }
        ignored = None
        params = self.getParams(params, defaults, ignored)

        self._recordTypes = params["recordTypes"]

        super(LdapDirectoryService, self).__init__(params["cacheTimeout"],
                                                   params["negativeCaching"])

        self.warningThresholdSeconds = params["warningThresholdSeconds"]
        self.batchSize = params["batchSize"]
        self.requestTimeoutSeconds = params["requestTimeoutSeconds"]
        self.requestResultsLimit = params["requestResultsLimit"]
        self.optimizeMultiName = params["optimizeMultiName"]
        if self.batchSize > self.requestResultsLimit:
            self.batchSize = self.requestResultsLimit
        self.queryLocationsImplicitly = params["queryLocationsImplicitly"]
        self.augmentService = params["augmentService"]
        self.groupMembershipCache = params["groupMembershipCache"]
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
        self.resourceSchema = params["resourceSchema"]
        self.partitionSchema = params["partitionSchema"]

        self.base = ldap.dn.str2dn(self.rdnSchema["base"])

        # Certain attributes (such as entryUUID) may be hidden and not
        # returned by default when queried for all attributes. Therefore it is
        # necessary to explicitly pass all the possible attributes list
        # for ldap searches.  Dynamically build the attribute list based on
        # config.
        attrSet = set()

        if self.rdnSchema["guidAttr"]:
            attrSet.add(self.rdnSchema["guidAttr"])
        for recordType in self.recordTypes():
            if self.rdnSchema[recordType]["attr"]:
                attrSet.add(self.rdnSchema[recordType]["attr"])
            if self.rdnSchema[recordType].get("calendarEnabledAttr", False):
                attrSet.add(self.rdnSchema[recordType]["calendarEnabledAttr"])
            for attrList in self.rdnSchema[recordType]["mapping"].values():
                if attrList:
                    # Since emailAddresses can map to multiple LDAP fields,
                    # support either string or list
                    if isinstance(attrList, str):
                        attrList = [attrList]
                    for attr in attrList:
                        attrSet.add(attr)
            # Also put the guidAttr attribute into the mappings for each type
            # so recordsMatchingFields can query on guid
            self.rdnSchema[recordType]["mapping"]["guid"] = self.rdnSchema["guidAttr"]
            # Also put the memberIdAttr attribute into the mappings for each type
            # so recordsMatchingFields can query on memberIdAttr
            self.rdnSchema[recordType]["mapping"]["memberIdAttr"] = self.groupSchema["memberIdAttr"]
        if self.groupSchema["membersAttr"]:
            attrSet.add(self.groupSchema["membersAttr"])
        if self.groupSchema["nestedGroupsAttr"]:
            attrSet.add(self.groupSchema["nestedGroupsAttr"])
        if self.groupSchema["memberIdAttr"]:
            attrSet.add(self.groupSchema["memberIdAttr"])
        if self.rdnSchema["users"]["loginEnabledAttr"]:
            attrSet.add(self.rdnSchema["users"]["loginEnabledAttr"])
        if self.resourceSchema["resourceInfoAttr"]:
            attrSet.add(self.resourceSchema["resourceInfoAttr"])
        if self.resourceSchema["autoScheduleAttr"]:
            attrSet.add(self.resourceSchema["autoScheduleAttr"])
        if self.resourceSchema["autoAcceptGroupAttr"]:
            attrSet.add(self.resourceSchema["autoAcceptGroupAttr"])
        if self.resourceSchema["proxyAttr"]:
            attrSet.add(self.resourceSchema["proxyAttr"])
        if self.resourceSchema["readOnlyProxyAttr"]:
            attrSet.add(self.resourceSchema["readOnlyProxyAttr"])
        if self.partitionSchema["serverIdAttr"]:
            attrSet.add(self.partitionSchema["serverIdAttr"])
        if self.partitionSchema["partitionIdAttr"]:
            attrSet.add(self.partitionSchema["partitionIdAttr"])
        self.attrlist = list(attrSet)

        self.typeDNs = {}
        for recordType in self.recordTypes():
            self.typeDNs[recordType] = ldap.dn.str2dn(
                self.rdnSchema[recordType]["rdn"].lower()
            ) + self.base


        self.ldap = None


        # Separate LDAP connection used solely for authenticating clients
        self.authLDAP = None

        # Restricting access by directory group
        self.restrictEnabledRecords = params['restrictEnabledRecords']
        self.restrictToGroup = params['restrictToGroup']
        self.restrictedTimestamp = 0


    def recordTypes(self):
        return self._recordTypes


    def listRecords(self, recordType):

        # Build base for this record Type
        base = self.typeDNs[recordType]

        # Build filter
        filterstr = "(!(objectClass=organizationalUnit))"
        typeFilter = self.rdnSchema[recordType]["filter"]
        if typeFilter:
            filterstr = "(&%s%s)" % (filterstr, typeFilter)

        # Query the LDAP server
        self.log.debug("Querying ldap for records matching base {base} and "
            "filter {filter} for attributes {attrs}.", 
            base=ldap.dn.dn2str(base), filter=filterstr, attrs=self.attrlist)

        # This takes a while, so if you don't want to have a "long request"
        # warning logged, use this instead of timedSearch:
        # results = self.ldap.search_s(ldap.dn.dn2str(base),
        #     ldap.SCOPE_SUBTREE, filterstr=filterstr, attrlist=self.attrlist)
        results = self.timedSearch(ldap.dn.dn2str(base),
            ldap.SCOPE_SUBTREE, filterstr=filterstr, attrlist=self.attrlist)

        records = []
        numMissingGuids = 0
        guidAttr = self.rdnSchema["guidAttr"]
        for dn, attrs in results:
            dn = normalizeDNstr(dn)

            unrestricted = self.isAllowedByRestrictToGroup(dn, attrs)

            try:
                record = self._ldapResultToRecord(dn, attrs, recordType)
                # self.log.debug("Got LDAP record {record}", record=record)
            except MissingGuidException:
                numMissingGuids += 1
                continue

            if not unrestricted:
                self.log.debug("{dn} is not enabled because it's not a member of group: {group}",
                    dn=dn, group=self.restrictToGroup)
                record.enabledForCalendaring = False
                record.enabledForAddressBooks = False

            records.append(record)

        if numMissingGuids:
            self.log.info("{num} {recordType} records are missing {attr}",
                num=numMissingGuids, recordType=recordType, attr=guidAttr)

        return records

    @inlineCallbacks
    def recordWithCachedGroupsAlias(self, recordType, alias):
        """
        @param recordType: the type of the record to look up.
        @param alias: the cached-groups alias of the record to look up.
        @type alias: C{str}

        @return: a deferred L{IDirectoryRecord} with the given cached-groups
            alias, or C{None} if no such record is found.
        """
        memberIdAttr = self.groupSchema["memberIdAttr"]
        attributeToSearch = "memberIdAttr" if memberIdAttr else "dn"

        fields = [[attributeToSearch, alias, False, "equals"]]
        results = (yield self.recordsMatchingFields(fields, recordType=recordType))
        if results:
            returnValue(results[0])
        else:
            returnValue(None)

    def getExternalProxyAssignments(self):
        """
        Retrieve proxy assignments for locations and resources from the
        directory and return a list of (principalUID, ([memberUIDs)) tuples,
        suitable for passing to proxyDB.setGroupMembers( )
        """
        assignments = []

        guidAttr = self.rdnSchema["guidAttr"]
        readAttr = self.resourceSchema["readOnlyProxyAttr"]
        writeAttr = self.resourceSchema["proxyAttr"]
        if not (guidAttr and readAttr and writeAttr):
            self.log.error("LDAP configuration requires guidAttr, proxyAttr, and readOnlyProxyAttr in order to use external proxy assignments efficiently; falling back to slower method")
            # Fall back to the less-specialized version
            return super(LdapDirectoryService, self).getExternalProxyAssignments()

        # Build filter
        filterstr = "(|(%s=*)(%s=*))" % (readAttr, writeAttr)
        # ...taking into account only calendar-enabled records
        enabledAttr = self.rdnSchema["locations"]["calendarEnabledAttr"]
        enabledValue = self.rdnSchema["locations"]["calendarEnabledValue"]
        if enabledAttr and enabledValue:
            filterstr = "(&(%s=%s)%s)" % (enabledAttr, enabledValue, filterstr)

        attrlist = [guidAttr, readAttr, writeAttr]

        # Query the LDAP server
        self.log.debug("Querying ldap for records matching base {base} and "
            "filter {filter} for attributes {attrs}.",
            base=ldap.dn.dn2str(self.base), filter=filterstr, attrs=attrlist)

        results = self.timedSearch(ldap.dn.dn2str(self.base),
            ldap.SCOPE_SUBTREE, filterstr=filterstr, attrlist=attrlist)

        for dn, attrs in results:
            dn = normalizeDNstr(dn)
            guid = self._getUniqueLdapAttribute(attrs, guidAttr)
            if guid:
                guid = normalizeUUID(guid)
                readDelegate = self._getUniqueLdapAttribute(attrs, readAttr)
                if readDelegate:
                    readDelegate = normalizeUUID(readDelegate)
                    assignments.append(("%s#calendar-proxy-read" % (guid,),
                        [readDelegate]))
                writeDelegate = self._getUniqueLdapAttribute(attrs, writeAttr)
                if writeDelegate:
                    writeDelegate = normalizeUUID(writeDelegate)
                    assignments.append(("%s#calendar-proxy-write" % (guid,),
                        [writeDelegate]))

        return assignments

    def getLDAPConnection(self):
        if self.ldap is None:
            self.log.info("Connecting to LDAP {uri}", uri=repr(self.uri))
            self.ldap = self.createLDAPConnection()
            self.log.info("Connection established to LDAP {uri}", uri=repr(self.uri))
            if self.credentials.get("dn", ""):
                try:
                    self.log.info("Binding to LDAP {dn}",
                        dn=repr(self.credentials.get("dn")))
                    self.ldap.simple_bind_s(self.credentials.get("dn"),
                        self.credentials.get("password"))
                    self.log.info("Successfully authenticated with LDAP as {dn}",
                        dn=repr(self.credentials.get("dn")))
                except ldap.INVALID_CREDENTIALS:
                    self.log.error("Can't bind to LDAP {uri}: check credentials", uri=self.uri)
                    raise DirectoryConfigurationError()
        return self.ldap

    def createLDAPConnection(self):
        """
        Create and configure LDAP connection
        """
        cxn = ldap.initialize(self.uri)

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
        TRIES = 3

        for i in xrange(TRIES):
            self.log.debug("Authenticating %s" % (dn,))

            if self.authLDAP is None:
                self.log.debug("Creating authentication connection to LDAP")
                self.authLDAP = self.createLDAPConnection()

            try:
                startTime = time.time()
                self.authLDAP.simple_bind_s(dn, password)
                # Getting here means success, so break the retry loop
                break

            except ldap.INAPPROPRIATE_AUTH:
                # Seen when using an empty password, treat as invalid creds
                raise ldap.INVALID_CREDENTIALS()

            except ldap.NO_SUCH_OBJECT:
                self.log.error("LDAP Authentication error for %s: NO_SUCH_OBJECT"
                    % (dn,))
                # fall through to try again; could be transient

            except ldap.INVALID_CREDENTIALS:
                raise

            except ldap.SERVER_DOWN:
                self.log.error("Lost connection to LDAP server.")
                self.authLDAP = None
                # Fall through and retry if TRIES has been reached

            except Exception, e:
                self.log.error("LDAP authentication failed with %s." % (e,))
                raise

            finally:
                totalTime = time.time() - startTime
                if totalTime > self.warningThresholdSeconds:
                    self.log.error("LDAP auth exceeded threshold: %.2f seconds for %s" % (totalTime, dn))

        else:
            self.log.error("Giving up on LDAP authentication after %d tries.  Responding with 503." % (TRIES,))
            raise HTTPError(StatusResponse(responsecode.SERVICE_UNAVAILABLE, "LDAP server unavailable"))

        self.log.debug("Authentication succeeded for %s" % (dn,))


    def timedSearch(self, base, scope, filterstr="(objectClass=*)",
        attrlist=None, timeoutSeconds=-1, resultLimit=0):
        """
        Execute an LDAP query, retrying up to 3 times in case the LDAP server has
        gone down and we need to reconnect. If it takes longer than the configured
        threshold, emit a log error.
        The number of records requested is controlled by resultLimit (0=no limit).
        If timeoutSeconds is not -1, the query will abort after the specified number
        of seconds and the results retrieved so far are returned.
        """
        TRIES = 3

        for i in xrange(TRIES):
            try:
                s = ldap.async.List(self.getLDAPConnection())
                s.startSearch(base, scope, filterstr, attrList=attrlist,
                    timeout=timeoutSeconds,
                    sizelimit=resultLimit)
                startTime = time.time()
                s.processResults()
            except ldap.NO_SUCH_OBJECT:
                return []
            except ldap.FILTER_ERROR, e:
                self.log.error("LDAP filter error: %s %s" % (e, filterstr))
                return []
            except ldap.SIZELIMIT_EXCEEDED, e:
                self.log.debug("LDAP result limit exceeded: %d" % (resultLimit,))
            except ldap.TIMELIMIT_EXCEEDED, e:
                self.log.warn("LDAP timeout exceeded: %d seconds" % (timeoutSeconds,))
            except ldap.SERVER_DOWN:
                self.ldap = None
                self.log.error("LDAP server unavailable (tried %d times)" % (i+1,))
                continue

            # change format, ignoring resultsType
            result = [resultItem for resultType, resultItem in s.allResults]

            totalTime = time.time() - startTime
            if totalTime > self.warningThresholdSeconds:
                if filterstr and len(filterstr) > 100:
                    filterstr = "%s..." % (filterstr[:100],)
                self.log.error("LDAP query exceeded threshold: %.2f seconds for %s %s %s (#results=%d)" %
                    (totalTime, base, filterstr, attrlist, len(result)))
            return result

        raise HTTPError(StatusResponse(responsecode.SERVICE_UNAVAILABLE, "LDAP server unavailable"))


    def isAllowedByRestrictToGroup(self, dn, attrs):
        """
        Check to see if the principal with the given DN and LDAP attributes is
        a member of the restrictToGroup.

        @param dn: an LDAP dn
        @type dn: C{str}
        @param attrs: LDAP attributes
        @type attrs: C{dict}
        @return: True if principal is in the group (or restrictEnabledRecords if turned off).
        @rtype: C{boolean}
        """
        if not self.restrictEnabledRecords:
            return True
        if self.groupSchema["memberIdAttr"]:
            value = self._getUniqueLdapAttribute(attrs, self.groupSchema["memberIdAttr"])
        else: # No memberIdAttr implies DN
            value = dn
        return value in self.restrictedPrincipals


    @property
    def restrictedPrincipals(self):
        """
        Look up (and cache) the set of guids that are members of the
        restrictToGroup.  If restrictToGroup is not set, return None to
        indicate there are no group restrictions.
        """
        if self.restrictEnabledRecords:

            if time.time() - self.restrictedTimestamp > self.cacheTimeout:
                # fault in the members of group of name self.restrictToGroup
                recordType = self.recordType_groups
                base = self.typeDNs[recordType]
                # TODO: This shouldn't be hardcoded to cn
                filterstr = "(cn=%s)" % (self.restrictToGroup,)
                self.log.debug("Retrieving ldap record with base %s and filter %s." %
                    (ldap.dn.dn2str(base), filterstr))
                result = self.timedSearch(ldap.dn.dn2str(base),
                    ldap.SCOPE_SUBTREE, filterstr=filterstr, attrlist=self.attrlist)

                members = []
                nestedGroups = []

                if len(result) == 1:
                    dn, attrs = result[0]
                    dn = normalizeDNstr(dn)
                    if self.groupSchema["membersAttr"]:
                        members = self._getMultipleLdapAttributes(attrs,
                            self.groupSchema["membersAttr"])
                        if not self.groupSchema["memberIdAttr"]: # these are DNs
                            members = [normalizeDNstr(m) for m in members]
                        members = set(members)

                    if self.groupSchema["nestedGroupsAttr"]:
                        nestedGroups = self._getMultipleLdapAttributes(attrs,
                            self.groupSchema["nestedGroupsAttr"])
                        if not self.groupSchema["memberIdAttr"]: # these are DNs
                            nestedGroups = [normalizeDNstr(g) for g in nestedGroups]
                        nestedGroups = set(nestedGroups)
                    else:
                        # Since all members are lumped into the same attribute,
                        # treat them all as nestedGroups instead
                        nestedGroups = members
                        members = set()

                self._cachedRestrictedPrincipals = set(self._expandGroupMembership(members,
                    nestedGroups))
                self.log.info("Got %d restricted group members" % (
                    len(self._cachedRestrictedPrincipals),))
                self.restrictedTimestamp = time.time()
            return self._cachedRestrictedPrincipals
        else:
            # No restrictions
            return None


    def _expandGroupMembership(self, members, nestedGroups, processedItems=None):
        """
        A generator which recursively yields principals which are included within nestedGroups

        @param members:  If the LDAP service is configured to use different attributes to
            indicate member users and member nested groups, members will include the non-groups.
            Otherwise, members will be empty and only nestedGroups will be used.
        @type members: C{set}
        @param nestedGroups:  If the LDAP service is configured to use different attributes to
            indicate member users and member nested groups, nestedGroups will include only
            the groups; otherwise nestedGroups will include all members
        @type members: C{set}
        @param processedItems: The set of members that have already been looked up in LDAP
            so the code doesn't have to look up the same member twice or get stuck in a
            membership loop.
        @type processedItems: C{set}
        @return: All members of the group, the values will correspond to memberIdAttr
            if memberIdAttr is set in the group schema, or DNs otherwise.
        @rtype: generator of C{str}
        """

        if processedItems is None:
            processedItems = set()

        if isinstance(members, str):
            members = [members]

        if isinstance(nestedGroups, str):
            nestedGroups = [nestedGroups]

        for member in members:
            if member not in processedItems:
                processedItems.add(member)
                yield member

        for group in nestedGroups:
            if group in processedItems:
                continue

            recordType = self.recordType_groups
            base = self.typeDNs[recordType]
            if self.groupSchema["memberIdAttr"]:
                scope = ldap.SCOPE_SUBTREE
                base = self.typeDNs[recordType]
                filterstr = "(%s=%s)" % (self.groupSchema["memberIdAttr"], group)
            else: # Use DN
                scope = ldap.SCOPE_BASE
                base = ldap.dn.str2dn(group)
                filterstr = "(objectClass=*)"

            self.log.debug("Retrieving ldap record with base %s and filter %s." %
                (ldap.dn.dn2str(base), filterstr))
            result = self.timedSearch(ldap.dn.dn2str(base),
                scope, filterstr=filterstr, attrlist=self.attrlist)

            if len(result) == 0:
                continue

            subMembers = set()
            subNestedGroups = set()
            if len(result) == 1:
                dn, attrs = result[0]
                dn = normalizeDNstr(dn)
                if self.groupSchema["membersAttr"]:
                    subMembers = self._getMultipleLdapAttributes(attrs,
                        self.groupSchema["membersAttr"])
                    if not self.groupSchema["memberIdAttr"]: # these are DNs
                        subMembers = [normalizeDNstr(m) for m in subMembers]
                    subMembers = set(subMembers)

                if self.groupSchema["nestedGroupsAttr"]:
                    subNestedGroups = self._getMultipleLdapAttributes(attrs,
                        self.groupSchema["nestedGroupsAttr"])
                    if not self.groupSchema["memberIdAttr"]: # these are DNs
                        subNestedGroups = [normalizeDNstr(g) for g in subNestedGroups]
                    subNestedGroups = set(subNestedGroups)

            processedItems.add(group)
            yield group

            for item in self._expandGroupMembership(subMembers, subNestedGroups,
                processedItems):
                yield item


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
            if key:
                values = attrs.get(key)
                if values is not None:
                    results += values
        return results


    def _ldapResultToRecord(self, dn, attrs, recordType):
        """
        Convert the attrs returned by a LDAP search into a LdapDirectoryRecord
        object.

        If guidAttr was specified in the config but is missing from attrs,
        raises MissingGuidException
        """

        guid = None
        shortNames = ()
        authIDs = set()
        fullName = None
        firstName = ""
        lastName = ""
        emailAddresses = set()
        enabledForCalendaring = None
        enabledForAddressBooks = None
        uid = None
        enabledForLogin = True

        shortNames = tuple(self._getMultipleLdapAttributes(attrs, self.rdnSchema[recordType]["mapping"]["recordName"]))
        if not shortNames:
            raise MissingRecordNameException()

        # First check for and add guid
        guidAttr = self.rdnSchema["guidAttr"]
        if guidAttr:
            guid = self._getUniqueLdapAttribute(attrs, guidAttr)
            if not guid:
                self.log.debug("LDAP data for %s is missing guid attribute %s" % (shortNames, guidAttr))
                raise MissingGuidException()
            guid = normalizeUUID(guid)

        # Find or build email
        # (The emailAddresses mapping is a list of ldap fields)
        emailAddressesMappedTo = self.rdnSchema[recordType]["mapping"]["emailAddresses"]
        # Supporting either string or list for emailAddresses:
        if isinstance(emailAddressesMappedTo, str):
            emailAddresses = set(self._getMultipleLdapAttributes(attrs, self.rdnSchema[recordType]["mapping"]["emailAddresses"]))
        else:
            emailAddresses = set(self._getMultipleLdapAttributes(attrs, *self.rdnSchema[recordType]["mapping"]["emailAddresses"]))
        emailSuffix = self.rdnSchema[recordType]["emailSuffix"]

        if len(emailAddresses) == 0 and emailSuffix:
            emailPrefix = self._getUniqueLdapAttribute(attrs,
                self.rdnSchema[recordType]["attr"])
            emailAddresses.add(emailPrefix + emailSuffix)

        proxyGUIDs = ()
        readOnlyProxyGUIDs = ()
        autoSchedule = False
        autoAcceptGroup = ""
        memberGUIDs = []

        # LDAP attribute -> principal matchings
        if recordType == self.recordType_users:
            fullName = self._getUniqueLdapAttribute(attrs, self.rdnSchema[recordType]["mapping"]["fullName"])
            firstName = self._getUniqueLdapAttribute(attrs, self.rdnSchema[recordType]["mapping"]["firstName"])
            lastName = self._getUniqueLdapAttribute(attrs, self.rdnSchema[recordType]["mapping"]["lastName"])
            enabledForCalendaring = True
            enabledForAddressBooks = True

        elif recordType == self.recordType_groups:
            fullName = self._getUniqueLdapAttribute(attrs, self.rdnSchema[recordType]["mapping"]["fullName"])
            enabledForCalendaring = False
            enabledForAddressBooks = False
            enabledForLogin = False

            if self.groupSchema["membersAttr"]:
                members = self._getMultipleLdapAttributes(attrs, self.groupSchema["membersAttr"])
                memberGUIDs.extend(members)
            if self.groupSchema["nestedGroupsAttr"]:
                members = self._getMultipleLdapAttributes(attrs, self.groupSchema["nestedGroupsAttr"])
                memberGUIDs.extend(members)

            # Normalize members if they're in DN form
            if not self.groupSchema["memberIdAttr"]: # empty = dn
                guids = list(memberGUIDs)
                memberGUIDs = []
                for dnStr in guids:
                    try:
                        dnStr = normalizeDNstr(dnStr)
                        memberGUIDs.append(dnStr)
                    except Exception, e:
                        # LDAP returned an illegal DN value, log and ignore it
                        self.log.warn("Bad LDAP DN: %s" % (dnStr,))

        elif recordType in (self.recordType_resources,
            self.recordType_locations):
            fullName = self._getUniqueLdapAttribute(attrs, self.rdnSchema[recordType]["mapping"]["fullName"])
            enabledForCalendaring = True
            enabledForAddressBooks = False
            enabledForLogin = False
            if self.resourceSchema["resourceInfoAttr"]:
                resourceInfo = self._getUniqueLdapAttribute(attrs,
                    self.resourceSchema["resourceInfoAttr"])
                if resourceInfo:
                    try:
                        (
                            autoSchedule,
                            proxy,
                            readOnlyProxy,
                            autoAcceptGroup
                        ) = self.parseResourceInfo(
                            resourceInfo,
                            guid,
                            recordType,
                            shortNames[0]
                        )
                        if proxy:
                            proxyGUIDs = (proxy,)
                        if readOnlyProxy:
                            readOnlyProxyGUIDs = (readOnlyProxy,)
                    except ValueError, e:
                        self.log.error("Unable to parse resource info (%s)" % (e,))
            else: # the individual resource attributes might be specified
                if self.resourceSchema["autoScheduleAttr"]:
                    autoScheduleValue = self._getUniqueLdapAttribute(attrs,
                        self.resourceSchema["autoScheduleAttr"])
                    autoSchedule = (autoScheduleValue ==
                        self.resourceSchema["autoScheduleEnabledValue"])
                if self.resourceSchema["proxyAttr"]:
                    proxyGUIDs = set(self._getMultipleLdapAttributes(attrs,
                        self.resourceSchema["proxyAttr"]))
                if self.resourceSchema["readOnlyProxyAttr"]:
                    readOnlyProxyGUIDs = set(self._getMultipleLdapAttributes(attrs,
                        self.resourceSchema["readOnlyProxyAttr"]))
                if self.resourceSchema["autoAcceptGroupAttr"]:
                    autoAcceptGroup = self._getUniqueLdapAttribute(attrs,
                        self.resourceSchema["autoAcceptGroupAttr"])

        serverID = partitionID = None
        if self.partitionSchema["serverIdAttr"]:
            serverID = self._getUniqueLdapAttribute(attrs,
                self.partitionSchema["serverIdAttr"])
        if self.partitionSchema["partitionIdAttr"]:
            partitionID = self._getUniqueLdapAttribute(attrs,
                self.partitionSchema["partitionIdAttr"])

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
            uid                     = uid,
            dn                      = dn,
            memberGUIDs             = memberGUIDs,
            extProxies              = proxyGUIDs,
            extReadOnlyProxies      = readOnlyProxyGUIDs,
            attrs                   = attrs,
        )

        if self.augmentService is not None:
            # Look up augment information
            # TODO: this needs to be deferred but for now we hard code
            # the deferred result because we know it is completing
            # immediately.
            d = self.augmentService.getAugmentRecord(record.guid,
                recordType)
            d.addCallback(lambda x:record.addAugmentInformation(x))

        else:
            # Generate augment record based on information retrieved from LDAP
            augmentRecord = AugmentRecord(
                guid,
                enabled=True,
                serverID=serverID,
                partitionID=partitionID,
                enabledForCalendaring=enabledForCalendaring,
                autoSchedule=autoSchedule,
                autoAcceptGroup=autoAcceptGroup,
                enabledForAddressBooks=enabledForAddressBooks, # TODO: add to LDAP?
                enabledForLogin=enabledForLogin,
            )
            record.addAugmentInformation(augmentRecord)

        # Override with LDAP login control if attribute specified
        if recordType == self.recordType_users:
            loginEnabledAttr = self.rdnSchema[recordType]["loginEnabledAttr"]
            if loginEnabledAttr:
                loginEnabledValue = self.rdnSchema[recordType]["loginEnabledValue"]
                record.enabledForLogin = self._getUniqueLdapAttribute(attrs,
                    loginEnabledAttr) == loginEnabledValue

        # Override with LDAP calendar-enabled control if attribute specified
        calendarEnabledAttr = self.rdnSchema[recordType].get("calendarEnabledAttr", "")
        if calendarEnabledAttr:
            calendarEnabledValue = self.rdnSchema[recordType]["calendarEnabledValue"]
            record.enabledForCalendaring = self._getUniqueLdapAttribute(attrs,
                calendarEnabledAttr) == calendarEnabledValue

        return record


    def queryDirectory(self, recordTypes, indexType, indexKey, queryMethod=None):
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

        if queryMethod is None:
            queryMethod = self.timedSearch

        self.log.debug("LDAP query for types %s, indexType %s and indexKey %s"
            % (recordTypes, indexType, indexKey))

        guidAttr = self.rdnSchema["guidAttr"]
        for recordType in recordTypes:
            # Build base for this record Type
            base = self.typeDNs[recordType]

            # Build filter
            filterstr = "(!(objectClass=organizationalUnit))"
            typeFilter = self.rdnSchema[recordType]["filter"]
            if typeFilter:
                filterstr = "(&%s%s)" % (filterstr, typeFilter)

            if indexType == self.INDEX_TYPE_GUID:
                # Query on guid only works if guid attribute has been defined.
                # Support for query on guid even if is auto-generated should
                # be added.
                if not guidAttr: return
                filterstr = "(&%s(%s=%s))" % (filterstr, guidAttr, indexKey)

            elif indexType == self.INDEX_TYPE_SHORTNAME:
                filterstr = "(&%s(%s=%s))" % (
                    filterstr,
                    self.rdnSchema[recordType]["mapping"]["recordName"],
                    ldapEsc(indexKey)
                )

            elif indexType == self.INDEX_TYPE_CUA:
                # indexKey is of the form "mailto:test@example.net"
                email = indexKey[7:] # strip "mailto:"
                emailSuffix = self.rdnSchema[recordType]["emailSuffix"]
                if emailSuffix is not None and email.partition("@")[2] == emailSuffix:
                    filterstr = "(&%s(|(&(!(mail=*))(%s=%s))(mail=%s)))" % (
                        filterstr,
                        self.rdnSchema[recordType]["attr"],
                        email.partition("@")[0],
                        ldapEsc(email)
                    )
                else:
                    # emailAddresses can map to multiple LDAP fields
                    ldapFields = self.rdnSchema[recordType]["mapping"]["emailAddresses"]
                    if isinstance(ldapFields, str):
                        if ldapFields:
                            subfilter = "(%s=%s)" % (ldapFields, ldapEsc(email))
                        else:
                            continue # No LDAP attribute assigned for emailAddresses

                    else:
                        subfilter = []
                        for ldapField in ldapFields:
                            if ldapField:
                                subfilter.append("(%s=%s)" % (ldapField, ldapEsc(email)))
                        if not subfilter:
                            continue # No LDAP attribute assigned for emailAddresses

                        subfilter = "(|%s)" % ("".join(subfilter))
                    filterstr = "(&%s%s)" % (filterstr, subfilter)

            elif indexType == self.INDEX_TYPE_AUTHID:
                return

            # Query the LDAP server
            self.log.debug("Retrieving ldap record with base %s and filter %s." %
                (ldap.dn.dn2str(base), filterstr))
            result = queryMethod(ldap.dn.dn2str(base),
                ldap.SCOPE_SUBTREE, filterstr=filterstr, attrlist=self.attrlist)

            if result:
                dn, attrs = result.pop()
                dn = normalizeDNstr(dn)

                unrestricted = self.isAllowedByRestrictToGroup(dn, attrs)

                try:
                    record = self._ldapResultToRecord(dn, attrs, recordType)
                    self.log.debug("Got LDAP record {rec}", rec=record)

                    if not unrestricted:
                        self.log.debug("%s is not enabled because it's not a member of group: %s" % (dn, self.restrictToGroup))
                        record.enabledForCalendaring = False
                        record.enabledForAddressBooks = False

                    record.applySACLs()

                    self.recordCacheForType(recordType).addRecord(record,
                        indexType, indexKey
                    )

                    # We got a match, so don't bother checking other types
                    break

                except MissingRecordNameException:
                    self.log.warn("Ignoring record missing record name attribute: recordType %s, indexType %s and indexKey %s"
                        % (recordTypes, indexType, indexKey))

                except MissingGuidException:
                    self.log.warn("Ignoring record missing guid attribute: recordType %s, indexType %s and indexKey %s"
                        % (recordTypes, indexType, indexKey))


    def recordsMatchingTokens(self, tokens, context=None, limitResults=50, timeoutSeconds=10):
        """
        # TODO: hook up limitResults to the client limit in the query

        @param tokens: The tokens to search on
        @type tokens: C{list} of C{str} (utf-8 bytes)
        @param context: An indication of what the end user is searching
            for; "attendee", "location", or None
        @type context: C{str}
        @return: a deferred sequence of L{IDirectoryRecord}s which
            match the given tokens and optional context.

        Each token is searched for within each record's full name and
        email address; if each token is found within a record that
        record is returned in the results.

        If context is None, all record types are considered.  If
        context is "location", only locations are considered.  If
        context is "attendee", only users, groups, and resources
        are considered.
        """
        self.log.debug("Peforming calendar user search for %s (%s)" % (tokens, context))
        startTime = time.time()
        records = []
        recordTypes = self.recordTypesForSearchContext(context)
        recordTypes = [r for r in recordTypes if r in self.recordTypes()]

        typeCounts = {}
        for recordType in recordTypes:
            if limitResults == 0:
                self.log.debug("LDAP search aggregate limit reached")
                break
            typeCounts[recordType] = 0
            base = self.typeDNs[recordType]
            scope = ldap.SCOPE_SUBTREE
            extraFilter = self.rdnSchema[recordType]["filter"]
            filterstr = buildFilterFromTokens(recordType, self.rdnSchema[recordType]["mapping"],
                tokens, extra=extraFilter)

            if filterstr is not None:
                # Query the LDAP server
                self.log.debug("LDAP search %s %s (limit=%d)" %
                    (ldap.dn.dn2str(base), filterstr, limitResults))
                results = self.timedSearch(ldap.dn.dn2str(base), scope,
                    filterstr=filterstr, attrlist=self.attrlist,
                    timeoutSeconds=timeoutSeconds,
                    resultLimit=limitResults)
                numMissingGuids = 0
                numMissingRecordNames = 0
                numNotEnabled = 0
                for dn, attrs in results:
                    dn = normalizeDNstr(dn)
                    # Skip if group restriction is in place and guid is not
                    # a member
                    if (recordType != self.recordType_groups and
                        not self.isAllowedByRestrictToGroup(dn, attrs)):
                        continue

                    try:
                        record = self._ldapResultToRecord(dn, attrs, recordType)

                        # For non-group records, if not enabled for calendaring do
                        # not include in principal property search results
                        if (recordType != self.recordType_groups):
                            if not record.enabledForCalendaring:
                                numNotEnabled += 1
                                continue

                        records.append(record)
                        typeCounts[recordType] += 1
                        limitResults -= 1

                    except MissingGuidException:
                        numMissingGuids += 1

                    except MissingRecordNameException:
                        numMissingRecordNames += 1

                self.log.debug("LDAP search returned %d results, %d usable" % (len(results), typeCounts[recordType]))


        typeCountsStr = ", ".join(["%s:%d" % (rt, ct) for (rt, ct) in typeCounts.iteritems()])
        totalTime = time.time() - startTime
        self.log.info("Calendar user search for %s matched %d records (%s) in %.2f seconds" % (tokens, len(records), typeCountsStr, totalTime))
        return succeed(records)


    @inlineCallbacks
    def recordsMatchingFields(self, fields, operand="or", recordType=None):
        """
        Carries out the work of a principal-property-search against LDAP
        Returns a deferred list of directory records.
        """
        records = []

        self.log.debug("Peforming principal property search for %s" % (fields,))

        if recordType is None:
            # Make a copy since we're modifying it
            recordTypes = list(self.recordTypes())

            # principal-property-search syntax doesn't provide a way to ask
            # for 3 of the 4 types (either all types or a single type).  This
            # is wasteful in the case of iCal looking for event attendees
            # since it always ignores the locations.  This config flag lets
            # you skip querying for locations in this case:
            if not self.queryLocationsImplicitly:
                if self.recordType_locations in recordTypes:
                    recordTypes.remove(self.recordType_locations)
        else:
            recordTypes = [recordType]

        guidAttr = self.rdnSchema["guidAttr"]
        for recordType in recordTypes:

            base = self.typeDNs[recordType]

            if fields[0][0] == "dn":
                # DN's are not an attribute that can be searched on by filter
                scope = ldap.SCOPE_BASE
                filterstr = "(objectClass=*)"
                base = ldap.dn.str2dn(fields[0][1])

            else:
                scope = ldap.SCOPE_SUBTREE
                filterstr = buildFilter(recordType,
                    self.rdnSchema[recordType]["mapping"],
                    fields, operand=operand,
                    optimizeMultiName=self.optimizeMultiName)

            if filterstr is not None:
                # Query the LDAP server
                self.log.debug("LDAP search %s %s %s" %
                    (ldap.dn.dn2str(base), scope, filterstr))
                results = (yield deferToThread(self.timedSearch, ldap.dn.dn2str(base), scope,
                    filterstr=filterstr, attrlist=self.attrlist,
                    timeoutSeconds=self.requestTimeoutSeconds,
                    resultLimit=self.requestResultsLimit))
                self.log.debug("LDAP search returned %d results" % (len(results),))
                numMissingGuids = 0
                numMissingRecordNames = 0
                for dn, attrs in results:
                    dn = normalizeDNstr(dn)
                    # Skip if group restriction is in place and guid is not
                    # a member
                    if (recordType != self.recordType_groups and
                        not self.isAllowedByRestrictToGroup(dn, attrs)):
                        continue

                    try:
                        record = self._ldapResultToRecord(dn, attrs, recordType)

                        # For non-group records, if not enabled for calendaring do
                        # not include in principal property search results
                        if (recordType != self.recordType_groups):
                            if not record.enabledForCalendaring:
                                continue

                        records.append(record)

                    except MissingGuidException:
                        numMissingGuids += 1

                    except MissingRecordNameException:
                        numMissingRecordNames += 1

                if numMissingGuids:
                    self.log.warn("%d %s records are missing %s" %
                        (numMissingGuids, recordType, guidAttr))

                if numMissingRecordNames:
                    self.log.warn("%d %s records are missing record name" %
                        (numMissingRecordNames, recordType))

        self.log.debug("Principal property search matched %d records" % (len(records),))
        returnValue(records)


    @inlineCallbacks
    def getGroups(self, guids):
        """
        Returns a set of group records for the list of guids passed in.  For
        any group that also contains subgroups, those subgroups' records are
        also returned, and so on.
        """

        recordsByAlias = {}

        groupsDN = self.typeDNs[self.recordType_groups]
        memberIdAttr = self.groupSchema["memberIdAttr"]

        # First time through the loop we search using the attribute
        # corresponding to guid, since that is what the proxydb uses.
        # Subsequent iterations fault in groups via the attribute
        # used to identify members.
        attributeToSearch = "guid"
        valuesToFetch = guids

        while valuesToFetch:
            results = []

            if attributeToSearch == "dn":
                # Since DN can't be searched on in a filter we have to call
                # recordsMatchingFields for *each* DN.
                for value in valuesToFetch:
                    fields = [["dn", value, False, "equals"]]
                    result = (yield self.recordsMatchingFields(fields,
                        recordType=self.recordType_groups))
                    results.extend(result)
            else:
                for batch in splitIntoBatches(valuesToFetch, self.batchSize):
                    fields = []
                    for value in batch:
                        fields.append([attributeToSearch, value, False, "equals"])
                    result = (yield self.recordsMatchingFields(fields,
                        recordType=self.recordType_groups))
                    results.extend(result)

            # Reset values for next iteration
            valuesToFetch = set()

            for record in results:
                alias = record.cachedGroupsAlias()
                if alias not in recordsByAlias:
                    recordsByAlias[alias] = record

                # record.memberGUIDs() contains the members of this group,
                # but it might not be in guid form; it will be data from
                # self.groupSchema["memberIdAttr"]
                for memberAlias in record.memberGUIDs():
                    if not memberIdAttr:
                        # Members are identified by dn so we can take a short
                        # cut:  we know we only need to examine groups, and
                        # those will be children of the groups DN
                        if not dnContainedIn(ldap.dn.str2dn(memberAlias),
                            groupsDN):
                            continue
                    if memberAlias not in recordsByAlias:
                        valuesToFetch.add(memberAlias)

            # Switch to the LDAP attribute used for identifying members
            # for subsequent iterations.  If memberIdAttr is not specified
            # in the config, we'll search using dn.
            attributeToSearch = "memberIdAttr" if memberIdAttr else "dn"

        returnValue(recordsByAlias.values())

    def recordTypeForDN(self, dnStr):
        """
        Examine a DN to determine which recordType it belongs to
        @param dn: DN to compare
        @type dn: string
        @return: recordType string, or None if no match
        """
        dn = ldap.dn.str2dn(dnStr.lower())
        for recordType in self.recordTypes():
            base = self.typeDNs[recordType] # already lowercase
            if dnContainedIn(dn, base):
                return recordType
        return None


def dnContainedIn(child, parent):
    """
    Return True if child dn is contained within parent dn, otherwise False.
    """
    return child[-len(parent):] == parent


def normalizeDNstr(dnStr):
    """
    Convert to lowercase and remove extra whitespace
    @param dnStr: dn
    @type dnStr: C{str}
    @return: normalized dn C{str}
    """
    return ' '.join(ldap.dn.dn2str(ldap.dn.str2dn(dnStr.lower())).split())


def _convertValue(value, matchType):
    if matchType == "starts-with":
        value = "%s*" % (ldapEsc(value),)
    elif matchType == "contains":
        value = "*%s*" % (ldapEsc(value),)
    # otherwise it's an exact match
    else:
        value = ldapEsc(value)
    return value

def buildFilter(recordType, mapping, fields, operand="or", optimizeMultiName=False):
    """
    Create an LDAP filter string from a list of tuples representing directory
    attributes to search

    mapping is a dict mapping internal directory attribute names to ldap names.
    fields is a list of tuples...
        (directory field name, value to search, caseless (ignored), matchType)
    ...where matchType is one of "starts-with", "contains", "exact"
    """

    converted = []
    combined = {}
    for field, value, caseless, matchType in fields:
        ldapField = mapping.get(field, None)
        if ldapField:
            combined.setdefault(field, []).append((value, caseless, matchType))
            value = _convertValue(value, matchType)
            if isinstance(ldapField, str):
                converted.append("(%s=%s)" % (ldapField, value))
            else:
                subConverted = []
                for lf in ldapField:
                    subConverted.append("(%s=%s)" % (lf, value))
                converted.append("(|%s)" % "".join(subConverted))

    if len(converted) == 0:
        return None

    if optimizeMultiName and recordType in ("users", "groups"):
        for field in [key for key in combined.keys() if key != "guid"]:
            if len(combined.get(field, [])) > 1:
                # Client is searching on more than one name -- interpret this as the user
                # explicitly looking up a user by name (ignoring other record types), and
                # try the various firstName/lastName permutations:
                if recordType == "users":
                    converted = []
                    for firstName, firstCaseless, firstMatchType in combined["firstName"]:
                        for lastName, lastCaseless, lastMatchType in combined["lastName"]:
                            if firstName != lastName:
                                firstValue = _convertValue(firstName, firstMatchType)
                                lastValue = _convertValue(lastName, lastMatchType)
                                converted.append("(&(%s=%s)(%s=%s))" %
                                    (mapping["firstName"], firstValue,
                                     mapping["lastName"], lastValue)
                                )
                else:
                    return None

    if len(converted) == 1:
        filterstr = converted[0]
    else:
        operand = ("|" if operand == "or" else "&")
        filterstr = "(%s%s)" % (operand, "".join(converted))

    if filterstr:
        # To reduce the amount of records returned, filter out the ones
        # that don't have (possibly) required attribute values (record
        # name, guid)
        additional = []
        for key in ("recordName", "guid"):
            if mapping.has_key(key):
                additional.append("(%s=*)" % (mapping.get(key),))
        if additional:
            filterstr = "(&%s%s)" % ("".join(additional), filterstr)

    return filterstr


def buildFilterFromTokens(recordType, mapping, tokens, extra=None):
    """
    Create an LDAP filter string from a list of query tokens.  Each token is
    searched for in each LDAP attribute corresponding to "fullName" and
    "emailAddresses" (could be multiple LDAP fields for either).

    @param recordType: The recordType to use to customize the filter
    @param mapping: A dict mapping internal directory attribute names to ldap names.
    @type mapping: C{dict}
    @param tokens: The list of tokens to search for
    @type tokens: C{list}
    @param extra: Extra filter to "and" into the final filter
    @type extra: C{str} or None
    @return: An LDAP filterstr
    @rtype: C{str}
    """

    filterStr = None
    tokens = [ldapEsc(t) for t in tokens if len(t) > 2]
    if len(tokens) == 0:
        return None

    attributes = [
        ("fullName", "(%s=*%s*)"),
        ("emailAddresses", "(%s=%s*)"),
    ]

    ldapFields = []
    for attribute, template in attributes:
        ldapField = mapping.get(attribute, None)
        if ldapField:
            if isinstance(ldapField, str):
                ldapFields.append((ldapField, template))
            else:
                for lf in ldapField:
                    ldapFields.append((lf, template))

    if len(ldapFields) == 0:
        return None

    tokenFragments = []
    if extra:
        tokenFragments.append(extra)

    for token in tokens:
        fragments = []
        for ldapField, template in ldapFields:
            fragments.append(template % (ldapField, token))
        if len(fragments) == 1:
            tokenFragment = fragments[0]
        else:
            tokenFragment = "(|%s)" % ("".join(fragments),)
        tokenFragments.append(tokenFragment)

    if len(tokenFragments) == 1:
        filterStr = tokenFragments[0]
    else:
        filterStr = "(&%s)" % ("".join(tokenFragments),)

    return filterStr


class LdapDirectoryRecord(CachingDirectoryRecord):
    """
    LDAP implementation of L{IDirectoryRecord}.
    """
    def __init__(
        self, service, recordType,
        guid, shortNames, authIDs, fullName,
        firstName, lastName, emailAddresses,
        uid, dn, memberGUIDs, extProxies, extReadOnlyProxies,
        attrs
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
            extProxies            = extProxies,
            extReadOnlyProxies    = extReadOnlyProxies,
            uid                   = uid,
        )

        # Save attributes of dn and attrs in case you might need them later
        self.dn = dn
        self.attrs = attrs

        # Store copy of member guids
        self._memberGUIDs = memberGUIDs

        # Identifier of this record as a group member
        memberIdAttr = self.service.groupSchema["memberIdAttr"]
        if memberIdAttr:
            self._memberId = self.service._getUniqueLdapAttribute(attrs,
                memberIdAttr)
        else:
            self._memberId = normalizeDNstr(self.dn)


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

        for memberId in self._memberGUIDs:

            if memberIdAttr:

                base = self.service.base
                filterstr = "(%s=%s)" % (memberIdAttr, ldapEsc(memberId))
                self.log.debug("Retrieving subtree of %s with filter %s" %
                    (ldap.dn.dn2str(base), filterstr),
                    system="LdapDirectoryService")
                result = self.service.timedSearch(ldap.dn.dn2str(base),
                    ldap.SCOPE_SUBTREE, filterstr=filterstr,
                    attrlist=self.service.attrlist)

            else: # using DN

                self.log.debug("Retrieving %s." % memberId,
                    system="LdapDirectoryService")
                result = self.service.timedSearch(memberId,
                    ldap.SCOPE_BASE, attrlist=self.service.attrlist)

            if result:

                dn, attrs = result.pop()
                dn = normalizeDNstr(dn)
                self.log.debug("Retrieved: %s %s" % (dn,attrs))
                recordType = self.service.recordTypeForDN(dn)
                if recordType is None:
                    self.log.error("Unable to map %s to a record type" % (dn,))
                    continue

                shortName = self.service._getUniqueLdapAttribute(attrs,
                    self.service.rdnSchema[recordType]["mapping"]["recordName"])

                if shortName:
                    record = self.service.recordWithShortName(recordType,
                        shortName)
                    if record:
                        results.append(record)

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
        base = self.service.typeDNs[recordType]

        membersAttrs = []
        if self.service.groupSchema["membersAttr"]:
            membersAttrs.append(self.service.groupSchema["membersAttr"])
        if self.service.groupSchema["nestedGroupsAttr"]:
            membersAttrs.append(self.service.groupSchema["nestedGroupsAttr"])

        if len(membersAttrs) == 1:
            filterstr = "(%s=%s)" % (membersAttrs[0], self._memberId)
        else:
            filterstr = "(|%s)" % ( "".join(
                    ["(%s=%s)" % (a, self._memberId) for a in membersAttrs]
                ),
            )
        self.log.debug("Finding groups containing %s" % (self._memberId,))
        groups = []

        try:
            results = self.service.timedSearch(ldap.dn.dn2str(base),
                ldap.SCOPE_SUBTREE, filterstr=filterstr, attrlist=self.service.attrlist)

            for dn, attrs in results:
                dn = normalizeDNstr(dn)
                shortName = self.service._getUniqueLdapAttribute(attrs, "cn")
                self.log.debug("%s is a member of %s" % (self._memberId, shortName))
                record = self.service.recordWithShortName(recordType, shortName)
                if record is not None:
                    groups.append(record)
        except ldap.PROTOCOL_ERROR, e:
            self.log.warn(str(e))

        return groups

    def cachedGroupsAlias(self):
        """
        See directory.py for full description

        LDAP group members can be referred to by attributes other than guid.  _memberId
        will be set to the appropriate value to look up group-membership with.
        """
        return self._memberId

    def memberGUIDs(self):
        return set(self._memberGUIDs)


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
                    self.log.error("PAM module is not installed")
                    raise DirectoryConfigurationError()

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
                    self.log.info("Invalid credentials for {dn}",
                        dn=repr(self.dn), system="LdapDirectoryService")
                    return False

            else:
                self.log.error("Unknown Authentication Method '{method}'",
                    method=self.service.authMethod.upper())
                raise DirectoryConfigurationError()

        return super(LdapDirectoryRecord, self).verifyCredentials(credentials)


class MissingRecordNameException(Exception):
    """ Raised when LDAP record is missing recordName """
    pass

class MissingGuidException(Exception):
    """ Raised when LDAP record is missing guidAttr and it's required """
    pass
