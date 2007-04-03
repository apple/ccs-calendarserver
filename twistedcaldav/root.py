##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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
# DRI: David Reid, dreid@apple.com
##

from twisted.python import log

from twisted.internet import defer
from twisted.python.failure import Failure
from twisted.cred.error import LoginFailed
from twisted.cred.error import UnauthorizedLogin

from twisted.web2.http import HTTPError
from twisted.web2.auth.wrapper import UnauthorizedResponse

from twisted.web2.dav import davxml

from twistedcaldav.extensions import DAVFile
from twistedcaldav.config import config

class RootResource(DAVFile):
    """
    A special root resource that contains support checking SACLs
    """

    useSacls = False
    saclService = 'calendar'

    def __init__(self, path, *args, **kwargs):
        super(RootResource, self).__init__(path, *args, **kwargs)

        if config.EnableSACLs:
            if RootResource.CheckSACL:
                self.useSacls = True
            else:
                log.msg(("RootResource.CheckSACL is unset but "
                         "config.EnableSACLs is True, SACLs will not be"
                         "turned on."))

    def checkSacl(self, request):
        """
        Check SACLs against the current request
        """

        def _authCb((authnUser, authzUser)):
            # Ensure that the user is not unauthenticated.
            # SACLs are authorization for the use of the service,
            # so unauthenticated access doesn't make any sense.
            if authzUser == davxml.Principal(davxml.Unauthenticated()):
                log.msg("Unauthenticated users not enabled with the '%s' SACL" % (self.saclService,))
                return Failure(HTTPError(UnauthorizedResponse(
                            request.credentialFactories,
                            request.remoteAddr)))

            return (authnUser, authzUser)

        def _authEb(failure):
            # Make sure we propogate UnauthorizedLogin errors.
            failure.trap(UnauthorizedLogin, LoginFailed)

            return Failure(HTTPError(UnauthorizedResponse(
                        request.credentialFactories,
                        request.remoteAddr)))

        def _checkSACLCb((authnUser, authzUser)):
            # Figure out the "username" from the davxml.Principal object
            username = authzUser.children[0].children[0].data
            username = username.rstrip('/').split('/')[-1]
            
            if RootResource.CheckSACL(username, self.saclService) != 0:
                log.msg("User '%s' is not enabled with the '%s' SACL" % (username, self.saclService,))
                return Failure(HTTPError(403))

            return True
            
        d = defer.maybeDeferred(self.authenticate, request)
        d.addCallbacks(_authCb, _authEb)
        d.addCallback(_checkSACLCb)
        return d

    def locateChild(self, request, segments):
        if self.useSacls:
            d = self.checkSacl(request)
            d.addCallback(lambda _: super(RootResource, self
                                          ).locateChild(request, segments))

            return d

        return super(RootResource, self).locateChild(request, segments)


# So CheckSACL will be parameterized
# We do this after RootResource is defined
try:
    from appleauth import CheckSACL
    RootResource.CheckSACL = CheckSACL
except ImportError:
    RootResource.CheckSACL = None
