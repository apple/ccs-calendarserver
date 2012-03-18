##
# Copyright (c) 2006-2010 Apple Inc. All rights reserved.
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
    "OpenDirectoryBackingService", "VCardRecord",
]

import traceback
import hashlib

import os
import sys
import time

from os import listdir
from os.path import join, abspath
from tempfile import mkstemp, gettempdir
from random import random

from pycalendar.n import N
from pycalendar.adr import Adr
from pycalendar.datetime import PyCalendarDateTime

from socket import getfqdn

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, deferredGenerator, succeed
from twext.python.filepath import CachingFilePath as FilePath
from txdav.xml import element as davxml
from txdav.xml.base import twisted_dav_namespace, dav_namespace, parse_date, twisted_private_namespace
from twext.web2.dav.resource import DAVPropertyMixIn
from twext.web2.dav.util import joinURL
from twext.web2.http_headers import MimeType, generateContentType, ETag


from twistedcaldav import customxml, carddavxml
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.config import config
from twistedcaldav.directory.directory import DirectoryService, DirectoryRecord
from twistedcaldav.memcachelock import MemcacheLock, MemcacheLockTimeoutError
from twistedcaldav.query import addressbookqueryfilter
from twistedcaldav.vcard import Component, Property, vCardProductID

from xmlrpclib import datetime

from calendarserver.platform.darwin.od import dsattributes, dsquery
from twisted.python.reflect import namedModule

