##
# Copyright (c) 2008-2009 Aymeric Augustin. All rights reserved.
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
from twistedcaldav.directory.util import splitIntoBatches
from twisted.internet.defer import succeed, inlineCallbacks, returnValue
from twext.web2.http import HTTPError, StatusResponse
from twext.web2 import responsecode

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
        self.log_debug("Querying ldap for records matching base %s and filter %s for attributes %s." %
            (ldap.dn.dn2str(base), filterstr, self.attrlist))

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

            unrestricted = True
            if self.restrictedGUIDs is not None:
                if guidAttr:
                    guid = self._getUniqueLdapAttribute(attrs, guidAttr)
                    if guid not in self.restrictedGUIDs:
                        unrestricted = False

            try:
                record = self._ldapResultToRecord(dn, attrs, recordType)
                # self.log_debug("Got LDAP record %s" % (record,))
            except MissingGuidException:
                numMissingGuids += 1
                continue

            if not unrestricted:
                self.log_debug("%s is not enabled because it's not a member of group: %s" % (guid, self.restrictToGroup))
                record.enabledForCalendaring = False
                record.enabledForAddressBooks = False

            records.append(record)

        if numMissingGuids:
            self.log_info("%d %s records are missing %s" %
                (numMissingGuids, recordType, guidAttr))

        return records

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
            self.log_error("LDAP configuration requires guidAttr, proxyAttr, and readOnlyProxyAttr in order to use external proxy assignments efficiently; falling back to slower method")
            # Fall back to the less-specialized version
            return super(LdapDirectoryService, self).getExternalProxyAssignments()

        # Build filter
        filterstr = "(|(%s=*)(%s=*))" % (readAttr, writeAttr)
        attrlist = [guidAttr, readAttr, writeAttr]

        # Query the LDAP server
        self.log_debug("Querying ldap for records matching base %s and filter %s for attributes %s." %
            (ldap.dn.dn2str(self.base), filterstr, attrlist))

        results = self.timedSearch(ldap.dn.dn2str(self.base),
            ldap.SCOPE_SUBTREE, filterstr=filterstr, attrlist=attrlist)

        for dn, attrs in results:
            dn = normalizeDNstr(dn)
            guid = self._getUniqueLdapAttribute(attrs, guidAttr)
            if guid:
                readDelegate = self._getUniqueLdapAttribute(attrs, readAttr)
                if readDelegate:
                    assignments.append(("%s#calendar-proxy-read" % (guid,),
                        [readDelegate]))
                writeDelegate = self._getUniqueLdapAttribute(attrs, writeAttr)
                if writeDelegate:
                    assignments.append(("%s#calendar-proxy-write" % (guid,),
                        [writeDelegate]))

        return assignments

    def getLDAPConnection(self):
        if self.ldap is None:
            self.log_info("Connecting to LDAP %s" % (repr(self.uri),))
            self.ldap = self.createLDAPConnection()
            self.log_info("Connection established to LDAP %s" % (repr(self.uri),))
            if self.credentials.get("dn", ""):
                try:
                    self.log_info("Binding to LDAP %s" %
                        (repr(self.credentials.get("dn")),))
                    self.ldap.simple_bind_s(self.credentials.get("dn"),
                        self.credentials.get("password"))
                    self.log_info("Successfully authenticated with LDAP as %s" %
                        (repr(self.credentials.get("dn")),))
                except ldap.INVALID_CREDENTIALS:
                    msg = "Can't bind to LDAP %s: check credentials" % (self.uri,)
                    self.log_error(msg)
                    raise DirectoryConfigurationError(msg)
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
            self.log_debug("Authenticating %s" % (dn,))

            if self.authLDAP is None:
                self.log_debug("Creating authentication connection to LDAP")
                self.authLDAP = self.createLDAPConnection()

            try:
                startTime = time.time()
                self.authLDAP.simple_bind_s(dn, password)
                # Getting here means success, so break the retry loop
                break

            except ldap.INAPPROPRIATE_AUTH:
                # Seen when using an empty password, treat as invalid creds
                raise ldap.INVALID_CREDENTIALS()

            except ldap.INVALID_CREDENTIALS:
                raise

            except ldap.SERVER_DOWN:
                self.log_error("Lost connection to LDAP server.")
                self.authLDAP = None
                # Fall through and retry if TRIES has been reached

            except Exception, e:
                self.log_error("LDAP authentication failed with %s." % (e,))
                raise

            finally:
                totalTime = time.time() - startTime
                if totalTime > self.warningThresholdSeconds:
                    self.log_error("LDAP auth exceeded threshold: %.2f seconds for %s" % (totalTime, dn))

        else:
            self.log_error("Giving up on LDAP authentication after %d tries.  Responding with 503." % (TRIES,))
            raise HTTPError(StatusResponse(responsecode.SERVICE_UNAVAILABLE, "LDAP server unavailable"))

        self.log_debug("Authentication succeeded for %s" % (dn,))


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
                self.log_error("LDAP filter error: %s %s" % (e, filterstr))
                return []
            except ldap.SIZELIMIT_EXCEEDED, e:
                self.log_debug("LDAP result limit exceeded: %d" % (resultLimit,))
            except ldap.TIMELIMIT_EXCEEDED, e:
                self.log_warn("LDAP timeout exceeded: %d seconds" % (timeoutSeconds,))
            except ldap.SERVER_DOWN:
                self.ldap = None
                self.log_error("LDAP server unavailable (tried %d times)" % (i+1,))
                continue

            # change format, ignoring resultsType
            result = [resultItem for resultType, resultItem in s.allResults]

            totalTime = time.time() - startTime
            if totalTime > self.warningThresholdSeconds:
                if filterstr and len(filterstr) > 100:
                    filterstr = "%s..." % (filterstr[:100],)
                self.log_error("LDAP query exceeded threshold: %.2f seconds for %s %s %s (#results=%d)" %
                    (totalTime, base, filterstr, attrlist, len(result)))
            return result

        raise HTTPError(StatusResponse(responsecode.SERVICE_UNAVAILABLE, "LDAP server unavailable"))


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
                base = self.typeDNs[recordType]
                filterstr = "(cn=%s)" % (self.restrictToGroup,)
                self.log_debug("Retrieving ldap record with base %s and filter %s." %
                    (ldap.dn.dn2str(base), filterstr))
                result = self.timedSearch(ldap.dn.dn2str(base),
                    ldap.SCOPE_SUBTREE, filterstr=filterstr, attrlist=self.attrlist)

                if len(result) == 1:
                    dn, attrs = result[0]
                    dn = normalizeDNstr(dn)
                    if self.groupSchema["membersAttr"]:
                        members = set(self._getMultipleLdapAttributes(attrs,
                            self.groupSchema["membersAttr"]))
                    if self.groupSchema["nestedGroupsAttr"]:
                        nestedGroups = set(self._getMultipleLdapAttributes(attrs,
                            self.groupSchema["nestedGroupsAttr"]))

                else:
                    members = []
                    nestedGroups = []

                self._cachedRestrictedGUIDs = set(self._expandGroupMembership(members, nestedGroups, returnGroups=True))
                self.log_info("Got %d restricted group members" % (len(self._cachedRestrictedGUIDs),))
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
            base = self.typeDNs[recordType]
            filterstr = "(%s=%s)" % (self.rdnSchema["guidAttr"], groupGUID)

            self.log_debug("Retrieving ldap record with base %s and filter %s." %
                (ldap.dn.dn2str(base), filterstr))
            result = self.timedSearch(ldap.dn.dn2str(base),
                ldap.SCOPE_SUBTREE, filterstr=filterstr, attrlist=self.attrlist)

            if len(result) == 0:
                continue

            if len(result) == 1:
                dn, attrs = result[0]
                dn = normalizeDNstr(dn)
                if self.groupSchema["membersAttr"]:
                    subMembers = set(self._getMultipleLdapAttributes(attrs,
                        self.groupSchema["membersAttr"]))
                else:
                    subMembers = []

                if self.groupSchema["nestedGroupsAttr"]:
                    subNestedGroups = set(self._getMultipleLdapAttributes(attrs,
                        self.groupSchema["nestedGroupsAttr"]))
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
                self.log_debug("LDAP data for %s is missing guid attribute %s" % (shortNames, guidAttr))
                raise MissingGuidException()

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
                memberGUIDs = [normalizeDNstr(dnStr) for dnStr in list(memberGUIDs)]


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
                            readOnlyProxy
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
                        self.log_error("Unable to parse resource info (%s)" % (e,))
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
                        subfilter = "(%s=%s)" % (ldapFields, ldapEsc(email))
                    else:
                        subfilter = []
                        for ldapField in ldapFields:
                            subfilter.append("(%s=%s)" % (ldapField, ldapEsc(email)))
                        subfilter = "(|%s)" % ("".join(subfilter))
                    filterstr = "(&%s%s)" % (filterstr, subfilter)

            elif indexType == self.INDEX_TYPE_AUTHID:
                return

            # Query the LDAP server
            self.log_debug("Retrieving ldap record with base %s and filter %s." %
                (ldap.dn.dn2str(base), filterstr))
            result = self.timedSearch(ldap.dn.dn2str(base),
                ldap.SCOPE_SUBTREE, filterstr=filterstr, attrlist=self.attrlist)

            if result:
                dn, attrs = result.pop()
                dn = normalizeDNstr(dn)

                unrestricted = True
                if self.restrictedGUIDs is not None:
                    if guidAttr:
                        guid = self._getUniqueLdapAttribute(attrs, guidAttr)
                        if guid not in self.restrictedGUIDs:
                            unrestricted = False

                try:
                    record = self._ldapResultToRecord(dn, attrs, recordType)
                    self.log_debug("Got LDAP record %s" % (record,))

                    if not unrestricted:
                        self.log_debug("%s is not enabled because it's not a member of group: %s" % (guid, self.restrictToGroup))
                        record.enabledForCalendaring = False
                        record.enabledForAddressBooks = False

                    record.applySACLs()

                    self.recordCacheForType(recordType).addRecord(record,
                        indexType, indexKey
                    )

                    # We got a match, so don't bother checking other types
                    break

                except MissingRecordNameException:
                    self.log_warn("Ignoring record missing record name attribute: recordType %s, indexType %s and indexKey %s"
                        % (recordTypes, indexType, indexKey))

                except MissingGuidException:
                    self.log_warn("Ignoring record missing guid attribute: recordType %s, indexType %s and indexKey %s"
                        % (recordTypes, indexType, indexKey))


    def recordsMatchingFields(self, fields, operand="or", recordType=None):
        """
        Carries out the work of a principal-property-search against LDAP
        Returns a deferred list of directory records.
        """
        records = []

        self.log_debug("Peforming principal property search for %s" % (fields,))

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
                self.log_debug("LDAP search %s %s %s" %
                    (ldap.dn.dn2str(base), scope, filterstr))
                results = self.timedSearch(ldap.dn.dn2str(base), scope,
                    filterstr=filterstr, attrlist=self.attrlist,
                    timeoutSeconds=self.requestTimeoutSeconds,
                    resultLimit=self.requestResultsLimit)
                self.log_debug("LDAP search returned %d results" % (len(results),))
                numMissingGuids = 0
                numMissingRecordNames = 0
                for dn, attrs in results:
                    dn = normalizeDNstr(dn)
                    # Skip if group restriction is in place and guid is not
                    # a member
                    if (recordType != self.recordType_groups and
                        self.restrictedGUIDs is not None):
                        if guidAttr:
                            guid = self._getUniqueLdapAttribute(attrs, guidAttr)
                            if guid not in self.restrictedGUIDs:
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
                    self.log_warn("%d %s records are missing %s" %
                        (numMissingGuids, recordType, guidAttr))

                if numMissingRecordNames:
                    self.log_warn("%d %s records are missing record name" %
                        (numMissingRecordNames, recordType))

        self.log_debug("Principal property search matched %d records" % (len(records),))
        return succeed(records)


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
            attributeToSearch = memberIdAttr if memberIdAttr else "dn"

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
                self.log_debug("Retrieving subtree of %s with filter %s" %
                    (ldap.dn.dn2str(base), filterstr),
                    system="LdapDirectoryService")
                result = self.service.timedSearch(ldap.dn.dn2str(base),
                    ldap.SCOPE_SUBTREE, filterstr=filterstr,
                    attrlist=self.service.attrlist)

            else: # using DN

                self.log_debug("Retrieving %s." % memberId,
                    system="LdapDirectoryService")
                result = self.service.timedSearch(memberId,
                    ldap.SCOPE_BASE, attrlist=self.service.attrlist)

            if result:

                dn, attrs = result.pop()
                dn = normalizeDNstr(dn)
                self.log_debug("Retrieved: %s %s" % (dn,attrs))
                recordType = self.service.recordTypeForDN(dn)
                if recordType is None:
                    self.log_error("Unable to map %s to a record type" % (dn,))
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
        self.log_debug("Finding groups containing %s" % (self._memberId,))
        groups = []

        try:
            results = self.service.timedSearch(ldap.dn.dn2str(base),
                ldap.SCOPE_SUBTREE, filterstr=filterstr, attrlist=self.service.attrlist)

            for dn, attrs in results:
                dn = normalizeDNstr(dn)
                shortName = self.service._getUniqueLdapAttribute(attrs, "cn")
                self.log_debug("%s is a member of %s" % (self._memberId, shortName))
                record = self.service.recordWithShortName(recordType, shortName)
                if record is not None:
                    groups.append(record)
        except ldap.PROTOCOL_ERROR, e:
            self.log_warn(str(e))

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


class MissingRecordNameException(Exception):
    """ Raised when LDAP record is missing recordName """
    pass

class MissingGuidException(Exception):
    """ Raised when LDAP record is missing guidAttr and it's required """
    pass
