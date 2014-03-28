##
# Copyright (c) 2008-2014 Apple Inc. All rights reserved.
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
Directory-backed address book service resource and operations.
"""

__all__ = [
    "DirectoryBackedAddressBookResource",
]

from twext.python.log import Logger
from twext.who.expression import Operand, MatchType, MatchFlags, \
    MatchExpression, CompoundExpression
from twext.who.idirectory import FieldName, RecordType
from twisted.internet.defer import succeed, inlineCallbacks, maybeDeferred, \
    returnValue
from twisted.python.constants import NamedConstant
from twistedcaldav import carddavxml
from twistedcaldav.config import config
from twistedcaldav.resource import CalDAVResource
from txdav.carddav.datastore.query.filter import IsNotDefined, TextMatch, \
    ParameterFilter
from txdav.who.idirectory import FieldName as CalFieldName, \
    RecordType as CalRecordType
from txdav.xml import element as davxml
from txweb2 import responsecode
from txweb2.dav.resource import TwistedACLInheritable
from txweb2.http import HTTPError, StatusResponse
import uuid

log = Logger()



class DirectoryBackedAddressBookResource (CalDAVResource):
    """
    Directory-backed address book
    """

    def __init__(self, principalCollections, principalDirectory, uri):

        CalDAVResource.__init__(self, principalCollections=principalCollections)

        self.principalDirectory = principalDirectory
        self.uri = uri
        self.directory = None


    def makeChild(self, name):
        return self.directory


    def provisionDirectory(self):
        if self.directory is None:
            log.info(
                "Setting search directory to {principalDirectory}",
                principalDirectory=self.principalDirectory)
            self.directory = self.principalDirectory
            # future: instantiate another directory based on /Search/Contacts (?)

        return succeed(None)


    def defaultAccessControlList(self):
        if config.AnonymousDirectoryAddressBookAccess:
            # DAV:Read for all principals (includes anonymous)
            accessPrincipal = davxml.All()
        else:
            # DAV:Read for all authenticated principals (does not include anonymous)
            accessPrincipal = davxml.Authenticated()

        return succeed(
            davxml.ACL(
                davxml.ACE(
                    davxml.Principal(accessPrincipal),
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                        davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet())
                                    ),
                    davxml.Protected(),
                    TwistedACLInheritable(),
               ),
            )
        )


    def supportedReports(self):
        result = super(DirectoryBackedAddressBookResource, self).supportedReports()
        if config.EnableSyncReport:
            # Not supported on the directory backed address book
            result.remove(davxml.Report(davxml.SyncCollection(),))
        return result


    def resourceType(self):
        return davxml.ResourceType.directory


    def resourceID(self):
        if self.directory:
            resource_id = uuid.uuid5(uuid.UUID("5AAD67BF-86DD-42D7-9161-6AF977E4DAA3"), self.directory.baseGUID).urn
        else:
            resource_id = "tag:unknown"
        return resource_id


    def isDirectoryBackedAddressBookCollection(self):
        return True


    def isAddressBookCollection(self):
        return True


    def isCollection(self):
        return True


    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        # Permissions here are fixed, and are not subject to inheritance rules, etc.
        return self.defaultAccessControlList()


    @inlineCallbacks
    def renderHTTP(self, request):
        if not self.directory:
            raise HTTPError(StatusResponse(responsecode.SERVICE_UNAVAILABLE, "Service is starting up"))

        response = (yield maybeDeferred(super(DirectoryBackedAddressBookResource, self).renderHTTP, request))
        returnValue(response)


    @inlineCallbacks
    def doAddressBookDirectoryQuery(self, addressBookFilter, addressBookQuery, maxResults):
        """
        Get vCards for a given addressBookFilter and addressBookQuery
        """

        log.debug("doAddressBookDirectoryQuery: directory={directory} addressBookFilter={addressBookFilter}, addressBookQuery={addressBookQuery}, maxResults={maxResults}",
                  directory=self.directory, addressBookFilter=addressBookFilter, addressBookQuery=addressBookQuery, maxResults=maxResults)
        results = []
        limited = False
        maxQueryRecords = 0

        schema = {
            RecordType.user: {
                "FN": (
                        FieldName.fullNames,
                        FieldName.shortNames,
                        ),
                "N": (
                        FieldName.fullNames,
                        FieldName.shortNames,
                        ),
                "EMAIL": FieldName.emailAddresses,
                "UID": FieldName.uid,
                "ADR": CalFieldName.streetAddress,
             },
            RecordType.group: {
                "FN": (
                        FieldName.fullNames,
                        FieldName.shortNames,
                        ),
                "N": (
                        FieldName.fullNames,
                        FieldName.shortNames,
                        ),
                "EMAIL": FieldName.emailAddresses,
                "UID": FieldName.uid,
                "ADR": CalFieldName.streetAddress,
                # LATER "X-ADDRESSBOOKSERVER-MEMBER": FieldName.members,
             },
        }

        recordTypeToKindMap = {
                       RecordType.user: "individual",
                       RecordType.group: "group",
                       CalRecordType.location: "location",
                       CalRecordType.resource: "device",
                       }

        allowedRecordTypes = set(self.directory.recordTypes()) & set(recordTypeToKindMap.keys()) & set(schema.keys())
        log.debug("doAddressBookDirectoryQuery: allowedRecordTypes={allowedRecordTypes}", allowedRecordTypes=allowedRecordTypes,)

        expressions = []
        for recordType in allowedRecordTypes:

            #log.debug("doAddressBookDirectoryQuery: recordType={recordType}", recordType=recordType,)

            vcardPropToRecordFieldMap = schema[recordType]
            kind = recordTypeToKindMap[recordType]
            constantProperties = ABDirectoryQueryResult.constantProperties.copy()
            constantProperties["KIND"] = kind
            # add KIND as constant so that query can be skipped if addressBookFilter needs a different kind

            propNames, expression = expressionFromABFilter(addressBookFilter, vcardPropToRecordFieldMap, recordType=recordType, constantProperties=constantProperties)
            log.debug("doAddressBookDirectoryQuery: recordType={recordType}, expression={expression!r}, propNames={propNames}", recordType=recordType, expression=expression, propNames=propNames)
            if expression:
                expressions.append(expression)

        if expressions:
            if expressions > 1:
                expression = CompoundExpression(expressions, Operand.OR)
            else:
                expression = expressions[0]

            maxRecords = int(maxResults * 1.2)

            # keep trying query till we get results based on filter.  Especially when doing "all results" query
            while True:

                log.debug("doAddressBookDirectoryQuery: expression={expression!r}, ", expression=expression)

                records = yield self.directory.recordsFromExpression(expression)
                log.debug("doAddressBookDirectoryQuery: #records={n}, records={records!r}", n=len(records), records=records)
                queryLimited = False

                vCardsResults = []#[ABDirectoryQueryResult(self, record) for record in records]

                filteredResults = []
                for vCardResult in vCardsResults:
                    if addressBookFilter.match(vCardResult.vCard()):
                        filteredResults.append(vCardResult)
                    else:
                        log.debug("doAddressBookQuery: vCard did not match filter: {vCard}", vcard=vCardResult.vCard())

                #no more results
                if not queryLimited:
                    break

                # more than requested results
                if maxResults and len(filteredResults) >= maxResults:
                    break

                # more than max report results
                if len(filteredResults) >= config.MaxQueryWithDataResults:
                    break

                # more than self limit
                if maxQueryRecords and maxRecords >= maxQueryRecords:
                    break

                # try again with 2x
                maxRecords *= 2
                if maxQueryRecords and maxRecords > maxQueryRecords:
                    maxRecords = maxQueryRecords

            results = sorted(list(filteredResults), key=lambda result: result.vCard().propertyValue("UID"))
            limited = maxResults and len(results) >= maxResults

        log.info("limited={l} result count={n}", l=limited, n=len(results))
        returnValue((results, limited,))



def propertiesInAddressBookQuery(addressBookQuery):
    """
    Get the vCard properties requested by a given query
    """

    etagRequested = False
    propertyNames = []
    if addressBookQuery.qname() == ("DAV:", "prop"):

        for property in addressBookQuery.children:
            if isinstance(property, carddavxml.AddressData):
                for addressProperty in property.children:
                    if isinstance(addressProperty, carddavxml.Property):
                        propertyNames += [addressProperty.attributes["name"], ]

            elif property.qname() == ("DAV:", "getetag"):
                # for a real etag == md5(vCard), we need all properties
                etagRequested = True

    return (etagRequested, propertyNames if len(propertyNames) else None)



def expressionFromABFilter(addressBookFilter, vcardPropToSearchableFieldMap, recordType, constantProperties={}):
    """
    Convert the supplied addressbook-query into a ds expression tree.

    @param addressBookFilter: the L{Filter} for the addressbook-query to convert.
    @param vcardPropToSearchableFieldMap: a mapping from vcard properties to searchable query attributes.
    @param constantProperties: a mapping of constant properties.  A query on a constant property will return all or None
    @return: (filterProperyNames, expressions) tuple.  expression==True means list all results, expression==False means no results
    """

    def propFilterListQuery(filterAllOf, propFilters):

        def combineExpressionLists(expressionList, allOf, addedExpressions):
            """
            deal with the 4-state logic
                addedExpressions=None means ignore
                addedExpressions=True means all records
                addedExpressions=False means no records
                addedExpressions=[expressionlist] add to expression list
            """
            if expressionList is None:
                expressionList = addedExpressions
            elif addedExpressions is not None:
                if addedExpressions is True:
                    if not allOf:
                        expressionList = True  # expressionList or True is True
                    #else  expressionList and True is expressionList
                elif addedExpressions is False:
                    if allOf:
                        expressionList = False  # expressionList and False is False
                    #else expressionList or False is expressionList
                else:
                    if expressionList is False:
                        if not allOf:
                            expressionList = addedExpressions  # False or addedExpressions is addedExpressions
                        #else False and addedExpressions is False
                    elif expressionList is True:
                        if allOf:
                            expressionList = addedExpressions  # False or addedExpressions is addedExpressions
                        #else False and addedExpressions is False
                    else:
                        expressionList += addedExpressions
            return expressionList


        def propFilterExpression(filterAllOf, propFilter):
            """
            Create an expression for a single prop-filter element.

            @param propFilter: the L{PropertyFilter} element.
            @return: (filterProperyNames, expressions) tuple.  expression==True means list all results, expression==False means no results
            """

            def definedExpression(defined, allOf):
                if constant or propFilter.filter_name in ("N" , "FN", "UID", "SOURCE",):
                    return defined  # all records have this property so no records do not have it
                else:
                    if defined:
                        matchList = [MatchExpression(fieldName, u"", MatchType.startsWith) for fieldName in searchableFields]
                    else:
                        # this may generate inefficient LDAP query stirng
                        matchList = [MatchExpression(fieldName, u"", MatchType.startsWith, MatchFlags.NOT) for fieldName in searchableFields]
                    return andOrExpression(allOf, matchList)

            def andOrExpression(propFilterAllOf, matchList):
                matchList = list(set(matchList))
                if propFilterAllOf and len(matchList) > 1:
                    # add OR expression because parent will AND
                    return [CompoundExpression(matchList, Operand.OR), ]
                else:
                    return matchList


            def paramFilterElementExpression(propFilterAllOf, paramFilterElement): #@UnusedVariable

                params = ABDirectoryQueryResult.vcardPropToParamMap.get(propFilter.filter_name.upper())
                defined = params and paramFilterElement.filter_name.upper() in params

                #defined test
                if defined != paramFilterElement.defined:
                    return False

                #parameter value text match
                if defined and paramFilterElement.filters:
                    paramValues = params[paramFilterElement.filter_name.upper()]
                    if paramValues and paramFilterElement.filters[0].text.upper() not in paramValues:
                        return False

                return True


            def textMatchElementExpression(propFilterAllOf, textMatchElement):

                # pre process text match strings for ds query
                def getMatchStrings(propFilter, matchString):

                    if propFilter.filter_name in ("REV" , "BDAY",):
                        rawString = matchString
                        matchString = ""
                        for c in rawString:
                            if not c in "TZ-:":
                                matchString += c
                    elif propFilter.filter_name == "GEO":
                        matchString = ",".join(matchString.split(";"))

                    if propFilter.filter_name in ("N" , "ADR", "ORG",):
                        # for structured properties, change into multiple strings for ds query
                        if propFilter.filter_name == "ADR":
                            #split by newline and comma
                            rawStrings = ",".join(matchString.split("\n")).split(",")
                        else:
                            #split by space
                            rawStrings = matchString.split(" ")

                        # remove empty strings
                        matchStrings = []
                        for oneString in rawStrings:
                            if len(oneString):
                                matchStrings += [oneString, ]
                        return matchStrings

                    elif len(matchString):
                        return [matchString, ]
                    else:
                        return []
                    # end getMatchStrings

                if constant:
                    #FIXME: match is not implemented in twisteddaldav.query.Filter.TextMatch so use _match for now
                    return textMatchElement._match([constant, ])
                else:

                    matchStrings = getMatchStrings(propFilter, textMatchElement.text)

                    if not len(matchStrings):
                        # no searching text in binary ds attributes, so change to defined/not defined case
                        if textMatchElement.negate:
                            return definedExpression(False, propFilterAllOf)
                        # else fall through to attribute exists case below
                    else:

                        # use match_type where possible depending on property/attribute mapping
                        # FIXME: case-sensitive negate will not work.  This should return all all records in that case
                        matchType = MatchType.contains
                        if propFilter.filter_name in ("NICKNAME" , "TITLE" , "NOTE" , "UID", "URL", "N", "ADR", "ORG", "REV", "LABEL",):
                            if textMatchElement.match_type == "equals":
                                matchType = MatchType.equals
                            elif textMatchElement.match_type == "starts-with":
                                matchType = MatchType.startsWith
                            elif textMatchElement.match_type == "ends-with":
                                matchType = MatchType.endsWith

                        matchList = []
                        for matchString in matchStrings:
                            if textMatchElement.negate:
                                matchList = [MatchExpression(fieldName, matchString.decode("utf-8"), matchType, MatchFlags.NOT) for fieldName in searchableFields]
                            else:
                                matchList = [MatchExpression(fieldName, matchString.decode("utf-8"), matchType) for fieldName in searchableFields]
                            matchList.extend(matchList)
                        return andOrExpression(propFilterAllOf, matchList)

                # attribute exists search
                return definedExpression(True, propFilterAllOf)
                #end textMatchElementExpression()

            # searchablePropFilterAttrNames are attributes to be used by this propfilter's expression
            searchableFields = vcardPropToSearchableFieldMap.get(propFilter.filter_name, [])
            if isinstance(searchableFields, NamedConstant):
                searchableFields = (searchableFields,)

            constant = constantProperties.get(propFilter.filter_name)
            if not searchableFields and not constant:
                # not allAttrNames means propFilter.filter_name is not mapped
                # return None to try to match all items if this is the only property filter
                return None

            #create a textMatchElement for the IsNotDefined qualifier
            if isinstance(propFilter.qualifier, IsNotDefined):
                textMatchElement = TextMatch(carddavxml.TextMatch.fromString(""))
                textMatchElement.negate = True
                propFilter.filters.append(textMatchElement)

            # if only one propFilter, then use filterAllOf as propFilterAllOf to reduce subexpressions and simplify generated query string
            if len(propFilter.filters) == 1:
                propFilterAllOf = filterAllOf
            else:
                propFilterAllOf = propFilter.propfilter_test == "allof"

            propFilterExpressions = None
            for propFilterElement in propFilter.filters:
                propFilterExpression = None
                if isinstance(propFilterElement, ParameterFilter):
                    propFilterExpression = paramFilterElementExpression(propFilterAllOf, propFilterElement)
                elif isinstance(propFilterElement, TextMatch):
                    propFilterExpression = textMatchElementExpression(propFilterAllOf, propFilterElement)
                propFilterExpressions = combineExpressionLists(propFilterExpressions, propFilterAllOf, propFilterExpression)
                if isinstance(propFilterExpressions, bool) and propFilterAllOf != propFilterExpression:
                    break

            if isinstance(propFilterExpressions, list):
                propFilterExpressions = list(set(propFilterExpressions))
                if propFilterExpressions and (filterAllOf != propFilterAllOf):
                    propFilterExpressions = [CompoundExpression(propFilterExpressions, Operand.AND if propFilterAllOf else Operand.OR)]

            return propFilterExpressions
            #end propFilterExpression

        """
        Create an expression for a list of prop-filter elements.

        @param filterAllOf: the C{True} if parent filter test is "allof"
        @param propFilters: the C{list} of L{ComponentFilter} elements.
        @return: (filterProperyNames, expressions) tuple.  expression==True means list all results, expression==False means no results
        """
        expressions = None
        for propFilter in propFilters:

            propExpressions = propFilterExpression(filterAllOf, propFilter)
            expressions = combineExpressionLists(expressions, filterAllOf, propExpressions)

            # early loop exit
            if isinstance(expressions, bool) and filterAllOf != expressions:
                break

        # convert to needsAllRecords to return
        log.debug("expressionFromABFilter: expressions={q!r}", q=expressions,)
        if isinstance(expressions, list):
            expressions = list(set(expressions))
            if len(expressions) > 1:
                expr = CompoundExpression(expressions, Operand.AND if filterAllOf else Operand.OR)
            elif len(expressions):
                expr = expressions[0]
            else:
                expr = not filterAllOf  # empty expression list. should not happen
        elif expressions is None:
            expr = not filterAllOf
        else:
            # True or False
            expr = expressions

        properties = [propFilter.filter_name for propFilter in propFilters]

        return (tuple(set(properties)), expr)

    # Assume the filter is valid

    # Top-level filter contains zero or more prop-filters
    properties = tuple()
    expression = None
    if addressBookFilter:
        filterAllOf = addressBookFilter.filter_test == "allof"
        if len(addressBookFilter.children):
            properties, expression = propFilterListQuery(filterAllOf, addressBookFilter.children)
        else:
            expression = not filterAllOf

    #log.debug("expressionFromABFilter: recordType={rdn!r}, expression={q!r}, properties={pn}", rdn=recordType, q=expression, pn=properties)
    if expression:
        recordTypeExpression = MatchExpression(FieldName.recordType, recordType, MatchType.equals)
        if expression is True:
            expression = recordTypeExpression
        else:
            expression = CompoundExpression((expression, recordTypeExpression,), Operand.AND)

    #log.debug("expressionFromABFilter: expression={q!r}, properties={pn}", q=expression, pn=properties)
    return((properties, expression))



#===============================================================================
# Taken from obsolete twistedcaldav.directory.opendirctorybacker
# Work in Progress
#===============================================================================

from calendarserver.platform.darwin.od import dsattributes
from pycalendar.datetime import DateTime
from pycalendar.vcard.adr import Adr
from pycalendar.vcard.n import N
from twisted.internet.defer import deferredGenerator
from twistedcaldav.vcard import Component, Property, vCardProductID
from txdav.xml.base import twisted_dav_namespace, dav_namespace, parse_date, twisted_private_namespace
from txweb2.dav.resource import DAVPropertyMixIn
from txweb2.dav.util import joinURL
from txweb2.http_headers import MimeType, generateContentType, ETag
from xmlrpclib import datetime
import hashlib

addSourceProperty = False


class ABDirectoryQueryResult(DAVPropertyMixIn):
    """
    Result from ab query report or multiget on directory
    """

    log = Logger()

    # od attributes that may contribute to vcard properties
    # will be used to translate vCard queries to od queries

    vcardPropToDSAttrMap = {

        "FN": [
               dsattributes.kDS1AttrFirstName,
               dsattributes.kDS1AttrLastName,
               dsattributes.kDS1AttrMiddleName,
               dsattributes.kDSNAttrNamePrefix,
               dsattributes.kDSNAttrNameSuffix,
               dsattributes.kDS1AttrDistinguishedName,
               dsattributes.kDSNAttrRecordName,
               ],
        "N": [
               dsattributes.kDS1AttrFirstName,
               dsattributes.kDS1AttrLastName,
               dsattributes.kDS1AttrMiddleName,
               dsattributes.kDSNAttrNamePrefix,
               dsattributes.kDSNAttrNameSuffix,
               dsattributes.kDS1AttrDistinguishedName,
               dsattributes.kDSNAttrRecordName,
               ],
        "NICKNAME": [
                dsattributes.kDSNAttrNickName,
                ],
        # no binary searching
        "PHOTO": [
                (dsattributes.kDSNAttrJPEGPhoto, "base64"),
                ],
        "BDAY": [
                dsattributes.kDS1AttrBirthday,
                ],
        "ADR": [
                dsattributes.kDSNAttrBuilding,
                dsattributes.kDSNAttrStreet,
                dsattributes.kDSNAttrCity,
                dsattributes.kDSNAttrState,
                dsattributes.kDSNAttrPostalCode,
                dsattributes.kDSNAttrCountry,
                ],
        "LABEL": [
                dsattributes.kDSNAttrPostalAddress,
                dsattributes.kDSNAttrPostalAddressContacts,
                dsattributes.kDSNAttrAddressLine1,
                dsattributes.kDSNAttrAddressLine2,
                dsattributes.kDSNAttrAddressLine3,
                ],
         "TEL": [
                dsattributes.kDSNAttrPhoneNumber,
                dsattributes.kDSNAttrMobileNumber,
                dsattributes.kDSNAttrPagerNumber,
                dsattributes.kDSNAttrHomePhoneNumber,
                dsattributes.kDSNAttrPhoneContacts,
                dsattributes.kDSNAttrFaxNumber,
                #dsattributes.kDSNAttrAreaCode,
                ],
         "EMAIL": [
                dsattributes.kDSNAttrEMailAddress,
                dsattributes.kDSNAttrEMailContacts,
                ],
         "GEO": [
                dsattributes.kDSNAttrMapCoordinates,
                ],
         "TITLE": [
                dsattributes.kDSNAttrJobTitle,
                ],
         "ORG": [
                dsattributes.kDSNAttrCompany,
                dsattributes.kDSNAttrOrganizationName,
                dsattributes.kDSNAttrDepartment,
                ],
         "NOTE": [
                dsattributes.kDS1AttrComment,
                dsattributes.kDS1AttrNote,
                ],
         "REV": [
                dsattributes.kDS1AttrModificationTimestamp,
                ],
         "UID": [
                dsattributes.kDS1AttrGeneratedUID,
                dsattributes.kDSNAttrRecordName,
                ],
         "URL": [
                dsattributes.kDS1AttrWeblogURI,
                dsattributes.kDSNAttrURL,
                ],
         "KEY": [
                (dsattributes.kDSNAttrPGPPublicKey, "base64"),
                (dsattributes.kDS1AttrUserCertificate, "base64"),
                (dsattributes.kDS1AttrUserPKCS12Data, "base64"),
                (dsattributes.kDS1AttrUserSMIMECertificate, "base64"),
                ],
         "IMPP": [
                dsattributes.kDSNAttrIMHandle,
                ],
         "X-ABRELATEDNAMES": [
                dsattributes.kDSNAttrRelationships,
                ],
         "SOURCE": [
                dsattributes.kDS1AttrGeneratedUID,
                dsattributes.kDSNAttrRecordName,
                ],
    }

    allDSQueryAttributes = list(set([attr for lookupAttributes in vcardPropToDSAttrMap.values()
                                      for attr in lookupAttributes]))
    binaryDSAttrNames = [attr[0] for attr in allDSQueryAttributes
                                if isinstance(attr, tuple)]
    stringDSAttrNames = [attr for attr in allDSQueryAttributes
                                if isinstance(attr, str)]
    allDSAttrNames = stringDSAttrNames + binaryDSAttrNames

    # all possible generated parameters.
    vcardPropToParamMap = {
        "PHOTO": {"ENCODING": ("B",), "TYPE": ("JPEG",), },
        "ADR": {"TYPE": ("WORK", "PREF", "POSTAL", "PARCEL",), },
        "LABEL": {"TYPE": ("POSTAL", "PARCEL",)},
        "TEL": {"TYPE": None, },  # None means param can contain can be anything
        "EMAIL": {"TYPE": None, },
        "KEY": {"ENCODING": ("B",), "TYPE": ("PGPPUBILICKEY", "USERCERTIFICATE", "USERPKCS12DATA", "USERSMIMECERTIFICATE",)},
        "URL": {"TYPE": ("WEBLOG", "HOMEPAGE",)},
        "IMPP": {"TYPE": ("PREF",), "X-SERVICE-TYPE": None, },
        "X-ABRELATEDNAMES": {"TYPE": None, },
        "X-AIM": {"TYPE": ("PREF",), },
        "X-JABBER": {"TYPE": ("PREF",), },
        "X-MSN": {"TYPE": ("PREF",), },
        "X-ICQ": {"TYPE": ("PREF",), },
    }

    uidSeparator = "-cf07a1a2-"

    constantProperties = {
        # 3.6.3 PRODID Type Definition
        "PRODID": vCardProductID,
        # 3.6.9 VERSION Type Definition
        "VERSION": "3.0",
        }


    def __init__(self, directoryBackedAddressBook, recordAttributes,
                 kind=None,
                 additionalVCardProps=None,
                 ):

        self.log.debug("directoryBackedAddressBook={directoryBackedAddressBook}, attributes={attributes}, additionalVCardProps={additionalVCardProps}",
                       directoryBackedAddressBook=directoryBackedAddressBook, attributes=recordAttributes, additionalVCardProps=additionalVCardProps,)

        constantProperties = ABDirectoryQueryResult.constantProperties.copy()
        if additionalVCardProps:
            for key, value in additionalVCardProps.iteritems():
                if key not in constantProperties:
                    constantProperties[key] = value
        self.constantProperties = constantProperties
        self.log.debug("directoryBackedAddressBook={directoryBackedAddressBook}, attributes={attributes}, constantProperties={constantProperties}",
                       directoryBackedAddressBook=directoryBackedAddressBook, attributes=recordAttributes, constantProperties=self.constantProperties,)

        self._directoryBackedAddressBook = directoryBackedAddressBook
        self._vCard = None

        #clean attributes
        self.attributes = {}
        for key, values in recordAttributes.items():
            if key in ABDirectoryQueryResult.stringDSAttrNames:
                if isinstance(values, list):
                    self.attributes[key] = [removeControlChars(val).decode("utf8") for val in values]
                else:
                    self.attributes[key] = removeControlChars(values).decode("utf8")
            else:
                self.attributes[key] = values

        # find or create guid
        guid = self.firstValueForAttribute(dsattributes.kDS1AttrGeneratedUID)
        if not guid:
            nameUUIDStr = "".join(self.firstValueForAttribute(dsattributes.kDSNAttrRecordName).encode("base64").split("\n"))
            guid = ABDirectoryQueryResult.uidSeparator.join(["00000000", nameUUIDStr, ])
            #guid =  ABDirectoryQueryResult.uidSeparator.join(["d9a8e41b", nameUUIDStr,])

            self.attributes[dsattributes.kDS1AttrGeneratedUID] = guid

        if not kind:
            dsRecordTypeToKindMap = {
                           #dsattributes.kDSStdRecordTypePeople:"individual",
                           #dsattributes.kDSStdRecordTypeUsers:"individual",
                           dsattributes.kDSStdRecordTypeGroups: "group",
                           dsattributes.kDSStdRecordTypeLocations: "location",
                           dsattributes.kDSStdRecordTypeResources: "device",
                           }
            recordType = self.firstValueForAttribute(dsattributes.kDSNAttrRecordType)
            kind = dsRecordTypeToKindMap.get(recordType, "individual")
        self.kind = kind.lower()

        #generate a vCard here.  May throw an exception
        self.vCard()


    def __repr__(self):
        return "<{self.__class__.__name__}[{rn}({uid})]>".format(
            self=self,
            fn=self.vCard().propertyValue("FN"),
            uid=self.vCard().propertyValue("UID")
        )


    def __hash__(self):
        s = "".join([
              "{attr}:{values}".format(attr=attribute, values=self.valuesForAttribute(attribute),)
              for attribute in self.attributes
              ])
        return hash(s)


    def hasAttribute(self, attributeName):
        return self.valuesForAttribute(attributeName, None) is not None


    def valuesForAttribute(self, attributeName, default_values=[]):
        values = self.attributes.get(attributeName)
        if (values is None):
            return default_values
        elif not isinstance(values, list):
            values = [values, ]

        # ds templates often return empty attribute values
        #     get rid of them here
        nonEmptyValues = [(value.encode("utf-8") if isinstance(value, unicode) else value) for value in values if len(value) > 0]

        if len(nonEmptyValues) > 0:
            return nonEmptyValues
        else:
            return default_values


    def firstValueForAttribute(self, attributeName, default_value=""):
        values = self.attributes.get(attributeName)
        if values is None:
            return default_value
        elif isinstance(values, list):
            return values[0].encode("utf_8") if isinstance(values[0], unicode) else values[0]
        else:
            return values.encode("utf_8") if isinstance(values, unicode) else values


    def joinedValuesForAttribute(self, attributeName, separator=",", default_string=""):
        values = self.valuesForAttribute(attributeName, None)
        if not values:
            return default_string
        else:
            return separator.join(values)


    def isoDateStringForDateAttribute(self, attributeName, default_string=""):
        modDate = self.firstValueForAttribute(attributeName, default_string)
        revDate = None
        if modDate:
            if len(modDate) >= len("YYYYMMDD") and modDate[:8].isdigit():
                revDate = "{YYYY}-{MM}-{DD}".format(YYYY=modDate[:4], MM=modDate[4:6], DD=modDate[6:8],)
            if len(modDate) >= len("YYYYMMDDHHMMSS") and modDate[8:14].isdigit():
                revDate += "T{HH}:{MM}:{SS}Z".format(HH=modDate[8:10], MM=modDate[10:12], SS=modDate[12:14],)
        return revDate


    def vCard(self):

        def generateVCard():

            def isUniqueProperty(vcard, newProperty, ignoreParams=None):
                existingProperties = vcard.properties(newProperty.name())
                for existingProperty in existingProperties:
                    if ignoreParams:
                        existingProperty = existingProperty.duplicate()
                        for paramname, paramvalue in ignoreParams:
                            existingProperty.removeParameterValue(paramname, paramvalue)
                    if existingProperty == newProperty:
                        return False
                return True


            def addUniqueProperty(vcard, newProperty, ignoreParams=None, attrType=None, attrValue=None):
                if isUniqueProperty(vcard, newProperty, ignoreParams):
                    vcard.addProperty(newProperty)
                else:
                    if attrType and attrValue:
                        self.log.info("Ignoring attribute %r with value %r in creating property %r. A duplicate property already exists." % (attrType, attrValue, newProperty,))


            def addPropertyAndLabel(groupCount, label, propertyName, propertyValue, parameters=None):
                groupCount[0] += 1
                groupPrefix = "item%d" % groupCount[0]
                vcard.addProperty(Property(propertyName, propertyValue, params=parameters, group=groupPrefix))
                vcard.addProperty(Property("X-ABLabel", label, group=groupPrefix))


            # for attributes of the form  param:value
            def addPropertiesAndLabelsForPrefixedAttribute(groupCount, propertyPrefix, propertyName, attrType, defaultLabel, nolabelParamTypes=(), labelMap={}, specialParamType=None):
                preferred = True
                for attrValue in self.valuesForAttribute(attrType):
                    try:
                        colonIndex = attrValue.find(":")
                        if (colonIndex > len(attrValue) - 2):
                            raise ValueError("Nothing after colon.")

                        propertyValue = attrValue[colonIndex + 1:]
                        labelString = attrValue[:colonIndex] if colonIndex > 0 else defaultLabel
                        paramTypeString = labelString.upper()

                        if specialParamType:
                            parameters = {specialParamType: (paramTypeString,)}
                            if preferred:
                                parameters["TYPE"] = ("PREF",)
                        else:
                            # add PREF to first prop's parameters
                            paramTypeStrings = [paramTypeString, ]
                            if preferred and "PREF" != paramTypeString:
                                paramTypeStrings += ["PREF", ]
                            parameters = {"TYPE": paramTypeStrings, }

                        #special case for IMHandles which the param is the last part of the property like X-AIM or X-JABBER
                        if propertyPrefix:
                            propertyName = propertyPrefix + paramTypeString

                        # only add label prop if needed
                        if paramTypeString in nolabelParamTypes:
                            addUniqueProperty(vcard, Property(propertyName, attrValue[colonIndex + 1:], params=parameters), None, attrValue, attrType)
                        else:
                            # use special localizable addressbook labels where possible
                            localizedABLabelString = labelMap.get(labelString, labelString)
                            addPropertyAndLabel(groupCount, localizedABLabelString, propertyName, propertyValue, parameters)
                        preferred = False

                    except Exception, e:
                        self.log.debug(
                            "addPropertiesAndLabelsForPrefixedAttribute(): groupCount={groupCount}, propertyPrefix={propertyPrefix}, propertyName={propertyName}, nolabelParamTypes={nolabelParamTypes}, labelMap={labelMap}, attrType={attrType}",
                            groupCount=groupCount[0], propertyPrefix=propertyPrefix, propertyName=propertyName, nolabelParamTypes=nolabelParamTypes, labelMap=labelMap, attrType=attrType,
                        )
                        self.log.error(
                            "addPropertiesAndLabelsForPrefixedAttribute(): Trouble parsing attribute {attrType}, with value \"{attrValue}\".  Error = {e}",
                            attrType=attrType, attrValue=attrValue, e=e
                        )

            # create vCard
            vcard = Component("VCARD")
            groupCount = [0]

            # add constant properties - properties that are the same regardless of the record attributes
            for key, value in self.constantProperties.items():
                vcard.addProperty(Property(key, value))

            # 3.1 IDENTIFICATION TYPES http://tools.ietf.org/html/rfc2426#section-3.1
            # 3.1.1 FN Type Definition
            # dsattributes.kDS1AttrDistinguishedName,      # Users distinguished or real name
            #
            # full name is required but this is set in OpenDiretoryBackingRecord.__init__
            #vcard.addProperty(Property("FN", self.firstValueForAttribute(dsattributes.kDS1AttrDistinguishedName)))

            # 3.1.2 N Type Definition
            # dsattributes.kDS1AttrFirstName,           # Used for first name of user or person record.
            # dsattributes.kDS1AttrLastName,            # Used for the last name of user or person record.
            # dsattributes.kDS1AttrMiddleName,          #Used for the middle name of user or person record.
            # dsattributes.kDSNAttrNameSuffix,          # Represents the name suffix of a user or person.
                                                        #      ie. Jr., Sr., etc.
                                                        #      Usually found in user or people records (kDSStdRecordTypeUsers or
                                                        #      dsattributes.kDSStdRecordTypePeople).
            # dsattributes.kDSNAttrNamePrefix,          # Represents the title prefix of a user or person.
                                                        #      ie. Mr., Ms., Mrs., Dr., etc.
                                                        #      Usually found in user or people records (kDSStdRecordTypeUsers or
                                                        #      dsattributes.kDSStdRecordTypePeople).

            # name is required, so make sure we have one
            # vcard says: Each name attribute can be a string or a list of strings.
            if not self.hasAttribute(dsattributes.kDS1AttrFirstName) and not self.hasAttribute(dsattributes.kDS1AttrLastName):
                familyName = self.firstValueForAttribute(dsattributes.kDS1AttrDistinguishedName)
            else:
                familyName = self.valuesForAttribute(dsattributes.kDS1AttrLastName, "")

            nameObject = N(
                first=self.valuesForAttribute(dsattributes.kDS1AttrFirstName, ""),
                last=familyName,
                middle=self.valuesForAttribute(dsattributes.kDS1AttrMiddleName, ""),
                prefix=self.valuesForAttribute(dsattributes.kDSNAttrNamePrefix, ""),
                suffix=self.valuesForAttribute(dsattributes.kDSNAttrNameSuffix, ""),
            )
            vcard.addProperty(Property("N", nameObject))

            # set full name to Name with contiguous spaces stripped
            # it turns out that Address Book.app ignores FN and creates it fresh from N in ABRecord
            # so no reason to have FN distinct from N
            vcard.addProperty(Property("FN", nameObject.getFullName()))

            # 3.1.3 NICKNAME Type Definition
            # dsattributes.kDSNAttrNickName,            # Represents the nickname of a user or person.
                                                        #    Usually found in user or people records (kDSStdRecordTypeUsers or
                                                        #    dsattributes.kDSStdRecordTypePeople).
            for nickname in self.valuesForAttribute(dsattributes.kDSNAttrNickName):
                addUniqueProperty(vcard, Property("NICKNAME", nickname), None, dsattributes.kDSNAttrNickName, nickname)

            # 3.1.4 PHOTO Type Definition
            # dsattributes.kDSNAttrJPEGPhoto,           # Used to store binary picture data in JPEG format.
                                                        #      Usually found in user, people or group records (kDSStdRecordTypeUsers,
                                                        #      dsattributes.kDSStdRecordTypePeople,dsattributes.kDSStdRecordTypeGroups).
            # pyOpenDirectory always returns binary-encoded string

            for photo in self.valuesForAttribute(dsattributes.kDSNAttrJPEGPhoto):
                photo = "".join("".join(photo.split("\r")).split("\n")) # get rid of line folding: for PHOTO
                addUniqueProperty(vcard, Property("PHOTO", photo, params={"ENCODING": ["b", ], "TYPE": ["JPEG", ], }), None, dsattributes.kDSNAttrJPEGPhoto, photo)

            # 3.1.5 BDAY Type Definition
            # dsattributes.kDS1AttrBirthday,            # Single-valued attribute that defines the user's birthday.
                                                        #      Format is x.208 standard YYYYMMDDHHMMSSZ which we will require as GMT time.
                                                        #                               012345678901234

            birthdate = self.isoDateStringForDateAttribute(dsattributes.kDS1AttrBirthday)
            if birthdate:
                vcard.addProperty(Property("BDAY", DateTime.parseText(birthdate, fullISO=True)))

            # 3.2 Delivery Addressing Types http://tools.ietf.org/html/rfc2426#section-3.2
            #
            # 3.2.1 ADR Type Definition

            #address
            # vcard says: Each address attribute can be a string or a list of strings.
            extended = self.valuesForAttribute(dsattributes.kDSNAttrBuilding, "")
            street = self.valuesForAttribute(dsattributes.kDSNAttrStreet, "")
            city = self.valuesForAttribute(dsattributes.kDSNAttrCity, "")
            region = self.valuesForAttribute(dsattributes.kDSNAttrState, "")
            code = self.valuesForAttribute(dsattributes.kDSNAttrPostalCode, "")
            country = self.valuesForAttribute(dsattributes.kDSNAttrCountry, "")

            if len(extended) > 0 or len(street) > 0 or len(city) > 0 or len(region) > 0 or len(code) > 0 or len(country) > 0:
                vcard.addProperty(Property("ADR",
                    Adr(
                        #pobox = box,
                        extended=extended,
                        street=street,
                        locality=city,
                        region=region,
                        postalcode=code,
                        country=country,
                    ),
                    params={"TYPE": ["WORK", "PREF", "POSTAL", "PARCEL", ], }
                ))

            # 3.2.2 LABEL Type Definition
            #
            # dsattributes.kDSNAttrPostalAddress,           # The postal address usually excluding postal code.
            # dsattributes.kDSNAttrPostalAddressContacts,   # multi-valued attribute that defines a record's alternate postal addresses .
                                                            #      found in user records (kDSStdRecordTypeUsers) and resource records (kDSStdRecordTypeResources).
            # dsattributes.kDSNAttrAddressLine1,            # Line one of multiple lines of address data for a user.
            # dsattributes.kDSNAttrAddressLine2,            # Line two of multiple lines of address data for a user.
            # dsattributes.kDSNAttrAddressLine3,            # Line three of multiple lines of address data for a user.

            for label in self.valuesForAttribute(dsattributes.kDSNAttrPostalAddress):
                addUniqueProperty(vcard, Property("LABEL", label, params={"TYPE": ["POSTAL", "PARCEL", ]}), None, dsattributes.kDSNAttrPostalAddress, label)

            for label in self.valuesForAttribute(dsattributes.kDSNAttrPostalAddressContacts):
                addUniqueProperty(vcard, Property("LABEL", label, params={"TYPE": ["POSTAL", "PARCEL", ]}), None, dsattributes.kDSNAttrPostalAddressContacts, label)

            address = self.joinedValuesForAttribute(dsattributes.kDSNAttrAddressLine1)
            addressLine2 = self.joinedValuesForAttribute(dsattributes.kDSNAttrAddressLine2)
            if len(addressLine2) > 0:
                address += "\n" + addressLine2
            addressLine3 = self.joinedValuesForAttribute(dsattributes.kDSNAttrAddressLine3)
            if len(addressLine3) > 0:
                address += "\n" + addressLine3

            if len(address) > 0:
                vcard.addProperty(Property("LABEL", address, params={"TYPE": ["POSTAL", "PARCEL", ]}))

            # 3.3 TELECOMMUNICATIONS ADDRESSING TYPES http://tools.ietf.org/html/rfc2426#section-3.3
            # 3.3.1 TEL Type Definition
            #          TEL;TYPE=work,voice,pref,msg:+1-213-555-1234

            # dsattributes.kDSNAttrPhoneNumber,         # Telephone number of a user.
            # dsattributes.kDSNAttrMobileNumber,        # Represents the mobile numbers of a user or person.
                                                        #      Usually found in user or people records (kDSStdRecordTypeUsers or
                                                        #      dsattributes.kDSStdRecordTypePeople).
            # dsattributes.kDSNAttrFaxNumber,           # Represents the FAX numbers of a user or person.
                                                        # Usually found in user or people records (kDSStdRecordTypeUsers or
                                                        # kDSStdRecordTypePeople).
            # dsattributes.kDSNAttrPagerNumber,         # Represents the pager numbers of a user or person.
                                                        #      Usually found in user or people records (kDSStdRecordTypeUsers or
                                                        #      dsattributes.kDSStdRecordTypePeople).
            # dsattributes.kDSNAttrHomePhoneNumber,     # Home telephone number of a user or person.
            # dsattributes.kDSNAttrPhoneContacts,       # multi-valued attribute that defines a record's custom phone numbers .
                                                        #      found in user records (kDSStdRecordTypeUsers).
                                                        #      Example: home fax:408-555-4444

            params = {"TYPE": ["WORK", "PREF", "VOICE", ], }
            for phone in self.valuesForAttribute(dsattributes.kDSNAttrPhoneNumber):
                addUniqueProperty(vcard, Property("TEL", phone, params=params), (("TYPE", "PREF"),), phone, dsattributes.kDSNAttrPhoneNumber)
                params = {"TYPE": ["WORK", "VOICE", ], }

            params = {"TYPE": ["WORK", "PREF", "CELL", ], }
            for phone in self.valuesForAttribute(dsattributes.kDSNAttrMobileNumber):
                addUniqueProperty(vcard, Property("TEL", phone, params=params), (("TYPE", "PREF"),), phone, dsattributes.kDSNAttrMobileNumber)
                params = {"TYPE": ["WORK", "CELL", ], }

            params = {"TYPE": ["WORK", "PREF", "FAX", ], }
            for phone in self.valuesForAttribute(dsattributes.kDSNAttrFaxNumber):
                addUniqueProperty(vcard, Property("TEL", phone, params=params), (("TYPE", "PREF"),), phone, dsattributes.kDSNAttrFaxNumber)
                params = {"TYPE": ["WORK", "FAX", ], }

            params = {"TYPE": ["WORK", "PREF", "PAGER", ], }
            for phone in self.valuesForAttribute(dsattributes.kDSNAttrPagerNumber):
                addUniqueProperty(vcard, Property("TEL", phone, params=params), (("TYPE", "PREF"),), phone, dsattributes.kDSNAttrPagerNumber)
                params = {"TYPE": ["WORK", "PAGER", ], }

            params = {"TYPE": ["HOME", "PREF", "VOICE", ], }
            for phone in self.valuesForAttribute(dsattributes.kDSNAttrHomePhoneNumber):
                addUniqueProperty(vcard, Property("TEL", phone, params=params), (("TYPE", "PREF"),), phone, dsattributes.kDSNAttrHomePhoneNumber)
                params = {"TYPE": ["HOME", "VOICE", ], }

            addPropertiesAndLabelsForPrefixedAttribute(groupCount=groupCount, propertyPrefix=None, propertyName="TEL", defaultLabel="work",
                                                        nolabelParamTypes=("VOICE", "CELL", "FAX", "PAGER",),
                                                        attrType=dsattributes.kDSNAttrPhoneContacts,)

            """
            # EXTEND:  Use this attribute
            # dsattributes.kDSNAttrAreaCode,            # Area code of a user's phone number.
            """

            # 3.3.2 EMAIL Type Definition
            # dsattributes.kDSNAttrEMailAddress,        # Email address of usually a user record.

            # setup some params
            preferredWorkParams = {"TYPE": ["WORK", "PREF", "INTERNET", ], }
            workParams = {"TYPE": ["WORK", "INTERNET", ], }
            params = preferredWorkParams
            for emailAddress in self.valuesForAttribute(dsattributes.kDSNAttrEMailAddress):
                addUniqueProperty(vcard, Property("EMAIL", emailAddress, params=params), (("TYPE", "PREF"),), emailAddress, dsattributes.kDSNAttrEMailAddress)
                params = workParams

            # dsattributes.kDSNAttrEMailContacts,       # multi-valued attribute that defines a record's custom email addresses .
                                                        #    found in user records (kDSStdRecordTypeUsers).
                                                        #      Example: home:johndoe@mymail.com

            # check to see if parameters type are open ended. Could be any string
            addPropertiesAndLabelsForPrefixedAttribute(groupCount=groupCount, propertyPrefix=None, propertyName="EMAIL", defaultLabel="work",
                                                        nolabelParamTypes=("WORK", "HOME",),
                                                        attrType=dsattributes.kDSNAttrEMailContacts,)

            """
            # UNIMPLEMENTED:
            # 3.3.3 MAILER Type Definition
            """
            # 3.4 GEOGRAPHICAL TYPES http://tools.ietf.org/html/rfc2426#section-3.4
            """
            # UNIMPLEMENTED:
            # 3.4.1 TZ Type Definition
            """
            # 3.4.2 GEO Type Definition
            #dsattributes.kDSNAttrMapCoordinates,       # attribute that defines coordinates for a user's location .
                                                        #      Found in user records (kDSStdRecordTypeUsers) and resource records (kDSStdRecordTypeResources).
                                                        #      Example: 7.7,10.6
            for coordinate in self.valuesForAttribute(dsattributes.kDSNAttrMapCoordinates):
                parts = coordinate.split(",")
                if (len(parts) == 2):
                    vcard.addProperty(Property("GEO", parts))
                else:
                    log.info("Ignoring malformed attribute %r with value %r." % (dsattributes.kDSNAttrMapCoordinates, coordinate))
            #
            # 3.5 ORGANIZATIONAL TYPES http://tools.ietf.org/html/rfc2426#section-3.5
            #
            # 3.5.1 TITLE Type Definition
            for jobTitle in self.valuesForAttribute(dsattributes.kDSNAttrJobTitle):
                addUniqueProperty(vcard, Property("TITLE", jobTitle), None, dsattributes.kDSNAttrJobTitle, jobTitle)

            """
            # UNIMPLEMENTED:
            # 3.5.2 ROLE Type Definition
            # 3.5.3 LOGO Type Definition
            # 3.5.4 AGENT Type Definition
            """
            # 3.5.5 ORG Type Definition
            company = self.joinedValuesForAttribute(dsattributes.kDSNAttrCompany)
            if len(company) == 0:
                company = self.joinedValuesForAttribute(dsattributes.kDSNAttrOrganizationName)
            department = self.joinedValuesForAttribute(dsattributes.kDSNAttrDepartment)
            extra = self.joinedValuesForAttribute(dsattributes.kDSNAttrOrganizationInfo)
            if len(company) > 0 or len(department) > 0:
                vcard.addProperty(Property("ORG", (company, department, extra,),))

            # 3.6 EXPLANATORY TYPES http://tools.ietf.org/html/rfc2426#section-3.6
            """
            # UNIMPLEMENTED:
            # 3.6.1 CATEGORIES Type Definition
            """
            # 3.6.2 NOTE Type Definition
            # dsattributes.kDS1AttrComment,               # Attribute used for unformatted comment.
            # dsattributes.kDS1AttrNote,                  # Note attribute. Commonly used in printer records.
            notes = self.valuesForAttribute(dsattributes.kDS1AttrComment, []) + self.valuesForAttribute(dsattributes.kDS1AttrNote, [])
            if len(notes):
                vcard.addProperty(Property("NOTE", "\n".join(notes),))

            # 3.6.3 PRODID Type Definition
            #vcard.addProperty(Property("PRODID", vCardProductID + "//BUILD {build}".format(build=twistedcaldav.__version__))
            #vcard.addProperty(Property("PRODID", vCardProductID))
            # ADDED WITH CONTSTANT PROPERTIES

            # 3.6.4 REV Type Definition
            revDate = self.isoDateStringForDateAttribute(dsattributes.kDS1AttrModificationTimestamp)
            if revDate:
                vcard.addProperty(Property("REV", DateTime.parseText(revDate, fullISO=True)))

            """
            # UNIMPLEMENTED:
            # 3.6.5 SORT-STRING Type Definition
            # 3.6.6 SOUND Type Definition
            """
            # 3.6.7 UID Type Definition
            # dsattributes.kDS1AttrGeneratedUID,        # Used for 36 character (128 bit) unique ID. Usually found in user,
                                                        #      group, and computer records. An example value is "A579E95E-CDFE-4EBC-B7E7-F2158562170F".
                                                        #      The standard format contains 32 hex characters and four hyphen characters.

            vcard.addProperty(Property("UID", self.firstValueForAttribute(dsattributes.kDS1AttrGeneratedUID)))

            # 3.6.8 URL Type Definition
            # dsattributes.kDSNAttrURL,                 # List of URLs.
            # dsattributes.kDS1AttrWeblogURI,           # Single-valued attribute that defines the URI of a user's weblog.
                                                        #     Usually found in user records (kDSStdRecordTypeUsers).
                                                        #      Example: http://example.com/blog/jsmith
            for url in self.valuesForAttribute(dsattributes.kDS1AttrWeblogURI):
                addPropertyAndLabel(groupCount, "weblog", "URL", url, parameters={"TYPE": ["WEBLOG", ]})

            for url in self.valuesForAttribute(dsattributes.kDSNAttrURL):
                addPropertyAndLabel(groupCount, "_$!<HomePage>!$_", "URL", url, parameters={"TYPE": ["HOMEPAGE", ]})


            # 3.6.9 VERSION Type Definition
            # ALREADY ADDED
            #
            # 3.7 SECURITY TYPES http://tools.ietf.org/html/rfc2426#section-3.7
            # 3.7.1 CLASS Type Definition
            # ALREADY ADDED
            #
            # 3.7.2 KEY Type Definition
            #
            # dsattributes.kDSNAttrPGPPublicKey,        # Pretty Good Privacy public encryption key.
            # dsattributes.kDS1AttrUserCertificate,     # Attribute containing the binary of the user's certificate.
                                                        #       Usually found in user records. The certificate is data which identifies a user.
                                                        #       This data is attested to by a known party, and can be independently verified
                                                        #       by a third party.
            # dsattributes.kDS1AttrUserPKCS12Data,      # Attribute containing binary data in PKCS #12 format.
                                                        #       Usually found in user records. The value can contain keys, certificates,
                                                        #      and other related information and is encrypted with a passphrase.
            # dsattributes.kDS1AttrUserSMIMECertificate,# Attribute containing the binary of the user's SMIME certificate.
                                                        #       Usually found in user records. The certificate is data which identifies a user.
                                                        #       This data is attested to by a known party, and can be independently verified
                                                        #       by a third party. SMIME certificates are often used for signed or encrypted
                                                        #       emails.

            for key in self.valuesForAttribute(dsattributes.kDSNAttrPGPPublicKey):
                addUniqueProperty(vcard, Property("KEY", key, params={"ENCODING": ["b", ], "TYPE": ["PGPPublicKey", ]}), None, dsattributes.kDSNAttrPGPPublicKey, key)

            for key in self.valuesForAttribute(dsattributes.kDS1AttrUserCertificate):
                addUniqueProperty(vcard, Property("KEY", key, params={"ENCODING": ["b", ], "TYPE": ["UserCertificate", ]}), None, dsattributes.kDS1AttrUserCertificate, key)

            for key in self.valuesForAttribute(dsattributes.kDS1AttrUserPKCS12Data):
                addUniqueProperty(vcard, Property("KEY", key, params={"ENCODING": ["b", ], "TYPE": ["UserPKCS12Data", ]}), None, dsattributes.kDS1AttrUserPKCS12Data, key)

            for key in self.valuesForAttribute(dsattributes.kDS1AttrUserSMIMECertificate):
                addUniqueProperty(vcard, Property("KEY", key, params={"ENCODING": ["b", ], "TYPE": ["UserSMIMECertificate", ]}), None, dsattributes.kDS1AttrUserSMIMECertificate, key)

            """
            X- attributes, Address Book support
            """
            # X-AIM, X-JABBER, X-MSN, X-YAHOO, X-ICQ
            # instant messaging
            # dsattributes.kDSNAttrIMHandle,            # Represents the Instant Messaging handles of a user.
                                                        #      Values should be prefixed with the appropriate IM type
                                                        #       ie. AIM:, Jabber:, MSN:, Yahoo:, or ICQ:
                                                        #       Usually found in user records (kDSStdRecordTypeUsers).
            imNolabelParamTypes = ("AIM", "FACEBOOK", "GAGU-GAGU", "GOOGLE TALK", "ICQ", "JABBER", "MSN", "QQ", "SKYPE", "YAHOO",)
            addPropertiesAndLabelsForPrefixedAttribute(groupCount=groupCount, propertyPrefix="X-", propertyName=None, defaultLabel="aim",
                                                        nolabelParamTypes=imNolabelParamTypes,
                                                        attrType=dsattributes.kDSNAttrIMHandle,)

            # IMPP
            # Address Book's implementation of http://tools.ietf.org/html/rfc6350#section-6.4.3
            # adding IMPP property allows ab query report search on one property
            addPropertiesAndLabelsForPrefixedAttribute(groupCount=groupCount, propertyPrefix=None, propertyName="IMPP", defaultLabel="aim",
                                                        specialParamType="X-SERVICE-TYPE",
                                                        nolabelParamTypes=imNolabelParamTypes,
                                                        attrType=dsattributes.kDSNAttrIMHandle,)

            # X-ABRELATEDNAMES
            # dsattributes.kDSNAttrRelationships,       #      multi-valued attribute that defines the relationship to the record type .
                                                        #      found in user records (kDSStdRecordTypeUsers).
                                                        #      Example: brother:John
            addPropertiesAndLabelsForPrefixedAttribute(groupCount=groupCount, propertyPrefix=None, propertyName="X-ABRELATEDNAMES", defaultLabel="friend",
                                                        labelMap={"FATHER": "_$!<Father>!$_",
                                                            "MOTHER": "_$!<Mother>!$_",
                                                            "PARENT": "_$!<Parent>!$_",
                                                            "BROTHER": "_$!<Brother>!$_",
                                                            "SISTER": "_$!<Sister>!$_",
                                                            "CHILD": "_$!<Child>!$_",
                                                            "FRIEND": "_$!<Friend>!$_",
                                                            "SPOUSE": "_$!<Spouse>!$_",
                                                            "PARTNER": "_$!<Partner>!$_",
                                                            "ASSISTANT": "_$!<Assistant>!$_",
                                                            "MANAGER": "_$!<Manager>!$_", },
                                                        attrType=dsattributes.kDSNAttrRelationships,)

            # add apple-defined group vcard properties if record type is group
            if self.kind == "group":
                vcard.addProperty(Property("X-ADDRESSBOOKSERVER-KIND", "group"))

            # add members
            for memberguid in self.valuesForAttribute(dsattributes.kDSNAttrGroupMembers):
                vcard.addProperty(Property("X-ADDRESSBOOKSERVER-MEMBER", "urn:uuid:" + memberguid))

            """
            # UNIMPLEMENTED: X- attributes

            X-MAIDENNAME
            X-PHONETIC-FIRST-NAME
            X-PHONETIC-MIDDLE-NAME
            X-PHONETIC-LAST-NAME

            sattributes.kDS1AttrPicture,                # Represents the path of the picture for each user displayed in the login window.
                                                        #      Found in user records (kDSStdRecordTypeUsers).

            dsattributes.kDS1AttrMapGUID,               # Represents the GUID for a record's map.
            dsattributes.kDSNAttrMapURI,                # attribute that defines the URI of a user's location.

            dsattributes.kDSNAttrOrganizationInfo,      # Usually the organization info of a user.
            dsattributes.kDSNAttrAreaCode,              # Area code of a user's phone number.

            dsattributes.kDSNAttrMIME,                  # Data contained in this attribute type is a fully qualified MIME Type.

            """

            # 2.1.4 SOURCE Type http://tools.ietf.org/html/rfc2426#section-2.1.4
            #    If the SOURCE type is present, then its value provides information
            #    how to find the source for the vCard.

            # add the source, so that if the SOURCE is copied out and preserved, the client can refresh information
            # However, client should really do a ab-query report matching UID on /directory/ not a multiget.
            uri = joinURL(self._directoryBackedAddressBook.uri, vcard.propertyValue("UID") + ".vcf")

            # seems like this should be in some standard place.
            if config.EnableSSL and config.SSLPort:
                if config.SSLPort == 443:
                    source = "https://{server}{uri}".format(server=config.ServerHostName, uri=uri)
                else:
                    source = "https://{server}:{port}{uri}".format(server=config.ServerHostName, port=config.SSLPort, uri=uri)
            else:
                if config.HTTPPort == 80:
                    source = "https://{server}{uri}".format(server=config.ServerHostName, uri=uri)
                else:
                    source = "https://{server}:{port}{uri}".format(server=config.ServerHostName, port=config.HTTPPort, uri=uri)
            vcard.addProperty(Property("SOURCE", source))

            #  in 4.0 spec:
            # 6.1.4.  KIND http://tools.ietf.org/html/rfc6350#section-6.1.4
            #
            # see also: http://www.iana.org/assignments/vcard-elements/vcard-elements.xml
            #
            vcard.addProperty(Property("KIND", self.kind))

            # one more X- related to kind
            if self.kind == "org":
                vcard.addProperty(Property("X-ABShowAs", "COMPANY"))

            return vcard

        if not self._vCard:
            self._vCard = generateVCard()

        return self._vCard


    def vCardText(self):
        return str(self.vCard())


    def uri(self):
        return self.vCard().propertyValue("UID") + ".vcf"


    def hRef(self, parentURI=None):
        return davxml.HRef.fromString(joinURL(parentURI if parentURI else  self._directoryBackedAddressBook.uri, self.uri()))


    def readProperty(self, property, request):

        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()
        namespace, name = qname

        if namespace == dav_namespace:
            if name == "resourcetype":
                result = davxml.ResourceType.empty #@UndefinedVariable
                return result
            elif name == "getetag":
                result = davxml.GETETag(ETag(hashlib.md5(self.vCardText()).hexdigest()).generate())
                return result
            elif name == "getcontenttype":
                mimeType = MimeType('text', 'vcard', {})
                result = davxml.GETContentType(generateContentType(mimeType))
                return result
            elif name == "getcontentlength":
                result = davxml.GETContentLength.fromString(str(len(self.vCardText())))
                return result
            elif name == "getlastmodified":
                if self.vCard().hasProperty("REV"):
                    modDatetime = parse_date(self.vCard().propertyValue("REV"))
                else:
                    # use creation date attribute if it exists
                    creationDateString = self.isoDateStringForDateAttribute(dsattributes.kDS1AttrCreationTimestamp)
                    if creationDateString:
                        modDatetime = parse_date(creationDateString)
                    else:
                        modDatetime = datetime.datetime.utcnow()

                #strip time zone because time zones are unimplemented in davxml.GETLastModified.fromDate
                d = modDatetime.date()
                t = modDatetime.time()
                modDatetimeNoTZ = datetime.datetime(d.year, d.month, d.day, t.hour, t.minute, t.second, t.microsecond, None)
                result = davxml.GETLastModified.fromDate(modDatetimeNoTZ)
                return result
            elif name == "creationdate":
                creationDateString = self.isoDateStringForDateAttribute(dsattributes.kDS1AttrCreationTimestamp)
                if creationDateString:
                    creationDatetime = parse_date(creationDateString)
                elif self.vCard().hasProperty("REV"):  # use modification date property if it exists
                    creationDatetime = parse_date(self.vCard().propertyValue("REV"))
                else:
                    creationDatetime = datetime.datetime.utcnow()
                result = davxml.CreationDate.fromDate(creationDatetime)
                return result
            elif name == "displayname":
                # AddressBook.app uses N. Use FN or UID instead?
                result = davxml.DisplayName.fromString(self.vCard().propertyValue("N"))
                return result

        elif namespace == twisted_dav_namespace:
            return super(ABDirectoryQueryResult, self).readProperty(property, request)

        return self._directoryBackedAddressBook.readProperty(property, request)


    def listProperties(self, request):  # @UnusedVariable
        qnames = set(self.liveProperties())

        # Add dynamic live properties that exist
        dynamicLiveProperties = (
            (dav_namespace, "quota-available-bytes"),
            (dav_namespace, "quota-used-bytes"),
        )
        for dqname in dynamicLiveProperties:
            qnames.remove(dqname)

        for qname in self.deadProperties().list():
            if (qname not in qnames) and (qname[0] != twisted_private_namespace):
                qnames.add(qname)

        yield qnames

    listProperties = deferredGenerator(listProperties)



#remove illegal XML
def removeControlChars(utf8String):
    result = ''.join([c for c in utf8String if c not in "\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f"])
    return result
