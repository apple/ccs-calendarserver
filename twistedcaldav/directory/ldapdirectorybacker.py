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
    "LdapDirectoryBackingService",
]

import traceback
import ldap

from twisted.internet.defer import inlineCallbacks, returnValue, succeed

from twistedcaldav.config import config
from twistedcaldav.directory.ldapdirectory import LdapDirectoryService, normalizeDNstr
from twistedcaldav.directory.opendirectorybacker import ABDirectoryQueryResult, dsFilterFromAddressBookFilter, propertiesInAddressBookQuery


class LdapDirectoryBackingService(LdapDirectoryService):
    """
    Directory backer for L{LdapDirectoryService}.
    """

    def __init__(self, params):
        self._actuallyConfigure(**params)

    def _actuallyConfigure(self, **params):
        
        self.log_debug("_actuallyConfigure: params=%s" % (params,))
        defaults = {
            "recordTypes": (), # for super
            "rdnSchema": {
                "base": "dc=example,dc=com",
                "queries": (
                    { #people
                        "rdn":"ou=people",
                        "vcardPropToLdapAttrMap" : { # maps vCard properties to searchable ldap attributes
                            "FN" : "cn",
                         },
                        "ldapAttrToDSAttrMap" : { # maps ldap attributes to ds attribute types
                            "cn" : "dsAttrTypeStandard:RealName",
                         },
                        "additionalVCardProps":None,
                    },
                ),

            },
            "removeDuplicateUIDs":True,      # remove vCards with duplicate UIDs
            "appleInternalServer":False,    # does magic in ABDirectoryQueryResult
            "maxQueryResults":0,            # max records returned
            "fakeETag":True,                # eTag is fake, otherwise it is md5(all attributes)
       }

        #params = self.getParams(params, defaults, ignored)
        def addDefaults(params, defaults, remove=None):
            for key in defaults:
                if not key in params:
                    params[key] = defaults[key]
            return params
            
        params = addDefaults(params, defaults)
        self.log_debug("_actuallyConfigure after addDefaults: params=%s" % (params,))
        
        # super does not like these extra params
        directoryBackedAddressBook=params["directoryBackedAddressBook"]
        del params["directoryBackedAddressBook"]
        appleInternalServer=params["appleInternalServer"]
        del params["appleInternalServer"] 
        maxQueryResults=params["maxQueryResults"]
        del params["maxQueryResults"]
        fakeETag=params["fakeETag"]
        del params["fakeETag"]
        removeDuplicateUIDs=params["removeDuplicateUIDs"]
        del params["removeDuplicateUIDs"]

        
        #standardize ds attributes type names
        # or we could just require dsAttrTypeStandard: prefix in the plist
        rdnSchema = params["rdnSchema"];
        for query in rdnSchema["queries"]:
            ldapAttrToDSAttrMap = query["ldapAttrToDSAttrMap"]
            for ldapAttrName, dsAttrNames in ldapAttrToDSAttrMap.iteritems():
                if not isinstance(dsAttrNames, list):
                    dsAttrNames = [dsAttrNames,]
                
                normalizedDSAttrNames = []
                for dsAttrName in dsAttrNames:
                    if not dsAttrName.startswith("dsAttrTypeStandard:") and not dsAttrName.startswith("dsAttrTypeNative:"):
                        normalizedDSAttrNames.append("dsAttrTypeStandard:" + dsAttrName)
                    else:
                        normalizedDSAttrNames.append(dsAttrName)
                
                # not needed, but tests code paths
                if len(normalizedDSAttrNames) > 1:
                    ldapAttrToDSAttrMap[ldapAttrName] = normalizedDSAttrNames
                else:
                    ldapAttrToDSAttrMap[ldapAttrName] = normalizedDSAttrNames[0]
               
                
        self.log_debug("_actuallyConfigure after clean: params=%s" % (params,))
 
        assert directoryBackedAddressBook is not None
        self.directoryBackedAddressBook = directoryBackedAddressBook
       
        self.maxQueryResults = maxQueryResults
        
        ### params for ABDirectoryQueryResult()
        self.fakeETag = fakeETag
        self.appleInternalServer = appleInternalServer
        self.removeDuplicateUIDs = removeDuplicateUIDs
 
        super(LdapDirectoryBackingService, self).__init__(params)
        
 
    def createCache(self):
         succeed(None)
                        

    @inlineCallbacks
    def _getLdapQueryResults(self, base, queryStr, attributes=None, maxResults=0, ldapAttrToDSAttrMap=None, ldapAttrTransforms=None, additionalVCardProps=None, kind=None ):
        """
        Get a list of ABDirectoryQueryResult for the given query with the given attributes.
        query == None gets all records. attribute == None gets ABDirectoryQueryResult.allDSQueryAttributes
        """
        limited = False
        resultsDictionary = {}
        
        # can't resist also using a timeout, 1 sec per request result for now
        timeout = maxResults

        self.log_debug("_getLdapQueryResults: LDAP query base=%s and filter=%s and attributes=%s timeout=%s resultLimit=%s" % (ldap.dn.dn2str(base), queryStr, attributes, timeout, maxResults))
        
        ldapSearchResult = (yield self.timedSearch(ldap.dn.dn2str(base), ldap.SCOPE_SUBTREE, filterstr=queryStr, attrlist=attributes, timeoutSeconds=timeout, resultLimit=maxResults))
        self.log_debug("_getLdapQueryResults: ldapSearchResult=%s" % (ldapSearchResult,))
        
        if maxResults and len(ldapSearchResult) >= maxResults:
            limited = True
            self.log_debug("_getLdapQueryResults: limit (= %d) reached." % (maxResults, ))

        for dn, ldapAttributes in ldapSearchResult:
            #dn = normalizeDNstr(dn)
            result = None
            try:
                if "dn" not in ldapAttributes:
                    ldapAttributes["dn"] = [normalizeDNstr(dn),]
                
                # make a dsRecordAttributes dict from the ldap attributes
                dsRecordAttributes = {}
                for ldapAttributeName, ldapAttributeValues in ldapAttributes.iteritems():

                    #self.log_debug("inspecting ldapAttributeName %s with values %s" % (ldapAttributeName, ldapAttributeValues,))

                    # get rid of '' values
                    ldapAttributeValues = [attr for attr in ldapAttributeValues if len(attr)]
                    
                    if len(ldapAttributeValues):
                                                
                        
                        dsAttributeNames = ldapAttrToDSAttrMap.get(ldapAttributeName)
                        if dsAttributeNames:
                            
                            if ldapAttrTransforms:
                            
                                # do value transforms
                                # need to expand this to cover all cases
                                # All this does now is to pull part of an ldap string out
                                # e.g: uid=renuka,ou=People,o=apple.com,o=email -> renuka
                                transforms = ldapAttrTransforms.get(ldapAttributeName)
                                if transforms:
                                    if not isinstance(transforms, list):
                                        transforms = [transforms,]
                                    
                                    transformedValues = []
                                    for ldapAttributeValue in ldapAttributeValues:
                                        transformedValue = ldapAttributeValue
                                        for valuePart in normalizeDNstr(ldapAttributeValue).split(","):
                                            kvPair = valuePart.split("=")
                                            if len(kvPair) == 2:
                                                for transform in transforms:
                                                    if transform.lower() == kvPair[0]:
                                                        transformedValue = kvPair[1]
                                                        break
                                                    
                                        transformedValues += [transformedValue,]
                                    
                                    if (ldapAttributeValues != transformedValues):
                                        self.log_debug("_getLdapQueryResults: %s %s transformed to %s" % (ldapAttributeName, ldapAttributeValues, transformedValues))
                                        ldapAttributeValues = transformedValues
                                                
                                        
                            
                            if not isinstance(dsAttributeNames, list):
                                dsAttributeNames = [dsAttributeNames,]
                                
                            for dsAttributeName in dsAttributeNames:
                                
                                # base64 encode binary attributes
                                if dsAttributeName in ABDirectoryQueryResult.binaryDSAttrNames:
                                    ldapAttributeValues = [attr.encode('base64') for attr in ldapAttributeValues]
                                
                                # add to dsRecordAttributes
                                if dsAttributeName not in dsRecordAttributes:
                                    dsRecordAttributes[dsAttributeName] = list()
                                    
                                dsRecordAttributes[dsAttributeName] = list(set(dsRecordAttributes[dsAttributeName] + ldapAttributeValues))
                                self.log_debug("doAddressBookQuery: dsRecordAttributes[%s] = %s" % (dsAttributeName, dsRecordAttributes[dsAttributeName],))

                # get a record for dsRecordAttributes 
                result = ABDirectoryQueryResult(self.directoryBackedAddressBook, dsRecordAttributes, kind=kind, additionalVCardProps=additionalVCardProps, appleInternalServer=self.appleInternalServer)
            except:
                traceback.print_exc()
                self.log_info("Could not get vcard for %s" % (dn,))
            else:
                uid = result.vCard().propertyValue("UID")

                if uid in resultsDictionary:
                    self.log_info("Record skipped due to duplicate UID: %s" % (dn,))
                    continue
                    
                self.log_debug("VCard text =\n%s" % (result.vCardText(), ))
                resultsDictionary[uid] = result                   

        self.log_debug("%s results (limited=%s)." % (len(resultsDictionary), limited))
        returnValue((resultsDictionary, limited, ))

    @inlineCallbacks
    def doAddressBookQuery(self, addressBookFilter, addressBookQuery, maxResults ):
        """
        Get vCards for a given addressBookFilter and addressBookQuery
        """
    
        results = {} if self.removeDuplicateUIDs else []
        limited = False
        
        #one ldap query for each rnd in queries
        for queryMap in self.rdnSchema["queries"]:

            rdn = queryMap["rdn"]
            vcardPropToLdapAttrMap = queryMap["vcardPropToLdapAttrMap"]
            ldapAttrToDSAttrMap = queryMap["ldapAttrToDSAttrMap"]
            additionalVCardProps = queryMap.get("additionalVCardProps")
            ldapAttrTransforms = queryMap.get("ldapAttrTransforms")
            kind = queryMap.get("kind", "individual")
            
            # add constants and KIND
            constantProperties = ABDirectoryQueryResult.constantProperties.copy()
            if additionalVCardProps:
                for key, value in additionalVCardProps.iteritems():
                    if key not in constantProperties:
                        constantProperties[key] = value
                        
            # add KIND as constant so that query can be skipped if addressBookFilter needs a different kind
            constantProperties["KIND"] = kind
            

            filterPropertyNames, dsFilter  = dsFilterFromAddressBookFilter( addressBookFilter, vcardPropToLdapAttrMap, constantProperties=constantProperties );
            self.log_debug("doAddressBookQuery: rdn=%s, query=%s, propertyNames=%s" % (rdn, dsFilter if isinstance(dsFilter, bool) else dsFilter.generate(), filterPropertyNames))

            if dsFilter:
                if dsFilter is True:
                    dsFilter = None
                
                # calculate minimum attributes needed for this query
                etagRequested, queryPropNames = propertiesInAddressBookQuery( addressBookQuery )
            
                if (etagRequested and not self.fakeETag) or not queryPropNames:
                    queryAttributes = ldapAttrToDSAttrMap.keys()
                elif queryPropNames:
                    '''
                    # To DO:  Need mapping from properties to returned attributes 
                    queryPropNames += filterPropertyNames
                    queryAttributes = []
                    for prop in queryPropNames:
                        attributes = ABDirectoryQueryResult.vcardPropToDSAttrMap.get(prop)
                        if attributes:
                            queryAttributes += attributes
                    '''
                            
                    queryAttributes =  ldapAttrToDSAttrMap.keys()
                    
                self.log_debug("doAddressBookQuery: etagRequested=%s, queryPropNames=%s, queryAttributes=%s" % (etagRequested, queryPropNames, queryAttributes,))
                
                #get all ldap attributes -- for debug
                if queryMap.get("getAllAttributes"):
                    queryAttributes = None
                   
                base =  ldap.dn.str2dn(rdn) + self.base
                
                queryStr = "(cn=*)"    # all results query  - should make a param
                #add additional filter from config
                queryFilter = queryMap.get("filter")
                if dsFilter and queryFilter:
                    queryStr = "(&%s%s)" % (queryFilter, dsFilter.generate())
                elif queryFilter:
                    queryStr = queryFilter
                elif dsFilter:
                    queryStr = dsFilter.generate()

                
                # keep trying ldap query till we get results based on filter.  Especially when doing "all results" query
                remainingMaxResults = maxResults - len(results) if maxResults else 0
                maxLdapResults = int(remainingMaxResults * 1.2)
    
                while True:
                    ldapQueryResultsDictionary, ldapQueryLimited = (yield self._getLdapQueryResults(base=base, 
                                                                                                    queryStr=queryStr, 
                                                                                                    attributes=queryAttributes, 
                                                                                                    maxResults=maxLdapResults, 
                                                                                                    kind=kind, 
                                                                                                    ldapAttrToDSAttrMap=ldapAttrToDSAttrMap, 
                                                                                                    ldapAttrTransforms=ldapAttrTransforms, 
                                                                                                    additionalVCardProps=additionalVCardProps))
                    
                    for uid, ldapQueryResult in ldapQueryResultsDictionary.iteritems():

                        if self.removeDuplicateUIDs and uid in results:
                            self.log_info("Record skipped due to duplicate UID: %s" % (uid,))
                            continue
                    
                        if not addressBookFilter.match(ldapQueryResult.vCard()):
                            self.log_debug("doAddressBookQuery did not match filter: %s (%s)" % (ldapQueryResult.vCard().propertyValue("FN"), uid,))
                            continue
                        
                        if self.removeDuplicateUIDs:
                            results[uid] = ldapQueryResult
                        else:
                            results += [ldapQueryResult,]              

                    
                    #no more results    
                    if not ldapQueryLimited:
                        break;
                    
                    # more than requested results
                    if maxResults and len(results) >= maxResults:
                        break
                    
                    # more than max report results
                    if len(results) >= config.MaxQueryWithDataResults:
                        break
                    
                    # more than self limit
                    if self.maxQueryResults and maxLdapResults >= self.maxQueryResults:
                        break
                    
                    # try again with 2x
                    maxLdapResults *= 2
                    if self.maxQueryResults and maxLdapResults > self.maxQueryResults:
                        maxLdapResults = self.maxQueryResults
                    
                if maxResults and len(results) >= maxResults:
                    break
                
        
        limited = maxResults and len(results) >= maxResults
                         
        self.log_info("limited %s len(results) %s" % (limited,len(results),))
        returnValue((results.values() if self.removeDuplicateUIDs else results, limited,))        

