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

from zope.interface import implements

from twisted.internet.defer import succeed
from twisted.cred.error import UnauthorizedLogin
from twisted.cred.checkers import ICredentialsChecker
from twisted.web2.dav.auth import IPrincipalCredentials
from twisted.web2.dav.auth import TwistedPropertyChecker

from twistedcaldav import customxml

class DirectoryCredentialsChecker (object):
    implements(ICredentialsChecker)

    credentialInterfaces = (IPrincipalCredentials,)

    def __init__(self, service):
        """
        @param service: an L{IDirectoryService} provider.
        """
        self.service = service

    def requestAvatarId(self, credentials):
        credentials = IPrincipalCredentials(credentials)

        # FIXME: ?
        # We were checking if principal is enabled; seems unnecessary in current
        # implementation because you shouldn't have a principal object for a
        # disabled directory principal.

        user = self.service.recordWithShortName("user", credentials.credentials.username)
        if user is None:
            raise UnauthorizedLogin("No such user: %s" % (user,))

        if user.verifyCredentials(credentials.credentials):
            return succeed((credentials.authnPrincipal.principalURL(), credentials.authzPrincipal.principalURL()))
        else:
            raise UnauthorizedLogin("Incorrect credentials for %s" % (user,)) 