class OpenDirectoryBackingService(DirectoryService):
    """
    Open Directory implementation of L{IDirectoryService}.
    """

    baseGUID = "BF07A1A2-5BB5-4A4D-A59A-67260EA7E143"
    
    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.realmName, )

    def __init__(self, params):
        self._actuallyConfigure(**params)

    def _actuallyConfigure(
        self, queryPeopleRecords=True, 
        peopleNode = "/Search/Contacts",
        queryUserRecords=True, 
        userNode = "/Search",
        maxDSQueryRecords = 0,            # maximum number of records requested for any ds query
        
        queryDSLocal = False,              #query in DSLocal -- debug
        dsLocalCacheTimeout = 30,
        ignoreSystemRecords = True,
        
        liveQuery = True,                    # query directory service as needed
        fakeETag = True,                # eTag is not reliable if True 
        
        cacheQuery = False,
        cacheTimeout=30,                # cache timeout            
        
        addDSAttrXProperties=False,        # add dsattributes to vcards as "X-" attributes
        standardizeSyntheticUIDs = False,  # use simple synthetic UIDs --- good for testing
        appleInternalServer=False,
        
        additionalAttributes=[],
        allowedAttributes=[],
        directoryBackedAddressBook=None
    ):
        """
        @queryPeopleRecords: C{True} to query for People records
        @queryUserRecords: C{True} to query for User records
        @maxDSQueryRecords: maximum number of (unfiltered) ds records retrieved before raising 
            NumberOfMatchesWithinLimits exception or returning results
        @dsLocalCacheTimeout: how log to keep cache of DSLocal records
        @liveQuery: C{True} to query the directory as needed
        @fakeETag: C{True} to use a fake eTag; allows ds queries with partial attributes
        @cacheQuery: C{True} to query the directory and cache results
        @cacheTimeout: if caching, the average cache timeout
        @standardizeSyntheticUIDs: C{True} when creating synthetic UID (==f(Node, Type, Record Name)), 
            use a standard Node name. This allows testing with the same UID on different hosts
        @allowedAttributes: list of DSAttributes that are used to create VCards

        """
        assert directoryBackedAddressBook is not None
        self.directoryBackedAddressBook = directoryBackedAddressBook

        self.peopleDirectory = None
        self.peopleNode = None
        self.userDirectory = None
        self.userNode = None
        
        self.realmName = None # needed for super

        self.odModule = namedModule(config.OpenDirectoryModule)
        
        if queryPeopleRecords or not queryUserRecords:
            self.peopleNode = peopleNode
            try:
                self.peopleDirectory = self.odModule.odInit(peopleNode)
            except self.odModule.ODError, e:
                self.log_error("Open Directory (node=%s) Initialization error: %s" % (peopleNode, e))
                raise
            self.realmName = peopleNode

        if queryUserRecords:
            if self.peopleNode == userNode:          # use sane directory and node if they are equal
                self.userNode = self.peopleNode
                self.userDirectory = self.peopleDirectory
            else:
                self.userNode = userNode
                try:
                    self.userDirectory = self.odModule.odInit(userNode)
                except self.odModule.ODError, e:
                    self.log_error("Open Directory (node=%s) Initialization error: %s" % (userNode, e))
                    raise
                if self.realmName:
                    self.realmName += "+" + userNode
                else:
                    self.realmName = userNode
        
        
        self.maxDSQueryRecords = maxDSQueryRecords

        self.ignoreSystemRecords = ignoreSystemRecords
        self.queryDSLocal = queryDSLocal
        self.dsLocalCacheTimeout = dsLocalCacheTimeout

        self.liveQuery = liveQuery or not cacheQuery
        self.fakeETag = fakeETag

        self.cacheQuery = cacheQuery
        
        self.cacheTimeout = cacheTimeout if cacheTimeout > 0 else 30
        
        self.addDSAttrXProperties = addDSAttrXProperties
        self.standardizeSyntheticUIDs = standardizeSyntheticUIDs
        self.appleInternalServer = appleInternalServer
        
        self.additionalAttributes = additionalAttributes
        # filter allows attributes, but make sure there are a minimum of attributes for functionality
        if allowedAttributes:
            self.allowedDSQueryAttributes = sorted(list(set(
                                                [attr for attr in VCardRecord.allDSQueryAttributes
                                                    if (isinstance(attr, str) and attr in allowedAttributes) or
                                                       (isinstance(attr, tuple) and attr[0] in allowedAttributes)] +
                                                VCardRecord.dsqueryAttributesForProperty.get("X-INTERNAL-REQUIRED")
                                                )))
            if (self.allowedDSQueryAttributes != VCardRecord.allDSQueryAttributes):
                self.log_info("Allowed DS query attributes = %r" % (self.allowedDSQueryAttributes, ))
        else:
            self.allowedDSQueryAttributes = VCardRecord.allDSQueryAttributes
        
        #self.returnedAttributes = VCardRecord.allDSQueryAttributes
        self.returnedAttributes = self.allowedDSQueryAttributes
        
            
        
        
        self._dsLocalRecords = []
        self._nextDSLocalQueryTime = 0
        
        # get this now once
        hostname = getfqdn()
        if hostname:
            self.defaultNodeName = "/LDAPv3/" + hostname
        else:
            self.defaultNodeName = None
        
        #cleanup
        self._cleanupTime = time.time()
        
        # file system locks
        self._initLockPath = join(config.DocumentRoot, ".directory_address_book_create_lock")
        self._createdLockPath = join(config.DocumentRoot, ".directory_address_book_created_lock")
        self._updateLockPath = join(config.DocumentRoot, ".directory_address_book_update_lock")
        self._tmpDirAddressBookLockPath = join(config.DocumentRoot, ".directory_address_book_tmpFolder_lock")
        
        self._updateLock = MemcacheLock("OpenDirectoryBacker", self._updateLockPath)
        self._tmpDirAddressBookLock = MemcacheLock("OpenDirectoryBacker", self._tmpDirAddressBookLockPath)        
                
        # optimization so we don't have to always get create lock
        self._triedCreateLock = False
        self._created = False


    def __cmp__(self, other):
        if not isinstance(other, DirectoryRecord):
            return super(DirectoryRecord, self).__eq__(other)

        for attr in ("directory", "node"):
            diff = cmp(getattr(self, attr), getattr(other, attr))
            if diff != 0:
                return diff
        return 0

    def __hash__(self):
        h = hash(self.__class__.__name__)
        for attr in ("node",):
            h = (h + hash(getattr(self, attr))) & sys.maxint
        return h
    
    @inlineCallbacks
    def available(self):
        if not self._triedCreateLock:
            returnValue( False )
        elif not self._created:
            createdLock = MemcacheLock("OpenDirectoryBacker", self._createdLockPath)
            self.log_debug("blocking on lock of: \"%s\")" % self._createdLockPath)
            self._created = (yield createdLock.locked())
        
        returnValue(self._created)
        
    
    def updateLock(self):
        return self._updateLock

    
    @inlineCallbacks
    def createCache(self):
        """
        If caching, create the cache for the first time.
        """
        
        if not self.liveQuery:
            self.log_info("loading directory address book")
    
            # get init lock
            initLock = MemcacheLock("OpenDirectoryBacker", self._initLockPath, timeout=0)
            self.log_debug("Attempt lock of: \"%s\")" % self._initLockPath)
            gotCreateLock = False
            try:
                yield initLock.acquire()
                gotCreateLock = True
            except MemcacheLockTimeoutError:
                pass
                
            self._triedCreateLock = True
            
            if gotCreateLock:
                self.log_debug("Got lock!")
                yield self._refreshCache( flushCache=False, creating=True )
            else:
                self.log_debug("Could not get lock - directory address book will be filled by peer")
                        
        

    @inlineCallbacks
    def _refreshCache(self, flushCache=False, creating=False, reschedule=True, query=None, attributes=None, keepLock=False, clear=False, maxRecords=0 ):
        """
        refresh the cache.
        """

        #print("_refreshCache:, flushCache=%s, creating=%s, reschedule=%s, query = %s" % (flushCache, creating, reschedule, "None" if query is None else query.generate(),))

        def refreshLater():
            #
            # Add jitter/fuzz factor to avoid stampede for large OD query
            #
            cacheTimeout = min(self.cacheTimeout, 60) * 60
            cacheTimeout = (cacheTimeout * random()) - (cacheTimeout / 2)
            cacheTimeout += self.cacheTimeout * 60
            reactor.callLater(cacheTimeout, self._refreshCache) #@UndefinedVariable
            self.log_info("Refresh directory address book in %d minutes %d seconds" % divmod(cacheTimeout, 60))          

        def cleanupLater():
            
            # try to cancel previous call if last clean up was less than 15 minutes ago
            if (time.time() - self._cleanupTime) < 15*60:
                try:
                    self._lastCleanupCall.cancel()
                except:
                    pass
            
            #
            # Add jitter/fuzz factor 
            #
            nom = 120
            later = nom* (random() + .5)
            self._lastCleanupCall = reactor.callLater(later, removeTmpAddressBooks) #@UndefinedVariable
            self.log_info("Remove temporary directory address books in %d minutes %d seconds" % divmod(later, 60))          


        def getTmpDirAndTmpFilePrefixSuffix():
            # need to have temp file on same volumes as documents so that move works
            absDocPath = abspath(config.DocumentRoot)
            if absDocPath.startswith("/Volumes/"):
                tmpDir = absDocPath
                prefix = ".directoryAddressBook-"
            else:
                tmpDir = gettempdir()
                prefix = "directoryAddressBook-"
            
            return (tmpDir, prefix, ".tmp")
            
        def makeTmpFilename():
            tmpDir, prefix, suffix = getTmpDirAndTmpFilePrefixSuffix()
            fd, fname = mkstemp(suffix=suffix, prefix=prefix, dir=tmpDir)
            os.close(fd)
            os.remove(fname)
            return fname
        
        @inlineCallbacks
        def removeTmpAddressBooks():
            self.log_info("Checking for temporary directory address books")
            tmpDir, prefix, suffix = getTmpDirAndTmpFilePrefixSuffix()

            tmpDirLock = self._tmpDirAddressBookLock
            self.log_debug("blocking on lock of: \"%s\")" % self._tmpDirAddressBookLockPath)
            yield tmpDirLock.acquire()
            
            try:
                for name in listdir(tmpDir):
                    if name.startswith(prefix) and name.endswith(suffix):
                        try:
                            path = join(tmpDir, name)
                            self.log_info("Deleting temporary directory address book at: %s" %    path)
                            FilePath(path).remove()
                            self.log_debug("Done deleting")
                        except:
                            self.log_info("Deletion failed")
            finally:
                self.log_debug("unlocking: \"%s\")" % self._tmpDirAddressBookLockPath)
                yield tmpDirLock.release()
            
            self._cleanupTime = time.time()

        
        updateLock = None
        limited = False
        try:
            
            try:
                # get the records
                if clear:
                    records = {}
                else:
                    records, limited = (yield self._getDirectoryRecords(query, attributes, maxRecords))
                
                # calculate the hash
                # simple for now, could use MD5 digest if too many collisions     
                newAddressBookCTag = customxml.GETCTag(str(hash(self.baseGUID + ":" + self.realmName + ":" + "".join(str(hash(records[key])) for key in records.keys()))))
                
                # get the old hash
                oldAddressBookCTag = ""
                updateLock = self.updateLock()
                self.log_debug("blocking on lock of: \"%s\")" % self._updateLockPath)
                yield updateLock.acquire()
                
                if not flushCache:
                    # get update lock
                    try:
                        oldAddressBookCTag = self.directoryBackedAddressBook.readDeadProperty((calendarserver_namespace, "getctag"))
                    except:
                        oldAddressBookCTag = ""
    
                self.log_debug("Comparing {http://calendarserver.org/ns/}getctag: new = %s, old = %s" % (newAddressBookCTag, oldAddressBookCTag))
                if str(newAddressBookCTag) != str(oldAddressBookCTag):
                    
                    self.log_debug("unlocking: \"%s\")" % self._updateLockPath)
                    yield updateLock.release()
                    updateLock = None
                    

                if not keepLock:
                    self.log_debug("unlocking: \"%s\")" % self._updateLockPath)
                    yield updateLock.release()
                    updateLock = None
                    
            except:
                cleanupLater()
                if reschedule:
                    refreshLater() 
                raise
            
            if creating:
                createdLock = MemcacheLock("OpenDirectoryBacker", self._createdLockPath)
                self.log_debug("blocking on lock of: \"%s\")" % self._createdLockPath)
                yield createdLock.acquire()
            
            cleanupLater()
            if reschedule:
                refreshLater() 
        
        except:
            if updateLock:
                yield updateLock.release()
            raise

        returnValue( (updateLock, limited) )



    def _getDSLocalRecords(self):
        
        def generateDSLocalRecords():
                        
            records = {}
            
            recordTypes = [dsattributes.kDSStdRecordTypePeople, dsattributes.kDSStdRecordTypeUsers, ]
            try:
                localNodeDirectory = self.odModule.odInit("/Local/Default")
                self.log_debug("opendirectory.listAllRecordsWithAttributes_list(%r,%r,%r)" % (
                        "/DSLocal",
                        recordTypes,
                        self.returnedAttributes,
                    ))
                results = list(self.odModule.listAllRecordsWithAttributes_list(
                        localNodeDirectory,
                        recordTypes,
                        self.returnedAttributes,
                    ))
            except self.odModule.ODError, ex:
                self.log_error("Open Directory (node=%s) error: %s" % ("/Local/Default", str(ex)))
                raise
            
            self._dsLocalRecords = []        
            for (recordShortName, value) in results: #@UnusedVariable
                
                record = VCardRecord(self, value, "/Local/Default")

                if self.ignoreSystemRecords:
                    # remove system users and people
                    if record.guid.startswith("FFFFEEEE-DDDD-CCCC-BBBB-AAAA"):
                        self.log_info("Ignoring vcard for system record %s"  % (record,))
                        continue

                if record.guid in records:
                    self.log_info("Record skipped due to conflict (duplicate uuid): %s" % (record,))
                else:
                    try:
                        vCardText = record.vCardText()
                    except:
                        traceback.print_exc()
                        self.log_info("Could not get vcard for record %s" % (record,))
                    else:
                        self.log_debug("VCard text =\n%s" % (vCardText, ))
                        records[record.guid] = record                   
    
            return records
        

        if not self.liveQuery or not self.queryDSLocal:
            return {}
        
        if time.time() > self._nextDSLocalQueryTime:
            self._dsLocalRecords = generateDSLocalRecords()
            # Add jitter/fuzz factor 
            self._nextDSLocalQueryTime = time.time() + self.dsLocalCacheTimeout * (random() + 0.5)  * 60

        return self._dsLocalRecords
    

    @inlineCallbacks
    def _getDirectoryRecords(self, query=None, attributes=None, maxRecords=0 ):
        """
        Get a list of filtered VCardRecord for the given query with the given attributes.
        query == None gets all records. attribute == None gets VCardRecord.allDSQueryAttributes
        """
        limited = False
        queryResults = (yield self._queryDirectory(query, attributes, maxRecords ))
        if maxRecords and len(queryResults) >= maxRecords:
            limited = True
            self.log_debug("Directory address book record limit (= %d) reached." % (maxRecords, ))

        self.log_debug("Query done. Inspecting %s results" % len(queryResults))

        records = self._getDSLocalRecords().copy()
        self.log_debug("Adding %s DSLocal results" % len(records.keys()))
        
        for (recordShortName, value) in queryResults: #@UnusedVariable
            
            record = VCardRecord(self, value, self.defaultNodeName)

            if self.ignoreSystemRecords:
                # remove system users and people
                if record.guid.startswith("FFFFEEEE-DDDD-CCCC-BBBB-AAAA"):
                    self.log_info("Ignoring vcard for system record %s"  % (record,))
                    continue
        
            if record.guid in records:
                self.log_info("Ignoring vcard for record due to conflict (duplicate uuid): %s" % (record,))
            else:
                records[record.guid] = record                   
        
        self.log_debug("After filtering, %s records (limited=%s)." % (len(records), limited))
        returnValue((records, limited, ))


    def _queryDirectory(self, query=None, attributes=None, maxRecords=0 ):
        
        startTime = time.time()

        
        if not attributes:
            attributes = self.returnedAttributes
            
        attributes = list(set(attributes + self.additionalAttributes)) # remove duplicates
        
        directoryAndRecordTypes = []
        if self.peopleDirectory == self.userDirectory:
            # use single ds query if possible for best performance
            directoryAndRecordTypes.append( (self.peopleDirectory, self.peopleNode, (dsattributes.kDSStdRecordTypePeople, dsattributes.kDSStdRecordTypeUsers) ) )
        else:
            if self.peopleDirectory:
                directoryAndRecordTypes.append( (self.peopleDirectory, self.peopleNode, dsattributes.kDSStdRecordTypePeople) )
            if self.userDirectory:
                directoryAndRecordTypes.append( (self.userDirectory, self.userNode, dsattributes.kDSStdRecordTypeUsers) )
        
        allResults = []
        for directory, node, recordType in directoryAndRecordTypes:
            try:
                if query:
                    if isinstance(query, dsquery.match) and query.value is not "":
                        self.log_debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r,%r)" % (
                            node,
                            query.attribute,
                            query.value,
                            query.matchType,
                            False,
                            recordType,
                            attributes,
                            maxRecords,
                        ))
                        results = list(
                            self.odModule.queryRecordsWithAttribute_list(
                                directory,
                                query.attribute,
                                query.value,
                                query.matchType,
                                False,
                                recordType,
                                attributes,
                                maxRecords,
                            ))
                    else:
                        self.log_debug("opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r)" % (
                            node,
                            query.generate(),
                            False,
                            recordType,
                            attributes,
                            maxRecords,
                        ))
                        results = list(
                            self.odModule.queryRecordsWithAttributes_list(
                                directory,
                                query.generate(),
                                False,
                                recordType,
                                attributes,
                                maxRecords,
                            ))
                else:
                    self.log_debug("opendirectory.listAllRecordsWithAttributes_list(%r,%r,%r,%r)" % (
                        node,
                        recordType,
                        attributes,
                        maxRecords,
                    ))
                    results = list(
                        self.odModule.listAllRecordsWithAttributes_list(
                            directory,
                            recordType,
                            attributes,
                            maxRecords,
                        ))
            except self.odModule.ODError, ex:
                self.log_error("Open Directory (node=%s) error: %s" % (self.realmName, str(ex)))
                raise
            
            allResults.extend(results)
            
            if maxRecords:
                maxRecords -= len(results)
                if maxRecords <= 0:
                    break
        

        elaspedTime = time.time()-startTime
        self.log_info("Timing: Directory query: %.1f ms (%d records, %.2f records/sec)" % (elaspedTime*1000, len(allResults), len(allResults)/elaspedTime))
        return succeed(allResults)
    
    def _getDSFilter(self, addressBookFilter):
        """
        Convert the supplied addressbook-query into an expression tree.
    
        @param filter: the L{Filter} for the addressbook-query to convert.
        @return: (needsAllRecords, espressionAttributes, expression) tuple
        """
        def propFilterListQuery(filterAllOf, propFilters):

            def propFilterExpression(filterAllOf, propFilter):
                #print("propFilterExpression")
                """
                Create an expression for a single prop-filter element.
                
                @param propFilter: the L{PropertyFilter} element.
                @return: (needsAllRecords, espressionAttributes, expressions) tuple
                """
                
                def definedExpression( defined, allOf, filterName, constant, queryAttributes, allAttrStrings):
                    if constant or filterName in ("N" , "FN", "UID", ):
                        return (defined, [], [])     # all records have this property so no records do not have it
                    else:
                        matchList = list(set([dsquery.match(attrName, "", dsattributes.eDSStartsWith) for attrName in allAttrStrings]))
                        if defined:
                            return andOrExpression(allOf, queryAttributes, matchList)
                        else:
                            if len(matchList) > 1:
                                expr = dsquery.expression( dsquery.expression.OR, matchList )
                            else:
                                expr = matchList
                            return (False, queryAttributes, [dsquery.expression( dsquery.expression.NOT, expr),])
                    #end isNotDefinedExpression()
    
    
                def andOrExpression(propFilterAllOf, queryAttributes, matchList):
                    #print("andOrExpression(propFilterAllOf=%r, queryAttributes%r, matchList%r)" % (propFilterAllOf, queryAttributes, matchList))
                    if propFilterAllOf and len(matchList):
                        # add OR expression because parent will AND
                        return (False, queryAttributes, [dsquery.expression( dsquery.expression.OR, matchList),])
                    else:
                        return (False, queryAttributes, matchList)
                    #end andOrExpression()
                    
    
                # short circuit parameter filters
                def supportedParamter( filterName, paramFilters, propFilterAllOf ):
                    
                    def supported( paramFilterName, paramFilterDefined, params ):
                        paramFilterName = paramFilterName.upper()
                        if len(params.keys()) and ((paramFilterName in params.keys()) != paramFilterDefined):
                            return False
                        if len(params[paramFilterName]) and str(paramFilter.qualifier).upper() not in params[paramFilterName]:
                            return False
                        return True 
                        #end supported()
                
                    
                    oneSupported = False
                    for paramFilter in paramFilters:
                        if filterName == "PHOTO":
                            if propFilterAllOf != supported( paramFilter.filter_name, paramFilter.defined, { "ENCODING": ["B",], "TYPE": ["JPEG",], }):
                                return not propFilterAllOf
                            oneSupported |= propFilterAllOf
                        elif filterName == "ADR":
                            if propFilterAllOf != supported( paramFilter.filter_name, paramFilter.defined, { "TYPE": ["WORK", "PREF", "POSTAL", "PARCEL",], }):
                                return not propFilterAllOf
                            oneSupported |= propFilterAllOf
                        elif filterName == "LABEL":
                            if propFilterAllOf != supported( paramFilter.filter_name, paramFilter.defined, { "TYPE": ["POSTAL", "PARCEL",]}):
                                return not propFilterAllOf
                            oneSupported |= propFilterAllOf
                        elif filterName == "TEL":
                            if propFilterAllOf != supported( paramFilter.filter_name, paramFilter.defined, { "TYPE": [], }): # has params derived from ds attributes
                                return not propFilterAllOf
                            oneSupported |= propFilterAllOf
                        elif filterName == "EMAIL":
                            if propFilterAllOf != supported( paramFilter.filter_name, paramFilter.defined, { "TYPE": [], }): # has params derived from ds attributes
                                return not propFilterAllOf
                            oneSupported |= propFilterAllOf
                        elif filterName == "URL":
                            if propFilterAllOf != supported( paramFilter.filter_name, paramFilter.defined, {}):
                                return not propFilterAllOf
                            oneSupported |= propFilterAllOf
                        elif filterName == "KEY":
                            if propFilterAllOf != supported( paramFilter.filter_name, paramFilter.defined, { "ENCODING": ["B",], "TYPE": ["PGPPUBILICKEY", "USERCERTIFICATE", "USERPKCS12DATA", "USERSMIMECERTIFICATE",] }):
                                return not propFilterAllOf
                            oneSupported |= propFilterAllOf
                        elif not filterName.startswith("X-"): #X- IMHandles X-ABRELATEDNAMES excepted, no other params are used
                            if propFilterAllOf == paramFilter.defined:
                                return not propFilterAllOf
                            oneSupported |= propFilterAllOf
                    
                    if propFilterAllOf:
                        return True
                    else:
                        return oneSupported
                    #end supportedParamter()
                    
                    
                def textMatchElementExpression( propFilterAllOf, textMatchElement ):
    
                    # pre process text match strings for ds query 
                    def getMatchStrings( propFilter, matchString ):
                                            
                        if propFilter.filter_name in ("REV" , "BDAY", ):
                            rawString = matchString
                            matchString = ""
                            for c in rawString:
                                if not c in "TZ-:":
                                    matchString += c
                        elif propFilter.filter_name == "GEO":
                            matchString = ",".join(matchString.split(";"))
                        
                        if propFilter.filter_name in ("N" , "ADR", "ORG", ):
                            # for structured properties, change into multiple strings for ds query
                            if propFilter.filter_name == "ADR":
                                #split by newline and comma
                                rawStrings = ",".join( matchString.split("\n") ).split(",")
                            else:
                                #split by space
                                rawStrings = matchString.split(" ")
                            
                            # remove empty strings
                            matchStrings = []
                            for oneString in rawStrings:
                                if len(oneString):
                                    matchStrings += [oneString,]
                            return matchStrings
                        
                        elif len(matchString):
                            return [matchString,]
                        else:
                            return []
                        # end getMatchStrings
    
                    if constant:
                        # do the match right now!  Return either all or none.
                        return( textMatchElement.test([constant,]), [], [] )
                    else:

                        matchStrings = getMatchStrings(propFilter, textMatchElement.text)

                        if not len(matchStrings) or binaryAttrStrs:
                            # no searching text in binary ds attributes, so change to defined/not defined case
                            if textMatchElement.negate:
                                return definedExpression(False, propFilterAllOf, propFilter.filter_name, constant, queryAttributes, allAttrStrings)
                            # else fall through to attribute exists case below
                        else:
                            
                            # special case UID's formed from node and record name
                            if propFilter.filter_name == "UID":
                                matchString = matchStrings[0]
                                seperatorIndex = matchString.find(VCardRecord.peopleUIDSeparator)
                                if seperatorIndex > 1:
                                    recordNameStart = seperatorIndex + len(VCardRecord.peopleUIDSeparator)
                                else:
                                    seperatorIndex = matchString.find(VCardRecord.userUIDSeparator)                        
                                    if seperatorIndex > 1:
                                        recordNameStart = seperatorIndex + len(VCardRecord.userUIDSeparator)
                                    else:
                                        recordNameStart = sys.maxint
        
                                if recordNameStart < len(matchString)-1:
                                    try:
                                        recordNameQualifier = matchString[recordNameStart:].decode("base64").decode("utf8")
                                    except Exception, e:
                                        self.log_debug("Could not decode UID string %r in %r: %r" % (matchString[recordNameStart:], matchString, e,))
                                    else:
                                        if textMatchElement.negate:
                                            return (False, queryAttributes, 
                                                    [dsquery.expression(dsquery.expression.NOT, dsquery.match(dsattributes.kDSNAttrRecordName, recordNameQualifier, dsattributes.eDSExact)),]
                                                    )
                                        else:
                                            return (False, queryAttributes, 
                                                    [dsquery.match(dsattributes.kDSNAttrRecordName, recordNameQualifier, dsattributes.eDSExact),]
                                                    )
                            
                            # use match_type where possible depending on property/attribute mapping
                            # Note that case sensitive negate will not work
                            #        Should return all records in that case
                            matchType = dsattributes.eDSContains
                            if propFilter.filter_name in ("NICKNAME" , "TITLE" , "NOTE" , "UID", "URL", "N", "ADR", "ORG", "REV",  "LABEL", ):
                                if textMatchElement.match_type == "equals":
                                        matchType = dsattributes.eDSExact
                                elif textMatchElement.match_type == "starts-with":
                                        matchType = dsattributes.eDSStartsWith
                                elif textMatchElement.match_type == "ends-with":
                                        matchType = dsattributes.eDSEndsWith
                            
                            matchList = []
                            for matchString in matchStrings:
                                matchList += [dsquery.match(attrName, matchString, matchType) for attrName in stringAttrStrs]
                            
                            matchList = list(set(matchList))
    
                            if textMatchElement.negate:
                                if len(matchList) > 1:
                                    expr = dsquery.expression( dsquery.expression.OR, matchList )
                                else:
                                    expr = matchList
                                return (False, queryAttributes, [dsquery.expression( dsquery.expression.NOT, expr),])
                            else:
                                return andOrExpression(propFilterAllOf, queryAttributes, matchList)
    
                    # attribute exists search
                    return definedExpression(True, propFilterAllOf, propFilter.filter_name, constant, queryAttributes, allAttrStrings)
                    #end textMatchElementExpression()
                    
    
                # get attribute strings from dsqueryAttributesForProperty list 
                queryAttributes = list(set(VCardRecord.dsqueryAttributesForProperty.get(propFilter.filter_name, [])).intersection(set(self.allowedDSQueryAttributes)))
                
                binaryAttrStrs = []
                stringAttrStrs = []
                for attr in queryAttributes:
                    if isinstance(attr, tuple):
                        binaryAttrStrs.append(attr[0])
                    else:
                        stringAttrStrs.append(attr)
                allAttrStrings = stringAttrStrs + binaryAttrStrs
                                        
                constant = VCardRecord.constantProperties.get(propFilter.filter_name)
                if not constant and not allAttrStrings: 
                    return (False, [], [])
                
                if propFilter.qualifier and isinstance(propFilter.qualifier, addressbookqueryfilter.IsNotDefined):
                    return definedExpression(False, filterAllOf, propFilter.filter_name, constant, queryAttributes, allAttrStrings)
                
                paramFilterElements = [paramFilterElement for paramFilterElement in propFilter.filters if isinstance(paramFilterElement, addressbookqueryfilter.ParameterFilter)]
                textMatchElements = [textMatchElement for textMatchElement in propFilter.filters if isinstance(textMatchElement, addressbookqueryfilter.TextMatch)]
                propFilterAllOf = propFilter.propfilter_test == "allof"
                
                # handle parameter filter elements
                if len(paramFilterElements) > 0:
                    if supportedParamter(propFilter.filter_name, paramFilterElements, propFilterAllOf ):
                        if len(textMatchElements) == 0:
                            return definedExpression(True, filterAllOf, propFilter.filter_name, constant, queryAttributes, allAttrStrings)
                    else:
                        if propFilterAllOf:
                            return (False, [], [])
                
                # handle text match elements
                propFilterNeedsAllRecords = propFilterAllOf
                propFilterAttributes = []
                propFilterExpressionList = []
                for textMatchElement in textMatchElements:
                    
                    textMatchNeedsAllRecords, textMatchExpressionAttributes, textMatchExpression = textMatchElementExpression(propFilterAllOf, textMatchElement)
                    if propFilterAllOf:
                        propFilterNeedsAllRecords &= textMatchNeedsAllRecords
                    else:
                        propFilterNeedsAllRecords |= textMatchNeedsAllRecords
                    propFilterAttributes += textMatchExpressionAttributes
                    propFilterExpressionList += textMatchExpression
    

                if (len(propFilterExpressionList) > 1) and (filterAllOf != propFilterAllOf):
                    propFilterExpressions = [dsquery.expression(dsquery.expression.AND if propFilterAllOf else dsquery.expression.OR , list(set(propFilterExpressionList)))] # remove duplicates
                else:
                    propFilterExpressions = list(set(propFilterExpressionList))
                
                return (propFilterNeedsAllRecords, propFilterAttributes, propFilterExpressions)
                #end propFilterExpression

            #print("propFilterListQuery: filterAllOf=%r, propFilters=%r" % (filterAllOf, propFilters,))
            """
            Create an expression for a list of prop-filter elements.
            
            @param filterAllOf: the C{True} if parent filter test is "allof"
            @param propFilters: the C{list} of L{ComponentFilter} elements.
            @return: (needsAllRecords, espressionAttributes, expression) tuple
            """
            needsAllRecords = filterAllOf
            attributes = []
            expressions = []
            for propFilter in propFilters:
                
                propNeedsAllRecords, propExpressionAttributes, propExpression = propFilterExpression(filterAllOf, propFilter)
                if filterAllOf:
                    needsAllRecords &= propNeedsAllRecords
                else:
                    needsAllRecords |= propNeedsAllRecords
                attributes += propExpressionAttributes
                expressions += propExpression

            if len(expressions) > 1:
                expr = dsquery.expression(dsquery.expression.AND if filterAllOf else dsquery.expression.OR , list(set(expressions))) # remove duplicates
            elif len(expressions):
                expr = expressions[0]
            else:
                expr = None
            
            return (needsAllRecords, attributes, expr)
        
                
        #print("_getDSFilter")
        # Lets assume we have a valid filter from the outset
        
        # Top-level filter contains zero or more prop-filters
        if addressBookFilter:
            filterAllOf = addressBookFilter.filter_test == "allof"
            if len(addressBookFilter.children) > 0:
                return propFilterListQuery(filterAllOf, addressBookFilter.children)
            else:
                return (filterAllOf, [], [])
        else:
            return (False, [], [])    
    
                        

    def _attributesForAddressBookQuery(self, addressBookQuery ):
                        
        propertyNames = [] 
        #print( "addressBookQuery.qname=%r" % addressBookQuery.qname)
        if addressBookQuery.qname() == ("DAV:", "prop"):
        
            for property in addressBookQuery.children:                
                #print("property = %r" % property )
                if isinstance(property, carddavxml.AddressData):
                    for addressProperty in property.children:
                        #print("addressProperty = %r" % addressProperty )
                        if isinstance(addressProperty, carddavxml.Property):
                            #print("Adding property %r", addressProperty.attributes["name"])
                            propertyNames.append(addressProperty.attributes["name"])
                        
                elif not self.fakeETag and property.qname() == ("DAV:", "getetag"):
                    # for a real etag == md5(vCard), we need all attributes
                    propertyNames = None
                    break;
                            
        
        if not len(propertyNames):
            #print("using all attributes")
            return self.returnedAttributes
        
        else:
            propertyNames.append("X-INTERNAL-MINIMUM-VCARD-PROPERTIES") # these properties are required to make a vCard
            queryAttributes = []
            for prop in propertyNames:
                if prop in VCardRecord.dsqueryAttributesForProperty:
                    #print("adding attributes %r" % VCardRecord.dsqueryAttributesForProperty.get(prop))
                    queryAttributes += VCardRecord.dsqueryAttributesForProperty.get(prop)

            return list(set(queryAttributes).intersection(set(self.returnedAttributes)))

    
    @inlineCallbacks
    def cacheVCardsForAddressBookQuery(self, addressBookFilter, addressBookQuery, maxResults ):
        """
        Cache the vCards for a given addressBookFilder and addressBookQuery
        """
        startTime = time.time()
        #print("Timing: cacheVCardsForAddressBookQuery.starttime=%f" % startTime)
        
    
        allRecords, filterAttributes, dsFilter  = self._getDSFilter( addressBookFilter );
        #print("allRecords = %s, query = %s" % (allRecords, "None" if dsFilter is None else dsFilter.generate(),))
    
        if allRecords:
            dsFilter = None #  None expression == all Records
        clear = not allRecords and not dsFilter
        
        #get unique list of requested attributes
        if clear:
            attributes = None
        else:
            queryAttributes = self._attributesForAddressBookQuery( addressBookQuery )
            attributes = filterAttributes + queryAttributes
        
        #calc maxRecords from passed in maxResults allowing extra for second stage filtering in caller
        maxRecords = int(maxResults * 1.2)
        if self.maxDSQueryRecords and maxRecords > self.maxDSQueryRecords:
            maxRecords = self.maxDSQueryRecords
            
        updateLock, limited = (yield self._refreshCache(reschedule=False, query=dsFilter, attributes=attributes, keepLock=True, clear=clear, maxRecords=maxRecords ))

        elaspedTime = time.time()-startTime
        self.log_info("Timing: Cache fill: %.1f ms" % (elaspedTime*1000,))
        

        returnValue((updateLock, limited))


    @inlineCallbacks
    def vCardRecordsForAddressBookQuery(self, addressBookFilter, addressBookQuery, maxResults ):
        """
        Get vCards for a given addressBookFilder and addressBookQuery
        """
    
        allRecords, filterAttributes, dsFilter  = self._getDSFilter( addressBookFilter );
        #print("allRecords = %s, query = %s" % (allRecords, "None" if dsFilter is None else dsFilter.generate(),))
        
        # testing:
        # allRecords = True
        
        if allRecords:
            dsFilter = None #  None expression == all Records
        clear = not allRecords and not dsFilter
        
        queryRecords = []
        limited = False

        if not clear:
            queryAttributes = self._attributesForAddressBookQuery( addressBookQuery )
            attributes = filterAttributes + queryAttributes
            
            #calc maxRecords from passed in maxResults allowing extra for second stage filtering in caller
            maxRecords = int(maxResults * 1.2)
            if self.maxDSQueryRecords and maxRecords > self.maxDSQueryRecords:
                maxRecords = self.maxDSQueryRecords

            records, limited = (yield self._getDirectoryRecords(dsFilter, attributes, maxRecords))
            
            #filter out bad records --- should only happen during development
            for record in records.values():
                try:
                    vCardText = record.vCardText()
                except:
                    traceback.print_exc()
                    self.log_info("Could not get vcard for record %s" % (record,))
                else:
                    if not record.firstValueForAttribute(dsattributes.kDSNAttrMetaNodeLocation).startswith("/Local"):
                        self.log_debug("VCard text =\n%s" % (vCardText, ))
                    queryRecords.append(record)
                        
        returnValue((queryRecords, limited,))        


