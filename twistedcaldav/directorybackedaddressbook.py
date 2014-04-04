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
from twext.who.idirectory import FieldName
from twisted.internet.defer import deferredGenerator
from twisted.internet.defer import succeed, inlineCallbacks, maybeDeferred, \
    returnValue
from twisted.python.constants import NamedConstant
from twistedcaldav import carddavxml
from twistedcaldav.config import config
from twistedcaldav.resource import CalDAVResource
from txdav.carddav.datastore.query.filter import IsNotDefined, TextMatch, \
    ParameterFilter
from txdav.who.idirectory import FieldName as CalFieldName
from txdav.who.vcard import vCardKindToRecordTypeMap, recordTypeToVCardKindMap, \
    vCardPropToParamMap, vCardConstantProperties, vCardFromRecord
from txdav.xml import element as davxml
from txdav.xml.base import twisted_dav_namespace, dav_namespace, parse_date, \
    twisted_private_namespace
from txweb2 import responsecode
from txweb2.dav.resource import DAVPropertyMixIn
from txweb2.dav.resource import TwistedACLInheritable
from txweb2.dav.util import joinURL
from txweb2.http import HTTPError, StatusResponse
from txweb2.http_headers import MimeType, generateContentType, ETag
from xmlrpclib import datetime
import hashlib
import uuid

log = Logger()

MatchFlags_none = MatchFlags.NOT & ~MatchFlags.NOT  # can't import MatchFlags_none

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
        from twistedcaldav.simpleresource import SimpleCalDAVResource
        return SimpleCalDAVResource(principalCollections=self.principalCollections())
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
            resource_id = uuid.uuid5(uuid.UUID("5AAD67BF-86DD-42D7-9161-6AF977E4DAA3"), self.directory.guid).urn
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
    def doAddressBookDirectoryQuery(self, addressBookFilter, addressBookQuery, maxResults, defaultKind=None):
        """
        Get vCards for a given addressBookFilter and addressBookQuery
        """

        log.debug("doAddressBookDirectoryQuery: directory={directory} addressBookFilter={addressBookFilter}, addressBookQuery={addressBookQuery}, maxResults={maxResults}",
                  directory=self.directory, addressBookFilter=addressBookFilter, addressBookQuery=addressBookQuery, maxResults=maxResults)
        results = []
        limited = False
        maxQueryRecords = 0

        vcardPropToRecordFieldMap = {
            "FN": FieldName.fullNames,
            "N": FieldName.fullNames,
            "EMAIL": FieldName.emailAddresses,
            "UID": FieldName.uid,
            "ADR": (
                    CalFieldName.streetAddress,
                    CalFieldName.floor,
                    ),
            "KIND": FieldName.recordType,
            # LATER "X-ADDRESSBOOKSERVER-MEMBER": FieldName.membersUIDs,
        }

        propNames, expression = expressionFromABFilter(
            addressBookFilter, vcardPropToRecordFieldMap, vCardConstantProperties
        )

        if expression:
            if defaultKind and "KIND" not in propNames:
                defaultRecordExpression = MatchExpression(
                    FieldName.recordType,
                    vCardKindToRecordTypeMap[defaultKind],
                    MatchType.equals
                )
                if expression is True:
                    expression = defaultRecordExpression
                else:
                    expression = CompoundExpression(
                        (expression, defaultRecordExpression,),
                        Operand.AND
                    )
            elif expression is True: # True means all records
                allowedRecordTypes = set(self.directory.recordTypes()) & set(recordTypeToVCardKindMap.keys())
                expression = CompoundExpression(
                    [
                        MatchExpression(FieldName.recordType, recordType, MatchType.equals)
                            for recordType in allowedRecordTypes
                    ], Operand.OR
                )

            maxRecords = int(maxResults * 1.2)

            # keep trying query till we get results based on filter.  Especially when doing "all results" query
            while True:

                log.debug("doAddressBookDirectoryQuery: expression={expression!r}, propNames={propNames}", expression=expression, propNames=propNames)

                records = yield self.directory.recordsFromExpression(expression)
                log.debug("doAddressBookDirectoryQuery: #records={n}, records={records!r}", n=len(records), records=records)
                queryLimited = False

                vCardsResults = [(yield ABDirectoryQueryResult(self).generate(record)) for record in records]

                filteredResults = []
                for vCardResult in vCardsResults:
                    if addressBookFilter.match(vCardResult.vCard()):
                        filteredResults.append(vCardResult)
                    else:
                        log.debug("doAddressBookDirectoryQuery: vCard did not match filter:\n{vcard}", vcard=vCardResult.vCard())

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

        log.info("limited={l} #results={n}", l=limited, n=len(results))
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
                        propertyNames.append(addressProperty.attributes["name"])

            elif property.qname() == ("DAV:", "getetag"):
                # for a real etag == md5(vCard), we need all properties
                etagRequested = True

    return (etagRequested, propertyNames if len(propertyNames) else None)



