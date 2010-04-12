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
from twisted.internet.defer import succeed, inlineCallbacks, maybeDeferred, returnValue
from twisted.python.reflect import namedClass
from twext.web2 import responsecode
from twext.web2.dav import davxml
from twext.web2.dav.resource import TwistedACLInheritable
from twext.web2.http import HTTPError, StatusResponse

from twistedcaldav.config import config
from twistedcaldav.resource import CalDAVResource




log = Logger()



class DirectoryBackedAddressBookResource (CalDAVResource):
    """
    Directory-backed address book
    """

    def __init__(self):

        CalDAVResource.__init__(self)

        self.directory = None       # creates directory attribute

        
    def provisionDirectory(self):
        if self.directory is None:
            directoryClass = namedClass(config.DirectoryAddressBook.type)
        
            log.info("Configuring: %s:%r"
                 % (config.DirectoryAddressBook.type, config.DirectoryAddressBook.params))
        
            #add self as "directoryBackedAddressBook" parameter
            params = config.DirectoryAddressBook.params.copy()
            params["directoryBackedAddressBook"] = self

            self.directory = directoryClass(params)
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

    def resourceType(self, request):
        return succeed(davxml.ResourceType.addressbook)

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