class VCardRecord(DirectoryRecord, DAVPropertyMixIn):
    """
    Open Directory implementation of L{IDirectoryRecord}.
    """

    # od attributes that may contribute to vcard properties
    # will be used to translate vCard queries to od queries

    dsqueryAttributesForProperty = {
                             
        "FN" : [
               dsattributes.kDS1AttrFirstName, 
               dsattributes.kDS1AttrLastName, 
               dsattributes.kDS1AttrMiddleName,
               dsattributes.kDSNAttrNamePrefix,
               dsattributes.kDSNAttrNameSuffix,
               dsattributes.kDS1AttrDistinguishedName,
               dsattributes.kDSNAttrRecordName,
               ],
        "N" : [
               dsattributes.kDS1AttrFirstName, 
               dsattributes.kDS1AttrLastName, 
               dsattributes.kDS1AttrMiddleName,
               dsattributes.kDSNAttrNamePrefix,
               dsattributes.kDSNAttrNameSuffix,
               dsattributes.kDS1AttrDistinguishedName,
               dsattributes.kDSNAttrRecordName,
               ],
        "NICKNAME" : [
                dsattributes.kDSNAttrNickName,
                ],
        # no binary searching
        "PHOTO" : [
                (dsattributes.kDSNAttrJPEGPhoto, "base64"),
                ],
        "BDAY" : [
                dsattributes.kDS1AttrBirthday,
                ],
        "ADR" : [
                dsattributes.kDSNAttrBuilding,
                dsattributes.kDSNAttrStreet,
                dsattributes.kDSNAttrCity,
                dsattributes.kDSNAttrState,
                dsattributes.kDSNAttrPostalCode,
                dsattributes.kDSNAttrCountry,
                ],
        "LABEL" : [
                dsattributes.kDSNAttrPostalAddress,
                dsattributes.kDSNAttrPostalAddressContacts,
                dsattributes.kDSNAttrAddressLine1,
                dsattributes.kDSNAttrAddressLine2,
                dsattributes.kDSNAttrAddressLine3,
                ],
         "TEL" : [
                dsattributes.kDSNAttrPhoneNumber,
                dsattributes.kDSNAttrMobileNumber,
                dsattributes.kDSNAttrPagerNumber,
                dsattributes.kDSNAttrHomePhoneNumber,
                dsattributes.kDSNAttrPhoneContacts,
                dsattributes.kDSNAttrFaxNumber,
                #dsattributes.kDSNAttrAreaCode,
                ],
         "EMAIL" : [
                dsattributes.kDSNAttrEMailAddress,
                dsattributes.kDSNAttrEMailContacts,
                ],
         "GEO" : [
                dsattributes.kDSNAttrMapCoordinates,
                ],
         "TITLE" : [
                dsattributes.kDSNAttrJobTitle,
                ],
         "ORG" : [
                dsattributes.kDSNAttrCompany,
                dsattributes.kDSNAttrOrganizationName,
                dsattributes.kDSNAttrDepartment,
                ],
         "NOTE" : [
                dsattributes.kDS1AttrComment,
                dsattributes.kDS1AttrNote,
                ],
         "REV" : [
                dsattributes.kDS1AttrModificationTimestamp,
                ],
         "UID" : [
                dsattributes.kDS1AttrGeneratedUID,
                # special cased
                #dsattributes.kDSNAttrMetaNodeLocation,
                #dsattributes.kDSNAttrRecordName,
                #dsattributes.kDS1AttrDistinguishedName,
                ],
         "URL" : [
                dsattributes.kDS1AttrWeblogURI,
                dsattributes.kDSNAttrURL,
                ],
         "KEY" : [
                # check on format, are these all binary?
                (dsattributes.kDSNAttrPGPPublicKey, "base64"),
                (dsattributes.kDS1AttrUserCertificate, "base64"),
                (dsattributes.kDS1AttrUserPKCS12Data, "base64"),
                (dsattributes.kDS1AttrUserSMIMECertificate, "base64"),
                ],
         # too bad this is not one X-Attribute with params.     Would make searching easier
         "X-AIM" : [
                dsattributes.kDSNAttrIMHandle,
                ],
         "X-JABBER" :    [
                dsattributes.kDSNAttrIMHandle,
                ],
         "X-MSN" :    [
                dsattributes.kDSNAttrIMHandle,
                ],
         "X-YAHOO" :  [
                dsattributes.kDSNAttrIMHandle,
                ],
         "X-ICQ" :    [
                dsattributes.kDSNAttrIMHandle,
                ],
         "X-ABRELATEDNAMES" :  [
                dsattributes.kDSNAttrRelationships,
                ],
          "X-INTERNAL-MINIMUM-VCARD-PROPERTIES" : [
                dsattributes.kDS1AttrGeneratedUID,
                dsattributes.kDSNAttrMetaNodeLocation,
                dsattributes.kDS1AttrFirstName, 
                 dsattributes.kDS1AttrLastName, 
                dsattributes.kDS1AttrMiddleName,
                   dsattributes.kDSNAttrNamePrefix,
                  dsattributes.kDSNAttrNameSuffix,
                 dsattributes.kDS1AttrDistinguishedName,
                dsattributes.kDSNAttrRecordName,
                dsattributes.kDSNAttrRecordType,
                dsattributes.kDS1AttrModificationTimestamp,
                dsattributes.kDS1AttrCreationTimestamp,
                ],
          "X-INTERNAL-REQUIRED" : [
                dsattributes.kDS1AttrGeneratedUID,
                dsattributes.kDSNAttrMetaNodeLocation,
                 dsattributes.kDS1AttrDistinguishedName,
                dsattributes.kDSNAttrRecordName,
                dsattributes.kDS1AttrFirstName, 
                 dsattributes.kDS1AttrLastName, 
                dsattributes.kDSNAttrRecordType,
                ],
  
    }
    

    allDSQueryAttributes = sorted(list(set([attr for lookupAttributes in dsqueryAttributesForProperty.values()
                                      for attr in lookupAttributes])))

    binaryDSAttributeStrs = [attr[0] for attr in allDSQueryAttributes
                                if isinstance(attr, tuple) ]

    stringDSAttributeStrs = [attr for attr in allDSQueryAttributes
                                if isinstance(attr, str) ]

    allDSAttributeStrs = stringDSAttributeStrs + binaryDSAttributeStrs
    
    #peopleUIDSeparator = "-" + OpenDirectoryBackingService.baseGUID + "-"
    userUIDSeparator = "-bf07a1a2-"
    peopleUIDSeparator = "-cf07a1a2-"

    
    constantProperties = {
        # 3.6.3 PRODID Type Definition
        "PRODID": vCardProductID,
        # 3.6.9 VERSION Type Definition
        "VERSION": "3.0",
        }

    
    def __init__(self, service, recordAttributes, defaultNodeName=None):
        

        self.log_debug("service=%s, attributes=%s"    % (service, recordAttributes))

        #save off for debugging
        if service.addDSAttrXProperties:
            self.originalAttributes = recordAttributes.copy()

        self.directoryBackedAddressBook = service.directoryBackedAddressBook
        self._vCard = None
        self._vCardText = None
        self._uriName = None
        self._hRef = None
        
        self.attributes = {}
        for key, values in recordAttributes.items():
            if key in VCardRecord.stringDSAttributeStrs:
                if isinstance(values, list):
                    self.attributes[key] = [removeControlChars(val).decode("utf8") for val in values]
                else:
                    self.attributes[key] = removeControlChars(values).decode("utf8")
            else:
                self.attributes[key] = values
                                                        
        # fill in  missing essential attributes used for filtering
        fullName = self.firstValueForAttribute(dsattributes.kDS1AttrDistinguishedName)
        if not fullName:
            fullName = self.firstValueForAttribute(dsattributes.kDSNAttrRecordName)
            self.attributes[dsattributes.kDS1AttrDistinguishedName] = fullName
            
        node = self.firstValueForAttribute(dsattributes.kDSNAttrMetaNodeLocation)
        
        # use a better node name -- makes better synthetic GUIDS
        if not node or node == "/LDAPv3/127.0.0.1":
            node = defaultNodeName if defaultNodeName else service.realmName
            self.attributes[dsattributes.kDSNAttrMetaNodeLocation] = node
        
        guid = self.firstValueForAttribute(dsattributes.kDS1AttrGeneratedUID)
        if not guid:
            if service.standardizeSyntheticUIDs:
                nodeUUIDStr = "00000000"
            else:
                nodeUUIDStr = "%x" % abs(hash(node))
            nameUUIDStr = "".join(self.firstValueForAttribute(dsattributes.kDSNAttrRecordName).encode("utf8").encode("base64").split("\n"))
            if self.firstValueForAttribute(dsattributes.kDSNAttrRecordType) != dsattributes.kDSStdRecordTypePeople:
                guid =  VCardRecord.userUIDSeparator.join([nodeUUIDStr, nameUUIDStr,])
            else:
                guid =  VCardRecord.peopleUIDSeparator.join([nodeUUIDStr, nameUUIDStr,])

            
        # since guid is used as file name, normalize so uid uniqueness == fine name uniqueness
        #guid = "/".join(guid.split(":")).upper()
        self.attributes[dsattributes.kDS1AttrGeneratedUID] = guid
        
        if self.firstValueForAttribute(dsattributes.kDS1AttrLastName) == "99":
            del self.attributes[dsattributes.kDS1AttrLastName]
        
        if self.firstValueForAttribute(dsattributes.kDSNAttrRecordType) != dsattributes.kDSStdRecordTypePeople:
            recordType = DirectoryService.recordType_users
        else:
            recordType = DirectoryService.recordType_people
                        
        super(VCardRecord, self).__init__(
            service                  = service,
            recordType              = recordType,
            guid                  = guid,
            shortNames              = tuple(self.valuesForAttribute(dsattributes.kDSNAttrRecordName)),
            fullName              = fullName,
            firstName              = self.firstValueForAttribute(dsattributes.kDS1AttrFirstName, None),
            lastName              = self.firstValueForAttribute(dsattributes.kDS1AttrLastName, None),
            emailAddresses        = (),
            calendarUserAddresses = (),
            autoSchedule          = False,
            enabledForCalendaring = False,
        )
        


    def __repr__(self):
        return "<%s[%s(%s)] %s(%s) %r>" % (
            self.__class__.__name__,
            self.firstValueForAttribute(dsattributes.kDSNAttrRecordType),
            self.firstValueForAttribute(dsattributes.kDSNAttrMetaNodeLocation),
            self.guid,
            self.shortNames,
            self.fullName
        )
    
    def __hash__(self):
        s = "".join([
              "%s:%s" % (attribute, self.valuesForAttribute(attribute),)
              for attribute in self.attributes
              ])
        return hash(s)

    """
    def nextFileName(self):
        self.renameCounter += 1
        self.fileName = self.baseFileName + "-" + str(self.renameCounter)
        self.fileNameLower = self.fileName.lower()
    """
    
    def hasAttribute(self, attributeName ):
        return self.valuesForAttribute(attributeName, None) is not None


    def valuesForAttribute(self, attributeName, default_values=[] ):
        values = self.attributes.get(attributeName)
        if (values is None):
            return default_values
        elif not isinstance(values, list):
            values = [values, ] 
        
        # ds templates often return empty attribute values
        #     get rid of them here
        nonEmptyValues = [(value.encode("utf-8") if isinstance(value, unicode) else value) for value in values if len(value) > 0 ]
        
        if len(nonEmptyValues) > 0:
            return nonEmptyValues
        else:
            return default_values
        

    def firstValueForAttribute(self, attributeName, default_value="" ):
        values = self.attributes.get(attributeName)
        if values is None:
            return default_value
        elif isinstance(values, list):
            return values[0].encode("utf_8") if isinstance(values[0], unicode) else values[0]
        else:
            return values.encode("utf_8") if isinstance(values, unicode) else values

    def joinedValuesForAttribute(self, attributeName, separator=",", default_string="" ):
        values = self.valuesForAttribute(attributeName, None)
        if not values:
            return default_string
        else:
            return separator.join(values)
            

    def isoDateStringForDateAttribute(self, attributeName, default_string="" ):
        modDate = self.firstValueForAttribute(attributeName, default_string)
        revDate = None
        if modDate:
            if len(modDate) >= len("YYYYMMDD") and modDate[:8].isdigit():
                revDate = "%s-%s-%s" % (modDate[:4],modDate[4:6],modDate[6:8], )
            if len(modDate) >= len("YYYYMMDDHHMMSS") and modDate[8:14].isdigit():
                revDate += "T%s:%s:%sZ" % (modDate[8:10],modDate[10:12],modDate[12:14], )
        return revDate

    
                
    def vCard(self):
        
        
        def generateVCard():
            
            def isUniqueProperty(vcard, newProperty, ignoreParams = None):
                existingProperties = vcard.properties(newProperty.name())
                for existingProperty in existingProperties:
                    if ignoreParams:
                        existingProperty = existingProperty.duplicate()
                        for paramname, paramvalue in ignoreParams:
                            existingProperty.removeParameterValue(paramname, paramvalue)
                    if existingProperty == newProperty:
                        return False
                return True

            def addUniqueProperty(vcard, newProperty, ignoreParams = None, attrType = None, attrValue = None):
                if isUniqueProperty(vcard, newProperty, ignoreParams):
                    vcard.addProperty(newProperty)
                else:
                    if attrType and attrValue:
                        self.log_info("Ignoring attribute %r with value %r in creating property %r. A duplicate property already exists." % (attrType, attrValue, newProperty, ))
                            
            def addPropertyAndLabel(groupCount, label, propertyName, propertyValue, parameters = None ):
                groupCount[0] += 1
                groupPrefix = "item%d" % groupCount[0]
                vcard.addProperty(Property(propertyName, propertyValue, params=parameters, group=groupPrefix))
                vcard.addProperty(Property("X-ABLabel", label, group=groupPrefix))

            # for attributes of the form  param:value
            def addPropertiesAndLabelsForPrefixedAttribute(groupCount, propertyPrefix, propertyName, defaultLabel, nolabelParamTypes, labelMap, attrType):
                preferred = True
                for attrValue in self.valuesForAttribute(attrType):
                    try:
                        # special case for Apple
                        if self.service.appleInternalServer and attrType == dsattributes.kDSNAttrIMHandle:
                            splitValue = attrValue.split("|")
                            if len (splitValue) > 1:
                                attrValue = splitValue[0]

                        colonIndex = attrValue.find(":")
                        if (colonIndex > len(attrValue)-2):
                            raise ValueError("Nothing after colon.")

                        propertyValue = attrValue[colonIndex+1:]
                        labelString = attrValue[:colonIndex] if colonIndex > 0 else defaultLabel
                        paramTypeString = labelString.upper()
                        
                        # add PREF to first prop's parameters
                        paramTypeStrings = [paramTypeString,]
                        if preferred and "PREF" != paramTypeString:
                            paramTypeStrings += ["PREF",]
                        parameters = { "TYPE": paramTypeStrings, }

                        #special case for IMHandles which the param is the last part of the property like X-AIM or X-JABBER 
                        if propertyPrefix:
                            propertyName = propertyPrefix + paramTypeString

                        # only add label prop if needed
                        if paramTypeString in nolabelParamTypes:
                            addUniqueProperty(vcard, Property(propertyName, attrValue[colonIndex+1:], params=parameters), None, attrValue, attrType)
                        else:
                            # use special localizable addressbook labels where possible
                            abLabelString = labelMap.get(labelString, labelString)
                            addPropertyAndLabel(groupCount, abLabelString, propertyName, propertyValue, parameters)
                        preferred = False

                    except Exception, e:
                        traceback.print_exc()
                        self.log_debug("addPropertiesAndLabelsForPrefixedAttribute(): groupCount=%r, propertyPrefix=%r, propertyName=%r, nolabelParamTypes=%r, labelMap=%r, attrType=%r" % (groupCount[0], propertyPrefix, propertyName, nolabelParamTypes, labelMap, attrType,))
                        self.log_error("addPropertiesAndLabelsForPrefixedAttribute(): Trouble parsing attribute %s, with value \"%s\".  Error = %s" % (attrType, attrValue, e,))

            
            #print("VCardRecord.vCard")
            # create vCard
            vcard = Component("VCARD")
            groupCount = [0]
            
            # add constant properties - properties that are the same regardless of the record attributes
            for key, value in VCardRecord.constantProperties.items():
                vcard.addProperty(Property(key, value))
    
            # 3.1 IDENTIFICATION TYPES http://tools.ietf.org/html/rfc2426#section-3.1
            # 3.1.1 FN Type Definition
            # dsattributes.kDS1AttrDistinguishedName,      # Users distinguished or real name
            #
            # full name is required but this is set in OpenDiretoryBackingRecord.__init__
            #vcard.addProperty(Property("FN", self.firstValueForAttribute(dsattributes.kDS1AttrDistinguishedName)))
            
            # 3.1.2 N Type Definition
            # dsattributes.kDS1AttrFirstName,            # Used for first name of user or person record.
            # dsattributes.kDS1AttrLastName,            # Used for the last name of user or person record.
            # dsattributes.kDS1AttrMiddleName,            # Used for the middle name of user or person record.
            # dsattributes.kDSNAttrNameSuffix,            # Represents the name suffix of a user or person.
                                                        #      ie. Jr., Sr., etc.
                                                        #      Usually found in user or people records (kDSStdRecordTypeUsers or 
                                                        #      dsattributes.kDSStdRecordTypePeople).
            # dsattributes.kDSNAttrNamePrefix,            # Represents the title prefix of a user or person.
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
                first = self.valuesForAttribute(dsattributes.kDS1AttrFirstName, ""),
                last = familyName, 
                middle = self.valuesForAttribute(dsattributes.kDS1AttrMiddleName, ""),
                prefix = self.valuesForAttribute(dsattributes.kDSNAttrNamePrefix, ""),
                suffix = self.valuesForAttribute(dsattributes.kDSNAttrNameSuffix, ""),
            )
            vcard.addProperty(Property("N", nameObject))
            
            # set full name to Name with contiguous spaces stripped
            # it turns out that Address Book.app ignores FN and creates it fresh from N in ABRecord
            # so no reason to have FN distinct from N
            vcard.addProperty(Property("FN", nameObject.getFullName() ))
            
            # 3.1.3 NICKNAME Type Definition
            # dsattributes.kDSNAttrNickName,            # Represents the nickname of a user or person.
                                                        #    Usually found in user or people records (kDSStdRecordTypeUsers or 
                                                        #    dsattributes.kDSStdRecordTypePeople).
            for nickname in self.valuesForAttribute(dsattributes.kDSNAttrNickName):
                addUniqueProperty(vcard, Property("NICKNAME", nickname), None, dsattributes.kDSNAttrNickName, nickname)
            
            # 3.1.4 PHOTO Type Definition
            # dsattributes.kDSNAttrJPEGPhoto,            # Used to store binary picture data in JPEG format. 
                                                        #      Usually found in user, people or group records (kDSStdRecordTypeUsers, 
                                                        #      dsattributes.kDSStdRecordTypePeople,dsattributes.kDSStdRecordTypeGroups).
            # pyOpenDirectory always returns binary-encoded string                                       
                                                        
            for photo in self.valuesForAttribute(dsattributes.kDSNAttrJPEGPhoto):
                addUniqueProperty(vcard, Property("PHOTO", photo, params={"ENCODING": ["b",], "TYPE": ["JPEG",],}), None, dsattributes.kDSNAttrJPEGPhoto, photo)
    
    
            # 3.1.5 BDAY Type Definition
            # dsattributes.kDS1AttrBirthday,            # Single-valued attribute that defines the user's birthday.
                                                        #      Format is x.208 standard YYYYMMDDHHMMSSZ which we will require as GMT time.
                                                        #                               012345678901234
            
            birthdate = self.isoDateStringForDateAttribute(dsattributes.kDS1AttrBirthday)
            if birthdate:
                vcard.addProperty(Property("BDAY", PyCalendarDateTime.parseText(birthdate, fullISO=True)))
    
    
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
                        extended = extended,
                        street = street,
                        locality = city,
                        region = region,
                        postalcode = code,
                        country = country,
                    ),
                    params = {"TYPE": ["WORK", "PREF", "POSTAL", "PARCEL",],}
                ))
    
    
            # 3.2.2 LABEL Type Definition
            
            # dsattributes.kDSNAttrPostalAddress,            # The postal address usually excluding postal code.
            # dsattributes.kDSNAttrPostalAddressContacts,    # multi-valued attribute that defines a record's alternate postal addresses .
                                                            #      found in user records (kDSStdRecordTypeUsers) and resource records (kDSStdRecordTypeResources).
            # dsattributes.kDSNAttrAddressLine1,            # Line one of multiple lines of address data for a user.
            # dsattributes.kDSNAttrAddressLine2,            # Line two of multiple lines of address data for a user.
            # dsattributes.kDSNAttrAddressLine3,            # Line three of multiple lines of address data for a user.
            
            for label in self.valuesForAttribute(dsattributes.kDSNAttrPostalAddress):
                addUniqueProperty(vcard, Property("LABEL", label, params={"TYPE": ["POSTAL", "PARCEL",]}), None, dsattributes.kDSNAttrPostalAddress, label)
                
            for label in self.valuesForAttribute(dsattributes.kDSNAttrPostalAddressContacts):
                addUniqueProperty(vcard, Property("LABEL", label, params={"TYPE": ["POSTAL", "PARCEL",]}), None, dsattributes.kDSNAttrPostalAddressContacts, label)
                
            address = self.joinedValuesForAttribute(dsattributes.kDSNAttrAddressLine1)
            addressLine2 = self.joinedValuesForAttribute(dsattributes.kDSNAttrAddressLine2)
            if len(addressLine2) > 0:
                address += "\n" + addressLine2
            addressLine3 = self.joinedValuesForAttribute(dsattributes.kDSNAttrAddressLine3)
            if len(addressLine3) > 0:
                address += "\n" + addressLine3
            
            if len(address) > 0:
                vcard.addProperty(Property("LABEL", address, params={"TYPE": ["POSTAL", "PARCEL",]}))
    
            # 3.3 TELECOMMUNICATIONS ADDRESSING TYPES http://tools.ietf.org/html/rfc2426#section-3.3
            # 3.3.1 TEL Type Definition
            #          TEL;TYPE=work,voice,pref,msg:+1-213-555-1234
    
            # dsattributes.kDSNAttrPhoneNumber,            # Telephone number of a user.
            # dsattributes.kDSNAttrMobileNumber,        # Represents the mobile numbers of a user or person.
                                                        #      Usually found in user or people records (kDSStdRecordTypeUsers or 
                                                        #      dsattributes.kDSStdRecordTypePeople).
            # dsattributes.kDSNAttrFaxNumber,            # Represents the FAX numbers of a user or person.
                                                        # Usually found in user or people records (kDSStdRecordTypeUsers or 
                                                        # kDSStdRecordTypePeople).
            # dsattributes.kDSNAttrPagerNumber,            # Represents the pager numbers of a user or person.
                                                        #      Usually found in user or people records (kDSStdRecordTypeUsers or 
                                                        #      dsattributes.kDSStdRecordTypePeople).
            # dsattributes.kDSNAttrHomePhoneNumber,        # Home telephone number of a user or person.
            # dsattributes.kDSNAttrPhoneContacts,        # multi-valued attribute that defines a record's custom phone numbers .
                                                        #      found in user records (kDSStdRecordTypeUsers). 
                                                        #      Example: home fax:408-555-4444
            
            params = {"TYPE": ["WORK", "PREF", "VOICE",],}
            for phone in self.valuesForAttribute(dsattributes.kDSNAttrPhoneNumber):
                addUniqueProperty(vcard, Property("TEL", phone, params=params), (("TYPE", "PREF"),), phone, dsattributes.kDSNAttrPhoneNumber)
                params = {"TYPE": ["WORK", "VOICE",],}
    
            params = { "TYPE": ["WORK", "PREF", "CELL",], }
            for phone in self.valuesForAttribute(dsattributes.kDSNAttrMobileNumber):
                addUniqueProperty(vcard, Property("TEL", phone, params=params), (("TYPE", "PREF"),), phone, dsattributes.kDSNAttrMobileNumber)
                params = { "TYPE": ["WORK", "CELL",], }
    
            params = { "TYPE": ["WORK", "PREF", "FAX",], }
            for phone in self.valuesForAttribute(dsattributes.kDSNAttrFaxNumber):
                addUniqueProperty(vcard, Property("TEL", phone, params=params), (("TYPE", "PREF"),), phone, dsattributes.kDSNAttrFaxNumber)
                params = { "TYPE": ["WORK", "FAX",], }
    
            params = { "TYPE": ["WORK", "PREF", "PAGER",], }
            for phone in self.valuesForAttribute(dsattributes.kDSNAttrPagerNumber):
                addUniqueProperty(vcard, Property("TEL", phone, params=params), (("TYPE", "PREF"),), phone, dsattributes.kDSNAttrPagerNumber)
                params = { "TYPE": ["WORK", "PAGER",], }
    
            params = { "TYPE": ["HOME", "PREF", "VOICE",], }
            for phone in self.valuesForAttribute(dsattributes.kDSNAttrHomePhoneNumber):
                addUniqueProperty(vcard, Property("TEL", phone, params=params), (("TYPE", "PREF"),), phone, dsattributes.kDSNAttrHomePhoneNumber)
                params = { "TYPE": ["HOME", "VOICE",], }
                    
            addPropertiesAndLabelsForPrefixedAttribute(groupCount, None, "TEL", "work",
                                                        ["VOICE", "CELL", "FAX", "PAGER",], {},
                                                        dsattributes.kDSNAttrPhoneContacts, )

            """
            # EXTEND:  Use this attribute
            # dsattributes.kDSNAttrAreaCode,            # Area code of a user's phone number.
            """
    
            # 3.3.2 EMAIL Type Definition
            # dsattributes.kDSNAttrEMailAddress,        # Email address of usually a user record.
    
            # setup some params
            preferredWorkParams = { "TYPE": ["WORK", "PREF", "INTERNET",], }
            workParams = { "TYPE": ["WORK", "INTERNET",], }
            params = preferredWorkParams
            for emailAddress in self.valuesForAttribute(dsattributes.kDSNAttrEMailAddress):
                addUniqueProperty(vcard, Property("EMAIL", emailAddress, params=params), (("TYPE", "PREF"),), emailAddress, dsattributes.kDSNAttrEMailAddress)
                params = workParams
                
            # dsattributes.kDSNAttrEMailContacts,        # multi-valued attribute that defines a record's custom email addresses .
                                                        #    found in user records (kDSStdRecordTypeUsers). 
                                                        #      Example: home:johndoe@mymail.com
    
            # check to see if parameters type are open ended. Could be any string
            addPropertiesAndLabelsForPrefixedAttribute(groupCount, None, "EMAIL", "work",
                                                        ["WORK", "HOME",], {}, 
                                                        dsattributes.kDSNAttrEMailContacts, )
    
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
            #dsattributes.kDSNAttrMapCoordinates,        # attribute that defines coordinates for a user's location .
                                                        #      Found in user records (kDSStdRecordTypeUsers) and resource records (kDSStdRecordTypeResources).
                                                        #      Example: 7.7,10.6
            for coordinate in self.valuesForAttribute(dsattributes.kDSNAttrMapCoordinates):
                parts = coordinate.split(",")
                if (len(parts) == 2):
                    vcard.addProperty(Property("GEO", parts))
                else:
                    self.log_info("Ignoring malformed attribute %r with value %r. Well-formed example: 7.7,10.6." % (dsattributes.kDSNAttrMapCoordinates, coordinate))
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
                vcard.addProperty(Property("ORG", (company, department, extra, ),))
            
            # 3.6 EXPLANATORY TYPES http://tools.ietf.org/html/rfc2426#section-3.6
            """
            # UNIMPLEMENTED:
            # 3.6.1 CATEGORIES Type Definition
            """
            # 3.6.2 NOTE Type Definition
            # dsattributes.kDS1AttrComment,                  # Attribute used for unformatted comment.
            # dsattributes.kDS1AttrNote,                  # Note attribute. Commonly used in printer records.
            for comment in self.valuesForAttribute(dsattributes.kDS1AttrComment):
                addUniqueProperty(vcard, Property("NOTE", comment), None, dsattributes.kDS1AttrComment, comment)
    
            for note in self.valuesForAttribute(dsattributes.kDS1AttrNote):
                addUniqueProperty(vcard, Property("NOTE", note), None, dsattributes.kDS1AttrNote, note)
            
            # 3.6.3 PRODID Type Definition
            #vcard.addProperty(Property("PRODID", vCardProductID + "//BUILD %s" % twistedcaldav.__version__))
            #vcard.addProperty(Property("PRODID", vCardProductID))
            # ADDED WITH CONTSTANT PROPERTIES
            
            # 3.6.4 REV Type Definition
            revDate = self.isoDateStringForDateAttribute(dsattributes.kDS1AttrModificationTimestamp)
            if revDate:
                vcard.addProperty(Property("REV", PyCalendarDateTime.parseText(revDate, fullISO=True)))
            
            """
            # UNIMPLEMENTED:
            # 3.6.5 SORT-STRING Type Definition
            # 3.6.6 SOUND Type Definition
            """
            # 3.6.7 UID Type Definition
            # dsattributes.kDS1AttrGeneratedUID,        # Used for 36 character (128 bit) unique ID. Usually found in user, 
                                                        #      group, and computer records. An example value is "A579E95E-CDFE-4EBC-B7E7-F2158562170F".
                                                        #      The standard format contains 32 hex characters and four hyphen characters.
            # !! don't use self.guid which is URL encoded
            vcard.addProperty(Property("UID", self.firstValueForAttribute(dsattributes.kDS1AttrGeneratedUID)))
    
            # 3.6.8 URL Type Definition 
            # dsattributes.kDSNAttrURL,                    # List of URLs.
            # dsattributes.kDS1AttrWeblogURI,            # Single-valued attribute that defines the URI of a user's weblog.
                                                        #     Usually found in user records (kDSStdRecordTypeUsers). 
                                                        #      Example: http://example.com/blog/jsmith
            for url in self.valuesForAttribute(dsattributes.kDS1AttrWeblogURI):
                addPropertyAndLabel(groupCount, "weblog", "URL", url, parameters = {"TYPE": ["Weblog",]})
    
            for url in self.valuesForAttribute(dsattributes.kDSNAttrURL):
                addPropertyAndLabel(groupCount, "_$!<HomePage>!$_", "URL", url, parameters = {"TYPE": ["Homepage",]})
    
    
            # 3.6.9 VERSION Type Definition
            # ALREADY ADDED
    
            # 3.7 SECURITY TYPES http://tools.ietf.org/html/rfc2426#section-3.7
            # 3.7.1 CLASS Type Definition
            # ALREADY ADDED
            
            # 3.7.2 KEY Type Definition
            
            # dsattributes.kDSNAttrPGPPublicKey,        # Pretty Good Privacy public encryption key.
            # dsattributes.kDS1AttrUserCertificate,        # Attribute containing the binary of the user's certificate.
                                                        #       Usually found in user records. The certificate is data which identifies a user.
                                                        #       This data is attested to by a known party, and can be independently verified 
                                                        #       by a third party.
            # dsattributes.kDS1AttrUserPKCS12Data,        # Attribute containing binary data in PKCS #12 format. 
                                                        #       Usually found in user records. The value can contain keys, certificates,
                                                        #      and other related information and is encrypted with a passphrase.
            # dsattributes.kDS1AttrUserSMIMECertificate,# Attribute containing the binary of the user's SMIME certificate.
                                                        #       Usually found in user records. The certificate is data which identifies a user.
                                                        #       This data is attested to by a known party, and can be independently verified 
                                                        #       by a third party. SMIME certificates are often used for signed or encrypted
                                                        #       emails.
    
            for key in self.valuesForAttribute(dsattributes.kDSNAttrPGPPublicKey):
                addUniqueProperty(vcard, Property("KEY", key, params = {"ENCODING": ["b",], "TYPE": ["PGPPublicKey",]}), None, dsattributes.kDSNAttrPGPPublicKey, key)
    
            for key in self.valuesForAttribute(dsattributes.kDS1AttrUserCertificate):
                addUniqueProperty(vcard, Property("KEY", key, params = {"ENCODING": ["b",], "TYPE": ["UserCertificate",]}), None, dsattributes.kDS1AttrUserCertificate, key)
    
            for key in self.valuesForAttribute(dsattributes.kDS1AttrUserPKCS12Data):
                addUniqueProperty(vcard, Property("KEY", key, params = {"ENCODING": ["b",], "TYPE": ["UserPKCS12Data",]}), None, dsattributes.kDS1AttrUserPKCS12Data, key)
    
            for key in self.valuesForAttribute(dsattributes.kDS1AttrUserSMIMECertificate):
                addUniqueProperty(vcard, Property("KEY", key, params = {"ENCODING": ["b",], "TYPE": ["UserSMIMECertificate",]}), None, dsattributes.kDS1AttrUserSMIMECertificate, key)
    
            """
            X- attributes, Address Book support
            """
            # X-AIM, X-JABBER, X-MSN, X-YAHOO, X-ICQ
            # instant messaging
            # dsattributes.kDSNAttrIMHandle,            # Represents the Instant Messaging handles of a user.
                                                        #      Values should be prefixed with the appropriate IM type
                                                        #       ie. AIM:, Jabber:, MSN:, Yahoo:, or ICQ:
                                                        #       Usually found in user records (kDSStdRecordTypeUsers).
    
            addPropertiesAndLabelsForPrefixedAttribute(groupCount, "X-", None, "aim",
                                                        ["AIM", "JABBER", "MSN", "YAHOO", "ICQ"], 
                                                        {}, 
                                                        dsattributes.kDSNAttrIMHandle,)
                    
            # X-ABRELATEDNAMES
            # dsattributes.kDSNAttrRelationships,        #      multi-valued attribute that defines the relationship to the record type .
                                                        #      found in user records (kDSStdRecordTypeUsers). 
                                                        #      Example: brother:John
            addPropertiesAndLabelsForPrefixedAttribute(groupCount, None, "X-ABRELATEDNAMES", "friend",
                                                        [],  
                                                        {   "FATHER":"_$!<Father>!$_",
                                                            "MOTHER":"_$!<Mother>!$_",
                                                            "PARENT":"_$!<Parent>!$_",
                                                            "BROTHER":"_$!<Brother>!$_",
                                                            "SISTER":"_$!<Sister>!$_",
                                                            "CHILD":"_$!<Child>!$_",
                                                            "FRIEND":"_$!<Friend>!$_",
                                                            "SPOUSE":"_$!<Spouse>!$_",
                                                            "PARTNER":"_$!<Partner>!$_",
                                                            "ASSISTANT":"_$!<Assistant>!$_",
                                                            "MANAGER":"_$!<Manager>!$_", },
                                                        dsattributes.kDSNAttrRelationships, )
            
            
            # special case for Apple
            if self.service.appleInternalServer:
                for manager in self.valuesForAttribute("dsAttrTypeNative:appleManager"):
                    splitManager = manager.split("|")
                    if len(splitManager) >= 4:
                        managerValue = "%s %s, %s" % (splitManager[0], splitManager[1], splitManager[3],)
                    elif len(splitManager) >= 2:
                        managerValue = "%s %s" % (splitManager[0], splitManager[1])
                    else:
                        managerValue = manager
                    addPropertyAndLabel( groupCount, "_$!<Manager>!$_", "X-ABRELATEDNAMES", managerValue, parameters={ "TYPE": ["Manager",]} )
            
            """
            # UNIMPLEMENTED: X- attributes
            
            X-MAIDENNAME
            X-PHONETIC-FIRST-NAME
            X-PHONETIC-MIDDLE-NAME
            X-PHONETIC-LAST-NAME
        
            sattributes.kDS1AttrPicture,                # Represents the path of the picture for each user displayed in the login window.
                                                        #      Found in user records (kDSStdRecordTypeUsers).
           
            dsattributes.kDS1AttrMapGUID,                # Represents the GUID for a record's map.
            dsattributes.kDSNAttrMapURI,                # attribute that defines the URI of a user's location.
    
            dsattributes.kDSNAttrOrganizationInfo,        # Usually the organization info of a user.
            dsattributes.kDSNAttrAreaCode,                # Area code of a user's phone number.
    
            dsattributes.kDSNAttrMIME,                    # Data contained in this attribute type is a fully qualified MIME Type. 
            
            """
            
            # debug, create x attributes for all ds attributes
            if self.service.addDSAttrXProperties:
                for attribute in self.originalAttributes:
                    for value in self.valuesForAttribute(attribute):
                        vcard.addProperty(Property("X-"+"-".join(attribute.split(":")), removeControlChars(value)))
    
            return vcard

        
        if not self._vCard:
            self._vCard = generateVCard()
        
        return self._vCard
    
    def vCardText(self):
        if not self._vCardText:
            self._vCardText = str(self.vCard())
        
        return self._vCardText

    def uriName(self):
        if not self._uriName:
            self._uriName = self.vCard().getProperty("UID").value() + ".vcf"
        #print("uriName():self._uriName=%s" % self._uriName)
        return self._uriName
        
    
    def hRef(self, parentURI="/directory/"):
        if not self._hRef:
            self._hRef = davxml.HRef.fromString(joinURL(parentURI, self.uriName()))
            
        return self._hRef


    def readProperty(self, property, request):
        
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        namespace, name = qname
        
        #print("VCardResource.readProperty: qname = %s" % (qname, ))
        
        if namespace == dav_namespace:
            if name == "resourcetype":
                result = davxml.ResourceType.empty #@UndefinedVariable
                #print("VCardResource.readProperty: qname = %s, result = %s" % (qname, result))
                return result
            elif name == "getetag":
                result = davxml.GETETag( ETag(hashlib.md5(self.vCardText()).hexdigest()).generate() )
                #print("VCardResource.readProperty: qname = %s, result = %s" % (qname, result))
                return result
            elif name == "getcontenttype":
                mimeType = MimeType('text', 'vcard', {})
                result = davxml.GETContentType(generateContentType(mimeType))
                #print("VCardResource.readProperty: qname = %s, result = %s" % (qname, result))
                return result
            elif name == "getcontentlength":
                result = davxml.GETContentLength.fromString(str(len(self.vCardText())))
                #print("VCardResource.readProperty: qname = %s, result = %s" % (qname, result))
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
                #print("VCardResource.readProperty: qname = %s, result = %s" % (qname, result))
                return result
            elif name == "creationdate":
                creationDateString = self.isoDateStringForDateAttribute(dsattributes.kDS1AttrCreationTimestamp)
                if creationDateString:
                    creationDatetime = parse_date(creationDateString)
                elif self.vCard().hasProperty("REV"):    # use modification date property if it exists
                    creationDatetime = parse_date(self.vCard().propertyValue("REV"))
                else:
                    creationDatetime = datetime.datetime.utcnow()
                result = davxml.CreationDate.fromDate(creationDatetime)
                #print("VCardResource.readProperty: qname = %s, result = %s" % (qname, result))
                return result
            elif name == "displayname":
                # AddressBook.app uses N. Use FN or UID instead?
                result = davxml.DisplayName.fromString(self.vCard().propertyValue("N"))
                #print("VCardResource.readProperty: qname = %s, result = %s" % (qname, result))
                return result

        elif namespace == twisted_dav_namespace:
            return super(VCardRecord, self).readProperty(property, request)
            #return DAVPropertyMixIn.readProperty(self, property, request)

        return self.directoryBackedAddressBook.readProperty(property, request)

    def listProperties(self, request):
        #print("VCardResource.listProperties()")
        qnames = set(self.liveProperties())

        # Add dynamic live properties that exist
        dynamicLiveProperties = (
            (dav_namespace, "quota-available-bytes"     ),
            (dav_namespace, "quota-used-bytes"          ),
        )
        for dqname in dynamicLiveProperties:
            #print("VCardResource.listProperties: removing dqname=%s" % (dqname,))
            qnames.remove(dqname)

        for qname in self.deadProperties().list():
            if (qname not in qnames) and (qname[0] != twisted_private_namespace):
                #print("listProperties: adding qname=%s" % (qname,))
                qnames.add(qname)

        #for qn in qnames: print("VCardResource.listProperties: qn=%s" % (qn,))

        yield qnames
        
    listProperties = deferredGenerator(listProperties)
    
# utility
#remove control characters because vCard does not support them
def removeControlChars( utf8String ):
    result = utf8String
    for a in utf8String:
        if '\x00' <= a <= '\x1F':
            result = ""
            for c in utf8String:
                if '\x00' <= c <= '\x1F':
                    pass 
                else:
                    result += c
    #if utf8String != result: print ("changed %r to %r" % (utf8String, result))
    return result


