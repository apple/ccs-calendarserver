##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
Implements a directory-backed principal hierarchy.
"""

__all__ = [
    "DirectoryCredentialsChecker",
]

from twisted.internet.defer import succeed
from twisted.cred.credentials import UsernamePassword
from twisted.cred.error import UnauthorizedLogin
from twisted.web2.dav.auth import IPrincipalCredentials
from twisted.web2.dav.auth import TwistedPropertyChecker

import opendirectory

from twistedcaldav import customxml

class DirectoryCredentialsChecker (TwistedPropertyChecker):

    def requestAvatarId(self, credentials):

        # If there is no calendar principal URI then the calendar user is disabled.
        pcreds = IPrincipalCredentials(credentials)
        if not pcreds.authnPrincipal.hasDeadProperty(customxml.TwistedCalendarPrincipalURI):
            # Try regular password check
            return TwistedPropertyChecker.requestAvatarId(self, credentials)

        creds = pcreds.credentials
        if isinstance(creds, UsernamePassword):
            user = creds.username
            pswd = creds.password
            if opendirectory.authenticateUser(pcreds.authnPrincipal.directory(), user, pswd):
                return succeed((pcreds.authnURI, pcreds.authzURI,))
        
        raise UnauthorizedLogin("Bad credentials for: %s" % (pcreds.authnURI,))

#class DirectoryCredentialsChecker (TwistedPropertyChecker):
#    def __init__(self, service):
#        """
#        @param service: an L{IDirectoryService} provider.
#        """
#        self.service = service
#
#    def requestAvatarId(self, credentials):
#        # If there is no calendar principal URI then the calendar user is disabled.
#        credentials = IPrincipalCredentials(credentials)
#        if not credentials.authnPrincipal.hasDeadProperty(customxml.TwistedCalendarPrincipalURI):
#            # Try regular password check
#            return TwistedPropertyChecker.requestAvatarId(self, credentials)
#
#        user = self.service.userWithShortName(credentials.credentials.username)
#        raise UnauthorizedLogin("Unknown credentials type for principal: %s" % (credentials.authnURI,))
#
#        if not user:
#            raise UnauthorizedLogin("No such user: %s" % (user,))
#
#        if user.authenticate(credentials.credentials):
#            return succeed((credentials.authnURI, credentials.authzURI))
#        else:
#            raise UnauthorizedLogin("Incorrect credentials for user: %s" % (user,)) 
