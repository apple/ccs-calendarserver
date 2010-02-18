##
# Copyright (c) 2006-2009 Apple Inc. All rights reserved.
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
AddressBook Server "Find Shared" Address Books report
Based on addressbook-query report in report_addressbook_query.py
"""

__all__ = [
    "http___addressbookserver_org_ns__addressbook_findshared",
    "getReadWriteSharedAddressBookGroups",
    "getReadOnlySharedAddressBookGroups",
    "getWritersGroupForSharedAddressBookGroup",
]

#import traceback
import opendirectory
import dsattributes

from plistlib import readPlist
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log
from twext.python.filepath import CachingFilePath as FilePath
from twext.web2 import responsecode
from twext.web2.dav import davxml
from twext.web2.dav.http import MultiStatusResponse
from twext.web2.dav.util import joinURL
from twext.web2.http import HTTPError, StatusResponse

from twistedcaldav import customxml
from twistedcaldav.carddavxml import addressbookserver_namespace, carddav_namespace
from twistedcaldav.config import config
from twistedcaldav.stdconfig import DEFAULT_CONFIG_FILE as defaultConfigFile
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.directory.appleopendirectory import OpenDirectoryRecord
from twistedcaldav.resource import isAddressBookCollectionResource

from twistedcaldav.directory.directory import DirectoryService

gLogLocal = 0       # Poor mans logging control for this file only

class AddressBookAccessMode (davxml.WebDAVTextElement):
    """
    Access Mode XML element for Address Book "Find Shared" report
    """
    name = "current-addressbook-access-mode"
    namespace = addressbookserver_namespace
    protected = True
    

class AddressBookGroupAddressBookInfo (davxml.WebDAVElement):
    name = "addressbook-info"
    namespace = addressbookserver_namespace
    protected = True

    allowed_children = { (davxml.dav_namespace, "href"): (0, None),
                         (calendarserver_namespace, "getctag"): (0, None),
                         (davxml.dav_namespace, "displayname"): (0, None),
                       }
    
class AddressBookGroupAddressBooks (davxml.WebDAVElement):
    """
    The list (hrefs) of address books contained within a group principal
    """
    # Code based on CalendarHomeSet()
    
    name = "current-addressbooks-set"
    namespace = addressbookserver_namespace
    protected = True
    
    allowed_children = { (AddressBookGroupAddressBookInfo.namespace, AddressBookGroupAddressBookInfo.name): (0, None),
                       }
    
    _sharedABFileInfo = None
    _sharedABDict = None
    

def getABSharedFileAsDictionary():

    try:
    # get file path
        sharedABFilePath = "SharedAddressBooks.plist"
        if config._configFile:
            configFilePath = config._configFile
        else:
            configFilePath = defaultConfigFile
        sharedABFilePath = configFilePath[:configFilePath.rfind("/")+1] + sharedABFilePath
    
        sharedABFile = FilePath(sharedABFilePath)
        sharedABFile.restat()
        fileInfo  = (sharedABFile.getmtime(), sharedABFile.getsize())
        if fileInfo != AddressBookGroupAddressBooks._sharedABFileInfo:
            AddressBookGroupAddressBooks._sharedABFileInfo = fileInfo
            AddressBookGroupAddressBooks._sharedABDict = readPlist(sharedABFilePath)
            
            
    except Exception, e:
        log.msg("getABSharedFileAsDictionary(): could not read or decode %s: %r" % (sharedABFilePath, e,))
        AddressBookGroupAddressBooks._sharedABDict = None
    
    return AddressBookGroupAddressBooks._sharedABDict
        

def reloadRecordFromDS(record):
    # Cause the record to be re-read from DS by forcing a cache reload on it
    if record == None:
        return
        
    if gLogLocal:
        log.msg("(Shared Address Book) Reloading record from DS: %s (%s)" % (record.shortNames[0], record.guid));
    guid = record.guid
    service = record.service
    service.reloadCache(record.recordType, lookup=["guid", guid], logIt=False)
    record = service.recordWithUID(guid)               # reacquire record after cache reload
    return record


def reloadGroupMembersFromDS(groupRecord):
    # This routine is mainly for purposes of adding the "-writers" group to an ACL.  If the -writers group contains any nested groups, then
    # make sure that the memberships of those nested groups is up to date
    # Assumes that groupRecord itself is already current
    if groupRecord == None:
        return
    
    if gLogLocal:
        log.msg("(Shared Address Book) Reloading members from DS for record: %s (%s)" % (groupRecord.shortNames[0], groupRecord.guid));
    
    visitedGroups = []
    for m in groupRecord.members():
        if m.recordType == DirectoryService.recordType_groups:      # only care about refreshing group members - I hope
            if m.guid in visitedGroups:
                continue
            visitedGroups.append(m.guid)
            m = reloadRecordFromDS(m)                   # refresh the member group
            reloadGroupMembersFromDS(m)                 # and any of it's children

    if gLogLocal:
        log.msg("(Shared Address Book) Completed reload of members from DS for record: %s (%s)" % (groupRecord.shortNames[0], groupRecord.guid));
    
    
def getSharedAddressBookSpecialGroup(service, wantGroupName):
    # Used to find the "ab_readwrite", "ab_readonly" or "xx-writers" groups in the /Local/ node
 
    # Read these directory from DS because DSLocal recrods are not in principals
 
    # We now intentionally force the read to go to DS to make sure we don't have stale data (esp. between processes)
    if gLogLocal:
        log.msg("(Shared Address Book) Querying DS for provisioning group: %s" % wantGroupName);

    def _uniqueTupleFromAttribute(attribute):
        if attribute:
            if isinstance(attribute, str):
                return (attribute,)
            else:
                s = set()
                return tuple([(s.add(x), x)[1] for x in attribute if x not in s])
        else:
            return ()

    record = None
    attrs = [
        dsattributes.kDS1AttrGeneratedUID,
        dsattributes.kDSNAttrRecordName,
        dsattributes.kDS1AttrDistinguishedName,
        dsattributes.kDSNAttrGroupMembers,
        dsattributes.kDSNAttrNestedGroups,
        dsattributes.kDSNAttrMetaNodeLocation,
    ]

    try:
        localNodeDirectory = opendirectory.odInit("/Local/Default")
        
        if gLogLocal:
            log.msg("(Shared Address Book) opendirectory.queryRecordsWithAttribute_list(%r,%r,%r,%r,%r,%r,%r)" % (
            "/Local/Default",
            dsattributes.kDSNAttrRecordName,
            wantGroupName,
            dsattributes.eDSExact,
            False,
            dsattributes.kDSStdRecordTypeGroups,
            attrs,
        ))
        results = opendirectory.queryRecordsWithAttribute_list(
            localNodeDirectory,
            dsattributes.kDSNAttrRecordName,
            wantGroupName,
            dsattributes.eDSExact,
            False,
            dsattributes.kDSStdRecordTypeGroups,
            attrs,
        )
    
        if gLogLocal:
            log.msg("(Shared Address Book) results= %r" % (results,))

        if len(results) > 0:

            recordShortName, value = results[0] #@UnusedVariable

            memberGUIDs = value.get(dsattributes.kDSNAttrGroupMembers)
            if memberGUIDs is None:
                memberGUIDs = ()
            elif type(memberGUIDs) is str:
                memberGUIDs = (memberGUIDs,)
            nestedGUIDs = value.get(dsattributes.kDSNAttrNestedGroups)
            if nestedGUIDs:
                if type(nestedGUIDs) is str:
                    nestedGUIDs = (nestedGUIDs,)
                memberGUIDs += tuple(nestedGUIDs)

            record = OpenDirectoryRecord(
                service               = service,
                recordType            = DirectoryService.recordType_groups,
                guid                  = value.get(dsattributes.kDS1AttrGeneratedUID),
                nodeName              = value.get(dsattributes.kDSNAttrMetaNodeLocation),
                shortNames            = _uniqueTupleFromAttribute(value.get(dsattributes.kDSNAttrRecordName)),
                authIDs               = (),
                fullName              = value.get(dsattributes.kDS1AttrDistinguishedName),
                firstName             = None,
                lastName              = None,
                emailAddresses        = (),
                calendarUserAddresses = (),
                autoSchedule          = False,
                enabledForCalendaring = False,
                memberGUIDs           = memberGUIDs,
                proxyGUIDs            = (),
                readOnlyProxyGUIDs    = (),
            )
            
    except opendirectory.ODError, e:
        #traceback.print_exc()
        log.err("Open Directory (node=%s) error: %s" % ("/Local/Default", str(e,)))
    except Exception, e:
        #traceback.print_exc()
        log.err("Exception while qerying DS for provisioning group: %s: r" % (wantGroupName, e,))
    
    if gLogLocal:
        log.msg("(Shared Address Book) record= %r" % (record,))
    return record
    
                
    
def getSharedAddressBookGroups(service, masterGroupName):
    record = getSharedAddressBookSpecialGroup(service, masterGroupName)
    if record == None:
        return []  # don't return None since callers expect to be able to iterate the results
    
    return record.members()
    

def getReadWriteSharedAddressBookGroups(service):
    return getSharedAddressBookGroups(service, "com.apple.addressbookserver.sharedABs.readwrite")


def getReadOnlySharedAddressBookGroups(service):
    return getSharedAddressBookGroups(service, "com.apple.addressbookserver.sharedABs.readonly")


def getWritersGroupForSharedAddressBookGroup(groupRecord):
    # Find the "-writers" record object for a given group record
    # Do not just call:
    #       writerRecord = self.record.service.recordWithShortName(DirectoryService.recordType_groups, writerRecName)
    # because that will cause the DS cache to fault looking for the record name if it doesn't exist
    writerRecName = "com.apple.addressbookserver.sharedABs.writers." + groupRecord.shortNames[0]
    
    writersRec = getSharedAddressBookSpecialGroup(groupRecord.service, writerRecName)
    reloadGroupMembersFromDS(writersRec)        # Make sure all group memberships are up to date
    
    return writersRec

    
def groupRecordContainsMember(aGroup, wantMember):
    # Does recursive search of aGroup's members, looking for wantMember
    # Caller is responsible for insuring that "aGroup" is current before calling this routine; we'll make sure to re-read any nested groups
    
    if aGroup == None or wantMember == None:
        return False
        
    visitedGroups = []
    for m in aGroup.members():
        isGroup = m.recordType == DirectoryService.recordType_groups
        if isGroup:
            if m.guid in visitedGroups:
                continue
            visitedGroups.append(m.guid)
        
        if m.guid == wantMember.guid:
            return True
        
        if isGroup:
            # Reread the nested group information to make sure it's membership is current
            m = reloadRecordFromDS(m)
            if groupRecordContainsMember(m, wantMember):
                return True
        
    return False

    
def findPrincipalForRecord(rec, principalCollections):
    for pc in principalCollections:
        recs = pc.getChild(rec.recordType)
        if recs:
            p = recs.principalForRecord(rec)
            if p:
                return p
  
    return None
    
    
def userIsAddressBookGroupWriter(userRecord, groupRecord):
    # Check to see if the user is a member of the "-writers" record (if one exists)
            
    # Now go after the actual -writer record and insure that one exists in the local node
    writerRecord = getWritersGroupForSharedAddressBookGroup(groupRecord)
    if not writerRecord:
        return False
        
    # Check to see if the user is a member of the "-writers" record  
    return groupRecordContainsMember(writerRecord, userRecord)      # RECURSIVE search!
    

def filterGroupsForMember(groupList, wantMember):
    # Check to see which groups in "groupList" wantMember is a member of (recursively)
    # Will only return the top level groups from groupList, not the actual group that the user is a member of
    
    list = []
    for g in groupList:
        # "g" could conceivably be a user record but then g.members() will return [] so it shouldn't be necessary to preflight
        if groupRecordContainsMember(g, wantMember):
            list.append(g)

    return list

@inlineCallbacks
def http___addressbookserver_org_ns__addressbook_findshared(self, request, findshared):
    """
    Generate a findshared REPORT.
    """
        
    # Verify root element
    if findshared.qname() != (addressbookserver_namespace, "addressbook-findshared"):
        raise ValueError("addressbook-findshared expected as root element, not %s." % (findshared.sname(),))

    # Make sure target resource is of the right type
    uriResource = yield request.locateResource(request.uri)
    if uriResource == None:
        log.err("addressbook-findshared unable to convert request URI to resource: %s" % request.uri)
        raise HTTPError(StatusResponse(responsecode.NOT_FOUND, "Unable to convert request URI to resource: %s" % request.uri))
    
    if uriResource.record.recordType != DirectoryService.recordType_users:
        log.err("addressbook-findshared request URI is not a user principal: %s" % request.uri)
        raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "Request URI is not a user principal: %s" % request.uri))

    #
    # Reacquire the user record from DS to make sure it's information is up-to-date
    #
    userRecord = uriResource.record
    userRecord = reloadRecordFromDS(userRecord)
    if userRecord == None:
        raise HTTPError(StatusResponse(responsecode.NOT_FOUND, "Unable to reload user record from DS cache: %s" % request.uri))
    
    uriResource = None      # Invalidate since it contains a reference to a stale "record" instance
    
    #
    # Run the report
    #
    responses = []
    
    
    # 
    # Get the master lists of Address Book-enabled groups  (No group expansion necessary - each group must contain leaf groups that are enabled)
    #
    readOnlyGroups = getReadOnlySharedAddressBookGroups(userRecord.service)        # wrap in tuple() if we're going to use more than once since this returns a generator
    readOnlyGroups = filterGroupsForMember(readOnlyGroups, userRecord)             # keep only those groups that "user" is a member of (checking nested membership)
    
    readWriteGroups = getReadWriteSharedAddressBookGroups(userRecord.service)
    readWriteGroups = filterGroupsForMember(readWriteGroups, userRecord)

    
    #
    # Determine which of the groups have address books enabled and what the user's access is to them
    #
    processedGroups = []
    for memberList in (readWriteGroups, readOnlyGroups):        # Make sure to process R/W group access before R/O access
        isReadWriteGroup = memberList == readWriteGroups
        for g in memberList:
            if g.guid in processedGroups:                            # Just in case we have multiple references to the same group, process only once
                continue
            processedGroups.append(g.guid)
 
            # Reload the group from DS to make sure it's information is up-to-date
            g = reloadRecordFromDS(g)
            if g == None:                   # group disappeared on cache reload
                continue
            
            mode = None
            if isReadWriteGroup:
                mode = "ReadWrite"
            else:
                mode = "ReadOnly"
                if userIsAddressBookGroupWriter(userRecord, g):
                    mode = "ReadWrite"
    
            if mode == None:
                continue
                    
            groupPrincipalURL = None
            groupPrincipal = findPrincipalForRecord(g, self.principalCollections()) 
            if groupPrincipal:
                groupPrincipalURL = groupPrincipal.principalURL()
            
            
            abHome = yield groupPrincipal.readProperty((carddav_namespace, "addressbook-home-set"), request)
            
            groupDisplayName = yield groupPrincipal.readProperty((davxml.dav_namespace, "displayname"), request)
            
            groupUUID = customxml.ResourceID(g.guid)
            
            abMode = AddressBookAccessMode(mode)
    
            abInfos = []
            for home in groupPrincipal.addressBookHomeURLs():
                homeResource = yield request.locateResource(home)
                for child in homeResource.listChildren():
                    props = []
                    childPath = joinURL(homeResource.url(), child)
                    childResource = yield request.locateResource(childPath)
                    if childResource and isAddressBookCollectionResource(childResource):
                        childPath = childPath + "/"                     # Now that we know it's a directory, append the trailing slash
                        props.append(davxml.HRef(childPath))
                        
                        cTag = None
                        try:
                            cTag = yield childResource.readProperty((calendarserver_namespace, "getctag"), request)
                        except:
                            cTag = None
                        
                        if cTag is not None:
                            props.append(cTag)
                        
                        if str(child) == "addressbook":
                            sharedABFileDictionary = getABSharedFileAsDictionary()
                            if sharedABFileDictionary:
                                sharedABDict = sharedABFileDictionary.get("SharedAddressBooks")
                                if sharedABDict:
                                    thisGroupsDict = sharedABDict.get(g.guid)
                                    if thisGroupsDict:
                                        displayNameString = thisGroupsDict.get("AddressBookName")
                                        if displayNameString:                        
                                            displayName = davxml.DisplayName.fromString(displayNameString)
                                            props.append(displayName)

                        
                        thisInfo = AddressBookGroupAddressBookInfo(*props)
                        abInfos.append(thisInfo)
                            
            groupAddressBooksProp = AddressBookGroupAddressBooks(*abInfos)
            #groupAddressBooksProp = AddressBookGroupAddressBooks(*[davxml.HRef(url) for url in groupAddressBooks])                            
            
            xml_status      = davxml.Status.fromResponseCode(responsecode.OK)
            xml_container   = davxml.PropertyContainer(groupDisplayName, groupUUID, abHome, abMode, groupAddressBooksProp)
            xml_propstat    = davxml.PropertyStatus(xml_container, xml_status)
            
            propstats = []
            propstats.append(xml_propstat)
    
            xml_resource = davxml.HRef.fromString(groupPrincipalURL)
            xml_response = davxml.PropertyStatusResponse(xml_resource, *propstats)
        
            responses.append(xml_response)

    returnValue(MultiStatusResponse(responses))

