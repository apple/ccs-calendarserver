##
# Copyright (c) 2005-2012 Apple Computer, Inc. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
##

__all__ = [
    "IPrincipal",
    "DavRealm",
    "IPrincipalCredentials",
    "PrincipalCredentials",
    "AuthenticationWrapper",
]

from zope.interface import implements, Interface
from twisted.internet import defer
from twisted.cred import checkers, error, portal
from twext.web2.resource import WrapperResource
from txdav.xml.element import twisted_private_namespace, registerElement
from txdav.xml.element import WebDAVTextElement, Principal, HRef


class AuthenticationWrapper(WrapperResource):
    def __init__(self, resource, portal, credentialFactories, loginInterfaces,
        allowBasicOverNonSSL=False):
        """
        Wrap the given resource and use the parameters to set up the request
        to allow anyone to challenge and handle authentication.

        @param resource: L{DAVResource} FIXME: This should get promoted to
            twext.web2.auth
        @param portal: The cred portal
        @param credentialFactories: Sequence of credentialFactories that can
            be used to authenticate by resources in this tree.
        @param loginInterfaces: More cred stuff
        @param allowBasicOverNonSSL: Should we advertise Basic over non SSL
            connections?
        @type allowBasicOverNonSSL: C{bool}
        """
        super(AuthenticationWrapper, self).__init__(resource)

        self.portal = portal
        self.credentialFactories = dict([(factory.scheme, factory)
                                         for factory in credentialFactories])
        self.secureCredentialFactories = dict([(factory.scheme, factory)
                                         for factory in credentialFactories
                                         if factory.scheme != "basic"])
        self.loginInterfaces = loginInterfaces
        self.allowBasicOverNonSSL = allowBasicOverNonSSL

    def hook(self, req):
        req.portal = self.portal
        req.loginInterfaces = self.loginInterfaces

        # If not using SSL, use the factory list which excludes "Basic"
        if req.chanRequest is None: # This is only None in unit tests
            secureConnection = True
        else:
            ignored, secureConnection = req.chanRequest.getHostInfo()
        req.credentialFactories = (self.credentialFactories if secureConnection or
            self.allowBasicOverNonSSL else self.secureCredentialFactories)


class IPrincipal(Interface):
    pass

class DavRealm(object):
    implements(portal.IRealm)

    def requestAvatar(self, avatarId, mind, *interfaces):
        if IPrincipal in interfaces:
            return IPrincipal, Principal(HRef(avatarId[0])), Principal(HRef(avatarId[1]))
        
        raise NotImplementedError("Only IPrincipal interface is supported")


class IPrincipalCredentials(Interface):
    pass


class PrincipalCredentials(object):
    implements(IPrincipalCredentials)

    def __init__(self, authnPrincipal, authzPrincipal, credentials):
        """
        Initialize with both authentication and authorization values. Note that in most cases theses will be the same
        since HTTP auth makes no distinction between the two - but we may be layering some addition auth on top of this
        (.e.g.. proxy auth, cookies, forms etc) that make result in authentication and authorization being different.

        @param authnPrincipal: L{IDAVPrincipalResource} for the authenticated principal.
        @param authnURI: C{str} containing the URI of the authenticated principal.
        @param authzPrincipal: L{IDAVPrincipalResource} for the authorized principal.
        @param authzURI: C{str} containing the URI of the authorized principal.
        @param credentials: L{ICredentials} for the authentication credentials.
        """
        self.authnPrincipal = authnPrincipal
        self.authzPrincipal = authzPrincipal
        self.credentials = credentials

    def checkPassword(self, password):
        return self.credentials.checkPassword(password)


class TwistedPropertyChecker(object):
    implements(checkers.ICredentialsChecker)

    credentialInterfaces = (IPrincipalCredentials,)

    def _cbPasswordMatch(self, matched, principalURIs):
        if matched:
            # We return both URIs
            return principalURIs
        else:
            raise error.UnauthorizedLogin("Bad credentials for: %s" % (principalURIs[0],))

    def requestAvatarId(self, credentials):
        pcreds = IPrincipalCredentials(credentials)
        pswd = str(pcreds.authnPrincipal.readDeadProperty(TwistedPasswordProperty))

        d = defer.maybeDeferred(credentials.checkPassword, pswd)
        d.addCallback(self._cbPasswordMatch, (
            pcreds.authnPrincipal.principalURL(),
            pcreds.authzPrincipal.principalURL(),
            pcreds.authnPrincipal,
            pcreds.authzPrincipal,
        ))
        return d

##
# Utilities
##

class TwistedPasswordProperty (WebDAVTextElement):
    namespace = twisted_private_namespace
    name = "password"

registerElement(TwistedPasswordProperty)
