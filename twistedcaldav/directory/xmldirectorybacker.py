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
Apple Open Directory directory service implementation for backing up directory-backed address books
"""

__all__ = [
    "XMLDirectoryBackingService",
]

import traceback

from calendarserver.platform.darwin.od import dsattributes, dsquery

from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.directory.opendirectorybacker import ABDirectoryQueryResult, dsFilterFromAddressBookFilter, propertiesInAddressBookQuery


class XMLDirectoryBackingService(XMLDirectoryService):
    """
    Directory backer for L{XMLDirectoryService}.
    """

    def __init__(self, params):
        self._actuallyConfigure(**params)

    def _actuallyConfigure(self, **params):

        self.log.debug("_actuallyConfigure: params=%s" % (params,))
        defaults = {
            "recordTypes": (self.recordType_users, self.recordType_groups,),
            "rdnSchema": {
                self.recordType_users : {
                    "vcardPropToDirRecordAttrMap" : {
                        "FN" : (
                                "fullName",
                                "shortNames",
                                "firstName",
                                "lastName",
                                ),
                        "N" : (
                                "fullName",
                                "shortNames",
                                "firstName",
                                "lastName",
                                ),
                        "EMAIL" : "emailAddresses",
                        "UID" : "guid",
                     },
                     "dirRecordAttrToDSAttrMap" : {
                        "guid" :            dsattributes.kDS1AttrGeneratedUID,
                        "fullName" :        dsattributes.kDS1AttrDistinguishedName,
                        "firstName" :       dsattributes.kDS1AttrFirstName,
                        "lastName" :        dsattributes.kDS1AttrLastName,
                        "emailAddresses" :  dsattributes.kDSNAttrEMailAddress,
                     },
                },
                self.recordType_groups : {
                    "vcardPropToDirRecordAttrMap" : {
                        "FN" : (
                                "fullName",
                                "shortNames",
                                "firstName",
                                "lastName",
                                ),
                        "N" : (
                                "fullName",
                                "shortNames",
                                "firstName",
                                "lastName",
                                ),
                        "EMAIL" : "emailAddresses",
                        "UID" : "guid",
                        "X-ADDRESSBOOKSERVER-MEMBER" : "members",
                     },
                     "dirRecordAttrToDSAttrMap" : {
                        "guid" :            dsattributes.kDS1AttrGeneratedUID,
                        "fullName" :        dsattributes.kDS1AttrDistinguishedName,
                        "firstName" :       dsattributes.kDS1AttrFirstName,
                        "lastName" :        dsattributes.kDS1AttrLastName,
                        "emailAddresses" :  dsattributes.kDSNAttrEMailAddress,
                        "members" :         dsattributes.kDSNAttrGroupMembers,
                     },
                },
            },
            "maxQueryResults":0,  # max records returned
            "sortResults":True,  # sort results by UID
            "implementNot":True,  # implement Not query by listing all records and subtracting
       }

        #params = self.getParams(params, defaults, ignored)
        def addDefaults(params, defaults, remove=None):
            for key in defaults:
                if not key in params:
                    params[key] = defaults[key]
            return params

        params = addDefaults(params, defaults)
        self.log.debug("_actuallyConfigure after addDefaults: params=%s" % (params,))

        # super does not like these extra params
        directoryBackedAddressBook = params["directoryBackedAddressBook"]
        #del params["directoryBackedAddressBook"]
        rdnSchema = params["rdnSchema"]
        del params["rdnSchema"]
        maxQueryResults = params["maxQueryResults"]
        del params["maxQueryResults"]
        sortResults = params["sortResults"]
        del params["sortResults"]
        implementNot = params["implementNot"]
        del params["implementNot"]


        assert directoryBackedAddressBook is not None
        self.directoryBackedAddressBook = directoryBackedAddressBook

        self.maxQueryResults = maxQueryResults
        self.sortResults = sortResults
        self.implementNot = implementNot
        self.rdnSchema = rdnSchema


        super(XMLDirectoryBackingService, self).__init__(params)


    def createCache(self):
        succeed(None)


    @inlineCallbacks
    def doAddressBookQuery(self, addressBookFilter, addressBookQuery, maxResults):
        """
        Get vCards for a given addressBookFilter and addressBookQuery
        """

        results = []
        limited = False

        for recordType in self.recordTypes():

            queryMap = self.rdnSchema[recordType]
            vcardPropToDirRecordAttrMap = queryMap["vcardPropToDirRecordAttrMap"]
            dirRecordAttrToDSAttrMap = queryMap["dirRecordAttrToDSAttrMap"]

            kind = {self.recordType_groups:"group",
                    self.recordType_locations:"location",
                    self.recordType_resources:"calendarresource",
                    }.get(recordType, "individual")

            constantProperties = ABDirectoryQueryResult.constantProperties.copy()
            constantProperties["KIND"] = kind
            # add KIND as constant so that query can be skipped if addressBookFilter needs a different kind

            filterPropertyNames, dsFilter = dsFilterFromAddressBookFilter(addressBookFilter, vcardPropToDirRecordAttrMap, constantProperties=constantProperties);
            self.log.debug("doAddressBookQuery: rdn=%s, query=%s, propertyNames=%s" % (recordType, dsFilter if isinstance(dsFilter, bool) else dsFilter.generate(), filterPropertyNames))

            if dsFilter:

                @inlineCallbacks
                def recordsForDSFilter(dsFilter, recordType):

                    """
                        Although recordsForDSFilter() exercises the dsFilter expression tree and recordsMatchingFields(),
                        it make little difference to the result of an address book query because of filtering.
                    """

                    if not isinstance(dsFilter, dsquery.expression):
                        #change  match list  into an expression and recurse
                        returnValue((yield recordsForDSFilter(dsquery.expression(dsquery.expression.OR, (dsFilter,)), recordType)))

                    else:
                        #self.log.debug("recordsForDSFilter:  dsFilter=%s" % (dsFilter.generate(), ))
                        dsFilterSubexpressions = dsFilter.subexpressions if isinstance(dsFilter.subexpressions, list) else (dsFilter.subexpressions,)
                        #self.log.debug("recordsForDSFilter: #subs %s" % (len(dsFilterSubexpressions), ))

                        # evaluate matches
                        matches = [match for match in dsFilterSubexpressions if isinstance(match, dsquery.match)]
                        fields = []
                        for match in matches:
                            #self.log.debug("recordsForDSFilter: match=%s" % (match.generate(), ))
                            xmlMatchType = {
                                dsattributes.eDSExact :        "exact",
                                dsattributes.eDSStartsWith :   "starts-with",
                                dsattributes.eDSContains :     "contains",
                            }.get(match.matchType)
                            if not xmlMatchType:
                                self.log.debug("recordsForDSFilter: match type=%s match not supported" % (match.generate(),))
                                returnValue(None)  # match type not supported by recordsMatchingFields()

                            fields += ((match.attribute, match.value, True, xmlMatchType,),)
                            #self.log.debug("recordsForDSFilter: fields=%s" % (fields,))

                        # if there were matches, call get records that match
                        result = None
                        if len(fields):
                            operand = "and" if dsFilter.operator == dsquery.expression.AND else "or"
                            #self.log.debug("recordsForDSFilter: recordsMatchingFields(fields=%s, operand=%s, recordType=%s)" % (fields, operand, recordType,))
                            result = set((yield self.recordsMatchingFields(fields, operand=operand, recordType=recordType)))
                            #self.log.debug("recordsForDSFilter: result=%s" % (result,))
                            if dsFilter.operator == dsquery.expression.NOT:
                                if self.implementNot:
                                    result = (yield self.listRecords(recordType)).difference(result)
                                else:
                                    self.log.debug("recordsForDSFilter: NOT expression not supported" % (match.generate(),))
                                    returnValue(None)


                        # evaluate subexpressions
                        subexpressions = [subexpression for subexpression in dsFilterSubexpressions if isinstance(subexpression, dsquery.expression)]
                        for subexpression in subexpressions:
                            #self.log.debug("recordsForDSFilter: subexpression=%s" % (subexpression.generate(), ))
                            subresult = (yield recordsForDSFilter(subexpression, recordType))
                            #self.log.debug("recordsForDSFilter: subresult=%s" % (subresult,))
                            if subresult is None:
                                returnValue(None)

                            if dsFilter.operator == dsquery.expression.NOT:
                                if self.implementNot:
                                    result = (yield self.listRecords(recordType)).difference(subresult)
                                else:
                                    self.log.debug("recordsForDSFilter: NOT expression not supported" % (match.generate(),))
                                    returnValue(None)
                            elif result is None:
                                result = subresult
                            elif dsFilter.operator == dsquery.expression.OR:
                                result = result.union(subresult)
                            else:
                                result = result.intersection(subresult)

                    #self.log.debug("recordsForDSFilter:  dsFilter=%s returning %s" % (dsFilter.generate(), result, ))
                    returnValue(result)

                # calculate minimum attributes needed for this query: results unused
                etagRequested, queryPropNames = propertiesInAddressBookQuery(addressBookQuery)
                self.log.debug("doAddressBookQuery: etagRequested=%s, queryPropNames=%s" % (etagRequested, queryPropNames,))

                # walk the expression tree
                if dsFilter is True:
                    xmlDirectoryRecords = None
                else:
                    xmlDirectoryRecords = (yield recordsForDSFilter(dsFilter, recordType))
                self.log.debug("doAddressBookQuery: #xmlDirectoryRecords %s" % (len(xmlDirectoryRecords) if xmlDirectoryRecords is not None else xmlDirectoryRecords,))

                if xmlDirectoryRecords is None:
                    xmlDirectoryRecords = (yield self.listRecords(recordType))
                    self.log.debug("doAddressBookQuery: all #xmlDirectoryRecords %s" % (len(xmlDirectoryRecords),))

                for xmlDirectoryRecord in xmlDirectoryRecords:

                    def dsRecordAttributesFromDirectoryRecord(xmlDirectoryRecord):
                        #FIXME should filter based on request
                        dsRecordAttributes = {}
                        for attr in dirRecordAttrToDSAttrMap:
                            try:
                                if attr == "members":
                                    value = [member.guid for member in xmlDirectoryRecord.members()]
                                else:
                                    value = getattr(xmlDirectoryRecord, attr)
                                if value:
                                    dsRecordAttributes[dirRecordAttrToDSAttrMap[attr]] = value
                            except AttributeError:
                                self.log.info("Could not get attribute %s from record %s" % (attr, xmlDirectoryRecord,))
                                pass
                        return dsRecordAttributes

                    result = None
                    dsRecordAttributes = dsRecordAttributesFromDirectoryRecord(xmlDirectoryRecord)
                    try:
                        result = ABDirectoryQueryResult(self.directoryBackedAddressBook, dsRecordAttributes, kind=kind)
                    except:
                        traceback.print_exc()
                        self.log.info("Could not get vcard for %s" % (xmlDirectoryRecord,))
                    else:
                        self.log.debug("doAddressBookQuery: VCard text =\n%s" % (result.vCard(),))
                        if addressBookFilter.match(result.vCard()):
                            results.append(result)
                        else:
                            # should also filter for duplicate UIDs
                            self.log.debug("doAddressBookQuery did not match filter: %s (%s)" % (result.vCard().propertyValue("FN"), result.vCard().propertyValue("UID"),))

                if len(results) >= maxResults:
                    limited = True
                    break

        #sort results so that CalDAVTester can have consistent results when it uses limits
        if self.sortResults:
            results = sorted(list(results), key=lambda result:result.vCard().propertyValue("UID"))

        self.log.info("limited  %s len(results) %s" % (limited, len(results),))
        returnValue((results, limited,))

