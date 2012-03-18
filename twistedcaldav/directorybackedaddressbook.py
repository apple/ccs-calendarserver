##
# Copyright (c) 2008-2009 Apple Inc. All rights reserved.
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
from twext.web2 import responsecode
from txdav.xml import element as davxml
from twext.web2.dav.resource import TwistedACLInheritable
from twext.web2.http import HTTPError, StatusResponse

from twisted.internet.defer import succeed, inlineCallbacks, maybeDeferred, returnValue
from twisted.python.reflect import namedClass

from twistedcaldav.config import config
from twistedcaldav.resource import CalDAVResource

import uuid

log = Logger()



class DirectoryBackedAddressBookResource (CalDAVResource):
    """
    Directory-backed address book
    """

    def __init__(self, principalCollections):

        CalDAVResource.__init__(self, principalCollections=principalCollections)

        self.directory = None       # creates directory attribute

        # create with permissions, similar to CardDAVOptions in tap.py
        # FIXME:  /Directory does not need to be in file system unless debug-only caching options are used
#        try:
#            os.mkdir(path)
#            os.chmod(path, 0750)
#            if config.UserName and config.GroupName:
#                import pwd
#                import grp
#                uid = pwd.getpwnam(config.UserName)[2]
#                gid = grp.getgrnam(config.GroupName)[2]
#                os.chown(path, uid, gid)
# 
#            log.msg("Created %s" % (path,))
#            
#        except (OSError,), e:
#            # this is caused by multiprocessor race and is harmless
#            if e.errno != errno.EEXIST:
#                raise

        
    def makeChild(self, name):
        from twistedcaldav.simpleresource import SimpleCalDAVResource
        return SimpleCalDAVResource(principalCollections=self.principalCollections())

    def provisionDirectory(self):
        if self.directory is None:
            directoryClass = namedClass(config.DirectoryAddressBook.type)
        
            log.info("Configuring: %s:%r"
                 % (config.DirectoryAddressBook.type, config.DirectoryAddressBook.params))
        
            #add self as "directoryBackedAddressBook" parameter
            params = config.DirectoryAddressBook.params.copy()
            params["directoryBackedAddressBook"] = self

            try:
                self.directory = directoryClass(params)
            except ImportError, e:
                log.error("Unable to set up directory address book: %s" % (e,))
                return succeed(None)

            return self.directory.createCache()
            
            #print ("DirectoryBackedAddressBookResource.provisionDirectory: provisioned")
        
        return succeed(None)


    def defaultAccessControlList(self):
        #print( "DirectoryBackedAddressBookResource.defaultAccessControlList" )
        if config.AnonymousDirectoryAddressBookAccess:
            # DAV:Read for all principals (includes anonymous)
            accessPrincipal = davxml.All()
        else:
            # DAV:Read for all authenticated principals (does not include anonymous)
            accessPrincipal = davxml.Authenticated()

        return davxml.ACL(
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
        #print( "DirectoryBackedAddressBookResource.isAddressBookCollection: return True" )
        return True

    def isCollection(self):
        return True

    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        # Permissions here are fixed, and are not subject to inheritance rules, etc.
        return succeed(self.defaultAccessControlList())
    
    @inlineCallbacks
    def renderHTTP(self, request):
        if not self.directory:
            raise HTTPError(StatusResponse(responsecode.SERVICE_UNAVAILABLE,"Service is starting up" ))
        elif self.directory.liveQuery:
            response = (yield maybeDeferred(super(DirectoryBackedAddressBookResource, self).renderHTTP, request))
            returnValue(response)
        else:
            available = (yield maybeDeferred(self.directory.available, ))
        
            if not available:
                raise HTTPError(StatusResponse(responsecode.SERVICE_UNAVAILABLE,"Service is starting up" ))
            else:
                updateLock = self.directory.updateLock()
                yield updateLock.acquire()
                try:
                    response = (yield maybeDeferred(super(DirectoryBackedAddressBookResource, self).renderHTTP, request))
    
                finally:
                    yield updateLock.release()
                
                returnValue(response)