def expressionFromABFilter(addressBookFilter, vcardPropToSearchableFieldMap, constantProperties={}):
    """
    Convert the supplied addressbook-query into a ds expression tree.

    @param addressBookFilter: the L{Filter} for the addressbook-query to convert.
    @param vcardPropToSearchableFieldMap: a mapping from vcard properties to searchable query attributes.
    @param constantProperties: a mapping of constant properties.  A query on a constant property will return all or None
    @return: (filterProperyNames, expressions) tuple.  expression==True means list all results, expression==False means no results
    """

    def propFilterListQuery(filterAllOf, propFilters):

        """
        Create an expression for a list of prop-filter elements.

        @param filterAllOf: the C{True} if parent filter test is "allof"
        @param propFilters: the C{list} of L{ComponentFilter} elements.
        @return: (filterProperyNames, expressions) tuple.  expression==True means list all results, expression==False means no results
        """

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
                        expressionList.extend(addedExpressions)
            return expressionList


        def propFilterExpression(filterAllOf, propFilter):
            """
            Create an expression for a single prop-filter element.

            @param propFilter: the L{PropertyFilter} element.
            @return: (filterProperyNames, expressions) tuple.  expression==True means list all results, expression==False means no results
            """

            def matchExpression(fieldName, matchString, matchType, matchFlags):
                # special case recordType field
                if fieldName == FieldName.recordType:
                    # change kind to record type
                    matchValue = vCardKindToRecordTypeMap.get(matchString.lower())
                    if matchValue is None:
                        matchValue = NamedConstant()
                        matchValue.description = u""

                    # change types and flags
                    matchFlags &= ~MatchFlags.caseInsensitive
                    matchType = MatchType.equals
                else:
                    matchValue = matchString.decode("utf-8")

                return MatchExpression(fieldName, matchValue, matchType, matchFlags)


            def definedExpression(defined, allOf):
                if constant or propFilter.filter_name in ("N" , "FN", "UID", "SOURCE", "KIND",):
                    return defined  # all records have this property so no records do not have it
                else:
                    # FIXME: The startsWith expression below, which works with LDAP and OD. is not currently supported
                    return True
                    '''
                    # this may generate inefficient LDAP query string
                    matchFlags = MatchFlags_none if defined else MatchFlags.NOT
                    matchList = [matchExpression(fieldName, "", MatchType.startsWith, matchFlags) for fieldName in searchableFields]
                    return andOrExpression(allOf, matchList)
                    '''


            def andOrExpression(propFilterAllOf, matchList):
                matchList = list(set(matchList))
                if propFilterAllOf and len(matchList) > 1:
                    # add OR expression because parent will AND
                    return [CompoundExpression(matchList, Operand.OR), ]
                else:
                    return matchList


            def paramFilterElementExpression(propFilterAllOf, paramFilterElement): #@UnusedVariable

                params = vCardPropToParamMap.get(propFilter.filter_name.upper())
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
                            matchFlags = None
                            if textMatchElement.collation == "i;unicode-casemap" and textMatchElement.negate:
                                matchFlags = MatchFlags.caseInsensitive | MatchFlags.NOT
                            elif textMatchElement.collation == "i;unicode-casemap":
                                matchFlags = MatchFlags.caseInsensitive
                            elif textMatchElement.negate:
                                matchFlags = MatchFlags.NOT
                            else:
                                matchFlags = MatchFlags_none

                            matchList = [matchExpression(fieldName, matchString, matchType, matchFlags) for fieldName in searchableFields]
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

        expressions = None
        for propFilter in propFilters:

            propExpressions = propFilterExpression(filterAllOf, propFilter)
            expressions = combineExpressionLists(expressions, filterAllOf, propExpressions)

            # early loop exit
            if isinstance(expressions, bool) and filterAllOf != expressions:
                break

        # convert to needsAllRecords to return
        # log.debug("expressionFromABFilter: expressions={q!r}", q=expressions,)
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

    # Top-level filter contains zero or more prop-filters
    properties = tuple()
    expression = None
    if addressBookFilter:
        filterAllOf = addressBookFilter.filter_test == "allof"
        if len(addressBookFilter.children):
            properties, expression = propFilterListQuery(filterAllOf, addressBookFilter.children)
        else:
            expression = not filterAllOf

    #log.debug("expressionFromABFilter: expression={q!r}, properties={pn}", q=expression, pn=properties)
    return((properties, expression))



class ABDirectoryQueryResult(DAVPropertyMixIn):
    """
    Result from ab query report or multiget on directory
    """

    def __init__(self, directoryBackedAddressBook,):

        self._directoryBackedAddressBook = directoryBackedAddressBook
        #self._vCard = None


    def __repr__(self):
        return "<{self.__class__.__name__}[{rn}({uid})]>".format(
            self=self,
            fn=self.vCard().propertyValue("FN"),
            uid=self.vCard().propertyValue("UID")
        )

    '''
    def __hash__(self):
        s = "".join([
              "{attr}:{values}".format(attr=attribute, values=self.valuesForAttribute(attribute),)
              for attribute in self.attributes
              ])
        return hash(s)
    '''

    @inlineCallbacks
    def generate(self, record, forceKind=None, addProps=None,):
        self._vCard = yield vCardFromRecord(record, forceKind, addProps, None)
        returnValue(self)


    def vCard(self):
        return self._vCard


    def vCardText(self):
        return str(self._vCard)


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
                    modDatetime = datetime.datetime.utcnow()

                #strip time zone because time zones are unimplemented in davxml.GETLastModified.fromDate
                d = modDatetime.date()
                t = modDatetime.time()
                modDatetimeNoTZ = datetime.datetime(d.year, d.month, d.day, t.hour, t.minute, t.second, t.microsecond, None)
                result = davxml.GETLastModified.fromDate(modDatetimeNoTZ)
                return result
            elif name == "creationdate":
                if self.vCard().hasProperty("REV"):  # use modification date property if it exists
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
